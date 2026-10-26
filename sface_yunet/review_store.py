"""Private face-review storage, separate from the existing enrollment database."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

import numpy as np


def identifier(name):
    value = re.sub(r"[^a-z0-9_-]+", "_", name.strip().lower()).strip("_")[:48]
    return value or "person_" + uuid.uuid4().hex[:12]


def normalize(vec):
    vec = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(vec).all() or norm < 1e-8:
        raise ValueError("Invalid face embedding")
    return vec / norm


class ReviewStore:
    def __init__(self, directory, retention_days=7, max_groups=100, group_threshold=0.6):
        self.lock = threading.RLock()
        self.retention_days = retention_days
        self.max_groups = max_groups
        self.threshold = group_threshold
        self.db = sqlite3.connect(str(Path(directory) / "review.db"), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS excluded (person TEXT, file TEXT, PRIMARY KEY(person,file));
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY, vec BLOB NOT NULL, first REAL, last REAL,
                sightings INTEGER NOT NULL, camera TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY, person TEXT REFERENCES people(id) ON DELETE CASCADE,
                group_id TEXT REFERENCES groups(id) ON DELETE CASCADE,
                jpeg BLOB NOT NULL, vec BLOB NOT NULL, added REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS photo_group ON photos(group_id);
        ''')
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO settings VALUES ('instance', ?)", (uuid.uuid4().hex[:12],))
        self.instance = self.db.execute("SELECT value FROM settings WHERE key='instance'").fetchone()[0]
        self.prune()

    def prune(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM groups WHERE last < ?", (time.time()-self.retention_days*86400,))
            self.db.execute("DELETE FROM groups WHERE id IN (SELECT id FROM groups ORDER BY last DESC LIMIT -1 OFFSET ?)", (self.max_groups,))

    def names(self):
        with self.lock:
            return {r['id']:r['name'] for r in self.db.execute("SELECT id,name FROM people")}

    def ensure_person(self, name, person_id=None):
        name = str(name).strip()
        if not name or len(name)>80 or any(ord(c)<32 for c in name):
            raise ValueError("Enter a name between 1 and 80 characters")
        create=person_id is None
        person_id = person_id or identifier(name)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", person_id):
            raise ValueError("Invalid person ID")
        with self.lock, self.db:
            if create and self.db.execute('SELECT 1 FROM people WHERE id=?',(person_id,)).fetchone():
                raise ValueError('This name is already enrolled. Choose the existing person or use a different name.')
            self.db.execute("INSERT OR IGNORE INTO people VALUES (?,?)", (person_id,name))
        return person_id

    def rename(self, person, name):
        self.ensure_person(name, person)
        with self.lock, self.db:
            self.db.execute("UPDATE people SET name=? WHERE id=?", (name.strip(), person))

    def embeddings(self):
        with self.lock:
            return [(r['person'], np.frombuffer(r['vec'],np.float32).copy())
                    for r in self.db.execute("SELECT person,vec FROM photos WHERE person IS NOT NULL")]

    def exclusions(self):
        with self.lock:
            return set(tuple(r) for r in self.db.execute("SELECT person,file FROM excluded"))

    def exclude(self, person, filename):
        with self.lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO excluded VALUES (?,?)", (person,filename))

    def add_photo(self, person, jpeg, vector):
        photo = uuid.uuid4().hex
        with self.lock, self.db:
            self.db.execute("INSERT INTO photos VALUES (?,?,NULL,?,?,?)",
                            (photo,person,jpeg,normalize(vector).tobytes(),time.time()))
        return photo

    def observe(self, vector, jpeg, camera):
        vector=normalize(vector)
        now=time.time()
        with self.lock:
            self.prune()
            groups=list(self.db.execute("SELECT * FROM groups"))
            scores=[(float(vector @ np.frombuffer(r['vec'],np.float32)),r) for r in groups]
            score,group=max(scores,key=lambda s:s[0]) if scores else (-1,None)
            with self.db:
                if score < self.threshold:
                    gid=uuid.uuid4().hex
                    self.db.execute("INSERT INTO groups VALUES (?,?,?,?,?,?)",
                                    (gid,vector.tobytes(),now,now,1,camera))
                    save=True
                else:
                    gid=group['id']
                    self.db.execute("UPDATE groups SET last=?,sightings=sightings+1,camera=? WHERE id=?", (now,camera,gid))
                    latest=self.db.execute("SELECT MAX(added) FROM photos WHERE group_id=?",(gid,)).fetchone()[0]
                    save=latest is None or now-latest >= 30
                if save:
                    self.db.execute("INSERT INTO photos VALUES (?,NULL,?,?,?,?)",
                                    (uuid.uuid4().hex,gid,jpeg,vector.tobytes(),now))
                    self.db.execute("DELETE FROM photos WHERE group_id=? AND id NOT IN (SELECT id FROM photos WHERE group_id=? ORDER BY added DESC LIMIT 6)", (gid,gid))
            self.prune()
        return gid

    def groups(self):
        with self.lock:
            self.prune()
            result=[]
            for row in self.db.execute("SELECT id,first,last,sightings,camera FROM groups ORDER BY last DESC"):
                item=dict(row)
                item['photos']=[r['id'] for r in self.db.execute("SELECT id FROM photos WHERE group_id=? ORDER BY added DESC", (row['id'],))]
                result.append(item)
            return result

    def known_photos(self, person):
        with self.lock:
            return [r['id'] for r in self.db.execute("SELECT id FROM photos WHERE person=? ORDER BY added DESC",(person,))]

    def photo(self, photo_id):
        with self.lock:
            row=self.db.execute("SELECT jpeg FROM photos WHERE id=?",(photo_id,)).fetchone()
            if row is None:
                raise ValueError("Photo not found")
            return row['jpeg']

    def assign(self, group_id, photo_ids, person):
        if not photo_ids or len(photo_ids)>6 or len(set(photo_ids))!=len(photo_ids):
            raise ValueError("Select between one and six clear photos")
        with self.lock, self.db:
            rows=list(self.db.execute("SELECT id,vec FROM photos WHERE group_id=?",(group_id,)))
            if not set(photo_ids).issubset({r['id'] for r in rows}):
                raise ValueError("A selected photo is no longer in this group")
            for photo in photo_ids:
                self.db.execute("UPDATE photos SET person=?,group_id=NULL WHERE id=?",(person,photo))
            remaining=[r for r in rows if r['id'] not in photo_ids]
            if remaining:
                center=normalize(np.mean([np.frombuffer(r['vec'],np.float32) for r in remaining],axis=0))
                self.db.execute("UPDATE groups SET vec=? WHERE id=?",(center.tobytes(),group_id))
            else:
                self.db.execute("DELETE FROM groups WHERE id=?",(group_id,))

    def dismiss(self, group_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM groups WHERE id=?",(group_id,))

    def remove_photo(self, photo_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM photos WHERE id=? AND person IS NOT NULL",(photo_id,))

    def remove_person(self, person):
        with self.lock, self.db:
            self.db.execute("DELETE FROM people WHERE id=?",(person,))

    def close(self):
        with self.lock:
            self.db.close()
