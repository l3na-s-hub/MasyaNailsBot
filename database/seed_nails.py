"""Параметры маникюра — флоу v5."""
from sqlalchemy import select, delete
from database.models import Service, ServiceParameter

FLOW_VERSION = "v7_repair"


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
    add("procedure", t, "no_coating", "Маникюр без покрытия", 0, 0, 2)
    add("procedure", t, "repair", "Ремонт", 0, 0, 3)

    # 2. Без покрытия — 4 услуги → сразу окошки
    t2 = "На что именно записываемся?"
    add("without_type", t2, "manicure", "Маникюр", 80, 600, 1)
    add("without_type", t2, "removal", "Снятие без маникюра", 30, 500, 2)
    add("without_type", t2, "removal_manicure", "Снятие + маникюр", 60, 700, 3)
    add("without_type", t2, "removal_strengthen", "Снятие + укрепление", 75, 1000, 4)

    # 3. Есть покрытие сейчас?
    t3 = "Есть ли сейчас покрытие на ногтях?"
    add("has_coating", t3, "yes", "Да", 20, 0, 1)
    add("has_coating", t3, "no", "Нет", 0, 0, 2)

    # 4. Особенности текущего покрытия (если да)
    t4 = (
        "Какие особенности покрытия сейчас?\n\n"
        "• До 4 длины, без проблем (кроме отслоек)\n"
        "• Было наращивание на типсах\n"
        "• Длинные / толстое покрытие от другого мастера\n"
        "• Трещины, суперклей, много фигурок"
    )
    add("nails_condition", t4, "normal",
        "До 4 длины, без проблем (кроме отслоек)", 0, 0, 1)
    add("nails_condition", t4, "tips",
        "Было наращивание на типсах", 30, 500, 2)
    add("nails_condition", t4, "long_thick",
        "Длинные / толстое покрытие от другого мастера", 40, 700, 3)
    add("nails_condition", t4, "problems",
        "Трещины / суперклей / много фигурок", 50, 800, 4)

    # 5. Когти
    t5 = "Делаем ли когти?"
    add("claws", t5, "no", "Нет", 0, 0, 1)
    add("claws", t5, "up_to_4", "Да, до 4 длины", 35, 200, 2)
    add("claws", t5, "from_4", "Да, 4 длины или больше", 60, 300, 3)

    # 6. Какое покрытие делаем
    t6 = "Какое покрытие делаем?"
    add("coating_type", t6, "natural", "На свои натуральные короткие ногти", 30, 2000, 1)
    add("coating_type", t6, "build", "Наращивание / коррекция", 0, 0, 2)

    # 7. Длина (если наращивание)
    t7 = "Какую длину делаем?"
    add("length", t7, "1", "1 длина", 40, 200, 1)
    add("length", t7, "2", "2 длина", 60, 230, 2)
    add("length", t7, "3", "3 длина", 70, 800, 3)
    add("length", t7, "4", "4 длина", 85, 1200, 4)
    add("length", t7, "5", "5 длина", 105, 3400, 5)
    add("length", t7, "6", "6 длина", 120, 3400, 6)
    add("length", t7, "7", "7 длина", 140, 4400, 7)
    add("length", t7, "8", "8 длина", 40, 0, 8)
    add("length", t7, "mixed", "Одна короткая, другая длинная", 40, 0, 9)
    add("length", t7, "photo", "📷 Отправить фото длины", 0, 0, 10, photo=True)

    # 8. Дизайн
    t8 = "Нужен ли дизайн?"
    add("design", t8, "none", "Без дизайна", 0, 0, 1)
    add("design", t8, "solid", "Однотон", 0, 0, 2)
    add("design", t8, "gel_vtira", "Однотон гель-лаком / втиркой", 25, 100, 3)
    add("design", t8, "light", "Лёгкий дизайн / френч", 25, 600, 4)
    add("design", t8, "medium", "Средний дизайн", 40, 900, 5)
    add("design", t8, "complex", "Сложный дизайн", 60, 1500, 6)
    add("design", t8, "photo", "📷 Не знаю — отправить фото", 0, 0, 7, photo=True)

    # 9. Общение
    t9 = "Формат общения во время процедуры"
    add("communication", t9, "silent", "Предпочитаю молчать", 0, 0, 1)
    add("communication", t9, "light", "Мелкий непринуждённый разговор", 0, 0, 2)
    add("communication", t9, "chatty", "Люблю пообщаться", 0, 0, 3)
    add("communication", t9, "full", "Всё обсудить, поесть, посмотреть", 15, 0, 4)

    return p


async def reseed_nails_flow(session):
    """Пересоздаёт параметры под v5."""
    result = await session.execute(select(Service).where(Service.code == "nails"))
    nails = result.scalar_one_or_none()
    if not nails:
        return
    # маркер v5: есть nails_condition и coating_type без strengthen
    # v6: natural с +2000 и option 8 длины, gel_vtira в дизайне
    result = await session.execute(
        select(ServiceParameter).where(
            ServiceParameter.service_id == nails.id,
            ServiceParameter.step_code == "procedure",
            ServiceParameter.option_code == "repair",
        ).limit(1)
    )
    if result.scalar_one_or_none():
        return

    nails.base_duration_minutes = 0
    nails.base_price = 0.0
    await session.execute(
        delete(ServiceParameter).where(ServiceParameter.service_id == nails.id)
    )
    session.add_all(nails_parameters(nails.id))
    await session.commit()
    print("Маникюр: флоу v7 (+ ремонт → сразу дата)")
