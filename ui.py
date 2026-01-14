import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

log = logging.getLogger("ui")


# ===================== CORE HELPERS =====================

def get_chat_id(update: Update) -> int:
    if not update.effective_chat:
        raise RuntimeError("UI: update has no effective_chat")
    return update.effective_chat.id


def get_ui_message_id(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get("ui_message_id")


def set_ui_message_id(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    context.user_data["ui_message_id"] = message_id


def get_last_ui_state(context: ContextTypes.DEFAULT_TYPE):
    return (
        context.user_data.get("ui_last_text"),
        context.user_data.get("ui_last_markup"),
        context.user_data.get("ui_last_markup_sig"),
    )


def set_last_ui_state(context: ContextTypes.DEFAULT_TYPE, text, markup, markup_sig):
    context.user_data["ui_last_text"] = text
    context.user_data["ui_last_markup"] = markup
    context.user_data["ui_last_markup_sig"] = markup_sig


# ===================== TEMP MESSAGES =====================

async def show_temp(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> int:
    """
    Показывает ВРЕМЕННОЕ сообщение (бот занят, создается PDF и т.д.)

    ❗ Правила:
    - НЕ сохраняется в ui_message_id
    - НЕ участвует в debounce
    - НЕ редактируется
    - ДОЛЖНО быть удалено вручную
    """

    chat_id = get_chat_id(update)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
    )

    log.info("TEMP.show | message_id=%s | text=%r", msg.message_id, text)
    return msg.message_id


async def delete_temp(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message_id: int | None,
):
    """
    Удаляет временное сообщение.

    ❗ Безопасно:
    - если message_id=None
    - если сообщение уже удалено
    """

    if not message_id:
        return

    chat_id = get_chat_id(update)

    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )
        log.info("TEMP.delete | message_id=%s", message_id)

    except Exception as e:
        log.warning(
            "TEMP.delete failed | message_id=%s | %s",
            message_id,
            e,
        )



# ===================== SINGLE MESSAGE UI =====================

async def show_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    force_new: bool = False,
):
    chat_id = get_chat_id(update)
    ui_message_id = get_ui_message_id(context)
    can_edit = (
        update.callback_query is not None
        and ui_message_id is not None
        and not force_new
    )

    last_text, last_markup, last_sig = get_last_ui_state(context)

    # сериализуем клавиатуру для корректного сравнения
    markup_sig = repr(reply_markup) if reply_markup else None

    log.info(
        "UI.show | can_edit=%s | force_new=%s | ui_message_id=%s",
        can_edit,
        force_new,
        ui_message_id,
    )

    # ===================== GLOBAL DEBOUNCE =====================
    if (
        ui_message_id
        and can_edit
        and not force_new
        and last_text == text
        and last_markup == markup_sig
    ):
        log.info("UI.debounce | skip render (same text & markup)")
        return

    # ===================== EDIT PATH =====================
    if ui_message_id and can_edit and not force_new:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=ui_message_id,
                text=text,
                reply_markup=reply_markup,
            )

            set_last_ui_state(context, text, reply_markup, markup_sig)
            log.info("UI.edit OK (message_id=%s)", ui_message_id)
            return

        except BadRequest as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                log.info("UI.edit skipped (telegram says not modified)")
                set_last_ui_state(context, text, reply_markup, markup_sig)
                return

            log.warning("UI.edit failed (%s), fallback to send", e)

        except Exception as e:
            log.exception("UI.edit unexpected error: %s", e)

    # ===================== SEND PATH =====================
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )

    set_ui_message_id(context, msg.message_id)
    set_last_ui_state(context, text, reply_markup, markup_sig)
    log.info("UI.send OK (new message_id=%s)", msg.message_id)

# ===================== HELPER =====================
async def bump_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Перемещает UI в конец чата БЕЗ изменения текста.
    Использовать при idle user input.
    """
    chat_id = get_chat_id(update)
    ui_message_id = get_ui_message_id(context)

    if not ui_message_id:
        return

    try:
        await context.bot.delete_message(chat_id, ui_message_id)
    except Exception:
        pass

    last_text, last_markup, _ = get_last_ui_state(context)

    if not last_text:
        return

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=last_text,
        reply_markup=last_markup,
    )

    set_ui_message_id(context, msg.message_id)
    log.info("UI.bump | moved UI to bottom (message_id=%s)", msg.message_id)


# ===================== HARD RESET (RARE) =====================

async def reset_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Полный сброс UI.
    Использовать ТОЛЬКО при /start или logout.
    """

    chat_id = get_chat_id(update)
    ui_message_id = get_ui_message_id(context)

    log.warning("UI.reset called (message_id=%s)", ui_message_id)

    if ui_message_id:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=ui_message_id,
            )
            log.info("UI.reset deleted message %s", ui_message_id)
        except Exception as e:
            log.warning("UI.reset delete failed: %s", e)

    context.user_data.pop("ui_message_id", None)
    context.user_data.pop("ui_last_text", None)
    context.user_data.pop("ui_last_markup", None)
    context.user_data.pop("ui_last_markup_sig", None)
