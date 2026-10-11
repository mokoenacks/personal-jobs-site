"""Seed admin user, profile, and sample experience on first run."""

from flask import current_app
from sqlalchemy import inspect, text

from app.extensions import db
from app.models import Experience, Profile, User


DEFAULT_BIO = (
    "I design and ship reliable software — APIs, internal tools, and calm interfaces "
    "that people actually use. Currently open to roles where craft, ownership, and "
    "clear communication matter as much as velocity."
)

SAMPLE_EXPERIENCE = [
    {
        "company": "Northwind Digital",
        "title": "Software Engineer",
        "location": "Johannesburg, ZA",
        "start_date": "2023-03",
        "end_date": "",
        "is_current": True,
        "linkedin_raw": (
            "Delivered backend services and ops tooling. Improved release confidence "
            "with better monitoring and runbooks."
        ),
        "display_override": (
            "I own features end-to-end: from clarifying the problem with stakeholders "
            "to shipping Python services, tightening deploy paths, and leaving the "
            "next engineer a clearer system than I found."
        ),
        "use_custom_text": True,
        "sort_order": 10,
    },
    {
        "company": "Cedar Labs",
        "title": "Junior Developer",
        "location": "Remote",
        "start_date": "2021-01",
        "end_date": "2023-02",
        "is_current": False,
        "linkedin_raw": (
            "Built web features across Python and JavaScript. Collaborated with design "
            "on accessible UI patterns."
        ),
        "display_override": (
            "Learned to ship small, honest increments: forms that recover drafts, "
            "APIs with predictable errors, and UI that still works when the network "
            "does not. Mentored by senior engineers; left with a bias for clarity."
        ),
        "use_custom_text": True,
        "sort_order": 20,
    },
    {
        "company": "Campus Build Guild",
        "title": "Project Lead (volunteer)",
        "location": "Pretoria, ZA",
        "start_date": "2019-06",
        "end_date": "2020-11",
        "is_current": False,
        "linkedin_raw": "Led student builders on community web projects.",
        "display_override": (
            "Coordinated a small team of student builders delivering sites for local "
            "nonprofits — scoping, demos, and the awkward middle where requirements change."
        ),
        "use_custom_text": True,
        "sort_order": 30,
    },
]


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

    if Experience.query.count() == 0:
        for item in SAMPLE_EXPERIENCE:
            db.session.add(Experience(**item, is_published=True))

    db.session.commit()
