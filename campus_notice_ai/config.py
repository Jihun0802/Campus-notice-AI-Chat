from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "campus_notice_ai.sqlite3"
SOURCES_CONFIG_PATH = PROJECT_ROOT / "config" / "sources.json"
ENV_PATH = PROJECT_ROOT / ".env"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
RAG_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "rag_system.md"


def parse_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(path: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    env_path = Path(path).expanduser().resolve() if path else ENV_PATH
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = parse_env_value(raw_value)
        loaded[key] = value
        if override or not os.environ.get(key):
            os.environ[key] = value
    return loaded


def resolve_db_path(value: str | None = None) -> Path:
    configured = value or os.getenv("CAMPUS_NOTICE_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH


load_dotenv()
