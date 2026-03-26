import asyncio
import logging
import os
import sys

# Add root directory to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

import config
from bot.services.ai_service import extract_text_via_openrouter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_ocr():
    print("🚀 Bắt đầu test OpenRouter OCR...")
    
    if not config.OPENROUTER_API_KEY or config.OPENROUTER_API_KEY == "your_openrouter_key_here":
        print("❌ Lỗi: Chưa cấu hình OPENROUTER_API_KEY trong .env")
        return

    # Thử bóc chữ từ ảnh test_blue.jpg có sẵn trong root
    image_path = os.path.join(root_dir, "test_blue.jpg")
    image_list = []
    
    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_list.append(f.read())
        print(f"📸 Đã nạp ảnh: {image_path}")
    else:
        print(f"⚠️ Không tìm thấy ảnh test: {image_path}. Chạy test với list rỗng.")
    
    test_model = "google/gemma-3-4b-it:free"
    print(f"📡 Đang thử model: {test_model}")
    config.OPENROUTER_MODEL = test_model
    try:
        result = await extract_text_via_openrouter(image_list)
        if result:
            print(f"✅ Kết quả trích xuất:\n{result}")
        else:
            print("⚠️ Không có text trả về (có thể do image_list rỗng hoặc API trả về trống)")
    except Exception as e:
        print(f"❌ Lỗi khi test: {e}")

if __name__ == "__main__":
    asyncio.run(test_ocr())
