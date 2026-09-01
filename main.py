import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database.database import init_db
from database.seed import seed_data
from handlers import start, booking, info, manage, admin
from services.reminder_service import send_reminders, send_day_confirms
from services.expire_service import expire_pending_payments
from services.backup_service import create_backup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    await init_db()
    await seed_data()
    create_backup()  # стартовый бэкап
    logger.info("Database initialized, seeded, backup created")


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(info.router)
    dp.include_router(manage.router)
    dp.include_router(admin.router)

    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
    scheduler.add_job(send_reminders, "interval", minutes=1, args=[bot])
    scheduler.add_job(send_day_confirms, "interval", minutes=30, args=[bot])
    scheduler.add_job(expire_pending_payments, "interval", minutes=1, args=[bot])
    # Автобэкап раз в 3 дня
    scheduler.add_job(create_backup, "interval", days=3)
    scheduler.start()

    dp.startup.register(on_startup)

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
