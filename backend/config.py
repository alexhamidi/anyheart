import dotenv
import os

dotenv.load_dotenv()

PORT = int(os.getenv("PORT", "8000"))
MORPH_API_KEY = os.getenv("MORPH_API_KEY")


if not PORT:
    raise ValueError("PORT is not set")

if not MORPH_API_KEY:
    print("Warning: MORPH_API_KEY is not set. Some features may not work.")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick")
