from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from keyboards.main import main_menu_kb, main_reply_kb, BTN_BOOK, BTN_MANAGE, BTN_INFO, info_menu_kb
from database.database import async_session
from services.booking_service import BookingService
from services.content_service import ContentService

router = Router(name="start")


async def _welcome_text(session) -> str:
    return await ContentService(session).get_text("msg_welcome")


async def _main_text(session) -> str:
    return await ContentService(session).get_text("msg_main_menu")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        svc = BookingService(session)
        await svc.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        text = await _welcome_text(session)
        main_t = await _main_text(session)
        content = ContentService(session)
        block = await content.get_by_code("msg_welcome")
        media_id = block.media_file_id if block else None
        media_type = block.media_type if block else None

    await message.answer(text, reply_markup=main_reply_kb(), parse_mode="HTML")
    if media_id and media_type == "photo":
        try:
            await message.answer_photo(media_id)
        except Exception:
            pass
    elif media_id and media_type == "video":
        try:
            await message.answer_video(media_id)
        except Exception:
            pass
    await message.answer(main_t, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        main_t = await _main_text(session)
    await message.answer(main_t, reply_markup=main_reply_kb(), parse_mode="HTML")
    await message.answer("Разделы:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "menu:main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        main_t = await _main_text(session)
    try:
        await callback.message.edit_text(main_t, reply_markup=main_menu_kb(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(main_t, reply_markup=main_menu_kb(), parse_mode="HTML")
    await callback.message.answer("👇 Меню внизу всегда доступно", reply_markup=main_reply_kb())
    await callback.answer()


@router.message(F.text == BTN_BOOK)
async def reply_book(message: Message, state: FSMContext):
    from handlers.booking import start_booking_from_message
    await start_booking_from_message(message, state)


@router.message(F.text == BTN_MANAGE)
async def reply_manage(message: Message, state: FSMContext):
    from handlers.manage import manage_from_message
    await manage_from_message(message, state)


@router.message(F.text == BTN_INFO)
async def reply_info(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "ℹ️ Дополнительная информация. Выбери раздел:",
        reply_markup=info_menu_kb()
    )


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()
