import config
import os
import uuid
import asyncio
import asyncio.subprocess
import logging
import google.generativeai as genai

# Lấy đường dẫn CLI từ config (mặc định là "gemini")
# Khuyến khích Đại ca dùng đường dẫn tuyệt đối trong .env 
GEMINI_BIN = config.GEMINI_CLI_COMMAND

SYSTEM_INSTRUCTIONS = """
Bạn là một trợ lý ảo chuyên nghiệp giúp giáo viên chấm bài văn của học sinh. 
Hãy phân tích hình ảnh bài làm và phản hồi theo định dạng sau (sử dụng icon sinh động):

🏆 **TỔNG ĐIỂM:** [Điểm]/10

📝 **NHẬN XÉT CHUNG:** 
[Tóm tắt ưu nhược điểm chính của bài làm]

🛠 **CHI TIẾT CÁC LỖI CẦN LƯU Ý:**
- ❌ **Chính tả:** [Từ sai] ➡ [Từ đúng] (giải thích ngắn gọn nếu cần)
- 💡 **Cách hành văn:** "[Cụm từ/Câu chưa hay]" ➡ "[Gợi ý sửa lại cho hay hơn]"
- 📍 **Ngữ pháp/Dấu câu:** [Lỗi nếu có]

✨ **ƯU ĐIỂM:**
- [Liệt kê các điểm tốt]

🚀 **GÓP Ý CẢI THIỆN:**
- [Lời khuyên để học sinh làm tốt hơn lần sau]

Lưu ý: Luôn phản hồi bằng tiếng Việt chân thành, khích lệ nhưng vẫn công tâm và chính xác.
Dưới đây là yêu cầu cụ thể của giáo viên:
"""

OCR_PROMPT = """
Bạn là một hệ thống Trích xuất Văn bản (OCR) siêu việt. 
Nhiệm vụ của bạn là bóc tách toàn bộ chữ viết tay của học sinh trong các bức ảnh bài thi này.
Yêu cầu:
1. Trích xuất CHÍNH XÁC đến từng chữ, sai chính tả ghi nguyên văn chữ sai.
2. KHÔNG bình luận, KHÔNG sửa lỗi, KHÔNG thêm bớt bất cứ chữ nào.
3. Chỉ trả về kết quả là phần chữ đọc được, định dạng y hệt như học sinh viết (xuống dòng, thụt lề).
"""

_current_key_idx = 0
_current_model_idx = 0

FALLBACK_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

async def extract_text_via_sdk(image_list: list[bytes]) -> str:
    """Bước 1: Mắt thần đọc chữ từ ảnh (SDK) với cơ chế đảo Key vòng lặp và đổi Model."""
    global _current_key_idx, _current_model_idx
    keys = config.GEMINI_API_KEYS
    if not keys:
        raise Exception("Không có API key nào được cấu hình trong GEMINI_API_KEYS")
        
    parts = [OCR_PROMPT]
    for img_bytes in image_list:
        parts.append({
            "mime_type": "image/jpeg",
            "data": img_bytes
        })

    max_attempts = len(keys) * len(FALLBACK_MODELS)
    attempts = 0
    
    while attempts < max_attempts:
        api_key = keys[_current_key_idx]
        model_name = FALLBACK_MODELS[_current_model_idx]
        
        logging.info(f"🔄 Đang bóc chữ (OCR) với model {model_name} (Key Index: {_current_key_idx + 1}/{len(keys)})")
        genai.configure(api_key=api_key)
        
        try:
            model = genai.GenerativeModel(model_name)
            response = await asyncio.to_thread(model.generate_content, parts)
            
            if response.text:
                logging.info(f"✅ OCR bóc chữ thành công!")
                return response.text.strip()
            else:
                raise Exception("Phản hồi bóc chữ rỗng từ API")
                
        except Exception as e:
            logging.warning(f"⚠️ Lỗi OCR (Key {_current_key_idx}, Model {model_name}): {e}")
            attempts += 1
            
            _current_model_idx = (_current_model_idx + 1) % len(FALLBACK_MODELS)
            if _current_model_idx == 0:
                _current_key_idx = (_current_key_idx + 1) % len(keys)
                
            if attempts < max_attempts:
                await asyncio.sleep(2)
            
    raise Exception("❌ Đã thử toàn bộ API Keys và Model nhưng chức năng Đọc chữ (OCR) thất bại!")

async def grade_via_cli(extracted_text: str, user_prompt: str) -> str:
    """Bước 2: Phân tích bài làm qua CLI (Chỉ đẩy Text, KHÔNG cần up lại ảnh)."""
    
    # Text dài quá cần gói vào file tạm cho CLI đọc đỡ bị lỗi quá tải tham số
    # CLI hỗ trợ đọc từ file text qua stdin hoặc qua một file tạm.
    # Để an toàn nhất với số lượng text lớn (hàng ngàn chữ), mình lưu file tạm.
    
    if not os.path.exists(config.TEMP_IMAGE_DIR):
        os.makedirs(config.TEMP_IMAGE_DIR)
        
    temp_txt_path = os.path.abspath(os.path.join(config.TEMP_IMAGE_DIR, f"{uuid.uuid4()}.txt"))
    
    # Nạp cả yêu cầu của hệ thống, giáo viên và nội dung bài làm của học trò
    full_prompt_content = (
        f"{SYSTEM_INSTRUCTIONS}\n"
        f"--- YÊU CẦU CỦA GIÁO VIÊN ---\n{user_prompt}\n\n"
        f"--- BÀI LÀM CỦA HỌC SINH (TEXT ĐÃ BÓC TÁCH) ---\n{extracted_text}"
    )
    
    try:
        with open(temp_txt_path, "w", encoding="utf-8") as f:
            f.write(full_prompt_content)
            
        logging.info(f"🚀 Bắt đầu gọi CLI chấm điểm ({GEMINI_BIN}) cho bài làm đã trích xuất...")
        
        cmd_args = [GEMINI_BIN]
        model_name = os.getenv("GEMINI_MODEL")
        if model_name:
            cmd_args.extend(["-m", model_name])
            
        cmd_args.extend([
            # Thay vì truyền vào -p, ta dội thẳng cái file text kia là an toàn nhất.
            "-p", f"Vui lòng đọc yêu cầu và bài làm trong file này: @{temp_txt_path}",
            "--raw-output",
            "--accept-raw-output-risk"
        ])

        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            # 120s là quá đủ cho text (Ảnh nặng mới cần lên tới 300s)
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            logging.error("❌ CLI bị timeout sau 120s khi chấm thẻ Text!")
            try:
                process.kill()
            except:
                pass
            raise Exception("Chấm bài bằng Text mất quá nhiều thời gian (>120s)")
        
        if process.returncode == 0:
            result = stdout.decode().strip()
            logging.info("✅ CLI chấm thi qua Text thành công!")
            clean_result = "\n".join([
                line for line in result.splitlines() 
                if "cached credentials" not in line.lower() and "gemini cli" not in line.lower()
            ]).strip()
            return clean_result
        else:
            error_msg = stderr.decode().strip()
            logging.error(f"❌ CLI Error: {error_msg}")
            raise Exception(f"CLI Error: {error_msg}")
            
    finally:
        # Xoá file text tạm
        if os.path.exists(temp_txt_path):
            try:
                os.remove(temp_txt_path)
            except:
                pass

async def grade_literature_test(image_list: list[bytes], user_prompt: str) -> str:
    """Luồng Song kiếm hợp bích: Bước 1 (API Bóc chữ) -> Bước 2 (CLI Chấm bài)"""
    
    try:
        # BƯỚC 1: Bóc toàn bộ chữ từ ảnh thông qua SDK (không sợ lỗi timeout VPS vì có quay vòng)
        extracted_text = await extract_text_via_sdk(image_list)
        
        # BƯỚC 2: Nhồi hết đống text đó vào CLI để tư duy và chấm bài
        if config.USE_CLI:
            return await grade_via_cli(extracted_text, user_prompt)
        else:
            # Nếu đã tắt CLI ép cứng trong env, thì đành lấy SDK chấm bài học sinh luôn vậy.
            # (Phòng khi CLI bị đứt cáp gì đó)
            full_prompt = f"{SYSTEM_INSTRUCTIONS}\n{user_prompt}\n\nDưới đây là bài làm dạng văn bản:\n{extracted_text}"
            return await grade_via_cli_fallback(extracted_text, user_prompt)

    except Exception as e:
        logging.error(f"❌ Song kiếm hợp bích gặp trục trặc: {e}")
        return f"❌ Hệ thống AI đang bận hoặc gặp lỗi cấu hình: {str(e)}"

# Hàm dự phòng "Siêu mỏng" để chấm bằng AI SDK khi CLI chết hẳn
async def grade_via_cli_fallback(extracted_text: str, user_prompt: str) -> str:
    # Lấy luôn code cũ SDK sang 1 hàm riêng mini phòng hờ
    keys = config.GEMINI_API_KEYS
    full_prompt = (
        f"{SYSTEM_INSTRUCTIONS}\n"
        f"--- YÊU CẦU CỦA GIÁO VIÊN ---\n{user_prompt}\n\n"
        f"--- BÀI LÀM CỦA HỌC SINH (TEXT ĐÃ BÓC TÁCH) ---\n{extracted_text}"
    )
    for model_name in FALLBACK_MODELS:
        for key in keys:
            genai.configure(api_key=key)
            try:
                model = genai.GenerativeModel(model_name)
                response = await asyncio.to_thread(model.generate_content, full_prompt)
                if response.text:
                    return response.text.strip()
            except:
                continue
    raise Exception("Không thể chấm qua cả CLI và SDK.")
