#!/usr/bin/env bash
# Runs once when the Codespace is created.
set -e

echo "== Installing Python packages (CPU build of PyTorch) =="
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir -r requirements.txt

echo "== Waiting for MySQL to finish restoring backup/energydb.sql =="
python - <<'EOF'
import os, time, pymysql
for _ in range(120):
    try:
        conn = pymysql.connect(host=os.environ["MYSQL_HOST"], user=os.environ["MYSQL_USER"],
                               password=os.environ["MYSQL_PWD"], database=os.environ["MYSQL_DB"])
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM energy_reading")
            print(f"energydb is ready: {cur.fetchone()[0]:,} rows")
        break
    except pymysql.MySQLError:
        time.sleep(5)
else:
    raise SystemExit("MySQL did not become ready in 10 minutes")
EOF

echo "== Downloading ${NL2SQL_MODEL} (about 6 GB, first time only) =="
python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(os.environ['NL2SQL_MODEL'])"

echo "== Setup done. The web page starts on port 8000. =="
