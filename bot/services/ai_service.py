from typing import List, Dict, Optional
import config
import logging
import time
import asyncio
import threading
import io
import re
from PIL import Image
from google import genai
from google.genai import types

# ─────────────────────────────────────────────
# Key Rotator: Round-Robin + Auto-Skip on 429
# ─────────────────────────────────────────────

class KeyRotator:
    """Thread-safe round-robin key rotation with cooldown tracking."""

    def __init__(self, api_keys: List[str]):
        self._keys = api_keys
        self._index = 0
        self._lock = threading.Lock()
        self._cooldowns: Dict[str, float] = {}

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    def get_next_key(self) -> Optional[str]:
        """Get next available key (skips keys in cooldown)."""
        with self._lock:
            now = time.time()
            for _ in range(len(self._keys)):
                key = self._keys[self._index]
                self._index = (self._index + 1) % len(self._keys)
                if now >= self._cooldowns.get(key, 0):
                    return key
            soonest_key = min(self._keys, key=lambda k: self._cooldowns.get(k, 0))
            return soonest_key

    def mark_cooldown(self, key: str, duration: float = 60.0):
        with self._lock:
            self._cooldowns[key] = time.time() + duration
            logging.warning(f"🔑 Key ...{key[-6:]} cooldown {duration:.0f}s")

    def get_wait_time(self) -> float:
        with self._lock:
            now = time.time()
            soonest = min(self._cooldowns.get(k, 0) for k in self._keys)
            return max(0.0, soonest - now)


_rotator = KeyRotator(config.GEMINI_API_KEYS) if config.GEMINI_API_KEYS else None

# ─────────────────────────────────────────────
# System Instruction (tách riêng để Gemini cache)
# ─────────────────────────────────────────────

SYSTEM_INSTRUCTION = """Bạn là một trợ lý ảo chuyên nghiệp giúp giáo viên chấm bài văn của học sinh.
Hãy phân tích hình ảnh bài làm và phản hồi theo định dạng sau (sử dụng icon sinh động):

🏆 **TỔNG ĐIỂM:** [Điểm]/10

📝 **NHẬN XÉT CHUNG:**
[Tóm tắt ưu nhược điểm chính của bài làm]

🛠 **CHI TIẾT CÁC LỖI CẦN LƯU Ý:**
- ❌ **Chính tả:** [Từ sai] ➡ [Từ đúng]
- 💡 **Cách hành văn:** "[Câu chưa hay]" ➡ "[Gợi ý sửa]"
- 📍 **Ngữ pháp/Dấu câu:** [Lỗi nếu có]

✨ **ƯU ĐIỂM:**
- [Liệt kê các điểm tốt]

🚀 **GÓP Ý CẢI THIỆN:**
- [Lời khuyên để học sinh làm tốt hơn lần sau]

Luôn phản hồi bằng tiếng Việt chân thành, khích lệ nhưng công tâm và chính xác."""


# ─────────────────────────────────────────────
# Image Optimization
# ─────────────────────────────────────────────

MAX_IMAGE_DIMENSION = 1024  # px — đủ cho OCR chữ viết tay


def _optimize_image(img_bytes: bytes) -> bytes:
    """Resize ảnh xuống max 1024px và compress JPEG 85% → giảm 60-70% kích thước."""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        original_size = len(img_bytes)

        # Resize nếu ảnh quá lớn
        if max(img.size) > MAX_IMAGE_DIMENSION:
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

        # Convert to RGB (loại bỏ alpha channel nếu có)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Compress
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        optimized = buffer.getvalue()

        ratio = (1 - len(optimized) / original_size) * 100
        logging.info(f"📸 Ảnh {original_size // 1024}KB → {len(optimized) // 1024}KB (giảm {ratio:.0f}%)")
        return optimized
    except Exception as e:
        logging.warning(f"⚠️ Không thể optimize ảnh: {e}. Dùng ảnh gốc.")
        return img_bytes


# ─────────────────────────────────────────────
# Gemini Config: Tắt Thinking Mode cho tốc độ
# ─────────────────────────────────────────────

def _build_gen_config(model_name: str) -> types.GenerateContentConfig:
    """Build generation config — tắt thinking cho 2.5 models để tăng tốc."""
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.3,
    )
    # Tắt thinking mode trên gemini-2.5-* (mặc định bật → chậm 3-5x)
    if "2.5" in model_name:
        cfg.thinking_config = types.ThinkingConfig(thinking_budget=0)
    return cfg


# ─────────────────────────────────────────────
# Main Grading Function
# ─────────────────────────────────────────────

async def grade_literature_test(image_list: List[bytes], user_prompt: str) -> str:
    """Chấm bài qua Gemini API: Key Rotation + Model Fallback + Optimized Images."""
    if not _rotator or _rotator.total_keys == 0:
        return "❌ Lỗi: Chưa cấu hình GEMINI_API_KEYS trong file .env"

    # Optimize images (resize + compress) — chạy trong thread pool
    optimized_images = await asyncio.to_thread(
        lambda: [_optimize_image(img) for img in image_list]
    )

    user_content = f"Yêu cầu của giáo viên:\n{user_prompt}\n\nHãy phân tích ảnh bài làm và chấm điểm."

    # Build content: text prompt + optimized images
    contents = [user_content]
    for img_bytes in optimized_images:
        contents.append(
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
        )

    # Model fallback chain
    models_to_try = [config.GEMINI_MODEL, "gemini-2.0-flash", "gemini-2.0-flash-lite"]
    seen = set()
    models_to_try = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

    for model_name in models_to_try:
        gen_config = _build_gen_config(model_name)
        max_retries = _rotator.total_keys * 2
        attempt = 0

        while attempt < max_retries:
            api_key = _rotator.get_next_key()
            if not api_key:
                break

            wait_time = _rotator.get_wait_time()
            if wait_time > 0:
                logging.info(f"⏳ Tất cả key cooldown. Chờ {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)

            attempt += 1
            key_hint = f"...{api_key[-6:]}"
            try:
                logging.info(f"🔄 Key {key_hint} | {model_name} (thử {attempt}/{max_retries})")

                client = genai.Client(api_key=api_key)
                start_time = time.time()

                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=contents,
                    config=gen_config,
                )
                elapsed = time.time() - start_time

                if response.text:
                    result = response.text.strip()
                    logging.info(f"✅ OK! {model_name} key {key_hint} ({elapsed:.1f}s)")
                    return result

                logging.warning(f"⚠️ Key {key_hint} trả về rỗng.")

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    cooldown_secs = _parse_retry_delay(error_str)
                    _rotator.mark_cooldown(api_key, cooldown_secs)
                    logging.warning(f"⏳ Key {key_hint} rate-limited trên {model_name}. Cooldown {cooldown_secs:.0f}s")
                    continue
                logging.error(f"❌ Key {key_hint} {model_name}: {error_str[:200]}")
                continue

        logging.warning(f"⚠️ {model_name} thất bại. Thử model tiếp...")

    return "❌ Toàn bộ API key và model đều bị rate limit. Vui lòng thử lại sau vài phút!"


def _parse_retry_delay(error_str: str) -> float:
    """Extract retryDelay from Gemini 429 error. Fallback 15s."""
    match = re.search(r"retryDelay['\"]:\s*['\"](\d+)", error_str)
    if match:
        return float(match.group(1))
    match = re.search(r"retry in (\d+\.?\d*)", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 15.0
