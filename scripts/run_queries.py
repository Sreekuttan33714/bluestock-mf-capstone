"""
run_queries.py

Runs every query in sql/queries.sql against bluestock_mf.db and prints
the results. Avoids needing the sqlite3 command-line tool (not
installed by default on Windows) — uses Python's built-in sqlite3
module instead.

Usage (from project root, venv active):
    python scripts/run_queries.py
"""

import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "bluestock_mf.db"
QUERIES_PATH = PROJECT_ROOT / "sql" / "queries.sql"


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    if not QUERIES_PATH.exists():
        raise FileNotFoundError(f"queries.sql not found at {QUERIES_PATH}")

    raw = QUERIES_PATH.read_text(encoding="utf-8")

    # Strip comment lines, then split into individual statements on ';'
    no_comments = re.sub(r"--.*", "", raw)
    statements = [s.strip() for s in no_comments.split(";") if s.strip()]

    con = sqlite3.connect(DB_PATH)
    try:
        for i, stmt in enumerate(statements, start=1):
            print(f"\n{'=' * 70}")
            print(f"QUERY {i}")
            print("=" * 70)
            try:
                cur = con.execute(stmt)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                print(" | ".join(cols))
                print("-" * 70)
                for row in rows[:10]:
                    print(row)
                if len(rows) > 10:
                    print(f"... ({len(rows)} total rows)")
                else:
                    print(f"({len(rows)} total rows)")
            except sqlite3.Error as e:
                print(f"ERROR: {e}")
                print(stmt[:200])
    finally:
        con.close()


if __name__ == "__main__":
    main()