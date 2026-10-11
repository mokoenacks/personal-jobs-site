import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'site.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SITE_OWNER_NAME = os.environ.get("SITE_OWNER_NAME", "C.k.s Mokoena")
    GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "octocat")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
    LINKEDIN_PERSON_URN = os.environ.get("LINKEDIN_PERSON_URN", "")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
    GITHUB_CACHE_MINUTES = int(os.environ.get("GITHUB_CACHE_MINUTES", "30"))
