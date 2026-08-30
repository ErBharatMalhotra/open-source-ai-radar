"""List remaining uncategorized repos."""
import sqlite3
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect("data/radar.db")
conn.row_factory = sqlite3.Row

repos = conn.execute("""
    SELECT r.full_name, r.description, r.topics, r.language
    FROM repositories r
    LEFT JOIN ai_analysis a ON r.full_name = a.repo_full_name
    WHERE a.repo_full_name IS NULL
       OR a.category = '' 
       OR a.category = 'Uncategorized'
""").fetchall()

for r in repos:
    topics = json.loads(r["topics"] or "[]")
    desc = (r["description"] or "")[:120].encode("ascii", "replace").decode()
    print(f"{r['full_name']} | {desc} | {topics[:5]} | {r['language']}")

conn.close()
