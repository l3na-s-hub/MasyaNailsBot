from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional, Dict, Any
from datetime import date, time

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def services_kb(services: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in services:
        builder.row(InlineKeyboardButton(text=s.name, callback_data=f"service:{s.code}"))
    builder.row(InlineKeyboardButton(text="« Отмена", callback_data="menu:main"))
    return builder.as_markup()


def parameter_options_kb(step_code: str, options: list, prev_step: str | None = None, **_) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        price = getattr(opt, "price_modifier", 0) or 0
        dur = getattr(opt, "duration_modifier", 0) or 0
        extra = []
        if dur:
            extra.append(f"+{int(dur)} мин")
        if price:
            extra.append(f"+{int(price)} ₽")
        label = opt.option_text
        if extra:
            label = f"{label} ({', '.join(extra)})"
        # Telegram limit ~64 chars for button
        if len(label) > 60:
            label = label[:57] + "…"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"param:{step_code}:{opt.option_code}"))
    if prev_step:
        builder.row(InlineKeyboardButton(text="« Назад", callback_data=f"param_back:{prev_step}"))
    else:
        builder.row(InlineKeyboardButton(text="« К услугам", callback_data="menu:book"))
    return builder.as_markup()


def confirm_params_kb(duration: int, price: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"✅ Продолжить ({duration} мин / {int(price)} ₽)", callback_data="booking:confirm_params"))
    builder.row(InlineKeyboardButton(text="« Начать заново", callback_data="menu:book"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="menu:main"))
    return builder.as_markup()


def calendar_kb(year: int, month: int, open_days: set, surcharge_map: dict | None = None, selected: Optional[date] = None) -> InlineKeyboardMarkup:
    from calendar import monthcalendar
    surcharge_map = surcharge_map or {}
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"📅 {MONTH_NAMES[month]} {year}", callback_data="ignore"))
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[InlineKeyboardButton(text=d, callback_data="ignore") for d in days])
    cal = monthcalendar(year, month)
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                d = date(year, month, day)
                if d in open_days and d >= date.today():
                    sur = surcharge_map.get(d, 0)
                    if sur >= 300:
                        mark = "🔥"
                    elif sur >= 100:
                        mark = "⭐"
                    else:
                        mark = "🟢"
                    if selected == d:
                        mark = "✅"
                    row.append(InlineKeyboardButton(text=f"{mark}{day}", callback_data=f"date:{d.isoformat()}"))
                else:
                    row.append(InlineKeyboardButton(text=f"🔴{day}", callback_data="ignore"))
        builder.row(*row)
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    builder.row(
        InlineKeyboardButton(text=f"« {MONTH_NAMES[prev_m]}", callback_data=f"cal:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES[next_m]} »", callback_data=f"cal:{next_y}:{next_m}"),
    )
    builder.row(InlineKeyboardButton(text="« Отмена", callback_data="menu:main"))
    return builder.as_markup()


def time_slots_kb(slots: List[Dict[str, Any]], booking_date: date) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in slots:
        t = s["time"] if isinstance(s, dict) else s.strftime("%H:%M")
        sur = s.get("surcharge", 0) if isinstance(s, dict) else 0
        if sur >= 300:
            label = f"🔥 {t} (+{int(sur)} ₽)"
        elif sur >= 100:
            label = f"⭐ {t} (+{int(sur)} ₽)"
        elif sur > 0:
            label = f"🕐 {t} (+{int(sur)} ₽)"
        else:
            label = f"🕐 {t}"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"time:{booking_date.isoformat()}:{t}"))
    builder.row(InlineKeyboardButton(text="« Другая дата", callback_data="booking:choose_date"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="menu:main"))
    return builder.as_markup()


def final_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="booking:final_yes"))
    builder.row(InlineKeyboardButton(text="« Другое время", callback_data="booking:choose_date"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="menu:main"))
    return builder.as_markup()


def my_bookings_kb(bookings: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for b in bookings:
        text = f"📅 {b.booking_date.strftime('%d-%m-%Y')} {b.start_time.strftime('%H:%M')} — {b.service.name}"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"mybooking:{b.id}"))
    builder.row(InlineKeyboardButton(text="📂 Мой архив", callback_data="menu:archive"))
    builder.row(InlineKeyboardButton(text="« В главное меню", callback_data="menu:main"))
    return builder.as_markup()


def booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить / перенести", callback_data=f"cancel_booking:{booking_id}"))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data="menu:manage"))
    return builder.as_markup()


def confirm_cancel_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Да, отменить", callback_data=f"confirm_cancel:{booking_id}"))
    builder.row(InlineKeyboardButton(text="Нет, оставить", callback_data=f"mybooking:{booking_id}"))
    return builder.as_markup()
