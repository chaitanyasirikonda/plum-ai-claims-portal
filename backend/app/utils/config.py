import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from repo root (two levels up: utils -> app -> backend -> root)
_ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Config:
    # ── Groq LLM settings ──────────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ── Application settings ───────────────────────────────────────────────
    APP_ENV: str = os.getenv("APP_ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ── Policy / test-case helpers ─────────────────────────────────────────
    @staticmethod
    def get_policy_terms_path() -> Path:
        # Check standard locations
        paths = [
            BASE_DIR / "policy_terms.json",
            Path(os.getcwd()) / "policy_terms.json",
            Path(os.getcwd()) / "parent" / "policy_terms.json",
        ]
        for path in paths:
            if path.exists():
                return path
        raise FileNotFoundError("policy_terms.json not found in expected locations.")

    @classmethod
    def load_policy_terms(cls) -> dict:
        path = cls.get_policy_terms_path()
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def load_test_cases(cls) -> dict:
        test_path = cls.get_policy_terms_path().parent / "test_cases.json"
        if test_path.exists():
            with open(test_path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise FileNotFoundError("test_cases.json not found.")

