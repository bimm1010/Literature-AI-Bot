import config
import os
import uuid
import asyncio
import asyncio.subprocess
import logging

# Lấy đường dẫn CLI từ config (mặc định là "gemini")
# Khuyến khích Đại ca dùng đường dẫn tuyệt đối trong .env 
# Ví dụ: GEMINI_CLI_COMMAND=/opt/homebrew/bin/gemini
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

async def grade_via_cli(image_list: list[bytes], user_prompt: str) -> str:
    """Gọi Gemini qua CLI bằng cách lưu danh sách ảnh tạm và dùng cú pháp @file."""
    if not os.path.exists(config.TEMP_IMAGE_DIR):
        os.makedirs(config.TEMP_IMAGE_DIR)
        
    temp_paths = []
    
    try:
        # 1. Lưu các ảnh tạm
        file_references = []
        for img_bytes in image_list:
            temp_filename = f"{uuid.uuid4()}.jpg"
            temp_path = os.path.abspath(os.path.join(config.TEMP_IMAGE_DIR, temp_filename))
            with open(temp_path, "wb") as f:
                f.write(img_bytes)
            temp_paths.append(temp_path)
            file_references.append(f"@{temp_path}")
            
        # 2. Xây dựng prompt kèm danh sách file @path
        full_prompt = f"{user_prompt} {' '.join(file_references)}"
        
        logging.info(f"🚀 Bắt đầu gọi CLI ({GEMINI_BIN}) cho {len(image_list)} ảnh...")
        
        # Xây dựng danh sách tham số
        cmd_args = [GEMINI_BIN]
        
        # Chỉ thêm flag model nếu được cấu hình (để tránh 404 như flash)
        model_name = os.getenv("GEMINI_MODEL")
        if model_name:
            cmd_args.extend(["-m", model_name])
            
        cmd_args.extend([
            "-p", full_prompt,
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
            # Tăng giới hạn lên 300 giây (5 phút) vì bài thi nhiều ảnh tốn thời gian upload
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            logging.error("❌ CLI bị timeout sau 300s!")
            try:
                process.kill()
            except:
                pass
            raise Exception("AI CLI timeout after 300 seconds (Quá trình tải/chấm ảnh mất quá nhiều thời gian)")
        
        if process.returncode == 0:
            result = stdout.decode().strip()
            logging.info("✅ CLI phản hồi thành công!")
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
        # 3. Luôn dọn dẹp tất cả ảnh tạm
        for path in temp_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

async def grade_literature_test(image_list: list[bytes], user_prompt: str) -> str:
    """Gửi danh sách ảnh + prompt tới Gemini CLI duy nhất."""
    
    # Kết hợp hướng dẫn hệ thống với yêu cầu của người dùng
    full_prompt = f"{SYSTEM_INSTRUCTIONS}\n{user_prompt}"
    
    try:
        return await grade_via_cli(image_list, full_prompt)
    except Exception as e:
        logging.error(f"❌ Lỗi xử lý CLI (Top Level): {e}")
        return f"❌ Hệ thống AI đang bận hoặc gặp sự cố: {str(e)}"
