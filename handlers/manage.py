from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime, date, timedelta

from keyboards.main import main_menu_kb, main_reply_kb
from keyboards.booking import my_bookings_kb, booking_actions_kb, confirm_cancel_kb, calendar_kb, time_slots_kb
from database.database import async_session
from services.booking_service import BookingService
from services.schedule_service import ScheduleService
from services.content_service import ContentService
from utils.formatting import format_booking_summary
from config import settings, TZ
from states.booking_states import BookingStates

router = Router(name="manage")

STEP_LABELS = {
    "procedure": "Процедура", "has_coating": "Текущее покрытие",
    "nails_condition": "Особенности покрытия", "coating_type": "Тип покрытия",
    "without_type": "Без покрытия", "length": "Длина", "claws": "Когти",
    "communication": "Общение", "design": "Дизайн",
}


def _params_from_booking(booking) -> str:
    params = booking.selected_params or {}
    texts = params.get("texts") if isinstance(params, dict) else None
    if not texts:
        return ""
    return "\n".join(f"• <b>{STEP_LABELS.get(s, s)}:</b> {t}" for s, t in texts.items())


async def manage_from_message(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        svc = BookingService(session)
        user = await svc.get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        bookings = await svc.get_user_active_bookings(user.id)
    if not bookings:
        await message.answer("У тебя нет активных записей.", reply_markup=main_reply_kb())
        await message.answer("Разделы:", reply_markup=main_menu_kb())
    else:
        await message.answer("Твои предстоящие записи:", reply_markup=my_bookings_kb(bookings))


@router.callback_query(F.data == "menu:manage")
async def manage_bookings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        svc = BookingService(session)
        user = await svc.get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
        bookings = await svc.get_user_active_bookings(user.id)
    if not bookings:
        await callback.message.edit_text("У тебя нет активных записей.")
        await callback.message.answer("👇", reply_markup=main_reply_kb())
        await callback.message.answer("Разделы:", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text("Твои предстоящие записи:", reply_markup=my_bookings_kb(bookings))
    await callback.answer()


@router.callback_query(F.data == "menu:archive")
async def client_archive(callback: CallbackQuery):
    async with async_session() as session:
        svc = BookingService(session)
        user = await svc.get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
        archive = await svc.get_user_archive(user.id)
    if not archive:
        await callback.answer("Архив пуст", show_alert=True)
        return
    lines = ["<b>📂 Твой архив записей</b>\n"]
    for b in archive[:20]:
        st = {"confirmed": "активна", "completed": "завершена", "cancelled": "отменена", "pending_payment": "ждёт оплату"}.get(b.status, b.status)
        lines.append(
            f"• {b.booking_date.strftime('%d-%m-%Y')} {b.start_time.strftime('%H:%M')} — {b.service.name}\n"
            f"  {int(b.total_price)} ₽ · {st}"
        )
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=my_bookings_kb([]))
    await callback.answer()


@router.callback_query(F.data.startswith("mybooking:"))
async def view_booking(callback: CallbackQuery):
    bid = int(callback.data.split(":")[1])
    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
    if not booking or booking.user.telegram_id != callback.from_user.id:
        await callback.answer("Не найдено", show_alert=True)
        return
    summary = format_booking_summary(
        booking.service.name, booking.total_duration_minutes, booking.total_price,
        booking_date=booking.booking_date, start_time=booking.start_time, end_time=booking.end_time,
        params_text=_params_from_booking(booking)
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📅 Перенести", callback_data=f"reschedule:{booking.id}"))
    kb.row(InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_booking:{booking.id}"))
    kb.row(InlineKeyboardButton(text="« Назад", callback_data="menu:manage"))
    await callback.message.edit_text(
        f"<b>Детали записи</b>\n\n{summary}\n\nСтатус: {booking.status}",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking:"))
async def ask_cancel(callback: CallbackQuery):
    bid = int(callback.data.split(":")[1])
    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
    if not booking:
        await callback.answer("Не найдено", show_alert=True)
        return
    hours = svc.hours_until(booking) if booking else 0
    async with async_session() as session:
        cs = ContentService(session)
        if hours < settings.CANCEL_FREE_HOURS:
            text = await cs.get_text("msg_cancel_late", master=settings.MASTER_USERNAME)
        else:
            text = await cs.get_text("msg_cancel_ok")
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Да, отменить", callback_data=f"confirm_cancel:{bid}"))
    if hours >= settings.CANCEL_FREE_HOURS:
        kb.row(InlineKeyboardButton(text="📅 Перенести на другую дату", callback_data=f"reschedule:{bid}"))
    kb.row(InlineKeyboardButton(text="Нет, оставить", callback_data=f"mybooking:{bid}"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel:"))
async def do_cancel(callback: CallbackQuery, bot: Bot):
    bid = int(callback.data.split(":")[1])
    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
        if not booking or booking.user.telegram_id != callback.from_user.id:
            await callback.answer("Не найдено", show_alert=True)
            return
        hours = svc.hours_until(booking)
        ok = await svc.cancel_booking(bid)
    if ok:
        name = callback.from_user.full_name or str(callback.from_user.id)
        username = f"@{callback.from_user.username}" if callback.from_user.username else "—"
        when = f"{booking.booking_date.strftime('%d-%m-%Y')} {booking.start_time.strftime('%H:%M')} · {booking.service.name}"

        if hours < settings.CANCEL_FREE_HOURS:
            note = (
                f"\n\nПредоплата не возвращается. "
                f"Новая запись — снова предоплата {settings.PREPAYMENT_AMOUNT} ₽."
            )
            await callback.message.edit_text("Запись отменена." + note)
            admin_msg = (
                f"❌ Клиентка отменила запись #{bid} (менее 2 дней — бронь сгорает)\n"
                f"👤 {name} {username}\n{when}"
            )
        else:
            async with async_session() as s2:
                refund_text = await ContentService(s2).get_text(
                    "msg_cancel_refund_client", master=settings.MASTER_USERNAME
                )
            await callback.message.edit_text(refund_text)
            admin_msg = (
                f"💸 Клиентка отменила запись #{bid} вовремя (≥2 дней)\n"
                f"Нужно вернуть предоплату {settings.PREPAYMENT_AMOUNT} ₽\n"
                f"👤 {name} {username}\n"
                f"📱 {booking.user.phone or (booking.selected_params or {}).get('contact') or '—'}\n"
                f"{when}"
            )

        await callback.message.answer("👇", reply_markup=main_reply_kb())
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_msg)
            except Exception:
                pass
        await callback.answer("Отменено")
    else:
        await callback.answer("Не удалось", show_alert=True)


@router.callback_query(F.data.startswith("reschedule:"))
async def reschedule_start(callback: CallbackQuery, state: FSMContext):
    bid = int(callback.data.split(":")[1])
    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
        if not booking or booking.user.telegram_id != callback.from_user.id:
            await callback.answer("Не найдено", show_alert=True)
            return
        hours = svc.hours_until(booking)
        if hours < settings.CANCEL_FREE_HOURS:
            await callback.answer("Перенос только не позднее чем за 2 дня", show_alert=True)
            return
        # раз в месяц
        rc = booking.reschedule_count or 0
        if rc >= 1 and booking.last_reschedule_at:
            last = booking.last_reschedule_at
            now = datetime.utcnow()
            if last.year == now.year and last.month == now.month:
                async with async_session() as s2:
                    msg = await ContentService(s2).get_text("msg_reschedule_limit", master=settings.MASTER_USERNAME)
                await callback.message.edit_text(msg)
                await callback.answer()
                return

        await state.set_state(BookingStates.rescheduling)
        await state.update_data(
            reschedule_booking_id=bid,
            duration=booking.total_duration_minutes,
            price=booking.total_price,
            service_name=booking.service.name,
        )
        now = datetime.now(TZ)
        schedule = ScheduleService(session)
        open_days = await schedule.get_open_days(now.year, now.month)
        # только ближайшие 10 дней
        max_day = datetime.now(TZ).date() + timedelta(days=settings.RESCHEDULE_MAX_DAYS)
        open_days = {d for d in open_days if d <= max_day}
        sur_map = await schedule.get_days_surcharge_map(now.year, now.month)

    await callback.message.edit_text(
        f"📅 Перенос: выбери дату в ближайшие {settings.RESCHEDULE_MAX_DAYS} дней.\n"
        f"Дальше этой даты — предоплата за текущую бронь не сохраняется.\n"
        f"При переносе нужна повторная предоплата {settings.PREPAYMENT_AMOUNT} ₽ (войдёт в стоимость, если придёшь).",
        reply_markup=calendar_kb(now.year, now.month, open_days, sur_map),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(BookingStates.rescheduling, F.data.startswith("cal:"))
async def reschedule_cal(callback: CallbackQuery, state: FSMContext):
    _, ys, ms = callback.data.split(":")
    year, month = int(ys), int(ms)
    data = await state.get_data()
    max_day = datetime.now(TZ).date() + timedelta(days=settings.RESCHEDULE_MAX_DAYS)
    async with async_session() as session:
        schedule = ScheduleService(session)
        open_days = {d for d in await schedule.get_open_days(year, month) if d <= max_day}
        sur_map = await schedule.get_days_surcharge_map(year, month)
    await callback.message.edit_text(
        f"📅 Перенос — только на ближайшие {settings.RESCHEDULE_MAX_DAYS} дней:",
        reply_markup=calendar_kb(year, month, open_days, sur_map),
    )
    await callback.answer()


@router.callback_query(BookingStates.rescheduling, F.data.startswith("date:"))
async def reschedule_date(callback: CallbackQuery, state: FSMContext):
    day = date.fromisoformat(callback.data.split(":", 1)[1])
    max_day = datetime.now(TZ).date() + timedelta(days=settings.RESCHEDULE_MAX_DAYS)
    if day > max_day:
        await callback.answer(
            f"Можно только в пределах {settings.RESCHEDULE_MAX_DAYS} дней. Иначе бронь сгорает.",
            show_alert=True,
        )
        return
    data = await state.get_data()
    duration = data.get("duration", 60)
    async with async_session() as session:
        schedule = ScheduleService(session)
        slots = await schedule.get_available_slots(day, duration)
    if not slots:
        await callback.answer("Нет слотов", show_alert=True)
        return
    await state.update_data(booking_date=day.isoformat())
    await callback.message.edit_text(
        f"📅 {day.strftime('%d-%m-%Y')}\nВыбери время:",
        reply_markup=time_slots_kb(slots, day),
    )
    await callback.answer()


@router.callback_query(BookingStates.rescheduling, F.data.startswith("time:"))
async def reschedule_time(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split(":")
    day = date.fromisoformat(parts[1])
    time_str = f"{parts[2]}:{parts[3]}"
    from datetime import time as dt_time
    start_t = dt_time.fromisoformat(time_str)
    data = await state.get_data()
    bid = data["reschedule_booking_id"]
    duration = data.get("duration", 60)
    end_dt = datetime.combine(day, start_t) + timedelta(minutes=duration)

    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
        if not booking:
            await callback.answer("Не найдено", show_alert=True)
            return
        # удалить старое событие календаря
        if booking.calendar_event_id:
            try:
                from services.google_calendar import delete_event
                delete_event(booking.calendar_event_id)
            except Exception:
                pass
            booking.calendar_event_id = None
        booking.booking_date = day
        booking.start_time = start_t
        booking.end_time = end_dt.time()
        booking.reschedule_count = (booking.reschedule_count or 0) + 1
        booking.last_reschedule_at = datetime.utcnow()
        booking.status = "pending_payment"
        booking.reminder_sent = False
        booking.day_confirm_sent = False
        booking.day_confirm_status = None
        booking.payment_photo_file_id = None
        booking.payment_note = None
        from datetime import datetime as _dt
        booking.updated_at = _dt.utcnow()
        await session.commit()
        bdate = booking.booking_date.strftime("%d-%m-%Y")
        btime = booking.start_time.strftime("%H:%M")
        sname = booking.service.name

    # Оставляем FSM на ожидании предоплаты по ЭТОЙ записи
    await state.set_state(BookingStates.waiting_payment)
    await state.update_data(pending_booking_id=bid, reschedule_payment=True)

    await callback.message.edit_text(
        f"✅ Дата изменена: <b>{bdate} в {btime}</b>\n\n"
        f"💳 Нужна повторная предоплата <b>{settings.PREPAYMENT_AMOUNT} ₽</b>.\n"
        f"Она войдёт в стоимость, если придёшь.\n\n"
        f"Отправь <b>скрин перевода</b> или напиши, <b>от кого перевод</b>.",
        parse_mode="HTML",
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📅 Перенос записи #{bid}\n{sname}\nНовая дата: {bdate} {btime}\n"
                f"Клиент: {callback.from_user.full_name or callback.from_user.id}\n"
                f"Ждёт повторную предоплату {settings.PREPAYMENT_AMOUNT} ₽",
            )
        except Exception:
            pass
    await callback.answer("Перенесено — ждём предоплату")
