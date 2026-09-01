from datetime import date, time, datetime, timedelta


def format_duration(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours} ч {mins} мин"
    elif hours:
        return f"{hours} ч"
    return f"{mins} мин"


def format_price(price: float) -> str:
    return f"{int(price)} ₽"


def format_datetime_range(d: date, start: time, end: time) -> str:
    date_str = d.strftime("%d-%m-%Y")
    return f"{date_str} с {start.strftime('%H:%M')} до {end.strftime('%H:%M')}"


def format_booking_summary(
    service_name: str,
    duration: int,
    price: float,
    booking_date: date | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
    params_text: str = ""
) -> str:
    lines = [
        f"<b>Услуга:</b> {service_name}",
        f"<b>Длительность:</b> {format_duration(duration)}",
        f"<b>Стоимость:</b> {format_price(price)}",
    ]
    if params_text:
        lines.append(f"\n{params_text}")
    if booking_date and start_time and end_time:
        lines.append(f"\n<b>Дата и время:</b> {format_datetime_range(booking_date, start_time, end_time)}")
    return "\n".join(lines)


STEP_LABELS_RU = {
    "procedure": "Процедура",
    "has_coating": "Текущее покрытие",
    "coating_type": "Тип покрытия",
    "without_type": "Без покрытия",
    "length": "Длина",
    "claws": "Когти",
    "communication": "Общение",
    "design": "Дизайн",
}


def format_selected_params(selected_params) -> str:
    """Человекочитаемые параметры записи из JSON selected_params."""
    if not selected_params or not isinstance(selected_params, dict):
        return ""
    texts = selected_params.get("texts")
    if not texts or not isinstance(texts, dict):
        # fallback: codes only
        codes = selected_params.get("codes") or selected_params
        if not isinstance(codes, dict):
            return ""
        lines = [f"• {STEP_LABELS_RU.get(k, k)}: {v}" for k, v in codes.items() if k != "contact"]
        return "\n".join(lines)
    lines = []
    for step, val in texts.items():
        if step == "contact":
            continue
        label = STEP_LABELS_RU.get(step, step)
        lines.append(f"• <b>{label}:</b> {val}")
    return "\n".join(lines)
