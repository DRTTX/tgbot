import os
import shutil
import sqlite3
import time
import logging
import re
from typing import Set

from config import DB_PATH, STORAGE_PDF

# ===================== CONFIG =====================

TELEGRAM_ID = 1361117475
EXPORT_DIR = os.path.join("export", str(TELEGRAM_ID))
SCAN_INTERVAL = 5  # seconds

# ===================== LOGGER =====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("watcher")

# ===================== NAME VALIDATION =====================

NAME_RE = re.compile(r"^[A-ZА-Я][a-zа-я]+$")

def is_valid_name(filename: str) -> bool:
    """
    Checks Name Surname.pdf
    """
    if not filename.lower().endswith(".pdf"):
        return False

    name = filename[:-4]  # remove .pdf
    parts = name.split()

    if len(parts) != 2:
        return False

    return all(NAME_RE.match(p) for p in parts)

# ===================== DB HELPERS =====================

def get_internal_user_id(cur) -> int | None:
    cur.execute(
        "SELECT id FROM users WHERE telegram_id=?",
        (TELEGRAM_ID,)
    )
    row = cur.fetchone()
    return row["id"] if row else None


def get_db_files(cur, user_id: int):
    cur.execute(
        "SELECT original_name, stored_name FROM files WHERE user_id=?",
        (user_id,)
    )
    return cur.fetchall()


def get_expected_filenames(cur, user_id: int) -> Set[str]:
    cur.execute(
        "SELECT original_name FROM files WHERE user_id=?",
        (user_id,)
    )
    return {f"{row['original_name']}.pdf" for row in cur.fetchall()}

# ===================== CORE LOGIC =====================

def sync_export(cur, user_id: int):
    os.makedirs(EXPORT_DIR, exist_ok=True)

    db_files = get_db_files(cur, user_id)
    expected_names = get_expected_filenames(cur, user_id)

    export_files = {
        f for f in os.listdir(EXPORT_DIR)
        if f.lower().endswith(".pdf")
    }

    copied = 0
    deleted = 0

    # ---------- COPY ----------
    for row in db_files:
        original = row["original_name"]
        stored = row["stored_name"]

        if not stored:
            continue

        filename = f"{original}.pdf"

        if not is_valid_name(filename):
            continue  # ❗ не копируем невалидные имена

        src = os.path.join(STORAGE_PDF, stored)
        dst = os.path.join(EXPORT_DIR, filename)

        if not os.path.exists(src) or os.path.exists(dst):
            continue

        shutil.copy2(src, dst)
        copied += 1
        log.info("📄 Copied → %s", filename)

    # ---------- CLEANUP ----------
    for fname in export_files:
        reason = None

        if fname not in expected_names:
            reason = "not in database"
        elif not is_valid_name(fname):
            reason = "invalid name format"

        if reason:
            try:
                os.remove(os.path.join(EXPORT_DIR, fname))
                deleted += 1
                log.warning("🗑 Deleted (%s) → %s", reason, fname)
            except Exception as e:
                log.error("❌ Failed to delete %s: %s", fname, e)

    # ---------- STATS ----------
    export_now = {
        f for f in os.listdir(EXPORT_DIR)
        if f.lower().endswith(".pdf")
    }

    valid_now = {f for f in export_now if is_valid_name(f)}

    log.info(
        "📊 Export stats → db:%d | export:%d | valid:%d | invalid:%d",
        len(expected_names),
        len(export_now),
        len(valid_now),
        len(export_now) - len(valid_now),
    )

    if copied:
        log.info("✅ Copied %d new file(s)", copied)
    if deleted:
        log.info("🧹 Removed %d invalid file(s)", deleted)

# ===================== MAIN =====================

def main():
    log.info("🚀 Watcher started for telegram_id=%s", TELEGRAM_ID)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    user_id = get_internal_user_id(cur)
    if not user_id:
        log.error("❌ User %s not found in database", TELEGRAM_ID)
        return

    log.info("👤 Watching internal user_id=%s", user_id)

    while True:
        try:
            sync_export(cur, user_id)
        except Exception as e:
            log.error("💥 Unexpected error: %s", e)

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
