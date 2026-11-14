"""All settings come from environment variables (a .env file in development)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional, plain environment variables still work
    pass

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Folder that holds the lab's reference files and the patient reports.
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "lab_reports")))

# Rule 3 of the lab safety rules: if age or sex is missing, do not pick a range, ask instead.
STRICT_DEMOGRAPHICS = _bool("STRICT_DEMOGRAPHICS", True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
