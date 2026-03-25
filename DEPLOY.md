# Hướng dẫn Triển khai (Deployment Guide) - Literature AI Bot

Tài liệu này hướng dẫn cách cài đặt và chạy Bot trên máy chủ (Server/VPS) sử dụng **Gemini CLI**.

## 1. Yêu cầu hệ thống
- **Python**: 3.10 trở lên.
- **Node.js**: 18 trở lên (để chạy Gemini CLI).
- **Git**: Để tải mã nguồn.

## 2. Cài đặt Gemini CLI (Node.js)
Trên server, chạy lệnh sau để cài đặt công cụ chính:
```bash
brew install gemini-cli
# HOẶC nếu dùng npm:
npm install -g @google/gemini-cli
```

**Quan trọng**: Sau khi cài đặt, hãy tìm đường dẫn tuyệt đối của lệnh `gemini`:
```bash
which gemini
# Ví dụ kết quả: /usr/local/bin/gemini hoặc /opt/homebrew/bin/gemini
```

## 3. Cấu hình Môi trường (.env)
Tạo file `.env` từ file mẫu và điền các thông tin sau:
- `BOT_TOKEN`: Token lấy từ @BotFather.
- `USE_CLI=True`: Bắt buộc để dùng CLI.
- `GEMINI_CLI_COMMAND`: **Đường dẫn tuyệt đối** vừa tìm được ở bước 2.
- `TEMP_IMAGE_DIR=temp_images`: Thư mục lưu ảnh tạm.

## 4. Cài đặt Python Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Chạy Bot (Production)
Để bot chạy ngầm và tự khởi động lại, khuyến khích dùng **PM2** hoặc **Systemd**.

### Cách 1: Dùng PM2 (Khuyên dùng)
```bash
pm2 start main.py --name literature-bot --interpreter python3
```

### Cách 2: Dùng nohup (Đơn giản)
```bash
nohup python3 main.py > bot.log 2>&1 &
```

## 6. Xử lý sự cố (Troubleshooting)
- **Lỗi "Command not found"**: Đảm bảo `GEMINI_CLI_COMMAND` trong `.env` là đường dẫn tuyệt đối.
- **Lỗi "Conflict: terminated by other getUpdates"**: Kẻ thù là các tiến trình Bot cũ vẫn đang chạy. Hãy dùng `pkill -f main.py` trước khi chạy lệnh mới.
- **Lỗi "Timeout"**: Kiểm tra kết nối mạng từ Server tới Google API (Gemini).
