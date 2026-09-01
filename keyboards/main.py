from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


BTN_BOOK = "💅 Записаться"
BTN_MANAGE = "📋 Управление записью"
BTN_INFO = "ℹ️ Доп. информация"


def main_reply_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_BOOK))
    builder.row(KeyboardButton(text=BTN_MANAGE))
    builder.row(KeyboardButton(text=BTN_INFO))
    return builder.as_markup(resize_keyboard=True)


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💅 Записаться", callback_data="menu:book"))
    builder.row(InlineKeyboardButton(text="📋 Управление записью", callback_data="menu:manage"))
    builder.row(InlineKeyboardButton(text="ℹ️ Дополнительная информация", callback_data="menu:info"))
    return builder.as_markup()


def info_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Прайс", callback_data="info:price_list"))
    builder.row(InlineKeyboardButton(text="📖 Правила", callback_data="info:rules"))
    builder.row(InlineKeyboardButton(text="📞 Мои каналы и сети", callback_data="info:socials"))
    builder.row(InlineKeyboardButton(text="👀 Для тех, кто идёт впервые", callback_data="info:first_time"))
    builder.row(InlineKeyboardButton(text="🐣 Для тех, кому нет 16 лет", callback_data="info:under_16"))
    builder.row(InlineKeyboardButton(text="🩹 Что я не делаю", callback_data="info:not_doing"))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data="menu:main"))
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="« В главное меню", callback_data="menu:main"))
    return builder.as_markup()


def back_to_info_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="« Назад", callback_data="menu:info"))
    return builder.as_markup()
