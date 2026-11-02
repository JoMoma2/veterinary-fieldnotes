from __future__ import annotations
import json, sqlite3
from pathlib import Path
from .util import now

class Store:
    def __init__(self,root:Path):
        self.root=root.resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(self.root/'jobs.sqlite3',timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS library_records (kind TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS applied_recordings (id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS case_keys (key TEXT PRIMARY KEY,id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, shift_id TEXT NOT NULL, shift_date TEXT NOT NULL,
          origin TEXT NOT NULL, authorization_ref TEXT NOT NULL, source_name TEXT NOT NULL, source_mtime REAL NOT NULL,
          source_kind TEXT NOT NULL, sequence INTEGER NOT NULL, stage TEXT NOT NULL DEFAULT 'transcribe',
          attempts INTEGER NOT NULL DEFAULT 0, retry_after REAL NOT NULL DEFAULT 0, error TEXT,
          created_at TEXT NOT NULL, completed_at TEXT, cleaned INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL,
          snapshot_hash TEXT NOT NULL DEFAULT '', applied_ids TEXT NOT NULL DEFAULT '[]', uploaded INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL);
        ''');self.db.commit()
    def jobs(self): return list(self.db.execute('SELECT * FROM jobs ORDER BY shift_date,shift_id,sequence,id'))
    def get(self,id):return self.db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
    def update(self,id,**fields):
        if set(fields)-{'stage','attempts','retry_after','error','completed_at','cleaned'}: raise ValueError('Unknown job field')
        with self.db:self.db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),id))
    def close(self): self.db.close()
