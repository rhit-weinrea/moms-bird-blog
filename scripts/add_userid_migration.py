#!/usr/bin/env python3
"""One-off migration: add user_id column to post table if missing."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.db')

if not os.path.exists(DB):
    print('No database file found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()
try:
    cur.execute("PRAGMA table_info(post);")
    cols = [r[1] for r in cur.fetchall()]
    print('post columns:', cols)
    if 'user_id' in cols:
        print('user_id already present — nothing to do')
    else:
        print('Adding user_id column to post table...')
        cur.execute('ALTER TABLE post ADD COLUMN user_id INTEGER;')
        conn.commit()
        print('Added user_id column.')
except Exception as e:
    print('Migration failed:', e)
    raise
finally:
    conn.close()
