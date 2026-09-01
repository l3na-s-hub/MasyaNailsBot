from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    choosing_service = State()
    has_coating = State()
    nails_condition = State()
    length = State()
    design = State()
    waiting_photo = State()
    waiting_admin_choice = State()  # ждём, пока админ выберет вариант по фото
    claws = State()
    communication = State()
    confirming_params = State()
    choosing_date = State()
    choosing_time = State()
    waiting_contact = State()
    waiting_payment = State()  # ждём скрин предоплаты
    waiting_payment_confirm = State()  # ждём подтверждения админа
    final_confirm = State()
    viewing_booking = State()
    cancelling_booking = State()
    rescheduling = State()


class AdminStates(StatesGroup):
    editing_content = State()
    waiting_content_text = State()
    adding_service = State()
    editing_service = State()
    waiting_service_field = State()
    managing_schedule = State()
    choosing_month = State()
    viewing_stats = State()
