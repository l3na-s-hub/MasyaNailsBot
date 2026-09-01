from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto, InputMediaVideo

from keyboards.main import info_menu_kb, back_to_info_kb
from database.database import async_session
from services.content_service import ContentService

router = Router(name="info")


async def _safe_show_info_menu(callback: CallbackQuery):
    text = "ℹ️ Дополнительная информация. Выбери раздел:"
    kb = info_menu_kb()
    try:
        if callback.message.photo or callback.message.video or callback.message.document:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(text, reply_markup=kb)
        else:
            await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:info")
async def show_info_menu(callback: CallbackQuery):
    await _safe_show_info_menu(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("info:"))
async def show_content(callback: CallbackQuery):
    code = callback.data.split(":", 1)[1]
    async with async_session() as session:
        svc = ContentService(session)
        block = await svc.get_by_code(code)
        media = svc.list_media(block) if block else []
    if not block:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    text = block.text or ""
    kb = back_to_info_kb()

    try:
        try:
            await callback.message.delete()
        except Exception:
            pass

        if not media:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        elif len(media) == 1:
            m = media[0]
            if m.get("type") == "video":
                await callback.message.answer_video(
                    m["file_id"], caption=text[:1024], parse_mode="HTML", reply_markup=kb
                )
            else:
                await callback.message.answer_photo(
                    m["file_id"], caption=text[:1024], parse_mode="HTML", reply_markup=kb
                )
        else:
            # альбом: caption только у первого; кнопка «назад» отдельным сообщением
            group = []
            for i, m in enumerate(media[:10]):
                cap = text[:1024] if i == 0 else None
                if m.get("type") == "video":
                    group.append(InputMediaVideo(media=m["file_id"], caption=cap, parse_mode="HTML" if cap else None))
                else:
                    group.append(InputMediaPhoto(media=m["file_id"], caption=cap, parse_mode="HTML" if cap else None))
            await callback.message.answer_media_group(group)
            await callback.message.answer("⬆️", reply_markup=kb)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    await callback.answer()
