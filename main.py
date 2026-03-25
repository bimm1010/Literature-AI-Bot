import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN
from bot.database import db
from bot.handlers import commands, messages

logging.basicConfig(level=logging.INFO)

async def main():
    # Khởi tạo SQLite Asynchronous
    await db.init_db()

    # Khởi tạo Bot Telegram
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Thiết lập Menu Lệnh (Bot Command Menu)
    commands_list = [
        BotCommand(command="start", description="Cài đặt/Xem tiêu chí chấm điểm"),
        BotCommand(command="clear", description="Xoá tiêu chí cũ"),
        BotCommand(command="help", description="Xem hướng dẫn sử dụng")
    ]
    await bot.set_my_commands(commands_list)

    # Đăng ký các router xử lý luồng sự kiện
    dp.include_router(commands.router)
    dp.include_router(messages.router)

    # Bắt đầu chạy vòng lặp bắt sự kiện
    print("🤖 Literature AI Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
