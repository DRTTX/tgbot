import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CommandHandler,
    ConversationHandler,
)

from config import BOT_TOKEN, STORAGE_PDF, STORAGE_TEMP
from database import Database, UserRepo, FileRepo
from services import PDFService
from keyboards import (
    lang_kb,
    main_menu,
    collect_kb,
    files_list_kb,
    file_actions_kb,
    merge_files_kb,
)
from texts import TEXT
from ui import update_ui, reset_ui

# ===================== LOGGER ===================

import logging
import sys

class HumanFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\033[92m",     # green
        "WARNING": "\033[93m",  # yellow
        "ERROR": "\033[91m",    # red
        "RESET": "\033[0m",
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        record.levelname = f"{color}{record.levelname:<7}{reset}"
        return super().format(record)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    HumanFormatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
)

root = logging.getLogger()
root.handlers.clear()
root.addHandler(handler)
root.setLevel(logging.INFO)

# глушим шум
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logging.info("🚀 Bot process initialized")


def log_user(update: Update, action: str):
    user = update.effective_user
    uid = user.id if user else "unknown"
    logging.info("👤 User %s %s", uid, action)




# ===================== INIT =====================

os.makedirs(STORAGE_PDF, exist_ok=True)
os.makedirs(STORAGE_TEMP, exist_ok=True)

logging.basicConfig(level=logging.INFO)

(
    LANG,
    MENU,
    COLLECT,
    NAME,
    FILES_MENU,
    SETTINGS_MENU,
    RENAME,
    MERGE_SELECT,
) = range(8)

db = Database()
users = UserRepo(db)
files = FileRepo(db)

# ===================== START =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_user(update, "started bot")
    users.get_or_create(update.effective_user.id)
    context.user_data.clear()
    context.user_data["lang"] = "en"

    await reset_ui(
        update,
        context,
        TEXT["en"]["welcome"],
        reply_markup=lang_kb()
    )
    return LANG

# ===================== LANGUAGE =====================

async def set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    lang = q.data.split("_")[1]
    users.set_language(q.from_user.id, lang)
    context.user_data["lang"] = lang

    await update_ui(
        update,
        context,
        TEXT[lang]["menu_title"],
        reply_markup=main_menu(lang)
    )
    return MENU

# ===================== MENU =====================

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = context.user_data["lang"]

    if q.data == "create":
        context.user_data["images"] = []
        await update_ui(update, context, TEXT[lang]["collect_images"], collect_kb(lang))
        return COLLECT

    if q.data == "files":
        return await show_files(update, context)

    if q.data == "settings":
        await update_ui(update, context, TEXT[lang]["choose_language"], lang_kb())
        return SETTINGS_MENU

    if q.data in ("back_menu", "files"):
        await update_ui(update, context, TEXT[lang]["menu_title"], main_menu(lang))
        return MENU

# ===================== FILE LIST =====================

async def show_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_user(update, "opened My Files")
    lang = context.user_data["lang"]
    user = users.get_or_create(update.effective_user.id)
    items = files.list(user["id"])

    if not items:
        await update_ui(update, context, TEXT[lang]["no_files"], main_menu(lang))
        return MENU

    text = TEXT[lang]["your_files"] + "\n\n"
    for f in items:
        text += f"📄 {f['original_name']} (ID {f['id']})\n"

    await update_ui(
        update,
        context,
        text,
        reply_markup=files_list_kb(items, lang)
    )
    return FILES_MENU

# ===================== COLLECT IMAGES =====================

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("images", [])

    file = await update.message.photo[-1].get_file()
    path = os.path.join(
        STORAGE_TEMP,
        f"{update.effective_user.id}_{len(context.user_data['images'])}.jpg"
    )
    await file.download_to_drive(path)
    context.user_data["images"].append(path)

async def collect_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = context.user_data["lang"]

    if q.data == "done":
        if not context.user_data.get("images"):
            await update_ui(update, context, TEXT[lang]["no_images"], main_menu(lang))
            return MENU
        await update_ui(update, context, TEXT[lang]["enter_pdf_name"])
        return NAME

    if q.data == "cancel":
        context.user_data.pop("images", None)
        await update_ui(update, context, TEXT[lang]["cancelled"], main_menu(lang))
        return MENU

# ===================== CREATE PDF =====================

async def create_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_user(update, f"created PDF '{update.message.text.strip()}'")
    lang = context.user_data["lang"]
    name = update.message.text.strip()
    user = users.get_or_create(update.effective_user.id)

    file_id = files.create(user["id"], name, "")
    stored = f"{file_id:06}.pdf"
    pdf_path = os.path.join(STORAGE_PDF, stored)

    PDFService.images_to_pdf(context.user_data["images"], pdf_path)
    files.set_stored_name(file_id, stored)

    await update.message.reply_document(
        document=open(pdf_path, "rb"),
        filename=f"{name}.pdf",
        caption=TEXT[lang]["pdf_created"]
    )

    for img in context.user_data["images"]:
        try:
            os.remove(img)
        except FileNotFoundError:
            pass

    context.user_data["images"] = []

    await reset_ui(update, context, TEXT[lang]["menu_title"], main_menu(lang))
    return MENU

# ===================== FILE CRUD =====================

async def file_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid = int(update.callback_query.data.split("_")[1])
    log_user(update, f"selected file #{fid}")
    q = update.callback_query
    await q.answer()
    lang = context.user_data["lang"]

    fid = int(q.data.split("_")[1])
    file = files.get(fid, users.get_or_create(q.from_user.id)["id"])

    if not file:
        await reset_ui(update, context, TEXT[lang]["file_not_found"], main_menu(lang))
        return MENU

    await update_ui(
        update,
        context,
        f"📄 {file['original_name']}",
        file_actions_kb(fid, lang)
    )
    return FILES_MENU

async def file_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid = int(update.callback_query.data.split("_")[1])
    log_user(update, f"downloaded file #{fid}")
    q = update.callback_query
    await q.answer()
    lang = context.user_data["lang"]

    fid = int(q.data.split("_")[1])
    user = users.get_or_create(q.from_user.id)
    file = files.get(fid, user["id"])

    if not file or not file["stored_name"]:
        await reset_ui(update, context, TEXT[lang]["error"], main_menu(lang))
        return MENU

    path = os.path.join(STORAGE_PDF, file["stored_name"])
    if not os.path.exists(path):
        await reset_ui(update, context, TEXT[lang]["error"], main_menu(lang))
        return MENU

    await q.message.reply_document(
        document=open(path, "rb"),
        filename=f"{file['original_name']}.pdf"
    )

    await reset_ui(update, context, TEXT[lang]["menu_title"], main_menu(lang))
    return MENU

async def file_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = context.user_data["lang"]

    user = users.get_or_create(q.from_user.id)
    fid = int(q.data.split("_")[1])
    file = files.get(fid, user["id"])

    if file and file["stored_name"]:
        try:
            os.remove(os.path.join(STORAGE_PDF, file["stored_name"]))
        except FileNotFoundError:
            pass

    files.delete(fid, user["id"])
    return await show_files(update, context)

# ===================== RENAME =====================

async def rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["rename_id"] = int(q.data.split("_")[1])

    await update_ui(update, context, TEXT[context.user_data["lang"]]["rename"] + ":")
    return RENAME

async def rename_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_user(update, "renamed file")
    fid = context.user_data.pop("rename_id")
    user = users.get_or_create(update.effective_user.id)

    files.rename(fid, user["id"], update.message.text.strip())

    await reset_ui(
        update,
        context,
        TEXT[context.user_data["lang"]]["file_renamed"],
        main_menu(context.user_data["lang"])
    )
    return MENU

# ===================== MERGE =====================

async def merge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["merge_ids"] = set()
    return await merge_show(update, context)

async def merge_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    fid = int(q.data.split("_")[2])

    context.user_data.setdefault("merge_ids", set())
    context.user_data["merge_ids"].symmetric_difference_update({fid})
    return await merge_show(update, context)

async def merge_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data["lang"]
    context.user_data.setdefault("merge_ids", set())

    user = users.get_or_create(update.effective_user.id)
    items = files.list(user["id"])

    await update_ui(
        update,
        context,
        TEXT[lang]["merge_select"],
        merge_files_kb(items, context.user_data["merge_ids"], lang)
    )
    return MERGE_SELECT

async def merge_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ids = list(context.user_data.get("merge_ids", []))
    log_user(update, f"merged files {ids}")
    q = update.callback_query
    await q.answer()

    lang = context.user_data["lang"]
    ids = list(context.user_data.get("merge_ids", []))
    user = users.get_or_create(q.from_user.id)

    if len(ids) < 2:
        return await merge_show(update, context)

    paths = files.get_paths(ids, user["id"])

    fid = files.create(user["id"], "Merged PDF", "")
    stored = f"{fid:06}.pdf"
    out = os.path.join(STORAGE_PDF, stored)

    PDFService.merge_pdfs(paths, out)
    files.set_stored_name(fid, stored)

    context.user_data.pop("merge_ids", None)

    await reset_ui(update, context, TEXT[lang]["pdf_created"], main_menu(lang))
    return MENU

# ===================== MAIN =====================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(set_lang)],
            MENU: [CallbackQueryHandler(menu_handler)],
            COLLECT: [
                MessageHandler(filters.PHOTO, photo_handler),
                CallbackQueryHandler(collect_actions),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_pdf)],
            FILES_MENU: [
                CallbackQueryHandler(rename_start, pattern="^rename_"),
                CallbackQueryHandler(merge_start, pattern="^merge_start$"),
                CallbackQueryHandler(file_select_handler, pattern="^file_"),
                CallbackQueryHandler(file_download_handler, pattern="^download_"),
                CallbackQueryHandler(file_delete_handler, pattern="^delete_"),
                CallbackQueryHandler(menu_handler),
            ],
            RENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_apply)],
            MERGE_SELECT: [
                CallbackQueryHandler(merge_toggle, pattern="^merge_toggle_"),
                CallbackQueryHandler(merge_done, pattern="^merge_done$"),
                CallbackQueryHandler(menu_handler, pattern="^back_menu$"),
            ],
            SETTINGS_MENU: [CallbackQueryHandler(set_lang)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
