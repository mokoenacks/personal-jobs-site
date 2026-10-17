import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _database_uri() -> str:
    """Use DATABASE_URL when set. Render gives postgres://, which SQLAlchemy rejects."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{BASE_DIR / 'instance' / 'site.db'}"
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }
    SITE_OWNER_NAME = os.environ.get("SITE_OWNER_NAME", "C.k.s Mokoena")
    GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "octocat")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
    GITHUB_CACHE_MINUTES = int(os.environ.get("GITHUB_CACHE_MINUTES", "30"))
