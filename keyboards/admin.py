from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import date
from calendar import monthcalendar

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записи на сегодня", callback_data="admin:today"))
    builder.row(InlineKeyboardButton(text="📆 Записи на месяц", callback_data="admin:month_bookings"))
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"))
    builder.row(InlineKeyboardButton(text="🗓 Расписание записи", callback_data="admin:schedule"))
    builder.row(InlineKeyboardButton(text="💅 Управление услугами", callback_data="admin:services"))
    builder.row(InlineKeyboardButton(text="📝 Управление контентом", callback_data="admin:content"))
    builder.row(InlineKeyboardButton(text="🚫 Чёрный список", callback_data="admin:blacklist"))
    builder.row(InlineKeyboardButton(text="📂 Архив клиента", callback_data="admin:user_archive"))
    builder.row(InlineKeyboardButton(text="💾 Резервные копии", callback_data="admin:backup"))
    builder.row(InlineKeyboardButton(text="🚪 Выйти из админки", callback_data="admin:exit"))
    return builder.as_markup()


def admin_month_nav_kb(prefix: str, year: int, month: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    builder.row(
        InlineKeyboardButton(text=f"« {MONTH_NAMES[prev_m]}", callback_data=f"{prefix}:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES[next_m]} »", callback_data=f"{prefix}:{next_y}:{next_m}"),
    )
    builder.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
    return builder.as_markup()


def admin_schedule_calendar_kb(year: int, month: int, open_days: set) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"🗓 {MONTH_NAMES[month]} {year}", callback_data="ignore"))

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
                mark = "🟢" if d in open_days else "🔴"
                row.append(InlineKeyboardButton(
                    text=f"{mark}{day}",
                    callback_data=f"admin_day:{d.isoformat()}"
                ))
        builder.row(*row)

    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    builder.row(
        InlineKeyboardButton(text=f"« {MONTH_NAMES[prev_m]}", callback_data=f"admin_cal:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES[next_m]} »", callback_data=f"admin_cal:{next_y}:{next_m}"),
    )
    builder.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
    return builder.as_markup()


def admin_day_actions_kb(day_iso: str, is_open: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🕐 Выбрать слоты времени", callback_data=f"admin_slots:{day_iso}"))
    if is_open:
        builder.row(InlineKeyboardButton(text="🔴 Закрыть день", callback_data=f"admin_close:{day_iso}"))
    builder.row(InlineKeyboardButton(text="« К календарю", callback_data="admin:schedule"))
    return builder.as_markup()


def admin_slots_kb(day_iso: str, selected) -> InlineKeyboardMarkup:
    """selected: list of dicts {time, surcharge} or list of time strings"""
    from services.schedule_service import all_possible_slots, normalize_slots
    builder = InlineKeyboardBuilder()
    norm = normalize_slots(selected if selected else [])
    by_time = {s["time"]: s for s in norm}
    row = []
    for slot in all_possible_slots():
        if slot in by_time:
            sur = by_time[slot]["surcharge"]
            if sur >= 300:
                mark = "🔥"
            elif sur >= 100:
                mark = "⭐"
            else:
                mark = "✅"
        else:
            mark = "⬜"
        row.append(InlineKeyboardButton(text=f"{mark}{slot}", callback_data=f"admin_tgslot:{day_iso}:{slot}"))
        if len(row) == 4:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="💰 Доплата к слоту", callback_data=f"admin_sursel:{day_iso}"))
    builder.row(InlineKeyboardButton(text="💾 Готово", callback_data=f"admin_day:{day_iso}"))
    return builder.as_markup()


def admin_surcharge_pick_slot_kb(day_iso: str, selected) -> InlineKeyboardMarkup:
    from services.schedule_service import normalize_slots
    builder = InlineKeyboardBuilder()
    for s in normalize_slots(selected or []):
        builder.row(InlineKeyboardButton(
            text=f"{s['time']} (сейчас +{int(s['surcharge'])}₽)",
            callback_data=f"admin_surt:{day_iso}:{s['time']}"
        ))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data=f"admin_slots:{day_iso}"))
    return builder.as_markup()


def admin_surcharge_amount_kb(day_iso: str, slot: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for amount in (0, 100, 200, 300, 500):
        builder.row(InlineKeyboardButton(
            text=f"+{amount} ₽" if amount else "Без доплаты",
            callback_data=f"admin_surset:{day_iso}:{slot}:{amount}"
        ))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data=f"admin_sursel:{day_iso}"))
    return builder.as_markup()


def admin_services_kb(services: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in services:
        status = "✅" if s.is_active else "❌"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {s.name}",
                callback_data=f"admin_service:{s.id}"
            )
        )
    builder.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
    return builder.as_markup()


def admin_service_actions_kb(service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚙️ Параметры / шаги", callback_data=f"admin_svc_params:{service_id}"))
    builder.row(InlineKeyboardButton(text="⏱ Базовое время", callback_data=f"admin_svc_dur:{service_id}"))
    builder.row(InlineKeyboardButton(text="💰 Базовая цена", callback_data=f"admin_svc_price:{service_id}"))
    builder.row(InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_svc_name:{service_id}"))
    builder.row(InlineKeyboardButton(text="❌ Деактивировать", callback_data=f"admin_delete_service:{service_id}"))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data="admin:services"))
    return builder.as_markup()


def admin_params_list_kb(params: list, service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in params:
        builder.row(
            InlineKeyboardButton(
                text=f"{p.option_text[:40]} ({p.duration_modifier:+d}м / {int(p.price_modifier):+d}₽)",
                callback_data=f"admin_param:{p.id}"
            )
        )
    builder.row(InlineKeyboardButton(text="« К услугам", callback_data="admin:services"))
    return builder.as_markup()


def admin_param_edit_kb(param_id: int, service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить текст кнопки", callback_data=f"admin_pe_text:{param_id}"))
    builder.row(InlineKeyboardButton(text="⏱ Изменить время (+/- мин)", callback_data=f"admin_pe_dur:{param_id}"))
    builder.row(InlineKeyboardButton(text="💰 Изменить цену (+/- ₽)", callback_data=f"admin_pe_price:{param_id}"))
    builder.row(InlineKeyboardButton(text="« К параметрам", callback_data=f"admin_svc_params:{service_id}"))
    return builder.as_markup()


def admin_content_kb(blocks: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for b in blocks:
        media = " 📷" if getattr(b, "media_file_id", None) else ""
        builder.row(InlineKeyboardButton(
            text=f"{b.title}{media}",
            callback_data=f"admin_content:{b.code}"
        ))
    builder.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
    return builder.as_markup()


def admin_content_item_kb(code: str, has_media: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"admin_content_edit:{code}"))
    builder.row(InlineKeyboardButton(text="📷 Добавить / заменить фото", callback_data=f"admin_content_media:{code}"))
    if has_media:
        builder.row(InlineKeyboardButton(text="🗑 Убрать фото", callback_data=f"admin_content_delmedia:{code}"))
        builder.row(InlineKeyboardButton(text="👁 Посмотреть как у клиента", callback_data=f"admin_content_preview:{code}"))
    builder.row(InlineKeyboardButton(text="« К списку", callback_data="admin:content"))
    return builder.as_markup()


def admin_backup_kb(backups: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💾 Создать копию сейчас", callback_data="admin:backup_create"))
    for b in backups[:10]:
        name = b.stem.replace("bot_", "")
        builder.row(InlineKeyboardButton(
            text=f"📦 {name}",
            callback_data=f"admin_restore:{b.name}"
        ))
    builder.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
    return builder.as_markup()


def admin_booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"admin_cancel_b:{booking_id}"))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data="admin:today"))
    return builder.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
    return builder.as_markup()
