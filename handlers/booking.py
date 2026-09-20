from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from datetime import date, time, datetime, timedelta

from states.booking_states import BookingStates
from keyboards.main import main_menu_kb, main_reply_kb
from keyboards.booking import (
    services_kb, parameter_options_kb, confirm_params_kb,
    calendar_kb, time_slots_kb, final_confirm_kb
)
from database.database import async_session
from services.pricing_service import PricingService
from services.schedule_service import ScheduleService
from services.booking_service import BookingService
from services.content_service import ContentService
from services.backup_service import create_backup
from services.google_calendar import create_event
from utils.formatting import format_duration, format_price, format_booking_summary, format_selected_params
from config import settings, TZ

router = Router(name="booking")

# Порядок шагов для «Назад»
NAILS_ORDER = [
    "procedure", "has_coating", "nails_condition", "claws",
    "coating_type", "length", "design", "communication", "without_type",
]

STEP_LABELS = {
    "procedure": "Процедура",
    "has_coating": "Текущее покрытие",
    "nails_condition": "Особенности покрытия",
    "claws": "Когти",
    "coating_type": "Тип покрытия",
    "length": "Длина",
    "design": "Дизайн",
    "communication": "Общение",
    "without_type": "Без покрытия",
}


def next_nails_step(selected: dict, current: str) -> str | None:
    """
    без покрытия → 4 услуги → окошки
    с покрытием → есть? → [состояние] → когти → тип → [длина] → дизайн → общение
    """
    if current == "procedure":
        if selected.get("procedure") == "no_coating":
            return "without_type"
        if selected.get("procedure") == "repair":
            return None  # сразу итог → дата
        return "has_coating"
    if current == "has_coating":
        if selected.get("has_coating") == "yes":
            return "nails_condition"
        return "claws"
    if current == "nails_condition":
        return "claws"
    if current == "claws":
        return "coating_type"
    if current == "coating_type":
        if selected.get("coating_type") == "build":
            return "length"
        return "design"
    if current == "length":
        return "design"
    if current == "design":
        return "communication"
    if current == "communication":
        return None
    if current == "without_type":
        return None
    return None


def prev_nails_step(selected: dict, current: str) -> str | None:
    if current == "has_coating":
        return "procedure"
    if current == "nails_condition":
        return "has_coating"
    if current == "claws":
        if selected.get("has_coating") == "yes":
            return "nails_condition"
        return "has_coating"
    if current == "coating_type":
        return "claws"
    if current == "length":
        return "coating_type"
    if current == "design":
        if selected.get("coating_type") == "build":
            return "length"
        return "coating_type"
    if current == "communication":
        return "design"
    if current == "without_type":
        return "procedure"
    if current == "procedure":
        return None
    return "procedure"


async def notify_admins(bot: Bot, text: str, photo_file_id: str | None = None):
    for admin_id in settings.ADMIN_IDS:
        try:
            if photo_file_id:
                await bot.send_photo(admin_id, photo_file_id, caption=text[:1000], parse_mode="HTML")
            else:
                await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


def _build_params_text(selected_texts: dict) -> str:
    lines = [f"• <b>{STEP_LABELS.get(s, s)}:</b> {t}" for s, t in selected_texts.items()]
    return "\n".join(lines) if lines else ""


async def start_booking_from_message(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        svc = BookingService(session)
        if await svc.is_blacklisted(message.from_user.id):
            async with async_session() as s2:
                msg = await ContentService(s2).get_text("msg_no_slots")
            await message.answer(msg, reply_markup=main_reply_kb(), parse_mode="HTML")
            return
        from sqlalchemy import select
        from database.models import Service
        result = await session.execute(select(Service).where(Service.is_active == True).order_by(Service.sort_order))
        services = list(result.scalars().all())
    if not services:
        await message.answer("Услуги временно недоступны", reply_markup=main_reply_kb())
        return
    await state.set_state(BookingStates.choosing_service)
    async with async_session() as s2:
        choose = await ContentService(s2).get_text("msg_choose_service")
    await message.answer(choose, reply_markup=services_kb(services), parse_mode="HTML")


@router.callback_query(F.data == "menu:book")
async def start_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        svc = BookingService(session)
        if await svc.is_blacklisted(callback.from_user.id):
            async with async_session() as s2:
                msg = await ContentService(s2).get_text("msg_no_slots")
            await callback.message.edit_text(msg, parse_mode="HTML")
            await callback.message.answer("👇", reply_markup=main_reply_kb())
            await callback.answer()
            return
        from sqlalchemy import select
        from database.models import Service
        result = await session.execute(select(Service).where(Service.is_active == True).order_by(Service.sort_order))
        services = list(result.scalars().all())
    if not services:
        await callback.answer("Услуги недоступны", show_alert=True)
        return
    await state.set_state(BookingStates.choosing_service)
    async with async_session() as s2:
        choose = await ContentService(s2).get_text("msg_choose_service")
    try:
        await callback.message.edit_text(choose, reply_markup=services_kb(services), parse_mode="HTML")
    except Exception:
        await callback.message.answer(choose, reply_markup=services_kb(services), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "booking:cancel")
async def cancel_booking_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена.")
    await callback.message.answer("👇 Меню:", reply_markup=main_reply_kb())
    await callback.message.answer("Разделы:", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(BookingStates.choosing_service, F.data.startswith("service:"))
async def service_chosen(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    async with async_session() as session:
        pricing = PricingService(session)
        service = await pricing.get_service_by_code(code)
        if not service:
            await callback.answer("Не найдено", show_alert=True)
            return
        # бонус 5-я запись: -50% на дизайн (запоминаем)
        bsvc = BookingService(session)
        user = await bsvc.get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name)
        bonus = (user.completed_count or 0) > 0 and (user.completed_count + 1) % 5 == 0
        await state.update_data(
            service_id=service.id, service_code=service.code, service_name=service.name,
            selected_params={}, selected_params_text={},
            duration=service.base_duration_minutes, price=service.base_price,
            photo_file_id=None, surcharge=0, design_bonus=bonus, calendar_color_id=service.calendar_color_id or "1",
        )
        if service.has_complex_flow:
            await state.set_state(BookingStates.has_coating)  # переиспользуем state
            options = await pricing.get_parameters_for_step(service.id, "procedure")
            title = options[0].step_title if options else "Процедура"
            bonus_note = "\n\n🎁 На эту запись — скидка 50% на дизайн!" if bonus else ""
            text = f"<b>💅 {service.name}</b>{bonus_note}\n\n<b>{title}</b>"
            await callback.message.edit_text(text, reply_markup=parameter_options_kb("procedure", options), parse_mode="HTML")
        else:
            await state.set_state(BookingStates.confirming_params)
            text = f"<b>💅 {service.name}</b>\n\n⏱ {format_duration(service.base_duration_minutes)} · 💰 {format_price(service.base_price)}\n\nК выбору даты?"
            await callback.message.edit_text(text, reply_markup=confirm_params_kb(service.base_duration_minutes, service.base_price), parse_mode="HTML")
    await callback.answer()


async def _show_next_step(target, state: FSMContext, next_step: str | None, is_message: bool = False):
    data = await state.get_data()
    selected = data.get("selected_params", {})
    async with async_session() as session:
        pricing = PricingService(session)
        service = await pricing.get_service_by_code(data["service_code"])
        duration, price = await pricing.calculate(service, selected)
        if data.get("design_bonus") and selected.get("design"):
            opt = await pricing.get_option(service.id, "design", selected["design"])
            if opt and opt.price_modifier:
                price -= opt.price_modifier * 0.5
        await state.update_data(duration=duration, price=price)
        params_text = _build_params_text(data.get("selected_params_text", {}))
        if next_step is None:
            await state.set_state(BookingStates.confirming_params)
            text = (
                f"<b>📋 Проверь запись</b>\n\n"
                f"{format_booking_summary(service.name, duration, price, params_text=params_text)}\n\n"
                f"Всё верно — переходим к выбору даты?"
            )
            kb = confirm_params_kb(duration, price)
            if is_message:
                await target.answer(text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return

        state_map = {
            "procedure": BookingStates.has_coating,
            "has_coating": BookingStates.has_coating,
            "nails_condition": BookingStates.nails_condition,
            "coating_type": BookingStates.has_coating,
            "without_type": BookingStates.has_coating,
            "length": BookingStates.length,
            "claws": BookingStates.claws,
            "design": BookingStates.design,
            "communication": BookingStates.communication,
        }
        await state.set_state(state_map.get(next_step, BookingStates.has_coating))
        options = await pricing.get_parameters_for_step(service.id, next_step)
        title = options[0].step_title if options else STEP_LABELS.get(next_step, next_step)
        prev = prev_nails_step(selected, next_step)
        text = (
            f"<b>💅 {service.name}</b>\n"
            f"⏱ {format_duration(duration)} · 💰 {format_price(price)}\n\n"
            f"<b>{title}</b>"
        )
        kb = parameter_options_kb(next_step, options, prev_step=prev)
        if is_message:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")



@router.callback_query(F.data.startswith("param_back:"))
async def param_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться на предыдущий шаг и перевыбрать."""
    prev = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = dict(data.get("selected_params", {}))
    selected_texts = dict(data.get("selected_params_text", {}))
    # убрать ответы начиная с prev и дальше по цепочке
    drop_from = ["procedure", "has_coating", "nails_condition", "claws", "coating_type", "length", "design", "communication", "without_type"]
    try:
        idx = drop_from.index(prev)
        for s in drop_from[idx:]:
            selected.pop(s, None)
            selected_texts.pop(s, None)
    except ValueError:
        selected.pop(prev, None)
        selected_texts.pop(prev, None)
    await state.update_data(selected_params=selected, selected_params_text=selected_texts)
    await _show_next_step(callback, state, prev, False)
    await callback.answer()


@router.callback_query(F.data.startswith("param:"))
async def param_chosen(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, step_code, option_code = parts
    data = await state.get_data()
    selected = data.get("selected_params", {})
    selected_texts = data.get("selected_params_text", {})
    selected[step_code] = option_code
    async with async_session() as session:
        pricing = PricingService(session)
        service = await pricing.get_service_by_code(data["service_code"])
        option = await pricing.get_option(service.id, step_code, option_code)
        if option:
            selected_texts[step_code] = option.option_text
        await state.update_data(selected_params=selected, selected_params_text=selected_texts)
        if option and option.requires_photo:
            await state.set_state(BookingStates.waiting_photo)
            await state.update_data(photo_after_step=step_code)
            await callback.message.edit_text("📷 Отправь фото.")
            await callback.answer()
            return
        next_step = next_nails_step(selected, step_code)
    await _show_next_step(callback, state, next_step, False)
    await callback.answer()


@router.message(BookingStates.waiting_photo, F.photo)
async def photo_received(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    data = await state.get_data()
    step = data.get("photo_after_step", "design")
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(BookingStates.waiting_admin_choice)
    async with async_session() as session:
        msg = await ContentService(session).get_text("msg_photo_received")
    await message.answer(msg, parse_mode="HTML")
    async with async_session() as session:
        pricing = PricingService(session)
        service = await pricing.get_service_by_code(data["service_code"])
        options = [o for o in await pricing.get_parameters_for_step(service.id, step) if not o.requires_photo]
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    cid = message.from_user.id
    for opt in options:
        kb.row(InlineKeyboardButton(text=opt.option_text[:40], callback_data=f"adm_pick:{cid}:{step}:{opt.option_code}"))
    kb.row(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_pick_reject:{cid}"))
    client_name = message.from_user.full_name or str(cid)
    caption = f"<b>📷 Нужен твой ответ</b>\n👤 {client_name}\nШаг: {STEP_LABELS.get(step, step)}\nУслуга: {data.get('service_name')}\n\nВыбери вариант:"
    await notify_admins(bot, caption, photo.file_id)
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "Варианты:", reply_markup=kb.as_markup())
        except Exception:
            pass


@router.message(BookingStates.waiting_photo)
async def photo_expected(message: Message):
    await message.answer("📷 Отправь фото.")


@router.message(BookingStates.waiting_admin_choice)
async def waiting_admin_block(message: Message):
    async with async_session() as session:
        msg = await ContentService(session).get_text("msg_waiting_admin")
    await message.answer(msg, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_pick_reject:"))
async def admin_pick_reject(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.from_user.id not in settings.ADMIN_IDS:
        return
    client_id = int(callback.data.split(":")[1])
    key = StorageKey(bot_id=bot.id, chat_id=client_id, user_id=client_id)
    await state.storage.set_state(key, None)
    await state.storage.set_data(key, {})
    try:
        await bot.send_message(client_id, "😔 Не получилось определить по фото. Начни запись заново или пришли другое фото.")
    except Exception:
        pass
    await callback.answer("Отклонено")


@router.callback_query(F.data.startswith("adm_pick:"))
async def admin_pick_option(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.from_user.id not in settings.ADMIN_IDS:
        return
    parts = callback.data.split(":")
    client_id, step, option_code = int(parts[1]), parts[2], parts[3]
    key = StorageKey(bot_id=bot.id, chat_id=client_id, user_id=client_id)
    storage = state.storage
    data = await storage.get_data(key)
    if not data:
        await callback.answer("Сессия устарела", show_alert=True)
        return
    selected = data.get("selected_params", {})
    selected_texts = data.get("selected_params_text", {})
    selected[step] = option_code
    async with async_session() as session:
        pricing = PricingService(session)
        service = await pricing.get_service_by_code(data["service_code"])
        option = await pricing.get_option(service.id, step, option_code)
        if option:
            selected_texts[step] = option.option_text
        duration, price = await pricing.calculate(service, selected)
        if data.get("design_bonus") and selected.get("design"):
            opt = await pricing.get_option(service.id, "design", selected["design"])
            if opt and opt.price_modifier:
                price -= opt.price_modifier * 0.5
    data["selected_params"] = selected
    data["selected_params_text"] = selected_texts
    data["duration"] = duration
    data["price"] = price
    await storage.set_data(key, data)
    next_step = next_nails_step(selected, step)
    try:
        await bot.send_message(client_id, f"✅ Мастер выбрал: <b>{selected_texts.get(step)}</b>\nПродолжаем!", parse_mode="HTML")
    except Exception:
        pass
    client_state = FSMContext(storage=storage, key=key)
    if next_step is None:
        await client_state.set_state(BookingStates.confirming_params)
        pt = _build_params_text(selected_texts)
        await bot.send_message(client_id, f"<b>📋 Итог</b>\n\n{format_booking_summary(service.name, duration, price, params_text=pt)}\n\nК дате?",
                               reply_markup=confirm_params_kb(duration, price), parse_mode="HTML")
    else:
        state_map = {
            "design": BookingStates.design, "length": BookingStates.length,
            "claws": BookingStates.claws, "communication": BookingStates.communication,
            "nails_condition": BookingStates.nails_condition,
            "has_coating": BookingStates.has_coating, "coating_type": BookingStates.has_coating,
            "procedure": BookingStates.has_coating, "without_type": BookingStates.has_coating,
        }
        await client_state.set_state(state_map.get(next_step, BookingStates.confirming_params))
        async with async_session() as session:
            pricing = PricingService(session)
            options = await pricing.get_parameters_for_step(service.id, next_step)
        title = options[0].step_title if options else next_step
        await bot.send_message(client_id, f"<b>💅 {service.name}</b>\n\n⏱ {format_duration(duration)} · 💰 {format_price(price)}\n\n<b>{title}</b>",
                               reply_markup=parameter_options_kb(next_step, options), parse_mode="HTML")
    await callback.answer("Передано")
    try:
        await callback.message.edit_text((callback.message.text or "") + f"\n✅ {selected_texts.get(step)}")
    except Exception:
        pass


@router.callback_query(F.data == "booking:confirm_params")
async def confirm_params(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BookingStates.choosing_date)
    now = datetime.now(TZ)
    async with async_session() as session:
        schedule = ScheduleService(session)
        open_days = await schedule.get_open_days(now.year, now.month)
        sur_map = await schedule.get_days_surcharge_map(now.year, now.month)
    if not open_days:
        await callback.message.edit_text("😔 Пока нет открытых дат.")
        await callback.message.answer("👇", reply_markup=main_reply_kb())
        await callback.answer()
        return
    text = f"📅 Выбери дату.\n\n⏱ {format_duration(data['duration'])} · 💰 {format_price(data['price'])}\n🔥 +300 · ⭐ +100 — особые окошки"
    await callback.message.edit_text(text, reply_markup=calendar_kb(now.year, now.month, open_days, sur_map), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cal:"))
async def change_calendar_month(callback: CallbackQuery, state: FSMContext):
    _, ys, ms = callback.data.split(":")
    year, month = int(ys), int(ms)
    data = await state.get_data()
    async with async_session() as session:
        schedule = ScheduleService(session)
        open_days = await schedule.get_open_days(year, month)
        sur_map = await schedule.get_days_surcharge_map(year, month)
    text = f"📅 Выбери дату.\n\n⏱ {format_duration(data.get('duration', 0))} · 💰 {format_price(data.get('price', 0))}"
    await callback.message.edit_text(text, reply_markup=calendar_kb(year, month, open_days, sur_map), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("date:"))
async def date_chosen(callback: CallbackQuery, state: FSMContext):
    day = date.fromisoformat(callback.data.split(":", 1)[1])
    data = await state.get_data()
    duration = data.get("duration", 60)
    async with async_session() as session:
        schedule = ScheduleService(session)
        slots = await schedule.get_available_slots(day, duration)
    if not slots:
        await callback.answer("Нет свободных слотов", show_alert=True)
        return
    await state.update_data(booking_date=day.isoformat())
    await state.set_state(BookingStates.choosing_time)
    await callback.message.edit_text(
        f"📅 <b>{day.strftime('%d-%m-%Y')}</b>\n\nВыбери время:",
        reply_markup=time_slots_kb(slots, day), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "booking:choose_date")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    await confirm_params(callback, state)


@router.callback_query(F.data.startswith("time:"))
async def time_chosen(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    day = date.fromisoformat(parts[1])
    time_str = f"{parts[2]}:{parts[3]}"
    start_t = time.fromisoformat(time_str)
    data = await state.get_data()
    duration = data["duration"]
    end_t = (datetime.combine(day, start_t) + timedelta(minutes=duration)).time()
    async with async_session() as session:
        schedule = ScheduleService(session)
        info = await schedule.get_slot_info(day, time_str)
    surcharge = float(info.get("surcharge") or 0)
    await state.update_data(start_time=time_str, end_time=end_t.strftime("%H:%M"), surcharge=surcharge)
    await state.set_state(BookingStates.waiting_contact)
    sur_note = f"\n🔥 Доплата за окошко: +{int(surcharge)} ₽" if surcharge else ""
    async with async_session() as s2:
        contact_msg = await ContentService(s2).get_text("msg_ask_contact")
    await callback.message.edit_text(
        f"📅 {day.strftime('%d-%m-%Y')} в {time_str}{sur_note}\n\n{contact_msg}",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(BookingStates.waiting_contact)
async def contact_received(message: Message, state: FSMContext):
    contact = (message.text or "").strip()
    if len(contact) < 3:
        await message.answer("Напиши @username или номер:")
        return
    await state.update_data(contact=contact)
    data = await state.get_data()
    surcharge = data.get("surcharge") or 0
    total = data["price"] + surcharge

    # Временная бронь слота до предоплаты (истекает через PREPAYMENT_TIMEOUT_MINUTES)
    async with async_session() as session:
        bsvc = BookingService(session)
        pricing = PricingService(session)
        user = await bsvc.get_or_create_user(
            message.from_user.id, message.from_user.username, message.from_user.full_name
        )
        user.phone = contact
        service = await pricing.get_service_by_code(data["service_code"])
        booking = await bsvc.create_booking(
            user=user, service=service,
            selected_params={
                "codes": data.get("selected_params", {}),
                "texts": data.get("selected_params_text", {}),
                "contact": contact,
            },
            duration=data["duration"], price=data["price"],
            booking_date=date.fromisoformat(data["booking_date"]),
            start_time=time.fromisoformat(data["start_time"]),
            photo_file_id=data.get("photo_file_id"),
            status="pending_payment",
            surcharge=surcharge,
        )
        bid = booking.id
        content = ContentService(session)
        pay = await content.get_by_code("payment_details")
    pay_text = pay.text if pay else "Реквизиты уточни у мастера."

    await state.set_state(BookingStates.waiting_payment)
    await state.update_data(pending_booking_id=bid)

    summary = format_booking_summary(
        data["service_name"], data["duration"], total,
        booking_date=date.fromisoformat(data["booking_date"]),
        start_time=time.fromisoformat(data["start_time"]),
        end_time=time.fromisoformat(data["end_time"]),
        params_text=_build_params_text(data.get("selected_params_text", {}))
    )
    mins = settings.PREPAYMENT_TIMEOUT_MINUTES
    await message.answer(
        f"<b>💳 Предоплата</b>\n\n{summary}\n📱 {contact}\n\n{pay_text}\n\n"
        f"После перевода <b>отправь скрин</b> или напиши, <b>от кого перевод</b>.\n\n"
        f"⏳ На это есть <b>{mins} минут</b> — иначе окошко освободится.",
        parse_mode="HTML"
    )


async def _create_pending_payment(message, state, bot, payment_photo=None, payment_note=None):
    data = await state.get_data()
    client_name = message.from_user.full_name or str(message.from_user.id)

    # --- Повторная предоплата после переноса (запись уже есть) ---
    if data.get("pending_booking_id"):
        bid = int(data["pending_booking_id"])
        async with async_session() as session:
            bsvc = BookingService(session)
            booking = await bsvc.get_booking_by_id(bid)
            if not booking or booking.user.telegram_id != message.from_user.id:
                await message.answer("Запись не найдена. Начни запись заново.")
                await state.clear()
                return
            booking.status = "pending_payment"
            booking.payment_photo_file_id = payment_photo
            booking.payment_note = payment_note
            await session.commit()
            total = booking.total_price
            sname = booking.service.name
            bdate = booking.booking_date.strftime("%d-%m-%Y")
            btime = booking.start_time.strftime("%H:%M")
            contact = booking.user.phone or "—"
            params_s = ""
            texts = (booking.selected_params or {}).get("texts") or {}
            if texts:
                params_s = "\n" + _build_params_text(texts)

        await state.set_state(BookingStates.waiting_payment_confirm)
        await state.update_data(pending_booking_id=bid)
        async with async_session() as s2:
            wait_msg = await ContentService(s2).get_text("msg_payment_wait")
        await message.answer(wait_msg, parse_mode="HTML")

        admin_text = (
            f"<b>💳 Предоплата / запись</b>\n"
            f"👤 {client_name}\n📱 {contact}\n"
            f"{'Скрин приложен' if payment_photo else f'От кого: {payment_note}'}\n"
            f"{sname} · {bdate} {btime}\n"
            f"Сумма услуги: {int(total)} ₽ · предоплата {settings.PREPAYMENT_AMOUNT} ₽\n"
            f"ID: {bid}{params_s}"
        )
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="✅ Предоплата пришла", callback_data=f"adm_pay_ok:{bid}:{message.from_user.id}"))
        kb.row(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_pay_no:{bid}:{message.from_user.id}"))
        for admin_id in settings.ADMIN_IDS:
            try:
                if payment_photo:
                    await bot.send_photo(admin_id, payment_photo, caption=admin_text[:1000], parse_mode="HTML")
                else:
                    await bot.send_message(admin_id, admin_text, parse_mode="HTML")
                await bot.send_message(admin_id, "Действие:", reply_markup=kb.as_markup())
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"admin notify fail: {e}")
        return

    # --- Обычная новая запись ---
    async with async_session() as session:
        bsvc = BookingService(session)
        pricing = PricingService(session)
        user = await bsvc.get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        if data.get("contact"):
            user.phone = data["contact"]
            await session.commit()
        service = await pricing.get_service_by_code(data["service_code"])
        booking = await bsvc.create_booking(
            user=user, service=service,
            selected_params={"codes": data.get("selected_params", {}), "texts": data.get("selected_params_text", {}), "contact": data.get("contact")},
            duration=data["duration"], price=data["price"],
            booking_date=date.fromisoformat(data["booking_date"]),
            start_time=time.fromisoformat(data["start_time"]),
            photo_file_id=data.get("photo_file_id"),
            status="pending_payment",
            surcharge=data.get("surcharge") or 0,
            payment_note=payment_note,
            payment_photo_file_id=payment_photo,
        )
        bid = booking.id
        total = booking.total_price
    await state.set_state(BookingStates.waiting_payment_confirm)
    await state.update_data(pending_booking_id=bid)
    async with async_session() as s2:
        wait_msg = await ContentService(s2).get_text("msg_payment_wait")
    await message.answer(wait_msg, parse_mode="HTML")
    params_block = _build_params_text(data.get("selected_params_text", {}))
    params_s = f"\n{params_block}" if params_block else ""
    admin_text = (
        f"<b>💳 Предоплата / запись</b>\n"
        f"👤 {client_name}\n📱 {data.get('contact')}\n"
        f"{'Скрин приложен' if payment_photo else f'От кого: {payment_note}'}\n"
        f"{data.get('service_name', '')} · {date.fromisoformat(data['booking_date']).strftime('%d-%m-%Y')} {data['start_time']}\n"
        f"Сумма: {int(total)} ₽\nID: {bid}"
        f"{params_s}"
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Предоплата пришла", callback_data=f"adm_pay_ok:{bid}:{message.from_user.id}"))
    kb.row(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_pay_no:{bid}:{message.from_user.id}"))
    for admin_id in settings.ADMIN_IDS:
        try:
            if payment_photo:
                await bot.send_photo(admin_id, payment_photo, caption=admin_text[:1000], parse_mode="HTML")
            else:
                await bot.send_message(admin_id, admin_text, parse_mode="HTML")
            await bot.send_message(admin_id, "Действие:", reply_markup=kb.as_markup())
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"admin notify fail: {e}")


@router.message(BookingStates.waiting_payment, F.photo)
async def payment_photo(message: Message, state: FSMContext, bot: Bot):
    await _create_pending_payment(message, state, bot, payment_photo=message.photo[-1].file_id)


@router.message(BookingStates.waiting_payment, F.text)
async def payment_text(message: Message, state: FSMContext, bot: Bot):
    note = (message.text or "").strip()
    if len(note) < 2:
        await message.answer("Напиши, от кого перевод, или пришли скрин.")
        return
    await _create_pending_payment(message, state, bot, payment_note=note)


@router.message(BookingStates.waiting_payment_confirm)
async def payment_wait(message: Message):
    await message.answer("⏳ Ещё ждём проверку предоплаты.")


@router.callback_query(F.data.startswith("adm_pay_ok:"))
async def admin_pay_ok(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.from_user.id not in settings.ADMIN_IDS:
        return
    _, bid_s, cid_s = callback.data.split(":")
    bid, cid = int(bid_s), int(cid_s)
    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
        if not booking or booking.status != "pending_payment":
            await callback.answer("Уже обработано", show_alert=True)
            return
        booking.status = "confirmed"
        await session.commit()
        color = booking.service.calendar_color_id or "1"
        contact = booking.user.phone or ""
        event_id = create_event(
            summary=f"{booking.service.name} — {booking.user.full_name or contact}",
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            description=f"Контакт: {contact}\nID: {booking.id}",
            color_id=color,
        )
        if event_id:
            booking.calendar_event_id = event_id
            await session.commit()
            import logging
            logging.getLogger(__name__).info(f"GCal OK event={event_id}")
        else:
            import logging
            logging.getLogger(__name__).warning(
                "GCal: событие НЕ создано (проверь .env, JSON, доступ к календарю)"
            )
        try:
            create_backup()
        except Exception:
            pass
        summary = format_booking_summary(
            booking.service.name, booking.total_duration_minutes, booking.total_price,
            booking_date=booking.booking_date, start_time=booking.start_time, end_time=booking.end_time
        )
    key = StorageKey(bot_id=bot.id, chat_id=cid, user_id=cid)
    await state.storage.set_state(key, None)
    await state.storage.set_data(key, {})
    try:
        async with async_session() as s2:
            conf = await ContentService(s2).get_text("msg_booking_confirmed", summary=summary)
        await bot.send_message(cid, conf, parse_mode="HTML", reply_markup=main_reply_kb())
    except Exception:
        pass
    await notify_admins(bot, f"✅ Запись #{bid} подтверждена (предоплата ок)")
    try:
        await callback.message.edit_text(
            (callback.message.text or "Предоплата") + f"\n\n✅ Подтверждено (запись #{bid})"
        )
    except Exception:
        try:
            await callback.message.answer(f"✅ Запись #{bid} подтверждена")
        except Exception:
            pass
    await callback.answer("Подтверждено")


@router.callback_query(F.data.startswith("adm_pay_no:"))
async def admin_pay_no(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        _, bid_s, cid_s = callback.data.split(":")
        bid, cid = int(bid_s), int(cid_s)
    except Exception:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    async with async_session() as session:
        svc = BookingService(session)
        booking = await svc.get_booking_by_id(bid)
        if not booking:
            await callback.answer("Запись не найдена", show_alert=True)
            return
        if booking.status == "cancelled":
            await callback.answer("Уже отменена", show_alert=True)
            try:
                await callback.message.edit_text((callback.message.text or "") + "\n\n❌ Уже отклонено")
            except Exception:
                pass
            return
        # принудительно отменяем pending_payment
        booking.status = "cancelled"
        if booking.calendar_event_id:
            try:
                from services.google_calendar import delete_event
                delete_event(booking.calendar_event_id)
            except Exception:
                pass
            booking.calendar_event_id = None
        await session.commit()

    key = StorageKey(bot_id=bot.id, chat_id=cid, user_id=cid)
    try:
        await state.storage.set_state(key, None)
        await state.storage.set_data(key, {})
    except Exception:
        pass

    try:
        async with async_session() as s2:
            rej = await ContentService(s2).get_text("msg_payment_rejected")
        await bot.send_message(cid, rej, reply_markup=main_reply_kb(), parse_mode="HTML")
        await bot.send_message(cid, "Разделы:", reply_markup=main_menu_kb())
    except Exception:
        pass

    try:
        await callback.message.edit_text(
            (callback.message.text or "Предоплата") + f"\n\n❌ Отклонено (запись #{bid})"
        )
    except Exception:
        try:
            await callback.message.answer(f"❌ Предоплата по записи #{bid} отклонена")
        except Exception:
            pass

    await callback.answer("Отклонено")


@router.callback_query(F.data.startswith("day_yes:"))
async def day_yes(callback: CallbackQuery):
    bid = int(callback.data.split(":")[1])
    async with async_session() as session:
        svc = BookingService(session)
        b = await svc.get_booking_by_id(bid)
        if b and b.user.telegram_id == callback.from_user.id:
            b.day_confirm_status = "yes"
            await session.commit()
    await callback.message.edit_text((callback.message.text or "") + "\n\n✅ Спасибо, ждём тебя!")
    await callback.answer()


@router.callback_query(F.data.startswith("day_no:"))
async def day_no(callback: CallbackQuery, bot: Bot):
    bid = int(callback.data.split(":")[1])
    info = ""
    async with async_session() as session:
        svc = BookingService(session)
        b = await svc.get_booking_by_id(bid)
        if not b or b.user.telegram_id != callback.from_user.id:
            await callback.answer("Запись не найдена", show_alert=True)
            return
        if b.status == "cancelled":
            await callback.answer("Уже отменена", show_alert=True)
            return
        info = (
            f"{b.service.name} · {b.booking_date.strftime('%d-%m-%Y')} "
            f"{b.start_time.strftime('%H:%M')}"
        )
        b.day_confirm_status = "no"
        await session.commit()
        # Полная отмена + удаление из Google Calendar
        await svc.cancel_booking(bid)

    await notify_admins(
        bot,
        f"❌ Клиентка не придёт — запись #{bid} отменена\n{info}"
    )
    try:
        await callback.message.edit_text(
            (callback.message.text or "") + "\n\n❌ Запись отменена. Если нужно перенести — напиши мастеру."
        )
    except Exception:
        pass
    await callback.answer("Запись отменена")
