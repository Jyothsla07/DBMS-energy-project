"""
nl2sql.py
Ask questions about the energy database in plain English.

An open-source language model (Qwen2.5-Coder-3B-Instruct) runs locally
on this computer and turns the question into a MySQL SELECT query. The
query runs inside a read-only transaction, and a short answer is built
from the rows that come back. If MySQL rejects the query, the error is
given back to the model so it can fix the SQL (up to MAX_ATTEMPTS
tries). No cloud API is used.

One question:  python python/nl2sql.py "Which month had the most solar production?"
Interactive:   python python/nl2sql.py
Web page:      python python/ask_web.py   (then open http://localhost:8000)

pip install torch transformers accelerate pymysql pandas python-dotenv
The model (~6 GB) is downloaded from Hugging Face the first time it runs.
Settings come from environment variables or a .env file (see .env.example).
"""
import glob
import os
import re
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd
import pymysql
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.getenv("NL2SQL_MODEL", "Qwen/Qwen2.5-Coder-3B-Instruct")
MAX_ATTEMPTS = 3          # SQL generation tries (the first try plus 2 repairs)
MAX_ROWS = 5000           # rows fetched from MySQL per query
QUERY_TIMEOUT_MS = 20000  # MySQL MAX_EXECUTION_TIME for each SELECT

# ---------------------------------------------------------------------
# Database description given to the model
# ---------------------------------------------------------------------
SCHEMA_PROMPT = """You write MySQL 8.0 SELECT queries that answer questions about this database.

Data: 5-minute readings for California, 2019-01-01 00:00 to 2021-12-31 23:55 (315,648 rows).

CREATE TABLE energy_reading (
  reading_time     DATETIME PRIMARY KEY,  -- one row every 5 minutes
  season_id        TINYINT,   -- references season.season_id
  day_id           TINYINT,   -- references day_of_week.day_id
  dhi              FLOAT,     -- diffuse horizontal irradiance, W/m2
  dni              FLOAT,     -- direct normal irradiance, W/m2
  ghi              FLOAT,     -- global horizontal irradiance, W/m2
  wind_speed       FLOAT,     -- m/s
  humidity         FLOAT,     -- relative humidity, %
  temperature      FLOAT,     -- degrees C
  pv_production    INT,       -- solar power, MW
  wind_production  INT,       -- wind power, MW
  electric_demand  INT        -- electricity demand, MW
);
CREATE TABLE season (       -- calendar quarters
  season_id   TINYINT PRIMARY KEY,  -- 1 Jan-Mar, 2 Apr-Jun, 3 Jul-Sep, 4 Oct-Dec
  season_name VARCHAR(20),          -- 'Q1 (Winter)', 'Q2 (Spring)', 'Q3 (Summer)', 'Q4 (Autumn)'
  months      VARCHAR(20)
);
CREATE TABLE day_of_week (
  day_id     TINYINT PRIMARY KEY,   -- 0 = Monday ... 6 = Sunday
  day_name   VARCHAR(10),
  is_weekend BOOLEAN
);

Rules:
- Write exactly one SELECT (or WITH ... SELECT) statement. Never change data.
- pv_production, wind_production and electric_demand are power in MW.
  Energy in MWh = SUM(column) * 5 / 60. Divide by 1000 more for GWh.
- Renewable share % = 100 * SUM(pv_production + wind_production) / SUM(electric_demand).
- Net load = electric_demand - pv_production - wind_production.
- Filter dates with ranges, e.g. reading_time >= '2020-07-01' AND reading_time < '2020-08-01'.
- Aggregate (by hour, day, month, year...) so the result has at most a few hundred rows.
- Give computed columns short aliases that include the unit, e.g. avg_demand_mw, solar_gwh.
- Round averages with ROUND(). Order time series by time.
- Only filter by a year, season or date if the question mentions one.
- For a time of day ("at noon", "at 6 pm"), filter HOUR(reading_time) = hour over the whole period.
- Only use LIMIT when the question asks for a top or bottom N.
- For bands or bins of a number, group by FLOOR(column / size) * size.
- If the database cannot answer the question, reply with CANNOT_ANSWER: and the reason.

Examples:

Question: What was the average demand for each hour of the day?
```sql
SELECT HOUR(reading_time) AS hour_of_day, ROUND(AVG(electric_demand), 0) AS avg_demand_mw
FROM energy_reading
GROUP BY HOUR(reading_time)
ORDER BY hour_of_day;
```

Question: How much solar energy was produced each year?
```sql
SELECT YEAR(reading_time) AS year, ROUND(SUM(pv_production) * 5 / 60 / 1000, 0) AS solar_gwh
FROM energy_reading
GROUP BY YEAR(reading_time)
ORDER BY year;
```

Question: Compare average demand on weekdays and weekends in each season.
```sql
SELECT s.season_name,
       CASE WHEN d.is_weekend THEN 'Weekend' ELSE 'Weekday' END AS day_type,
       ROUND(AVG(e.electric_demand), 0) AS avg_demand_mw
FROM energy_reading e
JOIN season s ON e.season_id = s.season_id
JOIN day_of_week d ON e.day_id = d.day_id
GROUP BY s.season_id, s.season_name, day_type
ORDER BY s.season_id, day_type;
```

Question: What was the average solar production at noon in June 2020?
```sql
SELECT ROUND(AVG(pv_production), 0) AS avg_solar_mw
FROM energy_reading
WHERE reading_time >= '2020-06-01' AND reading_time < '2020-07-01'
  AND HOUR(reading_time) = 12;
```

Question: How does wind production change with wind speed, in 1 m/s bands?
```sql
SELECT FLOOR(wind_speed / 1) * 1 AS wind_speed_band_ms,
       COUNT(*) AS readings,
       ROUND(AVG(wind_production), 0) AS avg_wind_mw
FROM energy_reading
GROUP BY wind_speed_band_ms
ORDER BY wind_speed_band_ms;
```

Question: What share of demand did renewables cover each year?
```sql
SELECT YEAR(reading_time) AS year,
       ROUND(100 * SUM(pv_production) / SUM(electric_demand), 1) AS solar_pct,
       ROUND(100 * SUM(wind_production) / SUM(electric_demand), 1) AS wind_pct,
       ROUND(100 * SUM(pv_production + wind_production) / SUM(electric_demand), 1) AS renewable_pct
FROM energy_reading
GROUP BY YEAR(reading_time)
ORDER BY year;
```

Question: Which 5 days had the highest peak demand?
```sql
SELECT DATE(reading_time) AS day, MAX(electric_demand) AS peak_demand_mw
FROM energy_reading
GROUP BY DATE(reading_time)
ORDER BY peak_demand_mw DESC
LIMIT 5;
```

Reply with only the SQL query inside a ```sql block."""

# Column-name endings the model is asked to use, and the unit each one means
UNITS = [("_mwh", "MWh"), ("_gwh", "GWh"), ("_mw", "MW"), ("_pct", "%"), ("_c", "°C"),
         ("_ms", "m/s"), ("_wm2", "W/m²")]


# ---------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------
@dataclass
class Answer:
    question: str
    answer: str = ""
    sql: str = ""
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    truncated: bool = False
    attempts: int = 0
    seconds: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------
def connect():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PWD", ""),
        database=os.getenv("MYSQL_DB", "energydb"),
        read_timeout=QUERY_TIMEOUT_MS // 1000 + 10,
    )


BLOCKED = re.compile(
    r"\b(insert|update|delete|replace\s+into|drop|alter|create|truncate|rename|grant|revoke|"
    r"load\s+data|lock|unlock|call|handler|set|sleep|benchmark)\b|\binto\s+(outfile|dumpfile)\b",
    re.IGNORECASE,
)


def check_sql(sql):
    """Return the cleaned SQL, or raise ValueError if it is not a single read-only SELECT."""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise ValueError("The query is empty.")
    if ";" in sql:
        raise ValueError("Only one statement is allowed (remove the ';').")
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("The query must start with SELECT or WITH.")
    # Look for blocked keywords outside of quoted strings
    unquoted = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "''", sql)
    match = BLOCKED.search(unquoted)
    if match:
        raise ValueError(f"'{match.group(0)}' is not allowed; write a read-only SELECT.")
    return sql


def run_sql(sql):
    """Run one SELECT in a read-only transaction. Returns (DataFrame, truncated)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {QUERY_TIMEOUT_MS}")
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute(sql)
            rows = cur.fetchmany(MAX_ROWS + 1)
            columns = [c[0] for c in cur.description] if cur.description else []
        conn.rollback()
    finally:
        conn.close()

    truncated = len(rows) > MAX_ROWS
    df = pd.DataFrame(list(rows[:MAX_ROWS]), columns=columns)
    # MySQL returns ROUND/AVG/SUM results as Decimal; convert them to float
    for col in df.columns:
        if len(df) and df[col].map(lambda v: isinstance(v, Decimal) or v is None).all():
            df[col] = df[col].astype(float)
    return df, truncated


# ---------------------------------------------------------------------
# Local language model
# ---------------------------------------------------------------------
_model = None
_tokenizer = None


def load_model():
    """Load the model once. Uses an Intel (XPU) or NVIDIA (CUDA) GPU if there is one."""
    global _model, _tokenizer
    if _model is not None:
        return
    # If the model is already downloaded, stay offline (no Hugging Face checks).
    # This must be set before transformers / huggingface_hub are imported.
    hub = os.path.join(os.getenv("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    cached = os.path.join(hub, "models--" + MODEL_NAME.replace("/", "--"), "snapshots")
    if glob.glob(os.path.join(cached, "*", "*.safetensors")):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch, "xpu") and torch.xpu.is_available():
        device = "xpu"
    else:
        device = "cpu"

    print(f"Loading {MODEL_NAME} on {device} ...", flush=True)
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    _model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.bfloat16)
    _model.to(device).eval()


def generate(system, user_text, max_new_tokens=400):
    """Run the model on one system + user message and return its reply."""
    import torch

    load_model()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_text}]
    inputs = _tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(_model.device)
    with torch.no_grad():
        # Greedy decoding: the same question always gives the same SQL
        output = _model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=_tokenizer.eos_token_id)
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    return _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def extract_sql(reply):
    """Pull the SQL out of the model's reply (a ```sql block, or bare SELECT/WITH)."""
    block = re.search(r"```(?:sql)?\s*(.*?)```", reply, re.DOTALL | re.IGNORECASE)
    if block:
        return block.group(1).strip()
    start = re.search(r"\b(SELECT|WITH)\b", reply, re.IGNORECASE)
    return reply[start.start():].strip() if start else reply.strip()


def generate_sql(question, history=(), feedback=""):
    """Ask the model for a SQL query. history is a list of earlier (question, sql) pairs."""
    parts = []
    if history:
        parts.append("Earlier questions in this conversation:")
        for q, s in history[-3:]:
            parts.append(f"Question: {q}\n```sql\n{s}\n```")
        parts.append("")
    parts.append(f"Question: {question}")
    if feedback:
        parts.append(f"\n{feedback}")
    return generate(SCHEMA_PROMPT, "\n".join(parts))


# ---------------------------------------------------------------------
# Answer text, built from the result table (not written by the model,
# so every number shown is exactly what MySQL returned)
# ---------------------------------------------------------------------
def describe_column(col):
    """'avg_demand_mw' -> ('avg demand', 'MW')"""
    for suffix, unit in UNITS:
        if col.lower().endswith(suffix):
            return col[: -len(suffix)].replace("_", " "), unit
    return col.replace("_", " "), ""


def fmt(value, unit=""):
    if hasattr(value, "item"):  # numpy number -> plain Python number
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = f"{value:,}" if isinstance(value, int) else (
        f"{value:,.2f}" if isinstance(value, float) else str(value))
    if unit == "%":
        return text + "%"
    return f"{text} {unit}".strip()


def fmt_label(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def summarize(df, truncated):
    """Short plain-English summary of a query result."""
    cols = list(df.columns)
    numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    if len(df) == 1:
        parts = [f"{describe_column(c)[0]}: {fmt(df.iloc[0][c], describe_column(c)[1])}"
                 for c in cols]
        return "; ".join(parts) + "."

    # First column is usually the label (year, hour, day, season); the rest are values
    values = [c for c in numeric if c != cols[0]] or numeric
    if not values:
        return f"{len(df):,} rows returned; see the table."
    key = next((c for c in values if c.lower() not in ("readings", "count", "n")), values[0])
    labels = [c for c in cols if c not in values] or [cols[0]]
    name, unit = describe_column(key)

    def label(row):  # plain text, so years and hours are not written as "2,020"
        return ", ".join(f"{describe_column(c)[0]} {fmt_label(row[c])}" for c in labels)

    hi, lo = df.loc[df[key].idxmax()], df.loc[df[key].idxmin()]
    text = (f"{len(df):,} rows{' (limited to the first ' + str(MAX_ROWS) + ')' if truncated else ''}. "
            f"Highest {name}: {fmt(hi[key], unit)} ({label(hi)}). "
            f"Lowest {name}: {fmt(lo[key], unit)} ({label(lo)}).")
    if len(values) > 1:
        text += " See the table for the other columns."
    return text


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------
def ask(question, history=()):
    """Question in, Answer out. Errors are reported in Answer.error rather than raised."""
    result = Answer(question=question)
    start = time.time()
    feedback = ""
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            result.attempts = attempt
            reply = generate_sql(question, history, feedback)

            if "CANNOT_ANSWER" in reply:
                result.answer = reply.split("CANNOT_ANSWER:", 1)[-1].strip() or \
                    "This question cannot be answered from the energy database."
                return result

            result.sql = extract_sql(reply)
            try:
                sql = check_sql(result.sql)
                result.data, result.truncated = run_sql(sql)
                break
            except (ValueError, pymysql.MySQLError) as e:
                # Give the error back to the model and try again
                feedback = (f"Your previous query was:\n```sql\n{result.sql}\n```\n"
                            f"It failed with this error: {e}\nWrite a corrected query.")
                if attempt == MAX_ATTEMPTS:
                    result.error = f"The query still failed after {attempt} tries: {e}"
                    return result

        if result.data.empty:
            result.answer = "The query ran but returned no rows."
        else:
            result.answer = summarize(result.data, result.truncated)
    except pymysql.MySQLError as e:
        result.error = f"Could not connect to MySQL: {e}"
    except Exception as e:  # noqa: BLE001 - surface anything else to the user
        result.error = f"{type(e).__name__}: {e}"
    finally:
        result.seconds = time.time() - start
    return result


def print_answer(r):
    if r.error:
        print("Error:", r.error)
    if r.sql:
        print("\nSQL:\n" + r.sql)
    if not r.data.empty:
        print(f"\nResult ({len(r.data)} rows{', truncated' if r.truncated else ''}):")
        print(r.data.head(20).to_string(index=False))
    if r.answer:
        print("\nAnswer:\n" + r.answer)
    print(f"\n({r.seconds:.1f} s)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print_answer(ask(" ".join(sys.argv[1:])))
        sys.exit(0)

    # Interactive mode: keep asking; earlier questions are used for follow-ups
    load_model()
    print("Ask a question about the energy data (blank line or 'quit' to exit).")
    history = []
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("", "quit", "exit"):
            break
        r = ask(question, history)
        print_answer(r)
        if r.sql and not r.error:
            history.append((r.question, r.sql))
