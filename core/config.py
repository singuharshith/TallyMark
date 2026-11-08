import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_MODEL = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
if not GROQ_MODEL or GROQ_MODEL == "llama-3.3-70b-versatile":
    GROQ_MODEL = DEFAULT_GROQ_MODEL
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_RESULT_ROWS = 5000      # rows kept from a query result
QUERY_TIMEOUT_S = 20        # DuckDB interrupt after this many seconds
MAX_RETRIES = 2             # automatic SQL repair attempts
HISTORY_TURNS = 4           # turns of context sent to the planner
