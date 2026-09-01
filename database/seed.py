"""Начальное заполнение базы данных"""
from sqlalchemy import select
from database.database import async_session
from database.models import Service, ServiceParameter, ContentBlock
from services.content_service import ensure_all_content
from database.seed_nails import nails_parameters, reseed_nails_flow


async def seed_data():
    async with async_session() as session:
        result = await session.execute(select(Service).limit(1))
        if result.scalar_one_or_none():
            await ensure_all_content(session)
            await reseed_nails_flow(session)
            return

        nails = Service(
            code="nails",
            name="Ноготочки (маникюр)",
            description="Классический и аппаратный маникюр с покрытием",
            base_duration_minutes=0,
            base_price=0.0,
            calendar_color_id="6",
            has_complex_flow=True,
            sort_order=1,
        )
        pedicure = Service(
            code="pedicure",
            name="Педикюр",
            description="Аппаратный педикюр с покрытием",
            base_duration_minutes=90,
            base_price=2800.0,
            calendar_color_id="9",
            has_complex_flow=False,
            sort_order=2,
        )
        lashes = Service(
            code="lashes",
            name="Реснички",
            description="Наращивание и ламинирование ресниц",
            base_duration_minutes=120,
            base_price=3500.0,
            calendar_color_id="3",
            has_complex_flow=False,
            sort_order=3,
        )
        session.add_all([nails, pedicure, lashes])
        await session.flush()

        params = nails_parameters(nails.id)
        session.add_all(params)

        contents = [
            ContentBlock(
                code="price_list",
                title="Прайс",
                text=(
                    "<b>💰 Прайс-лист</b>\n\n"
                    "Ноготочки (маникюр) — от 1000 ₽\n"
                    "Педикюр — от 2800 ₽\n"
                    "Реснички — от 3500 ₽\n\n"
                    "Точная стоимость рассчитывается индивидуально."
                )
            ),
            ContentBlock(
                code="rules",
                title="Правила",
                text=(
                    "<b>📋 Правила записи и посещения</b>\n\n"
                    "1. Запись только через бота.\n"
                    "2. Отмена и перенос — не позднее чем за 2 дня.\n"
                    "3. Перенос — не больше чем на 10 дней и не чаще 1 раза в месяц.\n"
                    "4. Предоплата 400 ₽. При переносе в срок — ещё 400 ₽, входит в стоимость, если придёшь.\n"
                    "5. При отмене позже срока предоплата не возвращается.\n"
                    "6. При опоздании более 15 мин мастер может отказать в услуге."
                )
            ),
            ContentBlock(
                code="socials",
                title="Мои Telegram-каналы и соцсети",
                text=(
                    "<b>📱 Мои каналы и соцсети</b>\n\n"
                    "Telegram-канал: @your_channel\n"
                    "Instagram: @your_instagram\n"
                    "VK: vk.com/your_page"
                )
            ),
            ContentBlock(
                code="first_time",
                title="Для тех, кто идёт впервые",
                text=(
                    "<b>✨ Для тех, кто идёт впервые</b>\n\n"
                    "• Сними украшения с рук перед процедурой.\n"
                    "• При аллергии на материалы — сообщи заранее.\n"
                    "• Процедура длится от 1 до 3+ часов.\n"
                    "• Можно взять наушники / книгу / планшет.\n"
                    "• В студии есть Wi-Fi и розетки."
                )
            ),
            ContentBlock(
                code="nail_shapes",
                title="Про формы ногтей",
                text=(
                    "<b>💅 Про формы ногтей</b>\n\n"
                    "• Квадрат / мягкий квадрат\n"
                    "• Овал\n"
                    "• Миндаль\n"
                    "• Стилет\n"
                    "• Балерина\n\n"
                    "Форму обсуждаем на месте."
                )
            ),
            ContentBlock(
                code="payment_details",
                title="Реквизиты для предоплаты",
                text=(
                    "<b>💳 Реквизиты для предоплаты</b>\n\n"
                    "Сбер: 0000 0000 0000 0000\n"
                    "Получатель: Имя Ф.\n\n"
                    "После перевода отправь скрин или напиши, от кого перевод."
                )
            ),
            ContentBlock(
                code="surcharge_legend",
                title="Легенда доплат за слоты",
                text=(
                    "<b>📌 Про особые окошки</b>\n\n"
                    "🔥 — доплата +300 ₽ (воскресенье / праздник)\n"
                    "⭐ — доплата +100 ₽\n\n"
                    "Обычные окошки без метки — без доплаты."
                )
            ),
        ]
        session.add_all(contents)
        await session.commit()
        await ensure_all_content(session)
        print("База данных успешно заполнена.")
