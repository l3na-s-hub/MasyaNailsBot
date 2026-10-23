"""Таймаут предоплаты: спрашиваем мастера, не автоотмена."""
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.database import async_session
from services.booking_service import BookingService
from config import settings

logger = logging.getLogger(__name__)


def _timeout_kb(bid: int, client_tg: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✅ Предоплата пришла — оставить запись",
        callback_data=f"adm_pay_ok:{bid}:{client_tg}",
    ))
    builder.row(InlineKeyboardButton(
        text="❌ Отменить запись",
        callback_data=f"adm_pay_no:{bid}:{client_tg}",
    ))
    return builder.as_markup()


async def expire_pending_payments(bot: Bot):
    """Через N минут без скрина — мастеру вопрос, отменять ли."""
    mins = getattr(settings, "PREPAYMENT_TIMEOUT_MINUTES", 20)
    async with async_session() as session:
        svc = BookingService(session)
        found = await svc.find_unpaid_needing_admin(minutes=mins)
        items = []
        for b in found:
            contact = (
                (b.user.phone if b.user else None)
                or (b.selected_params or {}).get("contact")
                or "—"
            )
            uname = ""
            if b.user and b.user.username:
                uname = f"@{b.user.username}"
            name = (b.user.full_name if b.user else None) or "Клиентка"
            items.append({
                "id": b.id,
                "tg": b.user.telegram_id if b.user else 0,
                "service": b.service.name if b.service else "услуга",
                "date": b.booking_date.strftime("%d-%m-%Y"),
                "time": b.start_time.strftime("%H:%M"),
                "contact": contact,
                "name": name,
                "username": uname,
                "price": int(b.total_price or 0),
            })

    for it in items:
        text = (
            f"⏳ <b>Прошло {mins} мин — скрин предоплаты не пришёл</b>\n\n"
            f"Запись #{it['id']}\n"
            f"👤 {it['name']} {it['username']}\n"
            f"📱 Контакт: <code>{it['contact']}</code>\n"
            f"💅 {it['service']}\n"
            f"📅 {it['date']} в {it['time']}\n"
            f"💰 Услуга: {it['price']} ₽ · бронь {settings.PREPAYMENT_AMOUNT} ₽\n\n"
            f"Предоплата пришла? Оставляем запись или отменяем?"
        )
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    text,
                    parse_mode="HTML",
                    reply_markup=_timeout_kb(it["id"], it["tg"] or 0),
                )
            except Exception as e:
                logger.warning(f"timeout notify admin: {e}")
        logger.info(f"Payment timeout ask admin for booking #{it['id']}")
