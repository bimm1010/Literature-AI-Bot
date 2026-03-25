import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]

# Gemini CLI Configuration
USE_CLI = os.getenv("USE_CLI", "False").lower() == "true"
GEMINI_CLI_COMMAND = os.getenv("GEMINI_CLI_COMMAND", "gemini")
TEMP_IMAGE_DIR = os.getenv("TEMP_IMAGE_DIR", "temp_images")
