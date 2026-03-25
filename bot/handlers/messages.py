from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.utils.chat_action import ChatActionSender
import io
import logging
from bot.database import db
from bot.services import ai_service
import asyncio

router = Router()

# Lưu trữ tạm thời cho Media Groups (Album ảnh)
# media_group_id -> [photo_bytes, ...]
# media_group_id -> [photo.file_id, ...]
_media_groups: dict[str, list[str]] = {}
_media_group_timers: dict[str, asyncio.Task] = {}

@router.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    media_group_id = message.media_group_id
    
    user_prompt = await db.get_prompt(user_id)
    if not user_prompt:
        await message.reply(
            "⚠️ Bạn chưa thiết lập yêu cầu chấm điểm!\n"
            "Hãy dùng lệnh /start <yêu cầu của bạn> trước khi gửi ảnh nhé."
        )
        return

    # Trường hợp 1: Ảnh đơn lẻ (Single Photo)
    if not media_group_id:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            wait_msg = await message.reply("⏳ Đang tải ảnh và chuẩn bị chấm bài...")
            try:
                photo = message.photo[-1]
                image_data = await _download_with_retry(message.bot, photo.file_id)
                result = await ai_service.grade_literature_test([image_data], user_prompt)
                await _send_long_message(message, result)
                await wait_msg.delete()
            except Exception as e:
                logging.error(f"Lỗi xử lý ảnh đơn cho user {user_id}: {e}")
                await wait_msg.edit_text(f"❌ Xảy ra lỗi: {e}")
        return

    # Trường hợp 2: Ảnh trong Album (Media Group)
    # Gom File ID lại, việc download sẽ do task trung tâm xử lý
    if media_group_id not in _media_groups:
        _media_groups[media_group_id] = []
    
    _media_groups[media_group_id].append(message.photo[-1].file_id)

    # Hủy timer cũ nếu có (Sliding window)
    if media_group_id in _media_group_timers:
        _media_group_timers[media_group_id].cancel()
    
    # Tạo timer mới: Chờ 3 giây im lặng rồi mới xử lý
    _media_group_timers[media_group_id] = asyncio.create_task(
        _wait_and_process_group(message, media_group_id, user_prompt)
    )

async def _download_with_retry(bot, file_id, retries=3):
    """Tải file với cơ chế retry khi gặp lỗi mạng."""
    for i in range(retries):
        try:
            file_info = await bot.get_file(file_id)
            file_bytes = io.BytesIO()
            await bot.download_file(file_info.file_path, destination=file_bytes)
            return file_bytes.getvalue()
        except Exception as e:
            if i == retries - 1:
                raise e
            logging.warning(f"⚠️ Thử lại lần {i+1} tải file {file_id} do lỗi: {e}")
            await asyncio.sleep(1)

async def _wait_and_process_group(message: Message, group_id: str, prompt: str):
    """Đợi 3 giây im lặng để gom đủ ảnh rồi mới xử lý."""
    try:
        await asyncio.sleep(3.0)
        
        file_ids = _media_groups.pop(group_id, [])
        _media_group_timers.pop(group_id, None)
        
        if not file_ids:
            return

        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id, interval=4.0):
            total = len(file_ids)
            wait_msg = await message.reply(f"⏳ Đã gom đủ {total} trang bài làm. Đang tải ảnh...")
            
            try:
                # Tải toàn bộ ảnh
                images_data = []
                for idx, f_id in enumerate(file_ids):
                    await wait_msg.edit_text(f"⏳ Đang tải ảnh {idx+1}/{total} (Bot đang 'typing' để bạn yên tâm)...")
                    img = await _download_with_retry(message.bot, f_id)
                    images_data.append(img)
                
                await wait_msg.edit_text(f"⏳ Đang tiến hành chấm {total} trang bài làm... (Sẽ mất khoảng 30-60s)")
                result = await ai_service.grade_literature_test(images_data, prompt)
                await _send_long_message(message, result)
                await wait_msg.delete()
            except Exception as e:
                logging.error(f"Lỗi xử lý Media Group {group_id}: {e}")
                await wait_msg.edit_text(f"❌ Xảy ra lỗi khi chấm album: {e}")
    except asyncio.CancelledError:
        # Task bị hủy do có ảnh mới chèn vào, ignore
        pass

async def _send_long_message(message: Message, text: str):
    """Hỗ trợ gửi tin nhắn dài vượt quá hạn mức rủa Telegram."""
    if len(text) <= 4000:
        try:
            await message.reply(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await message.reply(text)
    else:
        for x in range(0, len(text), 4000):
            chunk = text[x:x+4000]
            try:
                await message.reply(chunk, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await message.reply(chunk)
