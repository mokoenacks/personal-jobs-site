"""Seed the admin user and profile on first run."""

from flask import current_app
from sqlalchemy import inspect, text

from app.extensions import db
from app.models import Profile, User


DEFAULT_BIO = (
    "I design and ship reliable software — APIs, internal tools, and calm interfaces "
    "that people actually use. Currently open to roles where craft, ownership, and "
    "clear communication matter as much as velocity."
)

def _ensure_profile_github_url() -> None:
    inspector = inspect(db.engine)
    if "profile" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("profile")}
    if "github_url" not in columns:
        db.session.execute(text("ALTER TABLE profile ADD COLUMN github_url VARCHAR(255) DEFAULT ''"))
        db.session.commit()


def seed_database() -> None:
    db.create_all()
    _ensure_profile_github_url()

    if not User.query.filter_by(username=current_app.config["ADMIN_USERNAME"]).first():
        user = User(username=current_app.config["ADMIN_USERNAME"])
        user.set_password(current_app.config["ADMIN_PASSWORD"])
        db.session.add(user)

    if not Profile.query.first():
        profile = Profile(
            name=current_app.config.get("SITE_OWNER_NAME", "C.k.s Mokoena"),
            headline="Software engineer · Builder · Open to work",
            bio=DEFAULT_BIO,
            location="South Africa",
            email="hello@example.com",
            linkedin_url="",
            github_username=current_app.config.get("GITHUB_USERNAME", ""),
            github_url="",
            cta_label="See my work",
            cta_href="/experience",
        )
        db.session.add(profile)

    profile = Profile.query.first()
    if profile and not (profile.github_url or "").strip():
        username = (profile.github_username or "").strip()
        if username and username.lower() != "octocat":
            profile.github_url = f"https://github.com/{username}"

    db.session.commit()
