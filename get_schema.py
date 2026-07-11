import sqlite3
from pathlib import Path

DB_PATH = Path("bluestock_mf.db")

con = sqlite3.connect(DB_PATH)
rows = con.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name;"
).fetchall()

for name, sql in rows:
    print(f"\n{'-'*70}\nTABLE: {name}\n{'-'*70}")
    print(sql)

print(f"\n{'='*70}\nROW COUNTS\n{'='*70}")
for name, _ in rows:
    count = con.execute(f"SELECT COUNT(*) FROM {name};").fetchone()[0]
    print(f"{name}: {count}")

con.close()