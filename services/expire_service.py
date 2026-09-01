"""Автоотмена записей без предоплаты."""
import logging
from aiogram import Bot
from database.database import async_session
from services.booking_service import BookingService
from config import settings

logger = logging.getLogger(__name__)


async def expire_pending_payments(bot: Bot):
    mins = getattr(settings, "PREPAYMENT_TIMEOUT_MINUTES", 20)
    async with async_session() as session:
        svc = BookingService(session)
        expired = await svc.expire_unpaid_pending(minutes=mins)
        items = []
        for b in expired:
            items.append({
                "id": b.id,
                "tg": b.user.telegram_id if b.user else None,
                "service": b.service.name if b.service else "услуга",
                "date": b.booking_date.strftime("%d-%m-%Y"),
                "time": b.start_time.strftime("%H:%M"),
            })

    for it in items:
        if it["tg"]:
            try:
                await bot.send_message(
                    it["tg"],
                    f"⏳ Время на предоплату вышло ({mins} мин).\n"
                    f"Запись на {it['service']} {it['date']} в {it['time']} отменена, "
                    f"окошко снова свободно.\n"
                    f"Можешь записаться заново через меню.",
                )
            except Exception as e:
                logger.warning(f"expire notify client: {e}")
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⏳ Автоотмена #{it['id']}: нет предоплаты за {mins} мин\n"
                    f"{it['service']} · {it['date']} {it['time']}",
                )
            except Exception:
                pass
        logger.info(f"Expired unpaid booking #{it['id']}")
