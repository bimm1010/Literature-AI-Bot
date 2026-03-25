from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from bot.database import db

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    # Dùng nội dung phía sau /start làm prompt
    prompt_text = message.text.replace("/start", "").strip()
    
    if prompt_text:
        await db.set_prompt(message.from_user.id, prompt_text)
        await message.reply(
            "✅ Đã lưu yêu cầu chấm điểm của bạn! Từ giờ bạn cứ gửi ảnh bài thi, bot sẽ chấm theo chuẩn này.\n\n"
            "Nếu muốn đổi yêu cầu, soạn lại `/start <yêu cầu mới>`.\n"
            "Nếu muốn xoá, soạn `/clear`.",
            parse_mode="Markdown"
        )
    else:
        current_prompt = await db.get_prompt(message.from_user.id)
        if current_prompt:
            await message.reply(
                f"🤖 Bot đang hoạt động với yêu cầu chấm điểm hiện tại:\n\n`{current_prompt}`\n\n"
                "Bạn có thể gửi ảnh bài kiểm tra để bot chấm ngay, hoặc soạn `/start <yêu cầu mới>` để thay đổi.",
                parse_mode="Markdown"
            )
        else:
            await message.reply(
                "👋 Chào bạn! Để bắt đầu, hãy gửi lệnh `/start <yêu cầu chấm điểm của bạn>` "
                "để cài đặt tiêu chí chấm bài thi Ngữ Văn nhé.\n\nVí dụ:\n"
                "`/start Hãy chấm điểm bài văn này, tìm các lỗi chính tả, lỗi hành văn và đưa ra nhận xét chung.`",
                parse_mode="Markdown"
            )

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    await db.clear_prompt(message.from_user.id)
    await message.reply("🗑️ Đã xoá yêu cầu chấm điểm! Hãy dùng `/start <yêu cầu mới>` để thiết lập lại.")

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📖 **DANH SÁCH LỆNH CỦA BOT CHẤM VĂN**\n\n"
        "1️⃣  `/start <yêu cầu>` : Cài đặt tiêu chí chấm bài. \n"
        "   *Ví dụ: /start Chấm điểm và tìm lỗi chính tả.*\n"
        "2️⃣  `/start` : Kiểm tra yêu cầu chấm bài hiện tại của bạn.\n"
        "3️⃣  `/clear` : Xoá yêu cầu cũ để cài lại từ đầu.\n"
        "4️⃣  `/help` : Xem danh sách hướng dẫn này.\n\n"
        "🖼️ **CÁCH CHẤM BÀI:**\n"
        "Sau khi dùng `/start`, bạn chỉ cần gửi ảnh (hoặc album ảnh) vào đây. Bot sẽ tự động chấm toàn bộ bài làm của bạn! 🚀"
    )
    await message.reply(help_text, parse_mode="Markdown")
