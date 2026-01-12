from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest


def _get_chat_id(update: Update) -> int:
    """
    Универсально получаем chat_id
    (работает и для Message, и для CallbackQuery)
    """
    if update.effective_chat:
        return update.effective_chat.id
    raise RuntimeError("Cannot determine chat_id")


async def update_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None
):
    """
    Обновляет существующее UI-сообщение.
    Если редактирование невозможно — создаёт новое.
    """
    chat_id = _get_chat_id(update)
    msg_id = context.user_data.get("ui_message_id")

    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup,
            )
            return

        except BadRequest as e:
            # ❗ Сообщение не изменилось — это нормально
            if "message is not modified" in str(e).lower():
                return

            # ❗ Сообщение удалено / устарело — создадим новое
        except Exception:
            pass

    # 🔁 fallback — создаём новое UI-сообщение
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )
    context.user_data["ui_message_id"] = msg.message_id


async def reset_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None
):
    """
    Полностью удаляет старое UI-сообщение и создаёт новое.
    Использовать после завершённых действий
    (Create / Download / Merge / Rename).
    """
    chat_id = _get_chat_id(update)
    msg_id = context.user_data.get("ui_message_id")

    if msg_id:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=msg_id,
            )
        except Exception:
            pass

        context.user_data.pop("ui_message_id", None)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )
    context.user_data["ui_message_id"] = msg.message_id
