from datetime import time


def parse_time(value: str) -> time:
    """Безопасный парсинг времени. Поддерживает '9:00' и '09:00'."""
    value = value.strip()
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    return time(hour=hour, minute=minute)


def format_time(t: time) -> str:
    return t.strftime("%H:%M")
