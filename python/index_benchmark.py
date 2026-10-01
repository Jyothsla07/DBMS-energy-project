"""
index_benchmark.py  -  Step 6: indexing experiment (MySQL 8)

For each index configuration, this script:
  1. builds a test table `bench` from energy_reading with that configuration
  2. records the load (insert) time and the table/index size on disk
  3. runs each test query several times and records the median time
  4. saves the EXPLAIN ANALYZE plan of each query

Results are written to results/:
  index_benchmark.csv, index_sizes.csv, explain_plans.txt, index_benchmark.png

Run from the project root:  python python/index_benchmark.py
pip install pymysql cryptography pandas matplotlib
"""
import os
import time
import statistics
from getpass import getpass

import pandas as pd
import pymysql
import matplotlib.pyplot as plt

# ---------------------------------------------------------------- settings
HOST, PORT, USER, DB = "localhost", 3306, "root", "energydb"
REPEATS = 7          # runs per query; the first run is a warm-up and is dropped
COPIES = [1]         # data scale: 1 = original 315,648 rows.
                     # For the scaling test use e.g. [1, 4, 16]  (~1.3M and ~5M rows)
RESULTS_DIR = "results"

# ------------------------------------------------------ index configurations
BASE_COLUMNS = """
    reading_time     DATETIME NOT NULL,
    season_id        TINYINT  NOT NULL,
    day_id           TINYINT  NOT NULL,
    dhi FLOAT, dni FLOAT, ghi FLOAT,
    wind_speed FLOAT, humidity FLOAT, temperature FLOAT,
    pv_production INT, wind_production INT, electric_demand INT
"""

CONFIGS = {
    "A_no_index":        "",
    "B_secondary_time":  ", INDEX idx_time (reading_time)",
    "C_clustered_pk":    ", PRIMARY KEY (reading_time)",
    "D_pk_plus_temp":    ", PRIMARY KEY (reading_time), INDEX idx_temp (temperature)",
    "E_pk_plus_season":  ", PRIMARY KEY (reading_time), INDEX idx_season (season_id)",
}

# ------------------------------------------------------------- test queries
QUERIES = {
    "T1_point_lookup":
        "SELECT * FROM bench WHERE reading_time = '2020-08-18 17:00:00'",
    "T2_one_day":
        "SELECT AVG(electric_demand) FROM bench "
        "WHERE reading_time >= '2020-08-18' AND reading_time < '2020-08-19'",
    "T3_one_month":
        "SELECT AVG(electric_demand), AVG(pv_production) FROM bench "
        "WHERE reading_time >= '2020-08-01' AND reading_time < '2020-09-01'",
    "T4_one_year":
        "SELECT AVG(electric_demand) FROM bench "
        "WHERE reading_time >= '2020-01-01' AND reading_time < '2021-01-01'",
    "T5_hot_readings":
        "SELECT COUNT(*), AVG(electric_demand) FROM bench WHERE temperature >= 38",
    "T6_one_season":
        "SELECT AVG(electric_demand) FROM bench WHERE season_id = 3",
}


def connect(password):
    return pymysql.connect(host=HOST, port=PORT, user=USER, password=password,
                           database=DB, autocommit=True)


def build_table(cur, index_sql, copies):
    """Create `bench` with the given indexes and fill it. Returns load time (s)."""
    cur.execute("DROP TABLE IF EXISTS bench")
    cur.execute(f"CREATE TABLE bench ({BASE_COLUMNS}{index_sql}) ENGINE=InnoDB")
    start = time.perf_counter()
    for k in range(copies):
        # each extra copy is shifted 3 years later, so timestamps stay unique
        cur.execute(f"""
            INSERT INTO bench
            SELECT DATE_ADD(reading_time, INTERVAL {3 * k} YEAR), season_id, day_id,
                   dhi, dni, ghi, wind_speed, humidity, temperature,
                   pv_production, wind_production, electric_demand
            FROM energy_reading""")
    load_seconds = time.perf_counter() - start
    cur.execute("ANALYZE TABLE bench")
    cur.fetchall()
    return load_seconds


def table_size(cur):
    cur.execute("SET SESSION information_schema_stats_expiry = 0")
    cur.execute("""SELECT TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH
                   FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bench'""")
    rows, data_len, index_len = cur.fetchone()
    return rows, data_len / 1024**2, index_len / 1024**2


def time_query(cur, sql):
    times = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times[1:])      # drop warm-up run


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    password = os.environ.get("MYSQL_PWD") or getpass("MySQL root password: ")
    conn = connect(password)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM energy_reading")
    base_rows = cur.fetchone()[0]

    timings, sizes = [], []
    with open(os.path.join(RESULTS_DIR, "explain_plans.txt"), "w") as plans:
        for copies in COPIES:
            for config, index_sql in CONFIGS.items():
                print(f"\n== {config}  ({base_rows * copies:,} rows) ==")
                load_s = build_table(cur, index_sql, copies)
                rows, data_mb, index_mb = table_size(cur)
                sizes.append(dict(rows=base_rows * copies, config=config,
                                  load_seconds=round(load_s, 2),
                                  data_mb=round(data_mb, 1),
                                  secondary_index_mb=round(index_mb, 1)))
                print(f"   load {load_s:.1f}s | data {data_mb:.1f} MB "
                      f"| secondary indexes {index_mb:.1f} MB")

                for qname, sql in QUERIES.items():
                    ms = time_query(cur, sql)
                    timings.append(dict(rows=base_rows * copies, config=config,
                                        query=qname, median_ms=round(ms, 2)))
                    print(f"   {qname:<18} {ms:9.2f} ms")

                    cur.execute("EXPLAIN ANALYZE " + sql)
                    plan = cur.fetchone()[0]
                    plans.write(f"### rows={base_rows * copies} | {config} | {qname}\n"
                                f"{sql}\n{plan}\n\n")

    cur.execute("DROP TABLE IF EXISTS bench")
    conn.close()

    # ---------------------------------------------------------- save results
    tdf = pd.DataFrame(timings)
    sdf = pd.DataFrame(sizes)
    tdf.to_csv(os.path.join(RESULTS_DIR, "index_benchmark.csv"), index=False)
    sdf.to_csv(os.path.join(RESULTS_DIR, "index_sizes.csv"), index=False)

    # summary table: queries x configs (smallest data scale)
    first = tdf[tdf["rows"] == tdf["rows"].min()]
    pivot = first.pivot(index="query", columns="config", values="median_ms")
    print("\nMedian query time (ms):\n", pivot.to_string())

    ax = pivot.plot(kind="bar", figsize=(11, 5), logy=True, width=0.8)
    ax.set_ylabel("Median time (ms, log scale)")
    ax.set_xlabel("")
    ax.set_title(f"Query time by index configuration ({first['rows'].iloc[0]:,} rows)")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "index_benchmark.png"), dpi=150)
    print(f"\nSaved results to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
