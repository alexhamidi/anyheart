import dotenv
import os

dotenv.load_dotenv()

PORT = int(os.getenv("PORT", "8000"))
MORPH_API_KEY = os.getenv("MORPH_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Agent configuration
FRONTEND_OBSERVATION_TIMEOUT = int(os.getenv("FRONTEND_OBSERVATION_TIMEOUT", "30"))

if not PORT:
    raise ValueError("PORT is not set")

if not MORPH_API_KEY:
    print("Warning: MORPH_API_KEY is not set. Some features may not work.")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
