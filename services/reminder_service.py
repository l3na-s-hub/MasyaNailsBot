import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.database import async_session
from services.booking_service import BookingService
from config import settings
from utils.formatting import format_datetime_range
from services.content_service import ContentService

logger = logging.getLogger(__name__)


async def send_reminders(bot: Bot):
    async with async_session() as session:
        svc = BookingService(session)
        bookings = await svc.get_upcoming_for_reminder(settings.REMINDER_HOURS_BEFORE)
        for booking in bookings:
            try:
                details = (
                    f"• {booking.service.name}\n"
                    f"• {format_datetime_range(booking.booking_date, booking.start_time, booking.end_time)}\n"
                    f"• {int(booking.total_price)} ₽"
                )
                text = await ContentService(session).get_text("msg_reminder", details=details)
                await bot.send_message(booking.user.telegram_id, text, parse_mode="HTML")
                await svc.mark_reminder_sent(booking.id)
            except Exception as e:
                logger.error(f"Reminder {booking.id}: {e}")


async def send_day_confirms(bot: Bot):
    """Подтверждение за ~сутки: «Придёшь?»"""
    async with async_session() as session:
        svc = BookingService(session)
        bookings = await svc.get_for_day_confirm()
        for booking in bookings:
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Да, приду", callback_data=f"day_yes:{booking.id}"),
                        InlineKeyboardButton(text="❌ Не смогу", callback_data=f"day_no:{booking.id}"),
                    ]
                ])
                details = (
                    f"• {booking.service.name}\n"
                    f"• {format_datetime_range(booking.booking_date, booking.start_time, booking.end_time)}"
                )
                text = await ContentService(session).get_text("msg_day_confirm", details=details)
                await bot.send_message(booking.user.telegram_id, text, parse_mode="HTML", reply_markup=kb)
                await svc.mark_day_confirm_sent(booking.id)
            except Exception as e:
                logger.error(f"Day confirm {booking.id}: {e}")
