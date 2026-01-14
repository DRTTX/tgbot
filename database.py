import sqlite3
import os
from typing import List, Optional
from datetime import datetime

from config import DB_PATH, STORAGE_PDF


# ===================== DATABASE =====================

class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        cur = self.conn.cursor()

        # ---------- USERS ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            language TEXT DEFAULT 'en',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ---------- FILES ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,

            original_name TEXT,
            stored_name TEXT NOT NULL,

            file_type TEXT NOT NULL,        -- pdf / image
            page_format TEXT DEFAULT 'A4',  -- A4 / original / fit

            size_bytes INTEGER,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,

            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """)

        # ---------- DRAFTS ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,

            page_format TEXT DEFAULT 'A4',

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,

            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """)

        # ---------- DRAFT ITEMS ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS draft_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER NOT NULL,

            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,        -- pdf / image
            size_bytes INTEGER,

            order_index INTEGER NOT NULL,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (draft_id) REFERENCES drafts(id)
        )
        """)

        self.conn.commit()


# ===================== USER REPO =====================

class UserRepo:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create(self, telegram_id: int) -> dict:
        cur = self.db.conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE telegram_id=?",
            (telegram_id,)
        )
        row = cur.fetchone()

        if not row:
            cur.execute(
                "INSERT INTO users (telegram_id) VALUES (?)",
                (telegram_id,)
            )
            self.db.conn.commit()
            return self.get_or_create(telegram_id)

        return dict(row)

    def set_language(self, telegram_id: int, lang: str):
        self.db.conn.execute(
            "UPDATE users SET language=? WHERE telegram_id=?",
            (lang, telegram_id)
        )
        self.db.conn.commit()


# ===================== FILE REPO =====================

class FileRepo:
    def __init__(self, db: Database):
        self.db = db

    # ---------- CREATE ----------

    def create(
        self,
        user_id: int,
        original_name: str,
        stored_name: str,
        file_type: str,
        page_format: str,
        size_bytes: int
    ) -> int:
        cur = self.db.conn.cursor()
        cur.execute("""
            INSERT INTO files (
                user_id,
                original_name,
                stored_name,
                file_type,
                page_format,
                size_bytes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            original_name,
            stored_name,
            file_type,
            page_format,
            size_bytes
        ))
        self.db.conn.commit()
        return cur.lastrowid

    # ---------- READ ----------

    def get(self, file_id: int, user_id: int) -> Optional[dict]:
        row = self.db.conn.execute("""
            SELECT *
            FROM files
            WHERE id=? AND user_id=?
        """, (file_id, user_id)).fetchone()
        return dict(row) if row else None

    def list_paginated(
        self,
        user_id: int,
        page: int,
        page_size: int = 5
    ) -> List[dict]:
        offset = (page - 1) * page_size
        rows = self.db.conn.execute("""
            SELECT *
            FROM files
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (user_id, page_size, offset)).fetchall()
        return [dict(r) for r in rows]

    def count(self, user_id: int) -> int:
        row = self.db.conn.execute("""
            SELECT COUNT(*) AS cnt
            FROM files
            WHERE user_id=?
        """, (user_id,)).fetchone()
        return row["cnt"]

    # ---------- UPDATE ----------

    def rename(self, file_id: int, user_id: int, new_name: str):
        self.db.conn.execute("""
            UPDATE files
            SET original_name=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND user_id=?
        """, (new_name, file_id, user_id))
        self.db.conn.commit()

    # ---------- DELETE ----------

    def delete(self, file_id: int, user_id: int):
        row = self.get(file_id, user_id)
        if row:
            try:
                os.remove(os.path.join(STORAGE_PDF, row["stored_name"]))
            except FileNotFoundError:
                pass

        self.db.conn.execute("""
            DELETE FROM files
            WHERE id=? AND user_id=?
        """, (file_id, user_id))
        self.db.conn.commit()


# ===================== DRAFT REPO =====================

class DraftRepo:
    def __init__(self, db: Database):
        self.db = db

    def get(self, user_id: int) -> Optional[dict]:
        row = self.db.conn.execute("""
            SELECT *
            FROM drafts
            WHERE user_id=?
        """, (user_id,)).fetchone()
        return dict(row) if row else None

    def create(self, user_id: int, page_format: str = "A4") -> dict:
        self.db.conn.execute("""
            INSERT OR REPLACE INTO drafts (
                user_id,
                page_format,
                created_at
            )
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (user_id, page_format))
        self.db.conn.commit()
        return self.get(user_id)

    def update_format(self, user_id: int, page_format: str):
        self.db.conn.execute("""
            UPDATE drafts
            SET page_format=?, updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?
        """, (page_format, user_id))
        self.db.conn.commit()

    def delete(self, user_id: int):
        draft = self.get(user_id)
        if not draft:
            return

        self.db.conn.execute(
            "DELETE FROM draft_items WHERE draft_id=?",
            (draft["id"],)
        )
        self.db.conn.execute(
            "DELETE FROM drafts WHERE user_id=?",
            (user_id,)
        )
        self.db.conn.commit()


# ===================== DRAFT ITEM REPO =====================

class DraftItemRepo:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self,
        draft_id: int,
        file_path: str,
        file_type: str,
        size_bytes: int
    ):
        cur = self.db.conn.cursor()

        row = cur.execute("""
            SELECT COALESCE(MAX(order_index), 0) + 1 AS next_order
            FROM draft_items
            WHERE draft_id=?
        """, (draft_id,)).fetchone()

        order_index = row["next_order"]

        cur.execute("""
            INSERT INTO draft_items (
                draft_id,
                file_path,
                file_type,
                size_bytes,
                order_index
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            draft_id,
            file_path,
            file_type,
            size_bytes,
            order_index
        ))

        self.db.conn.commit()

    def list(self, draft_id: int) -> List[dict]:
        rows = self.db.conn.execute("""
            SELECT *
            FROM draft_items
            WHERE draft_id=?
            ORDER BY order_index ASC
        """, (draft_id,)).fetchall()
        return [dict(r) for r in rows]

    def clear(self, draft_id: int):
        self.db.conn.execute(
            "DELETE FROM draft_items WHERE draft_id=?",
            (draft_id,)
        )
        self.db.conn.commit()
