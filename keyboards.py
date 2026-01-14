from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Iterable
from texts import TEXT


# ===================== MAIN MENU =====================

def main_menu(lang: str):
    t = TEXT[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["btn_files"], callback_data="files")],
        [InlineKeyboardButton(t["btn_settings"], callback_data="settings")],
    ])


# ===================== FILES LIST (PAGINATED) =====================

def files_list_kb(
    files: Iterable[dict],
    lang: str,
    page: int,
    total_pages: int
):
    t = TEXT[lang]
    buttons = []

    for f in files:
        buttons.append([
            InlineKeyboardButton(
                f"📄 {f['original_name']}",
                callback_data=f"file_{f['id']}"
            )
        ])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(t["btn_prev"], callback_data=f"files_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(t["btn_next"], callback_data=f"files_page_{page+1}"))

    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(t["btn_back"], callback_data="back_menu")
    ])

    return InlineKeyboardMarkup(buttons)


# ===================== FILE ACTIONS =====================

def file_actions_kb(file_id: int, lang: str):
    t = TEXT[lang]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t["btn_download"], callback_data=f"download_{file_id}"),
            InlineKeyboardButton(t["btn_rename"], callback_data=f"rename_{file_id}"),
        ],
        [
            InlineKeyboardButton(t["btn_delete"], callback_data=f"delete_{file_id}")
        ],
        [
            InlineKeyboardButton(t["btn_back"], callback_data="files")
        ]
    ])

def language_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇺🇿 O‘zbek", callback_data="lang_uz"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])



