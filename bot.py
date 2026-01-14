import os
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

from config import BOT_TOKEN, STORAGE_TEMP, STORAGE_PDF, MAX_FILE_SIZE_MB
from database import (
    Database,
    UserRepo,
    FileRepo,
    DraftRepo,
    DraftItemRepo,
)
from services import PDFService
from keyboards import (
    main_menu,
    files_list_kb,
    file_actions_kb,
    language_kb,
)
from texts import TEXT
from ui import show_ui, reset_ui, bump_ui, show_temp, delete_temp


# ===================== LOGGING =====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("bot")


# ===================== INIT =====================

os.makedirs(STORAGE_TEMP, exist_ok=True)
os.makedirs(STORAGE_PDF, exist_ok=True)

db = Database()
users = UserRepo(db)
files = FileRepo(db)
drafts = DraftRepo(db)
draft_items = DraftItemRepo(db)


# ===================== HELPERS =====================

def get_lang(user: dict) -> str:
    return user.get("language", "en")


def auto_name() -> str:
    return f"Document {datetime.now().strftime('%Y-%m-%d %H:%M')}"


def is_supported_image(filename: str) -> bool:
    return filename.lower().endswith((".jpg", ".jpeg", ".png", ".heic"))


def is_supported_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def file_too_large(size_bytes: int) -> bool:
    return size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024


# ===================== /start =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = users.get_or_create(update.effective_user.id)
    log.info("START | user=%s", user["id"])

    await reset_ui(update, context)
    drafts.delete(user["id"])
    context.user_data.clear()

    if user["language"] == "en":
        await show_ui(
            update,
            context,
            "🌐 Choose language / Tilni tanlang / Выберите язык",
            reply_markup=language_kb(),
            force_new=True,
        )
        return

    lang = user["language"]
    await show_ui(
        update,
        context,
        TEXT[lang]["welcome"],
        reply_markup=main_menu(lang),
        force_new=True,
    )


# ===================== FILE HANDLER =====================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = users.get_or_create(update.effective_user.id)
    lang = get_lang(user)

    doc = update.message.document
    photo = update.message.photo[-1] if update.message.photo else None

    tg_file = doc or photo
    file_name = doc.file_name if doc else "image.jpg"
    file_size = doc.file_size if doc else photo.file_size

    log.info("FILE | user=%s | name=%s | size=%s", user["id"], file_name, file_size)

    if file_too_large(file_size):
        await show_temp(update, context, TEXT[lang]["error_file_too_large"])
        return

    if not (is_supported_image(file_name) or is_supported_pdf(file_name)):
        await show_temp(update, context, TEXT[lang]["error_file_type"])
        return

    draft = drafts.get(user["id"]) or drafts.create(user["id"])
    log.info("DRAFT ACTIVE | id=%s", draft["id"])

    downloading_id = await show_temp(update, context, TEXT[lang]["file_downloading"])

    tg = await tg_file.get_file()
    local_path = os.path.join(
        STORAGE_TEMP,
        f"{user['id']}_{datetime.now().timestamp()}_{file_name}"
    )
    await tg.download_to_drive(local_path)

    await delete_temp(update, context, downloading_id)

    file_type = "pdf" if is_supported_pdf(file_name) else "image"

    draft_items.add(
        draft_id=draft["id"],
        file_path=local_path,
        file_type=file_type,
        size_bytes=file_size,
    )

    count = len(draft_items.list(draft["id"]))
    log.info("DRAFT ADD | items=%s", count)

    old_temp_id = context.user_data.pop("file_added_temp_id", None)
    if old_temp_id:
        await delete_temp(update, context, old_temp_id)

    # показать новое
    temp_id = await show_temp(
        update,
        context,
        TEXT[lang]["file_added_temp"].format(count=count),
    )

    context.user_data["file_added_temp_id"] = temp_id


# ===================== TEXT HANDLER =====================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = users.get_or_create(update.effective_user.id)
    lang = get_lang(user)
    text = update.message.text.strip()

    log.info("TEXT | user=%s | text='%s'", user["id"], text)

    rename_id = context.user_data.get("rename_file_id")
    if rename_id:
        files.rename(rename_id, user["id"], text)
        context.user_data.pop("rename_file_id", None)

        await show_ui(
            update,
            context,
            TEXT[lang]["file_renamed"],
            reply_markup=main_menu(lang),
            force_new=True,
        )
        return

    draft = drafts.get(user["id"])

    if not draft:
        await bump_ui(update, context)
        return

    items = draft_items.list(draft["id"])

    if not items:
        await show_ui(
            update,
            context,
            TEXT[lang]["draft_empty"],
            reply_markup=main_menu(lang),
        )
        return

    name = text or auto_name()
    stored_name = f"{int(datetime.now().timestamp())}.pdf"
    output_path = os.path.join(STORAGE_PDF, stored_name)

    temp_id = context.user_data.pop("file_added_temp_id", None)
    if temp_id:
        await delete_temp(update, context, temp_id)

    log.info("PDF BUILD | items=%s | name=%s", len(items), name)

    building_id = await show_temp(
        update,
        context,
        TEXT[lang]["pdf_building"],
    )

    PDFService.build_pdf(
        items=items,
        output_path=output_path,
        page_format=draft["page_format"],
    )

    files.create(
        user_id=user["id"],
        original_name=name,
        stored_name=stored_name,
        file_type="pdf",
        page_format=draft["page_format"],
        size_bytes=os.path.getsize(output_path),
    )

    drafts.delete(user["id"])
    log.info("DRAFT CLOSED")

    await delete_temp(update, context, building_id)

    sending_id = await show_temp(
        update,
        context,
        TEXT[lang]["pdf_sending"],
    )

    await update.message.reply_document(
        document=open(output_path, "rb"),
        filename=f"{name}.pdf",
    )

    await delete_temp(update, context, sending_id)

    await show_ui(
        update,
        context,
        TEXT[lang]["pdf_created"],
        reply_markup=main_menu(lang),
        force_new=True,
    )


# ===================== CALLBACKS =====================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    context.user_data["ui_message_id"] = q.message.message_id

    user = users.get_or_create(q.from_user.id)
    lang = get_lang(user)
    data = q.data

    log.info("CALLBACK | user=%s | data=%s", user["id"], data)

    if data == "back_menu":
        await show_ui(
            update,
            context,
            TEXT[lang]["menu_title"],
            reply_markup=main_menu(lang),
        )
        return

    if data == "settings":
        await show_ui(
            update,
            context,
            TEXT[lang]["choose_lang"],
            reply_markup=language_kb(),
        )
        return

    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        users.set_language(user["telegram_id"], new_lang)

        await show_ui(
            update,
            context,
            TEXT[new_lang]["welcome"],
            reply_markup=main_menu(new_lang),
        )
        return

    if data == "files":
        total = files.count(user["id"])

        if total == 0:
            await show_ui(
                update,
                context,
                TEXT[lang]["no_files"],
                reply_markup=main_menu(lang),
            )
            return

        PAGE_SIZE = 5
        page = 1
        pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        items = files.list_paginated(user["id"], page)

        start = (page - 1) * PAGE_SIZE + 1
        end = min(page * PAGE_SIZE, total)

        title = f"{TEXT[lang]['files_title']} ({start}–{end} из {total})"

        await show_ui(
            update,
            context,
            title,
            reply_markup=files_list_kb(items, lang, page, pages),
        )
        return

    if data.startswith("files_page_"):
        page = int(data.split("_")[-1])
        total = files.count(user["id"])

        if total == 0:
            await show_ui(
                update,
                context,
                TEXT[lang]["no_files"],
                reply_markup=main_menu(lang),
            )
            return

        PAGE_SIZE = 5
        pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        items = files.list_paginated(user["id"], page)

        start = (page - 1) * PAGE_SIZE + 1
        end = min(page * PAGE_SIZE, total)

        title = f"{TEXT[lang]['files_title']} ({start}–{end} из {total})"

        await show_ui(
            update,
            context,
            title,
            reply_markup=files_list_kb(items, lang, page, pages),
        )
        return

    if data.startswith("file_"):
        fid = int(data.split("_")[1])
        file = files.get(fid, user["id"])

        if not file:
            await show_ui(
                update,
                context,
                TEXT[lang]["error_file_not_found"],
                reply_markup=main_menu(lang),
            )
            return

        await show_ui(
            update,
            context,
            f"📄 {file['original_name']}",
            reply_markup=file_actions_kb(fid, lang),
        )
        return

    if data.startswith("rename_"):
        fid = int(data.split("_")[1])
        context.user_data["rename_file_id"] = fid

        await show_ui(
            update,
            context,
            TEXT[lang]["rename_prompt"],
        )
        return

    if data.startswith("download_"):
        fid = int(data.split("_")[1])
        file = files.get(fid, user["id"])

        await show_temp(update, context, TEXT[lang]["pdf_sending"])

        await q.message.reply_document(
            document=open(os.path.join(STORAGE_PDF, file["stored_name"]), "rb"),
            filename=f"{file['original_name']}.pdf",
        )

        await reset_ui(update, context)

        await show_ui(
            update,
            context,
            TEXT[lang]["menu_title"],
            reply_markup=main_menu(lang),
        )
        return

    if data.startswith("delete_"):
        fid = int(data.split("_")[1])
        files.delete(fid, user["id"])

        await show_ui(
            update,
            context,
            TEXT[lang]["file_deleted"],
            reply_markup=main_menu(lang),
            force_new=True,
        )
        return


# ===================== MAIN =====================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("🚀 BOT STARTED (single-message UI)")
    app.run_polling()


if __name__ == "__main__":
    main()
