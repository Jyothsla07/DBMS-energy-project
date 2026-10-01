"""
load_data.py
Reads Database.csv, cleans it, and loads it into the energy_reading table.
Run 01_schema.sql first.

pip install pandas sqlalchemy pymysql
"""
import pandas as pd
from sqlalchemy import create_engine, text

# Edit these to match your MySQL setup (run from the project root folder)
DB_URL = "mysql+pymysql://root:root@localhost:3306/energydb"
CSV_PATH = "data/Database.csv"

# 1. Read the CSV
df = pd.read_csv(CSV_PATH)
print("Rows read from CSV:", len(df))

# 2. Drop the leftover row-number column
df = df.drop(columns=["Unnamed: 0"])

# 3. Fix the timestamp format (2019-01-01-T00:00 -> proper datetime)
df["Time"] = pd.to_datetime(df["Time"], format="%Y-%m-%d-T%H:%M")

# 4. Rename columns to match the database table
df = df.rename(columns={
    "Time": "reading_time",
    "Season": "season_id",
    "Day_of_the_week": "day_id",
    "DHI": "dhi",
    "DNI": "dni",
    "GHI": "ghi",
    "Wind_speed": "wind_speed",
    "Humidity": "humidity",
    "Temperature": "temperature",
    "PV_production": "pv_production",
    "Wind_production": "wind_production",
    "Electric_demand": "electric_demand",
})

# 5. Basic checks before loading
assert df["reading_time"].is_unique, "Duplicate timestamps found"
assert df.isna().sum().sum() == 0, "Missing values found"

# 6. Load into MySQL (append into the table created by 01_schema.sql)
engine = create_engine(DB_URL)
df.to_sql("energy_reading", engine, if_exists="append", index=False,
          chunksize=10000, method="multi")

# 7. Confirm the row count in the database
with engine.connect() as conn:
    count = conn.execute(text("SELECT COUNT(*) FROM energy_reading")).scalar()
print("Rows in database:", count)
