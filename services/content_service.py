from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import ContentBlock

# Коды и дефолтные тексты всех редактируемых сообщений
DEFAULT_MESSAGES = {
    "msg_welcome": (
        "👋 Привет!\n\n"
        "Я помогу записаться на бьюти-услуги: маникюр, педикюр и реснички.\n\n"
        "Меню всегда внизу экрана — выбирай нужный раздел:"
    ),
    "msg_main_menu": "🏠 Главное меню\n\nВыбери раздел кнопками внизу или здесь:",
    "msg_choose_service": "💅 Выбери услугу:",
    "msg_ask_contact": "📱 Оставь контакт: @username или номер телефона",
    "msg_photo_received": (
        "✨ Отлично! Очень скоро я отвечу и выберу нужный вариант за тебя!\n"
        "Если передумала — можешь отменить запись и записаться заново."
    ),
    "msg_waiting_admin": (
        "⏳ Ещё жду ответа мастера. Если передумала — отмени в меню и запишись заново."
    ),
    "msg_payment_wait": (
        "✅ Получила! Жди подтверждения предоплаты мастером."
    ),
    "msg_booking_confirmed": (
        "<b>✅ Запись подтверждена!</b>\n\n"
        "{summary}\n\n"
        "Предоплата принята. Напоминание за 3 часа и подтверждение за сутки."
    ),
    "msg_payment_rejected": (
        "😔 Предоплата не подтверждена.\n"
        "Напиши мастеру или запишись заново."
    ),
    "msg_cancel_late": (
        "Отмена и перенос — не позднее чем за 2 дня.\n\n"
        "Сейчас до записи меньше 2 дней: предоплата (бронь) не возвращается.\n"
        "Чтобы записаться снова — нужна новая предоплата.\n\n"
        "Можешь написать {master}. Всё равно отменить?"
    ),
    "msg_cancel_ok": (
        "До записи 2 дня или больше.\n"
        "Можно отменить или перенести (перенос — не дальше чем на 10 дней, не чаще 1 раза в месяц).\n"
        "При переносе — ещё раз предоплата 400 ₽, она войдёт в стоимость, если придёшь.\n\n"
        "Что сделать?"
    ),
    "msg_reschedule_limit": (
        "Перенос возможен только на ближайшие 10 дней и не чаще 1 раза в месяц.\n"
        "Если нужна дата дальше — предоплата за текущую бронь не сохраняется.\n"
        "Напиши {master}, если есть вопросы."
    ),
    "msg_no_slots": "😔 Ой, окошек в ближайшее время нет(",
    "msg_admin_cancelled": (
        "❌ Твоя запись отменена мастером:\n{info}\n\n"
        "Если есть вопросы — напиши {master}."
    ),
    "msg_reminder": (
        "<b>⏰ Напоминание о записи</b>\n\n"
        "Через 3 часа:\n{details}\n\nЖдём тебя!"
    ),
    "msg_day_confirm": (
        "<b>📅 Подтверждение записи</b>\n\n"
        "Завтра у тебя запись:\n{details}\n\n"
        "Ты придёшь?\nОтветь, пожалуйста, в течение суток."
    ),
    "under_16": (
        "<b>🐣 Для тех, кому нет 16 лет</b>\n\n"
        "Текст можно изменить в админке."
    ),
    "not_doing": (
        "<b>🩹 Что я не делаю</b>\n\n"
        "Текст можно изменить в админке."
    ),
    "msg_payment_intro": (
        "<b>💳 Предоплата</b>\n\n"
        "{summary}\n"
        "📱 {contact}\n\n"
        "После перевода <b>отправь скрин</b> или напиши, <b>от кого перевод</b>."
    ),
}


class ContentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> ContentBlock | None:
        result = await self.session.execute(
            select(ContentBlock).where(ContentBlock.code == code)
        )
        return result.scalar_one_or_none()

    async def get_text(self, code: str, **kwargs) -> str:
        """Текст из БД или дефолт. Подставляет {placeholders}."""
        block = await self.get_by_code(code)
        text = block.text if block and block.text else DEFAULT_MESSAGES.get(code, code)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    async def get_block_or_default(self, code: str) -> tuple[str, str | None, str | None]:
        """Возвращает (text, media_file_id, media_type)."""
        block = await self.get_by_code(code)
        if block:
            return block.text, block.media_file_id, block.media_type
        return DEFAULT_MESSAGES.get(code, code), None, None

    async def get_all(self) -> list:
        result = await self.session.execute(select(ContentBlock).order_by(ContentBlock.id))
        return list(result.scalars().all())

    async def update_text(self, code: str, new_text: str) -> bool:
        block = await self.get_by_code(code)
        if not block:
            # создаём, если нет
            title = code
            for b in await self.get_all():
                pass
            titles = {
                **{k: k for k in DEFAULT_MESSAGES},
            }
            block = ContentBlock(code=code, title=titles.get(code, code), text=new_text)
            self.session.add(block)
        else:
            block.text = new_text
        await self.session.commit()
        return True

    async def update_media(self, code: str, file_id: str, media_type: str) -> bool:
        """Добавляет фото/видео к блоку (можно несколько)."""
        block = await self.get_by_code(code)
        item = {"file_id": file_id, "type": media_type}
        if not block:
            block = ContentBlock(
                code=code,
                title=code,
                text=DEFAULT_MESSAGES.get(code, ""),
                media_file_id=file_id,
                media_type=media_type,
                media_items=[item],
            )
            self.session.add(block)
        else:
            items = list(block.media_items or [])
            items.append(item)
            block.media_items = items
            # legacy single = первое
            block.media_file_id = items[0]["file_id"]
            block.media_type = items[0]["type"]
        await self.session.commit()
        return True

    async def clear_media(self, code: str) -> bool:
        block = await self.get_by_code(code)
        if not block:
            return False
        block.media_file_id = None
        block.media_type = None
        block.media_items = []
        await self.session.commit()
        return True

    def list_media(self, block: ContentBlock) -> list:
        """Список медиа [{file_id, type}, ...]."""
        if not block:
            return []
        if block.media_items:
            return list(block.media_items)
        if block.media_file_id:
            return [{"file_id": block.media_file_id, "type": block.media_type or "photo"}]
        return []


async def ensure_all_content(session: AsyncSession):
    """Добавляет недостающие блоки (для уже существующей БД)."""
    titles = {
        "price_list": "Прайс",
        "rules": "Правила",
        "socials": "Соцсети",
        "first_time": "Для тех, кто идёт впервые",
        "nail_shapes": "Про формы ногтей",
        "payment_details": "Реквизиты для предоплаты",
        "surcharge_legend": "Легенда доплат за слоты",
        "msg_welcome": "Приветствие (/start)",
        "msg_main_menu": "Главное меню",
        "msg_choose_service": "Выбор услуги",
        "msg_ask_contact": "Запрос контакта",
        "msg_photo_received": "После отправки фото",
        "msg_waiting_admin": "Ожидание ответа мастера",
        "msg_payment_wait": "Скрин предоплаты получен",
        "msg_booking_confirmed": "Запись подтверждена",
        "msg_payment_rejected": "Предоплата отклонена",
        "msg_cancel_late": "Отмена поздно (<2 дней)",
        "msg_cancel_ok": "Отмена/перенос вовремя",
        "msg_reschedule_limit": "Лимит переноса",
        "msg_no_slots": "Нет окошек / ЧС",
        "msg_admin_cancelled": "Мастер отменил запись",
        "msg_reminder": "Напоминание за 3 часа",
        "msg_day_confirm": "Подтверждение за сутки",
        "msg_payment_intro": "Вступление к предоплате",
        "under_16": "Для тех, кому нет 16 лет",
        "not_doing": "Что я не делаю",
        "msg_cancel_late": "Отмена поздно (<2 дней)",
        "msg_cancel_ok": "Отмена/перенос вовремя",
        "msg_reschedule_limit": "Лимит переноса",
        "msg_reschedule_limit": "Лимит переноса",
    }
    svc = ContentService(session)
    existing = {b.code for b in await svc.get_all()}
    for code, title in titles.items():
        if code not in existing:
            text = DEFAULT_MESSAGES.get(code, f"Текст «{title}»")
            session.add(ContentBlock(code=code, title=title, text=text))
    await session.commit()
