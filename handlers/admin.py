from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import date, datetime
from pathlib import Path

from config import settings, TZ, DATA_DIR
from states.booking_states import AdminStates
from keyboards.admin import (
    admin_main_kb, admin_month_nav_kb, admin_schedule_calendar_kb,
    admin_day_actions_kb, admin_slots_kb, admin_services_kb,
    admin_service_actions_kb, admin_params_list_kb, admin_param_edit_kb,
    admin_content_kb, admin_content_item_kb, admin_backup_kb, admin_booking_actions_kb, admin_back_kb,
    admin_surcharge_pick_slot_kb, admin_surcharge_amount_kb,
    MONTH_NAMES
)
from keyboards.main import main_menu_kb, main_reply_kb
from database.database import async_session
from database.models import Service, ServiceParameter, Booking
from services.schedule_service import ScheduleService, normalize_slots, slot_times
from services.content_service import ContentService
from services.booking_service import BookingService
from services.backup_service import create_backup, list_backups, restore_backup, BACKUP_DIR
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from utils.formatting import format_price, format_duration, format_selected_params

router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    await state.clear()
    await message.answer("🔧 Панель администратора", reply_markup=admin_main_kb())


@router.callback_query(F.data == "admin:main")
async def admin_main(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("🔧 Панель администратора", reply_markup=admin_main_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:exit")
async def admin_exit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Вышла из панели администратора.")
    await callback.message.answer("👇 Меню снова внизу:", reply_markup=main_reply_kb())
    await callback.message.answer("Разделы:", reply_markup=main_menu_kb())
    await callback.answer()


# === Записи на сегодня ===
@router.callback_query(F.data == "admin:today")
async def admin_today(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    today = datetime.now(TZ).date()
    async with async_session() as session:
        result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.service), selectinload(Booking.user))
            .where(
                Booking.booking_date == today,
                Booking.status.in_(["confirmed", "pending_photo", "pending_payment", "completed"])
            )
            .order_by(Booking.start_time)
        )
        bookings = list(result.scalars().all())

    if not bookings:
        text = f"📅 На сегодня ({today.strftime('%d-%m-%Y')}) записей нет."
        await callback.message.edit_text(text, reply_markup=admin_back_kb())
    else:
        lines = [f"<b>📅 Записи на {today.strftime('%d-%m-%Y')}</b>\n"]
        builder_rows = []
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        kb = InlineKeyboardBuilder()
        for b in bookings:
            contact = b.user.phone or (b.selected_params or {}).get("contact") or "—"
            params = format_selected_params(b.selected_params)
            params_s = f"\n{params}" if params else ""
            lines.append(
                f"• {b.start_time.strftime('%H:%M')}–{b.end_time.strftime('%H:%M')} "
                f"| {b.service.name} | {format_price(b.total_price)}\n"
                f"  👤 {b.user.full_name or b.user.username or b.user.telegram_id}\n"
                f"  📱 {contact}{params_s}"
            )
            kb.row(InlineKeyboardButton(
                text=f"❌ {b.start_time.strftime('%H:%M')} {b.service.name[:20]}",
                callback_data=f"admin_cancel_b:{b.id}"
            ))
        kb.row(InlineKeyboardButton(text="« В админ-меню", callback_data="admin:main"))
        text = "\n".join(lines)
        await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cancel_b:"))
async def admin_cancel_booking(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    bid = int(callback.data.split(":")[1])
    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
        if not booking or booking.status == "cancelled":
            await callback.answer("Запись не найдена или уже отменена", show_alert=True)
            return
        user_tg = booking.user.telegram_id
        info = (
            f"{booking.service.name}, "
            f"{booking.booking_date.strftime('%d-%m-%Y')} "
            f"{booking.start_time.strftime('%H:%M')}"
        )
        await svc.cancel_booking(bid)

    try:
        await bot.send_message(
            user_tg,
            f"❌ Твоя запись отменена мастером:\n{info}\n\n"
            f"Если есть вопросы — напиши {settings.MASTER_USERNAME}."
        )
    except Exception:
        pass

    await callback.answer("Запись отменена")
    await admin_today(callback)


# === Записи на месяц ===
@router.callback_query(F.data == "admin:month_bookings")
async def admin_month_bookings_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    now = datetime.now(TZ)
    await _show_month_bookings(callback, now.year, now.month)


@router.callback_query(F.data.startswith("admin_mb:"))
async def admin_month_bookings_nav(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    _, y, m = callback.data.split(":")
    await _show_month_bookings(callback, int(y), int(m))


async def _show_month_bookings(callback: CallbackQuery, year: int, month: int):
    async with async_session() as session:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.service), selectinload(Booking.user))
            .where(
                Booking.booking_date >= start,
                Booking.booking_date < end,
                Booking.status.in_(["confirmed", "pending_photo", "pending_payment", "completed"])
            )
            .order_by(Booking.booking_date, Booking.start_time)
        )
        bookings = list(result.scalars().all())

    if not bookings:
        text = f"📆 Записей за {MONTH_NAMES[month]} {year} нет."
    else:
        lines = [f"<b>📆 Записи за {MONTH_NAMES[month]} {year}</b>\n"]
        current_day = None
        for b in bookings:
            if b.booking_date != current_day:
                current_day = b.booking_date
                lines.append(f"\n<b>{current_day.strftime('%d-%m')}</b>")
            contact = b.user.phone or (b.selected_params or {}).get("contact") or ""
            status_mark = " ✅" if b.status == "completed" else ""
            contact_s = f" · 📱 {contact}" if contact else ""
            params = format_selected_params(b.selected_params)
            params_s = f"\n    {params.replace(chr(10), chr(10) + '    ')}" if params else ""
            lines.append(
                f"  {b.start_time.strftime('%H:%M')} {b.service.name} — {format_price(b.total_price)}{status_mark}{contact_s}{params_s}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=admin_month_nav_kb("admin_mb", year, month),
        parse_mode="HTML"
    )
    await callback.answer()


# === Статистика ===
@router.callback_query(F.data == "admin:stats")
async def admin_stats_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    now = datetime.now(TZ)
    await _show_stats(callback, now.year, now.month)


@router.callback_query(F.data.startswith("admin_st:"))
async def admin_stats_nav(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    _, y, m = callback.data.split(":")
    await _show_stats(callback, int(y), int(m))


async def _show_stats(callback: CallbackQuery, year: int, month: int):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    async with async_session() as session:
        result = await session.execute(
            select(
                func.count(Booking.id),
                func.coalesce(func.sum(Booking.total_price), 0)
            ).where(
                Booking.booking_date >= start,
                Booking.booking_date < end,
                Booking.status.in_(["confirmed", "completed", "pending_photo"])
            )
        )
        count, revenue = result.one()

    text = (
        f"<b>📊 Статистика за {MONTH_NAMES[month]} {year}</b>\n\n"
        f"Клиентов: {count}\n"
        f"Выручка: {format_price(float(revenue))}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_month_nav_kb("admin_st", year, month),
        parse_mode="HTML"
    )
    await callback.answer()


# === Расписание ===
@router.callback_query(F.data == "admin:schedule")
async def admin_schedule(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    now = datetime.now(TZ)
    await _show_schedule_calendar(callback, now.year, now.month)


@router.callback_query(F.data.startswith("admin_cal:"))
async def admin_cal_nav(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    _, y, m = callback.data.split(":")
    await _show_schedule_calendar(callback, int(y), int(m))


async def _show_schedule_calendar(callback: CallbackQuery, year: int, month: int):
    async with async_session() as session:
        schedule = ScheduleService(session)
        open_days = await schedule.get_open_days(year, month)

    await callback.message.edit_text(
        "🗓 Расписание записи\n"
        "🟢 — день открыт (есть слоты)\n"
        "🔴 — день закрыт\n\n"
        "Нажми на день, чтобы выбрать слоты:",
        reply_markup=admin_schedule_calendar_kb(year, month, open_days)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_day:"))
async def admin_day_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    day_iso = callback.data.split(":", 1)[1]
    day = date.fromisoformat(day_iso)

    async with async_session() as session:
        schedule = ScheduleService(session)
        is_open = await schedule.is_day_open(day)
        record = await schedule.get_day_record(day)

    status = "открыт 🟢" if is_open else "закрыт 🔴"
    slots_text = ""
    if record and record.available_slots:
        parts = []
        for item in record.available_slots:
            if isinstance(item, dict):
                t = str(item.get("time", ""))
                sur = float(item.get("surcharge") or 0)
                parts.append(f"{t}(+{int(sur)})" if sur else t)
            else:
                parts.append(str(item))
        if parts:
            slots_text = "\nСлоты: " + ", ".join(parts)

    await callback.message.edit_text(
        f"📅 {day.strftime('%d-%m-%Y')} — <b>{status}</b>{slots_text}",
        reply_markup=admin_day_actions_kb(day_iso, is_open),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_close:"))
async def admin_close_day(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    day_iso = callback.data.split(":", 1)[1]
    day = date.fromisoformat(day_iso)
    async with async_session() as session:
        schedule = ScheduleService(session)
        await schedule.set_day_open(day, False)
    await callback.answer("День закрыт")
    await _show_schedule_calendar(callback, day.year, day.month)


@router.callback_query(F.data.startswith("admin_slots:"))
async def admin_slots_edit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    day_iso = callback.data.split(":", 1)[1]
    day = date.fromisoformat(day_iso)

    async with async_session() as session:
        schedule = ScheduleService(session)
        record = await schedule.get_day_record(day)
        selected = record.available_slots if record and record.available_slots else []

    await callback.message.edit_text(
        f"🕐 Слоты на {day.strftime('%d-%m-%Y')}\n\n"
        "Нажми время: вкл/выкл.\n"
        "✅ обычный · ⭐ +100 · 🔥 +300\n"
        "«Доплата к слоту» — назначить наценку.\n"
        "07:00–22:00, шаг 30 мин.",
        reply_markup=admin_slots_kb(day_iso, selected)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_tgslot:"))
async def admin_toggle_slot(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    # admin_tgslot:YYYY-MM-DD:HH:MM
    parts = callback.data.split(":")
    day_iso = parts[1]
    slot = f"{parts[2]}:{parts[3]}"
    day = date.fromisoformat(day_iso)

    async with async_session() as session:
        schedule = ScheduleService(session)
        selected = await schedule.toggle_slot(day, slot)

    await callback.message.edit_reply_markup(reply_markup=admin_slots_kb(day_iso, selected))
    await callback.answer(f"{'✅' if slot in selected else '⬜'} {slot}")


# === Услуги ===
@router.callback_query(F.data == "admin:services")
async def admin_services(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    async with async_session() as session:
        result = await session.execute(select(Service).order_by(Service.sort_order))
        services = list(result.scalars().all())

    await callback.message.edit_text("💅 Управление услугами:", reply_markup=admin_services_kb(services))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_service:"))
async def admin_service_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(Service).where(Service.id == sid))
        service = result.scalar_one_or_none()

    if not service:
        await callback.answer("Не найдено", show_alert=True)
        return

    text = (
        f"<b>💅 {service.name}</b>\n\n"
        f"Код: {service.code}\n"
        f"Базовая длительность: {format_duration(service.base_duration_minutes)}\n"
        f"Базовая цена: {format_price(service.base_price)}\n"
        f"Сложный флоу: {'да' if service.has_complex_flow else 'нет'}\n"
        f"Активна: {'да' if service.is_active else 'нет'}"
    )
    await callback.message.edit_text(text, reply_markup=admin_service_actions_kb(service.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_service:"))
async def admin_delete_service(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(Service).where(Service.id == sid))
        service = result.scalar_one_or_none()
        if service:
            service.is_active = False
            await session.commit()
    await callback.answer("Услуга деактивирована")
    await admin_services(callback)


# === Параметры ===
@router.callback_query(F.data == "admin:params")
async def admin_params_menu(callback: CallbackQuery):
    # Перенаправление в управление услугами
    await admin_services(callback)


async def _show_params(callback: CallbackQuery, service_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(ServiceParameter)
            .where(ServiceParameter.service_id == service_id, ServiceParameter.is_active == True)
            .order_by(ServiceParameter.step_code, ServiceParameter.sort_order)
        )
        params = list(result.scalars().all())
        result2 = await session.execute(select(Service).where(Service.id == service_id))
        service = result2.scalar_one()

    if not params:
        msg = (
            f"⚙️ У «{service.name}» пока нет дополнительных шагов.\n"
            f"Можно изменить базовое время и цену в карточке услуги."
        )
    else:
        msg = f"⚙️ Параметры «{service.name}»:\nНажми на пункт, чтобы изменить:"
    await callback.message.edit_text(
        msg,
        reply_markup=admin_params_list_kb(params, service_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_svc_params:"))
async def admin_svc_params(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[1])
    await _show_params(callback, sid)


@router.callback_query(F.data.startswith("admin_param:"))
async def admin_param_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    pid = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(ServiceParameter).where(ServiceParameter.id == pid))
        param = result.scalar_one_or_none()

    if not param:
        await callback.answer("Не найдено", show_alert=True)
        return

    step_names = {
        "has_coating": "Покрытие",
        "nails_condition": "Состояние ногтей",
        "length": "Длина",
        "design": "Дизайн",
        "claws": "Когти",
        "communication": "Общение",
    }
    text = (
        f"<b>{param.option_text}</b>\n\n"
        f"Шаг: {step_names.get(param.step_code, param.step_code)}\n"
        f"Время: {param.duration_modifier:+d} мин\n"
        f"Цена: {int(param.price_modifier):+d} ₽\n"
        f"Требует фото: {'да' if param.requires_photo else 'нет'}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_param_edit_kb(param.id, param.service_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_pe_text:"))
async def admin_pe_text(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    pid = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_param_id=pid, edit_field="text")
    await callback.message.edit_text("✏️ Отправь новый текст кнопки:")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_pe_dur:"))
async def admin_pe_dur(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    pid = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_param_id=pid, edit_field="duration")
    await callback.message.edit_text("⏱ Отправь изменение времени в минутах (например: 20 или -10):")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_pe_price:"))
async def admin_pe_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    pid = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_param_id=pid, edit_field="price")
    await callback.message.edit_text("💰 Отправь изменение цены в рублях (например: 500 или -200):")
    await callback.answer()


@router.message(AdminStates.waiting_service_field)
async def admin_param_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    value = (message.text or "").strip()
    field = data.get("edit_field")

    # Чёрный список
    if field == "blacklist_add":
        await state.clear()
        remove = value.lower().startswith("убрать")
        digits = "".join(c for c in value if c.isdigit())
        if not digits:
            await message.answer("Нужен числовой Telegram ID", reply_markup=admin_main_kb())
            return
        tid = int(digits)
        async with async_session() as session:
            svc = BookingService(session)
            user = await svc.get_or_create_user(tid, None, None)
            user = await svc.set_blacklist(tid, not remove)
        if user:
            status = "в ЧС" if user.is_blacklisted else "убрана из ЧС"
            await message.answer(f"✅ Пользователь {tid}: {status}", reply_markup=admin_main_kb())
        else:
            await message.answer("Не найден", reply_markup=admin_main_kb())
        return

    # Архив клиента
    if field == "user_archive":
        await state.clear()
        digits = "".join(c for c in value if c.isdigit())
        if not digits:
            await message.answer("Нужен ID", reply_markup=admin_main_kb())
            return
        tid = int(digits)
        async with async_session() as session:
            svc = BookingService(session)
            from database.models import User
            from sqlalchemy import select as sa_select
            result = await session.execute(sa_select(User).where(User.telegram_id == tid))
            user = result.scalar_one_or_none()
            if not user:
                await message.answer("Клиент не найден", reply_markup=admin_main_kb())
                return
            archive = await svc.get_user_archive(user.id)
        lines = [f"<b>📂 Архив {user.full_name or tid}</b>\n📱 {user.phone or '—'}\nВизитов завершено: {user.completed_count}\nЧС: {'да' if user.is_blacklisted else 'нет'}\n"]
        for b in archive[:30]:
            lines.append(f"• {b.booking_date.strftime('%d-%m-%Y')} {b.start_time.strftime('%H:%M')} {b.service.name} — {int(b.total_price)}₽ [{b.status}]")
        await message.answer("\n".join(lines) or "Пусто", parse_mode="HTML", reply_markup=admin_main_kb())
        return

    # Медиа к контенту
    if field == "content_media":
        code = data.get("content_code")
        await state.clear()
        if message.photo:
            file_id = message.photo[-1].file_id
            mtype = "photo"
        elif message.video:
            file_id = message.video.file_id
            mtype = "video"
        else:
            await message.answer("Пришли фото или видео")
            return
        async with async_session() as session:
            svc = ContentService(session)
            ok = await svc.update_media(code, file_id, mtype)
            block = await svc.get_by_code(code)
        if ok and block:
            n = len(block.media_items or []) or (1 if block.media_file_id else 0)
            await message.answer(
                f"✅ Добавлено в «{block.title}» (всего медиа: {n}).\n"
                f"Можешь прислать ещё фото/видео или вернуться в меню.",
                reply_markup=admin_content_item_kb(code, True),
            )
            # остаёмся в режиме добавления медиа
            await state.set_state(AdminStates.waiting_service_field)
            await state.update_data(edit_field="content_media", content_code=code)
        else:
            await message.answer("Ошибка.", reply_markup=admin_main_kb())
        return

    # Редактирование полей самой услуги
    svc_id = data.get("edit_service_id")
    if svc_id:
        field = data.get("edit_field")
        async with async_session() as session:
            result = await session.execute(select(Service).where(Service.id == svc_id))
            service = result.scalar_one_or_none()
            if not service:
                await message.answer("Услуга не найдена", reply_markup=admin_main_kb())
                await state.clear()
                return
            if field == "base_duration":
                try:
                    service.base_duration_minutes = int(value)
                except ValueError:
                    await message.answer("Введи целое число (минуты)")
                    return
            elif field == "base_price":
                try:
                    service.base_price = float(value)
                except ValueError:
                    await message.answer("Введи число")
                    return
            elif field == "name":
                service.name = value
            await session.commit()
            await session.refresh(service)
        await state.clear()
        text = (
            f"✅ Сохранено.\n\n"
            f"<b>💅 {service.name}</b>\n\n"
            f"Базовая длительность: {format_duration(service.base_duration_minutes)}\n"
            f"Базовая цена: {format_price(service.base_price)}"
        )
        await message.answer(text, reply_markup=admin_service_actions_kb(service.id), parse_mode="HTML")
        return

    # Редактирование параметра
    pid = data.get("edit_param_id")
    field = data.get("edit_field")

    async with async_session() as session:
        result = await session.execute(select(ServiceParameter).where(ServiceParameter.id == pid))
        param = result.scalar_one_or_none()
        if not param:
            await message.answer("Параметр не найден", reply_markup=admin_main_kb())
            await state.clear()
            return

        if field == "text":
            param.option_text = value
        elif field == "duration":
            try:
                param.duration_modifier = int(value)
            except ValueError:
                await message.answer("Введи целое число")
                return
        elif field == "price":
            try:
                param.price_modifier = float(value)
            except ValueError:
                await message.answer("Введи число")
                return

        sid = param.service_id
        await session.commit()

        result = await session.execute(
            select(ServiceParameter)
            .where(ServiceParameter.service_id == sid, ServiceParameter.is_active == True)
            .order_by(ServiceParameter.step_code, ServiceParameter.sort_order)
        )
        params = list(result.scalars().all())
        result2 = await session.execute(select(Service).where(Service.id == sid))
        service = result2.scalar_one()

    await state.clear()
    await message.answer(
        f"✅ Сохранено.\n\n⚙️ Параметры «{service.name}»:",
        reply_markup=admin_params_list_kb(params, sid)
    )




# === Редактирование полей услуги ===
@router.callback_query(F.data.startswith("admin_svc_dur:"))
async def admin_svc_dur(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_service_id=sid, edit_field="base_duration")
    await callback.message.edit_text("⏱ Отправь базовую длительность в минутах (например: 60):")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_svc_price:"))
async def admin_svc_price(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_service_id=sid, edit_field="base_price")
    await callback.message.edit_text("💰 Отправь базовую цену в рублях (например: 1000):")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_svc_name:"))
async def admin_svc_name(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_service_id=sid, edit_field="name")
    await callback.message.edit_text("✏️ Отправь новое название услуги:")
    await callback.answer()


# === Контент ===
@router.callback_query(F.data == "admin:content")
async def admin_content(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    async with async_session() as session:
        from services.content_service import ensure_all_content
        await ensure_all_content(session)
        svc = ContentService(session)
        blocks = await svc.get_all()

    await callback.message.edit_text(
        "📝 <b>Все тексты бота</b>\n\n"
        "Выбери сообщение — можно изменить текст и добавить фото.\n"
        "📷 — уже есть фото.",
        reply_markup=admin_content_kb(blocks),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^admin_content:[\w]+$"))
async def admin_content_open(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    # не перехватывать admin_content_edit / media / delmedia / preview
    code = callback.data.split(":", 1)[1]
    if code in ("edit",) or callback.data.startswith("admin_content_edit"):
        return
    async with async_session() as session:
        svc = ContentService(session)
        block = await svc.get_by_code(code)
    if not block:
        await callback.answer("Не найдено", show_alert=True)
        return
    from services.content_service import ContentService as _CS
    # list_media не требует session на объекте block
    items = []
    if getattr(block, "media_items", None):
        items = list(block.media_items)
    elif block.media_file_id:
        items = [1]
    n_media = len(items)
    media_note = f"\n📷 Медиа: {n_media} шт." if n_media else "\nМедиа нет"
    preview = (block.text or "")[:800]
    await callback.message.edit_text(
        f"<b>{block.title}</b>\n<code>{block.code}</code>{media_note}\n\n"
        f"{preview}",
        reply_markup=admin_content_item_kb(code, bool(block.media_file_id)),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_content_edit:"))
async def admin_content_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    code = callback.data.split(":", 1)[1]
    async with async_session() as session:
        svc = ContentService(session)
        block = await svc.get_by_code(code)
    if not block:
        await callback.answer("Не найдено", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_content_text)
    await state.update_data(content_code=code)
    await callback.message.edit_text(
        f"✏️ Редактирование «{block.title}»\n\n"
        f"Текущий текст:\n{block.text}\n\n"
        f"Отправь новый текст (можно HTML: <b>жирный</b>).\n"
        f"Плейсхолдеры вроде {{summary}}, {{master}} — не удаляй, если они есть.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_content_media:"))
async def admin_content_media(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    code = callback.data.split(":", 1)[1]
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_field="content_media", content_code=code)
    await callback.message.edit_text(
        "📷 Пришли фото или видео (можно несколько подряд).\n"
        "Каждое вложение добавится к сообщению. Когда закончишь — «К списку»."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_content_delmedia:"))
async def admin_content_delmedia(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    code = callback.data.split(":", 1)[1]
    async with async_session() as session:
        svc = ContentService(session)
        await svc.clear_media(code)
        block = await svc.get_by_code(code)
    await callback.answer("Фото убрано")
    if block:
        await callback.message.edit_text(
            f"<b>{block.title}</b>\nФото нет\n\n{block.text[:800]}",
            reply_markup=admin_content_item_kb(code, False),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("admin_content_preview:"))
async def admin_content_preview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    code = callback.data.split(":", 1)[1]
    async with async_session() as session:
        svc = ContentService(session)
        block = await svc.get_by_code(code)
        media = svc.list_media(block) if block else []
    if not block:
        await callback.answer("Не найдено", show_alert=True)
        return
    try:
        text = block.text or "—"
        if not media:
            await callback.message.answer(text, parse_mode="HTML")
        elif len(media) == 1:
            m = media[0]
            if m.get("type") == "video":
                await callback.message.answer_video(m["file_id"], caption=text[:1024], parse_mode="HTML")
            else:
                await callback.message.answer_photo(m["file_id"], caption=text[:1024], parse_mode="HTML")
        else:
            from aiogram.types import InputMediaPhoto, InputMediaVideo
            group = []
            for i, m in enumerate(media[:10]):
                cap = text[:1024] if i == 0 else None
                if m.get("type") == "video":
                    group.append(InputMediaVideo(media=m["file_id"], caption=cap, parse_mode="HTML" if cap else None))
                else:
                    group.append(InputMediaPhoto(media=m["file_id"], caption=cap, parse_mode="HTML" if cap else None))
            await callback.message.answer_media_group(group)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return
    await callback.answer("Превью отправлено")


@router.message(AdminStates.waiting_content_text)
async def admin_content_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    code = data.get("content_code")
    new_text = message.html_text or message.text or ""

    async with async_session() as session:
        svc = ContentService(session)
        success = await svc.update_text(code, new_text)
        block = await svc.get_by_code(code)

    await state.clear()
    if success and block:
        await message.answer(
            f"✅ Текст «{block.title}» сохранён.",
            reply_markup=admin_content_item_kb(code, bool(block.media_file_id)),
        )
    else:
        await message.answer("Ошибка.", reply_markup=admin_main_kb())


# === Бэкапы ===
@router.callback_query(F.data == "admin:backup")
async def admin_backup_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    backups = list_backups()
    text = "💾 Резервные копии базы данных\n\n"
    if backups:
        text += "Нажми на копию, чтобы восстановить:"
    else:
        text += "Пока нет сохранённых копий."
    await callback.message.edit_text(text, reply_markup=admin_backup_kb(backups))
    await callback.answer()


@router.callback_query(F.data == "admin:backup_create")
async def admin_backup_create(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    path = create_backup()
    if path:
        await callback.answer(f"✅ Копия создана: {path.name}", show_alert=True)
    else:
        await callback.answer("База ещё не создана", show_alert=True)
    await admin_backup_menu(callback)


@router.callback_query(F.data.startswith("admin_restore:"))
async def admin_backup_restore(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    name = callback.data.split(":", 1)[1]
    path = BACKUP_DIR / name
    ok = restore_backup(path)
    if ok:
        await callback.answer("✅ База восстановлена. Перезапусти бота!", show_alert=True)
    else:
        await callback.answer("Ошибка восстановления", show_alert=True)
    await admin_backup_menu(callback)


# === Доплата к слотам ===
@router.callback_query(F.data.startswith("admin_sursel:"))
async def admin_sur_select(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    day_iso = callback.data.split(":", 1)[1]
    day = date.fromisoformat(day_iso)
    async with async_session() as session:
        schedule = ScheduleService(session)
        record = await schedule.get_day_record(day)
        selected = record.available_slots if record else []
    await callback.message.edit_text(
        "Выбери слот, для которого задать доплату:",
        reply_markup=admin_surcharge_pick_slot_kb(day_iso, selected)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_surt:"))
async def admin_sur_time(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    day_iso, slot = parts[1], f"{parts[2]}:{parts[3]}"
    await callback.message.edit_text(
        f"Доплата для {slot}:",
        reply_markup=admin_surcharge_amount_kb(day_iso, slot)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_surset:"))
async def admin_sur_set(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    day_iso = parts[1]
    slot = f"{parts[2]}:{parts[3]}"
    amount = float(parts[4])
    day = date.fromisoformat(day_iso)
    label = "🔥" if amount >= 300 else ("⭐" if amount >= 100 else "")
    async with async_session() as session:
        schedule = ScheduleService(session)
        await schedule.set_slot_surcharge(day, slot, amount, label)
        record = await schedule.get_day_record(day)
        selected = record.available_slots if record else []
    await callback.answer(f"{slot}: +{int(amount)}₽")
    await callback.message.edit_text(
        f"🕐 Слоты на {day.strftime('%d-%m-%Y')}\n🔥 +300 · ⭐ +100",
        reply_markup=admin_slots_kb(day_iso, selected)
    )



# === Чёрный список ===
@router.callback_query(F.data == "admin:blacklist")
async def admin_blacklist_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_field="blacklist_add")
    await callback.message.edit_text(
        "Чёрный список\n\n"
        "Отправь Telegram ID, чтобы добавить в ЧС.\n"
        "Или: убрать 123456789 — чтобы удалить из ЧС."
    )
    await callback.answer()


@router.callback_query(F.data == "admin:user_archive")
async def admin_user_archive_ask(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_service_field)
    await state.update_data(edit_field="user_archive")
    await callback.message.edit_text("Отправь Telegram ID клиентки для просмотра архива:")
    await callback.answer()


