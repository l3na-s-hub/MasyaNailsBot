"""Параметры маникюра — флоу v3 (покрытие → тип → длина → форма → дизайн)."""
from sqlalchemy import select, delete
from database.models import Service, ServiceParameter

FLOW_VERSION = "v4_claws_comm"  # маркер для reseed


def nails_parameters(service_id: int) -> list:
    p = []

    def add(step, title, code, text, dur=0, price=0, order=0, photo=False):
        p.append(ServiceParameter(
            service_id=service_id, step_code=step, step_title=title,
            option_code=code, option_text=text,
            duration_modifier=dur, price_modifier=float(price),
            sort_order=order, requires_photo=photo,
        ))

    # 1. Процедура
    t = "Выбери процедуру:"
    add("procedure", t, "with_coating", "Маникюр с покрытием", 0, 0, 1)
    add("procedure", t, "no_coating", "Снятие / маникюр без покрытия", 80, 0, 2)

    # 2. Есть ли сейчас покрытие (только «с покрытием»)
    t2 = "Есть ли сейчас покрытие на ногтях?"
    add("has_coating", t2, "yes", "Да (нужно снятие)", 20, 0, 1)
    add("has_coating", t2, "no", "Нет", 0, 0, 2)

    # 3. Тип покрытия
    t3 = "Какое покрытие делаем?"
    add("coating_type", t3, "natural", "На свои ногти", 60, 0, 1)
    add("coating_type", t3, "strengthen", "С укреплением", 75, 300, 2)
    add("coating_type", t3, "build", "Наращивание", 0, 0, 3)

    # 4. Длина (только наращивание) — настраивается в админке
    t4 = "Какую длину делаем?"
    add("length", t4, "1", "1 длина", 40, 200, 1)
    add("length", t4, "2", "2 длина", 60, 230, 2)
    add("length", t4, "3", "3 длина", 70, 800, 3)
    add("length", t4, "4", "4 длина", 85, 1200, 4)
    add("length", t4, "5", "5 длина", 105, 3400, 5)
    add("length", t4, "6", "6 длина", 120, 3400, 6)
    add("length", t4, "7", "7 длина", 140, 4400, 7)
    add("length", t4, "short", "Короткая длина", 40, 0, 8)
    add("length", t4, "mixed", "Одна короткая, другая длинная (2-я без доплаты)", 40, 0, 9)

    # 5. Когти
    t5 = "Делаем ли когти?"
    add("claws", t5, "no", "Нет", 0, 0, 1)
    add("claws", t5, "up_to_4", "Да, до 4 длины", 35, 200, 2)
    add("claws", t5, "from_4", "Да, 4 длины или больше", 60, 300, 3)

    # 6. Дизайн
    t6 = "Нужен ли дизайн?"
    add("design", t6, "none", "Без дизайна", 0, 0, 1)
    add("design", t6, "solid", "Однотон", 0, 0, 2)
    add("design", t6, "light", "Лёгкий дизайн / френч", 25, 600, 3)
    add("design", t6, "medium", "Средний дизайн", 40, 900, 4)
    add("design", t6, "complex", "Сложный дизайн", 60, 1500, 5)
    add("design", t6, "photo", "📷 Не знаю — отправить фото", 0, 0, 6, photo=True)

    # 7. Общение
    t8 = "Формат общения во время процедуры"
    add("communication", t8, "silent", "Предпочитаю молчать", 0, 0, 1)
    add("communication", t8, "light", "Мелкий непринуждённый разговор", 0, 0, 2)
    add("communication", t8, "chatty", "Люблю пообщаться", 0, 0, 3)
    add("communication", t8, "full", "Всё обсудить, поесть, посмотреть", 15, 0, 4)

    # Ветка без покрытия — доп. уточнение (опционально)
    t7 = "Уточни, что именно нужно:"
    add("without_type", t7, "manicure", "Маникюр без покрытия", 0, 600, 1)
    add("without_type", t7, "removal", "Только снятие", 0, 500, 2)
    add("without_type", t7, "removal_manicure", "Снятие + маникюр", 0, 700, 3)
    add("without_type", t7, "removal_strengthen", "Снятие + укрепление (база)", 15, 1000, 4)

    return p


async def reseed_nails_flow(session):
    """Пересоздаёт параметры, если нет маркера нового флоу (step shape)."""
    result = await session.execute(select(Service).where(Service.code == "nails"))
    nails = result.scalar_one_or_none()
    if not nails:
        return
    # v4: есть claws и communication, нет shape
    result = await session.execute(
        select(ServiceParameter).where(
            ServiceParameter.service_id == nails.id,
            ServiceParameter.step_code == "claws",
        ).limit(1)
    )
    has_claws = result.scalar_one_or_none()
    result2 = await session.execute(
        select(ServiceParameter).where(
            ServiceParameter.service_id == nails.id,
            ServiceParameter.step_code == "shape",
        ).limit(1)
    )
    has_shape = result2.scalar_one_or_none()
    result3 = await session.execute(
        select(ServiceParameter).where(
            ServiceParameter.service_id == nails.id,
            ServiceParameter.step_code == "communication",
        ).limit(1)
    )
    has_comm = result3.scalar_one_or_none()
    if has_claws and has_comm and not has_shape:
        return
    nails.base_duration_minutes = 0
    nails.base_price = 0.0
    await session.execute(
        delete(ServiceParameter).where(ServiceParameter.service_id == nails.id)
    )
    session.add_all(nails_parameters(nails.id))
    await session.commit()
    print("Маникюр: флоу обновлён (v4 claws + communication)")
