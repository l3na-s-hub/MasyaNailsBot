from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List
import pytz

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    BOT_TOKEN: str = "YOUR_BOT_TOKEN_HERE"
    ADMIN_IDS: List[int] = [123456789]

    DATABASE_URL: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'bot.db').as_posix()}"

    TIMEZONE: str = "Europe/Moscow"
    REMINDER_HOURS_BEFORE: int = 3

    DEFAULT_WORK_START: str = "08:00"
    DEFAULT_WORK_END: str = "20:00"
    SLOT_INTERVAL_MINUTES: int = 30

    # Ожидание ответа админа по фото (минуты)
    ADMIN_PHOTO_WAIT_MINUTES: int = 5
    MASTER_USERNAME: str = "@masya_slivch"
    CANCEL_FREE_HOURS: int = 48  # 2 дня
    RESCHEDULE_MAX_DAYS: int = 10
    PREPAYMENT_AMOUNT: int = 400
    PREPAYMENT_TIMEOUT_MINUTES: int = 20  # автоотмена без предоплаты

    # Google Calendar (опционально)
    # 1. Создай Service Account в Google Cloud
    # 2. Скачай JSON-ключ, положи как data/google_credentials.json
    # 3. Расшарь календарь на email сервис-аккаунта (право «вносить изменения»)
    # 4. Укажи ID календаря (обычно твой email или ID из настроек календаря)
    GOOGLE_CREDENTIALS_FILE: str = str(DATA_DIR / "google_credentials.json")
    GOOGLE_CALENDAR_ID: str = ""  # например primary или xxx@group.calendar.google.com
    GOOGLE_CALENDAR_ENABLED: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
TZ = pytz.timezone(settings.TIMEZONE)
