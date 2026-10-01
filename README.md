# Energy Data Management and Analysis Using a Relational Database

Storing, querying, indexing, and forecasting high-frequency renewable energy data with **MySQL 8.0** and **Python**.

This project loads three years of 5-minute electricity demand, solar, wind, and weather data from California into a normalized relational database. It then analyzes the data with SQL, measures how different indexing strategies affect query performance, and uses features engineered in SQL to forecast electricity demand one hour ahead.

---

## Research Question

> How can a relational database be used to efficiently store, query, and analyze high-frequency renewable energy data?

---

## Dataset

**Renewable Energy and Electricity Demand Time Series Dataset with Exogenous Variables at 5-minute Interval**
Rojas Ortega, S., Castro-Correa, P., Sepúlveda-Mora, S., & Castro-Correa, J. (2023). Mendeley Data, Version 1.

- **DOI / download:** https://doi.org/10.17632/fdfftr3tc2.1
- **Also listed on:** [ORNL Open Energy Data Portal](https://openenergyhub.ornl.gov/explore/dataset/renewable-energy-and-electricity-demand-time-series-dataset-with-exogenous-varia/)
- **License:** CC BY 4.0
- **Original sources:** CAISO (electricity data) and NREL (weather data)
- **Size:** 315,648 rows, 1 Jan 2019 – 31 Dec 2021, 5-minute intervals, no gaps or missing values

| Column | Description | Unit / coding |
|---|---|---|
| `Time` | Timestamp | `YYYY-MM-DD-Thh:mm` |
| `Season` | Season | 1 Winter, 2 Spring, 3 Summer, 4 Autumn |
| `Day_of_the_week` | Day of week | 0 Monday … 6 Sunday |
| `DHI`, `DNI`, `GHI` | Solar irradiance (diffuse, direct, global) | W/m² |
| `Wind_speed` | Wind speed | m/s |
| `Humidity` | Relative humidity | % |
| `Temperature` | Air temperature | °C |
| `PV_production` | Solar production | MW |
| `Wind_production` | Wind production | MW |
| `Electric_demand` | Electricity demand | MW |

> The dataset is not included in this repository. Download `Database.csv` from the DOI link above and place it in `data/`.

---

## Repository Structure

```
energy-db/
├── data/
│   └── Database.csv              # download separately (see Dataset)
├── sql/
│   ├── 01_schema.sql             # creates tables + lookup data
│   ├── 02_verify_load.sql        # post-load checks
│   ├── 03_analysis_queries.sql   # 12 analysis queries
│   └── 04_readonly_user.sql      # optional SELECT-only user for the Q&A tool
├── python/
│   ├── load_data.py              # CSV → MySQL loader
│   ├── index_benchmark.py        # indexing experiment
│   ├── nl2sql.py                 # plain-English question → SQL → answer
│   └── ask_web.py                # one-page website for nl2sql
├── notebooks/
│   └── 02_forecasting.ipynb      # SQL feature engineering + ML models
├── results/                      # query output, benchmark results, charts
├── report/                       # project report (.docx)
├── .env.example                  # settings template for the Q&A tool
├── .gitignore
└── README.md
```

---

## Database Design

One fact table plus two small lookup tables:

| Table | Rows | Primary key | Role |
|---|---|---|---|
| `energy_reading` | 315,648 | `reading_time` | One row per 5-minute reading |
| `season` | 4 | `season_id` | Season code → name and months |
| `day_of_week` | 7 | `day_id` | Day code → name and weekend flag |

Key design choices:
- **The timestamp is the primary key.** In InnoDB this is a *clustered* index, so rows are physically stored in time order, which speeds up time-range queries.
- **Compact data types:** `TINYINT` codes, `FLOAT` weather values, and `INT` megawatts.
- **Foreign keys** to the lookup tables prevent invalid codes.

---

## Requirements

- MySQL Server 8.0 or later (8.0.18+ for `EXPLAIN ANALYZE`)
- Python 3.9 or later (Anaconda recommended)
- Python packages:

```bash
pip install pandas sqlalchemy pymysql cryptography scikit-learn matplotlib jupyter python-dotenv torch transformers accelerate
```

On Windows, add MySQL's `bin` folder (e.g. `C:\Program Files\MySQL\MySQL Server 8.0\bin`) to your PATH so the `mysql` command works in the terminal.

---

## How to Run

Run all commands from the project root folder.

**1. Create the database and tables**
```bash
mysql -u root -p -e "CREATE DATABASE energydb;"
mysql -u root -p energydb -e "source sql/01_schema.sql"
```

**2. Load the data**
```bash
python python/load_data.py
```
The script asks for your MySQL password, cleans the timestamps, and loads all 315,648 rows.

**3. Verify the load**
```bash
mysql -u root -p energydb -e "source sql/02_verify_load.sql"
```

**4. Run the SQL analysis**
```bash
mysql -u root -p energydb --table -e "source sql/03_analysis_queries.sql" > results/analysis_output.txt
```
On Windows PowerShell, use this instead so the file is saved as UTF-8:
```powershell
mysql -u root -p energydb --table -e "source sql/03_analysis_queries.sql" | Out-File -Encoding utf8 results/analysis_output.txt
```

**5. Run the indexing experiment** (about 1–2 minutes)
```bash
python python/index_benchmark.py
```
To test larger data volumes, set `COPIES = [1, 4, 16]` in the script (about 0.3M, 1.3M, and 5M rows).

**6. Run the forecasting notebook**

Open `notebooks/02_forecasting.ipynb` in VS Code or Jupyter and run all cells.

**7. Ask your own questions in plain English**

`python/nl2sql.py` uses an open-source language model, [Qwen2.5-Coder-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct), running locally with Hugging Face `transformers`. The model gets a description of the tables plus a few example question → SQL pairs, and writes a MySQL `SELECT` query for your question. The query runs against `energydb`, and a short answer is built from the returned rows (the model writes only the SQL, so every number shown comes straight from MySQL). If MySQL rejects the query, the error goes back to the model to fix (up to 3 tries). No cloud API is used; the model (~6 GB) downloads from Hugging Face on first run and uses a GPU (NVIDIA or Intel) if there is one.

**Models**

| Model | Role | Parameters | Download | License |
|---|---|---:|---:|---|
| [Qwen2.5-Coder-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) | Default: turns questions into SQL | 3.1 B | ~6.2 GB | [Qwen Research License](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/blob/main/LICENSE) (non-commercial / research use) |
| [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) | Lightweight option for quick tests | 0.5 B | ~1 GB | Apache 2.0 |

Both run in bfloat16 with greedy decoding (the same question always gives the same SQL). To switch models, set `NL2SQL_MODEL` in `.env`, e.g. `NL2SQL_MODEL=Qwen/Qwen2.5-0.5B-Instruct`. The 0.5B model is faster but more often invents column names; the 3B model is recommended.

Setup: `pip install torch transformers accelerate`, then copy `.env.example` to `.env` and fill in your MySQL password.

```bash
# one question
python python/nl2sql.py "Which month in 2021 had the highest renewable share?"

# keep asking (follow-ups like "now split that by season" work)
python python/nl2sql.py

# simple web page at http://localhost:8000
python python/ask_web.py
```

Each answer shows the SQL that produced it, so you can check it. A 3B-parameter model can misread a question, so compare the SQL with what you asked.

Safety: only a single `SELECT`/`WITH` statement is accepted, it runs inside a `READ ONLY` transaction with a 20-second time limit, and results are capped at 5,000 rows. For an extra layer, create the SELECT-only user in `sql/04_readonly_user.sql` and put it in `.env`.

### Password handling

No passwords are stored in the code. The scripts read the `MYSQL_PWD` environment variable if it is set, and otherwise prompt for the password. Never commit a password to the repository. If you use a `.env` file, it is excluded by `.gitignore`.

---

## Results

### SQL analysis highlights

- **Evening peak:** average demand is lowest around 03:00 (~20,800 MW) and highest at 18:00 (~29,800 MW).
- **Rising renewables:** renewable share grew from **20.8%** (2019) to **21.5%** (2020) to **25.0%** (2021) while total demand stayed flat.
- **Temperature drives demand:** readings at 30 °C or above average **31,717 MW**, compared with **22,961 MW** at 10–20 °C. All top-10 peak days fell in August–September heat waves, and the record of **47,067 MW** came on 18 Aug 2020.
- **Duck curve:** net load (demand − solar − wind) falls to ~12,900 MW at 11:00, then climbs to ~26,900 MW by 19:00.
- **Data quality:** a `LAG()` query found 5-minute demand jumps of up to 4,855 MW, which may be recording anomalies.

### Indexing experiment

Median query time in milliseconds (315,648 rows, 7 runs, first run discarded as warm-up):

| Query | A: no index | B: secondary on time | C: clustered PK | D: PK + temp | E: PK + season |
|---|---:|---:|---:|---:|---:|
| T1 point lookup | 261.27 | 0.19 | 0.73 | 0.44 | 0.28 |
| T2 one day | 200.76 | 0.37 | 0.95 | 0.35 | 0.59 |
| T3 one month | 212.72 | 14.44 | 3.68 | 2.29 | 2.85 |
| T4 one year | 220.17 | 256.00 | 46.88 | 46.03 | 43.74 |
| T5 temp ≥ 38 °C | 188.16 | 198.94 | 77.98 | **1.20** | 73.57 |
| T6 one season | 233.39 | 241.82 | 83.51 | 86.72 | 108.59 |

Key findings:
1. **Time indexes cut small lookups from ~200–260 ms to under 1 ms.**
2. **The clustered primary key is about 4× faster than a secondary index for month-long ranges**, because matching rows are stored contiguously.
3. **For a full year, MySQL ignored the secondary index** and scanned the whole table. The clustered key still used a range scan.
4. **The selective temperature index gave a ~65× speedup** (63 matching rows).
5. **The low-selectivity season index made its query slower** (84 → 109 ms).
6. **Indexes cost space and write time:** the temperature index added 9.5 MB and made loading ~24% slower.

Full execution plans are in `results/explain_plans.txt`.

### Forecasting (1 hour ahead, test year 2021)

Features were built inside MySQL with `LAG()` window functions (demand 1 hour, 24 hours, and 7 days earlier), plus calendar and weather variables. The models were trained on 2019–2020 and tested on 2021.

| Model | MAE (MW) | RMSE (MW) | MAPE |
|---|---:|---:|---:|
| Baseline (demand 1 h earlier) | 934 | 1,127 | 3.71% |
| Linear Regression | 697 | 875 | 2.83% |
| **Random Forest** | **255** | **350** | **1.05%** |

### Question answering (text-to-SQL)

Qwen2.5-Coder-3B-Instruct, run locally on an Intel Arc 140V GPU. Model load takes about 40 s; each question then takes 6–15 s. On 12 test questions, 10 produced correct SQL and one unanswerable question was correctly refused:

| Question | Result |
|---|---|
| Peak electricity demand each year | ✅ 47,067 MW in 2020 |
| Monthly renewable share in 2021 | ✅ 17.0% (Jan) to 36.7% (May) |
| Top 5 days for solar production (GWh) | ✅ 140 GWh on 27 May 2021 |
| Weekday vs weekend demand in summer | ✅ Weekdays higher (per-day breakdown) |
| Average demand and net load by hour | ✅ Demand peaks at 18:00 (29,776 MW) |
| Demand by 5 °C temperature band | ✅ Rises from ~22,500 MW to ~35,600 MW |
| Season with highest average wind | ✅ Q2 (Spring), 2,793 MW |
| Hottest temperature and when | ✅ 39.02 °C on 6 Sep 2020 (fixed after one MySQL error) |
| Demand at 3 am vs 6 pm | ✅ About 9,000 MW lower at 3 am |
| Electricity price in 2020 | ✅ Refused: not in the dataset |
| Average solar at 1 pm in July 2021 | ❌ Averaged the wrong 24-hour window |
| Month with lowest wind production in 2020 | ⚠️ Used the single lowest reading, not the monthly total |

The model only writes SQL. The answer text is built from the rows MySQL returns, because in early tests the model's own sentences misquoted numbers that were correct in the table.

---

## Limitations

- Timings come from a single local machine with a warm cache, so absolute numbers will vary.
- Weather at the forecast time is treated as known, which assumes an accurate weather forecast.
- The dataset is moderate in size; larger volumes may change the relative performance of indexes.
- The text-to-SQL model is small (3B parameters) and can misread questions, especially times of day and ambiguous wording ("lowest" reading vs lowest total). Its accuracy was checked on 12 questions only, so the SQL shown with each answer should be reviewed.

---

## References

- Hadjichristofi, C., Diochnos, S., Andresakis, K., & Vescoukis, V. (2024). Using time-series databases for energy data infrastructures. *Energies, 17*(21), 5478. https://doi.org/10.3390/en17215478
- Hui, B., Yang, J., Cui, Z., et al. (2024). Qwen2.5-Coder technical report. *arXiv:2409.12186*. https://arxiv.org/abs/2409.12186
- Rojas Ortega, S., Castro-Correa, P., Sepúlveda-Mora, S., & Castro-Correa, J. (2023). Renewable energy and electricity demand time series dataset with exogenous variables at 5-minute interval. Mendeley Data. https://doi.org/10.17632/fdfftr3tc2.1
- Román-Portabales, A., López-Nores, M., & Pazos-Arias, J. J. (2021). Systematic review of electricity demand forecast using ANN-based machine learning algorithms. *Sensors, 21*(13), 4544. https://doi.org/10.3390/s21134544
- Ugbehe, P. O., Diemuodeke, O. E., & Aikhuele, D. O. (2025). Electricity demand forecasting methodologies and applications: A review. *Sustainable Energy Research, 12*, 19. https://doi.org/10.1186/s40807-025-00149-z
