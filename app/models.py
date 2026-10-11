from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Profile(db.Model):
    __tablename__ = "profile"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default="C.k.s Mokoena")
    headline = db.Column(db.String(255), default="Builder · Engineer · Open to work")
    bio = db.Column(db.Text, default="")
    location = db.Column(db.String(120), default="")
    email = db.Column(db.String(120), default="")
    linkedin_url = db.Column(db.String(255), default="")
    github_username = db.Column(db.String(120), default="")
    github_url = db.Column(db.String(255), default="")
    cta_label = db.Column(db.String(80), default="View experience")
    cta_href = db.Column(db.String(120), default="/experience")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class Experience(db.Model):
    """Work role with optional LinkedIn source text and local display override."""

    __tablename__ = "experiences"

    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(160), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    location = db.Column(db.String(120), default="")
    start_date = db.Column(db.String(40), default="")
    end_date = db.Column(db.String(40), default="")
    is_current = db.Column(db.Boolean, default=False)
    linkedin_raw = db.Column(db.Text, default="")
    display_override = db.Column(db.Text, default="")
    use_custom_text = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    linkedin_external_id = db.Column(db.String(120), default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @property
    def public_description(self) -> str:
        if self.use_custom_text and self.display_override.strip():
            return self.display_override
        if self.linkedin_raw.strip():
            return self.linkedin_raw
        return self.display_override or ""


class Skill(db.Model):
    """Skill synced from the member's LinkedIn export."""

    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    source = db.Column(db.String(40), default="linkedin")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class FreelanceProject(db.Model):
    """Private or client work that is not a public GitHub repository."""

    __tablename__ = "freelance_projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    client = db.Column(db.String(160), default="")
    summary = db.Column(db.Text, default="")
    technologies = db.Column(db.String(255), default="")
    project_url = db.Column(db.String(255), default="")
    start_date = db.Column(db.String(40), default="")
    end_date = db.Column(db.String(40), default="")
    is_current = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class GitHubProject(db.Model):
    """Cached display fields for a public GitHub repository."""

    __tablename__ = "github_projects"

    id = db.Column(db.Integer, primary_key=True)
    github_id = db.Column(db.Integer, unique=True, nullable=True)
    name = db.Column(db.String(160), nullable=False)
    full_name = db.Column(db.String(255), default="")
    description = db.Column(db.Text, default="")
    html_url = db.Column(db.String(255), default="")
    language = db.Column(db.String(80), default="")
    stars = db.Column(db.Integer, default=0)
    forks = db.Column(db.Integer, default=0)
    topics_json = db.Column(db.Text, default="[]")
    is_fork = db.Column(db.Boolean, default=False)
    is_featured = db.Column(db.Boolean, default=True)
    is_visible = db.Column(db.Boolean, default=True)
    pushed_at = db.Column(db.String(40), default="")
    synced_at = db.Column(db.DateTime, default=utcnow)
    created_at = db.Column(db.DateTime, default=utcnow)


class SiteMeta(db.Model):
    """Key/value store for sync status and misc settings."""

    __tablename__ = "site_meta"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, default="")
