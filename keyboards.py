from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from texts import TEXT
from typing import Set, Iterable


# ===================== LANGUAGE =====================

def lang_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇺🇿 O‘zbek", callback_data="lang_uz"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])


# ===================== MAIN MENU =====================

def main_menu(lang: str):
    t = TEXT[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["btn_create"], callback_data="create")],
        [InlineKeyboardButton(t["btn_files"], callback_data="files")],
        [InlineKeyboardButton(t["btn_settings"], callback_data="settings")],
    ])


# ===================== COLLECT IMAGES =====================

def collect_kb(lang: str):
    t = TEXT[lang]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t["done"], callback_data="done"),
            InlineKeyboardButton(t["cancel"], callback_data="cancel"),
        ]
    ])


# ===================== FILES LIST =====================

def files_list_kb(files: Iterable[dict], lang: str):
    """
    Список файлов пользователя
    """
    t = TEXT[lang]
    buttons = []

    for f in files:
        buttons.append([
            InlineKeyboardButton(
                f"📄 {f['original_name']}",
                callback_data=f"file_{f['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(t["btn_create"], callback_data="create")
    ])
    buttons.append([
        InlineKeyboardButton(t["back_to_menu"], callback_data="back_menu")
    ])

    return InlineKeyboardMarkup(buttons)


# ===================== FILE ACTIONS =====================

def file_actions_kb(file_id: int, lang: str):
    """
    Действия над конкретным PDF
    """
    t = TEXT[lang]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t["download"], callback_data=f"download_{file_id}"),
            InlineKeyboardButton(t["rename"], callback_data=f"rename_{file_id}"),
        ],
        [
            InlineKeyboardButton(t["delete"], callback_data=f"delete_{file_id}")
        ],
        [
            InlineKeyboardButton(t["merge"], callback_data="merge_start")
        ],
        [
            InlineKeyboardButton(t["back_to_menu"], callback_data="files")
        ]
    ])


# ===================== MERGE FILES =====================

def merge_files_kb(
    files: Iterable[dict],
    selected_ids: Set[int],
    lang: str
):
    """
    UI выбора PDF для объединения
    """
    t = TEXT[lang]
    buttons = []

    for f in files:
        fid = f["id"]
        mark = "✅" if fid in selected_ids else "⬜"

        buttons.append([
            InlineKeyboardButton(
                f"{mark} {f['original_name']}",
                callback_data=f"merge_toggle_{fid}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(t["merge_confirm"], callback_data="merge_done"),
        InlineKeyboardButton(t["cancel"], callback_data="back_menu"),
    ])

    return InlineKeyboardMarkup(buttons)
