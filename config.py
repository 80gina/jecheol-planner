"""설정·키·로깅. (bapsang-trend 의 구조를 그대로 이어받았다)"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
ENV_PATH = BASE_DIR / ".env"


class ConfigError(Exception):
    """설정을 읽지 못했을 때."""


def load_config(path: Path | None = None) -> dict:
    path = path or CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"config.json 형식이 잘못되었습니다 — {e.lineno}번째 줄 부근 ({e.msg})"
        ) from e


def resolve_path(cfg: dict, key: str) -> Path:
    rel = cfg.get("paths", {}).get(key)
    if not rel:
        raise ConfigError(f"config.json 의 paths 에 '{key}' 가 없습니다.")
    full = (BASE_DIR / rel).resolve()
    full.parent.mkdir(parents=True, exist_ok=True)
    return full


def news_db_path(cfg: dict) -> Path:
    """bapsang-trend 의 뉴스 DB 경로. 읽기 전용으로만 쓴다."""
    rel = cfg.get("news_db", "")
    if not rel:
        raise ConfigError("config.json 에 news_db 경로가 없습니다.")
    return (BASE_DIR / rel).resolve()


def get_key(name: str, required: bool = True) -> str | None:
    """환경 변수에서 키를 읽는다. 코드에는 키를 적지 않는다."""
    load_dotenv(ENV_PATH)
    value = os.getenv(name, "").strip()
    if not value or value.startswith("여기에"):
        if required:
            raise ConfigError(
                f"{name} 이(가) 설정되지 않았습니다.\n"
                "  1) .env.example 을 복사해 .env 를 만드세요\n"
                f"  2) .env 안의 {name}= 뒤에 값을 넣으세요"
            )
        return None
    return value


def mask(secret: str | None) -> str:
    if not secret:
        return "(없음)"
    if len(secret) <= 8:
        return secret[:2] + "*" * (len(secret) - 2)
    return secret[:4] + "*" * 8


def setup_logging(cfg: dict | None = None, level: str = "INFO") -> logging.Logger:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    log_file = BASE_DIR / "logs" / "app.log"
    if cfg:
        try:
            log_file = resolve_path(cfg, "log_file")
        except ConfigError:
            pass
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("jecheol")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(console)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)
    return logger
