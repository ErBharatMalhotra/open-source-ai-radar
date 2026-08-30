"""Read uncategorized repos for AI classification."""
import sqlite3
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

db_path = Path("data/radar.db")
if not db_path.exists():
    print("Database not found!")
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

repos = conn.execute("""
    SELECT r.full_name, r.description, r.topics, r.language
    FROM repositories r
    LEFT JOIN ai_analysis a ON r.full_name = a.repo_full_name
    WHERE a.repo_full_name IS NULL 
       OR a.category = '' 
       OR a.category = 'Uncategorized'
""").fetchall()

print(f"Total uncategorized: {len(repos)}")
print("=" * 80)

for i, r in enumerate(repos):
    topics = json.loads(r["topics"] or "[]")
    desc = (r["description"] or "")[:150].encode("ascii", "replace").decode()
    lang = r["language"] or "unknown"
    print(f"\n--- {i+1}. {r['full_name']} ---")
    print(f"Desc: {desc}")
    print(f"Topics: {topics[:8]}")
    print(f"Lang: {lang}")

conn.close()
