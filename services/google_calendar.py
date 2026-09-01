import logging
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional

from config import settings, TZ, BASE_DIR

logger = logging.getLogger(__name__)
_service = None


def _creds_path() -> Path:
    p = Path(settings.GOOGLE_CREDENTIALS_FILE)
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def _get_service():
    global _service
    if _service is not None:
        return _service

    enabled = settings.GOOGLE_CALENDAR_ENABLED
    # pydantic иногда читает строку
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")

    if not enabled:
        logger.warning("Google Calendar: ВЫКЛЮЧЕН (GOOGLE_CALENDAR_ENABLED != true)")
        return None

    creds_path = _creds_path()
    cal_id = (settings.GOOGLE_CALENDAR_ID or "").strip()

    if not cal_id:
        logger.warning("Google Calendar: пустой GOOGLE_CALENDAR_ID")
        return None
    if not creds_path.exists():
        logger.warning(f"Google Calendar: нет файла ключа: {creds_path}")
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            str(creds_path),
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        _service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        logger.info(f"Google Calendar: OK, calendarId={cal_id}, creds={creds_path.name}")
        return _service
    except Exception as e:
        logger.exception(f"Google Calendar init ERROR: {e}")
        return None


def create_event(
    summary: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    description: str = "",
    color_id: str = "1",
) -> Optional[str]:
    service = _get_service()
    if not service:
        logger.warning("create_event: сервис календаря недоступен")
        return None
    cal_id = (settings.GOOGLE_CALENDAR_ID or "").strip()
    try:
        start_dt = TZ.localize(datetime.combine(booking_date, start_time))
        end_dt = TZ.localize(datetime.combine(booking_date, end_time))
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": settings.TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": settings.TIMEZONE},
            "colorId": str(color_id or "1"),
        }
        event = (
            service.events()
            .insert(calendarId=cal_id, body=body)
            .execute()
        )
        event_id = event.get("id")
        logger.info(f"Calendar event created: {event_id} on {cal_id}")
        return event_id
    except Exception as e:
        logger.exception(f"Calendar create ERROR (id={cal_id}): {e}")
        return None


def delete_event(event_id: str) -> bool:
    if not event_id:
        return False
    service = _get_service()
    if not service:
        return False
    cal_id = (settings.GOOGLE_CALENDAR_ID or "").strip()
    try:
        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
        logger.info(f"Calendar event deleted: {event_id}")
        return True
    except Exception as e:
        logger.exception(f"Calendar delete ERROR: {e}")
        return False


def test_connection() -> str:
    """Проверка подключения. Возвращает текст результата."""
    enabled = settings.GOOGLE_CALENDAR_ENABLED
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
    lines = [
        f"ENABLED = {settings.GOOGLE_CALENDAR_ENABLED}",
        f"CALENDAR_ID = {settings.GOOGLE_CALENDAR_ID!r}",
        f"CREDS = {_creds_path()} exists={_creds_path().exists()}",
    ]
    if not enabled:
        lines.append("→ Календарь выключен в .env")
        return "\n".join(lines)
    if not (settings.GOOGLE_CALENDAR_ID or "").strip():
        lines.append("→ Нет GOOGLE_CALENDAR_ID")
        return "\n".join(lines)
    if not _creds_path().exists():
        lines.append("→ Нет JSON-файла ключа")
        return "\n".join(lines)

    global _service
    _service = None
    service = _get_service()
    if not service:
        lines.append("→ Не удалось создать service (см. лог выше)")
        return "\n".join(lines)

    cal_id = settings.GOOGLE_CALENDAR_ID.strip()
    try:
        cal = service.calendars().get(calendarId=cal_id).execute()
        lines.append(f"→ Календарь найден: {cal.get('summary')}")
    except Exception as e:
        lines.append(f"→ НЕ МОЖЕТ прочитать календарь: {e}")
        lines.append("  Обычно: неверный ID или нет доступа у service account")
        return "\n".join(lines)

    try:
        from datetime import timedelta
        now = datetime.now(TZ)
        body = {
            "summary": "🧪 Тест бота записи",
            "description": "Можно удалить",
            "start": {
                "dateTime": (now + timedelta(hours=1)).isoformat(),
                "timeZone": settings.TIMEZONE,
            },
            "end": {
                "dateTime": (now + timedelta(hours=2)).isoformat(),
                "timeZone": settings.TIMEZONE,
            },
        }
        event = service.events().insert(calendarId=cal_id, body=body).execute()
        eid = event.get("id")
        lines.append(f"→ Тестовое событие создано: {eid}")
        service.events().delete(calendarId=cal_id, eventId=eid).execute()
        lines.append("→ Тестовое событие удалено — ВСЁ РАБОТАЕТ")
    except Exception as e:
        lines.append(f"→ Не может СОЗДАТЬ событие: {e}")
        lines.append("  Нужны права «Изменять мероприятия», не только просмотр")
    return "\n".join(lines)
