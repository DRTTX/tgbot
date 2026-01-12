import sqlite3
import os
from typing import List
from config import DB_PATH, STORAGE_PDF


# ===================== DATABASE =====================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            language TEXT DEFAULT 'en'
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_name TEXT,
            stored_name TEXT
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

    def create(self, user_id: int, name: str, stored: str) -> int:
        cur = self.db.conn.cursor()
        cur.execute("""
            INSERT INTO files (user_id, original_name, stored_name)
            VALUES (?, ?, ?)
        """, (user_id, name, stored))
        self.db.conn.commit()
        return cur.lastrowid

    # ---------- READ ----------

    def list(self, user_id: int) -> List[dict]:
        rows = self.db.conn.execute(
            "SELECT * FROM files WHERE user_id=? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, file_id: int, user_id: int) -> dict | None:
        row = self.db.conn.execute(
            "SELECT * FROM files WHERE id=? AND user_id=?",
            (file_id, user_id)
        ).fetchone()
        return dict(row) if row else None

    # ---------- UPDATE ----------

    def rename(self, file_id: int, user_id: int, new_name: str):
        self.db.conn.execute(
            "UPDATE files SET original_name=? WHERE id=? AND user_id=?",
            (new_name, file_id, user_id)
        )
        self.db.conn.commit()

    def set_stored_name(self, file_id: int, stored_name: str):
        self.db.conn.execute(
            "UPDATE files SET stored_name=? WHERE id=?",
            (stored_name, file_id)
        )
        self.db.conn.commit()

    # ---------- DELETE ----------

    def delete(self, file_id: int, user_id: int):
        self.db.conn.execute(
            "DELETE FROM files WHERE id=? AND user_id=?",
            (file_id, user_id)
        )
        self.db.conn.commit()

    # ---------- MERGE SUPPORT ----------

    def get_paths(self, file_ids: List[int], user_id: int) -> List[str]:
        """
        Возвращает абсолютные пути к PDF-файлам
        в том порядке, в котором их выбрал пользователь
        """
        if not file_ids:
            return []

        placeholders = ",".join("?" for _ in file_ids)
        query = f"""
            SELECT id, stored_name
            FROM files
            WHERE user_id=? AND id IN ({placeholders})
        """

        rows = self.db.conn.execute(
            query,
            (user_id, *file_ids)
        ).fetchall()

        id_to_path = {
            row["id"]: os.path.join(STORAGE_PDF, row["stored_name"])
            for row in rows
            if row["stored_name"]
        }

        # сохранить порядок выбора
        return [
            id_to_path[i]
            for i in file_ids
            if i in id_to_path and os.path.exists(id_to_path[i])
        ]
