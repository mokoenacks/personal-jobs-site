"""LinkedIn export sync: roles, skills, and a second upload stay aligned."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from config import Config
from app import create_app
from app.extensions import db
from app.models import Experience, Skill
from app.services.linkedin import normalize_date


POSITIONS = """Company Name,Title,Description,Location,Started On,Finished On
Acme,Engineer,"Built APIs
and tools",Johannesburg,Mar 2022,
North Co,Analyst,Reports,Remote,Jan 2019,Dec 2021
"""

POSITIONS_UPDATED = """Company Name,Title,Description,Location,Started On,Finished On
Acme,Senior Engineer,Brand new linkedin text,Cape Town,Mar 2022,
North Co,Analyst,Reports,Remote,Jan 2019,Dec 2021
"""

SKILLS = """Name
Python
Flask
SQL
"""

SKILLS_UPDATED = """Name
Python
SQL
Go
"""

PROFILE = """First Name,Last Name,Headline,Summary,Geo Location
Clement,Mokoena,Engineer and builder,I ship software,Johannesburg
"""


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _make_app(db_path: Path):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        ADMIN_USERNAME = "admin"
        ADMIN_PASSWORD = "changeme"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path.as_posix()

    return create_app(TestConfig)


class LinkedInExportSyncTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.app = _make_app(Path(self._tmp.name) / "synccheck.db")
        self.client = self.app.test_client()
        self.client.post(
            "/admin/login",
            data={"username": "admin", "password": "changeme"},
            follow_redirects=True,
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self._tmp.cleanup()

    def _upload(self, filename: str, payload: bytes, *, update_profile: bool = True):
        data = {
            "action": "sync_export",
            "linkedin_export": (io.BytesIO(payload), filename),
        }
        if update_profile:
            data["update_profile"] = "1"
        return self.client.post(
            "/admin/linkedin",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    def test_dates_normalize(self):
        self.assertEqual(normalize_date("Mar 2022"), "2022-03")
        self.assertEqual(normalize_date("2021-12-01"), "2021-12")
        self.assertEqual(normalize_date("Present"), "")

    def test_sync_then_update_keeps_custom_wording(self):
        first = _zip(
            {
                "Complete/Positions.csv": POSITIONS,
                "Complete/Skills.csv": SKILLS,
                "Complete/Profile.csv": PROFILE,
            }
        )
        response = self._upload("LinkedInExport.zip", first)
        self.assertIn(b"LinkedIn sync updated", response.data)
        self.assertNotIn(b"Northwind", response.data)

        page = self.client.get("/experience")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Engineer", page.data)
        self.assertIn(b"Acme", page.data)
        self.assertIn(b"and tools", page.data)
        self.assertIn(b"2022-03", page.data)
        self.assertIn(b"Present", page.data)
        self.assertIn(b"2021-12", page.data)
        self.assertIn(b"Python", page.data)
        self.assertIn(b"Flask", page.data)
        self.assertIn(b"SQL", page.data)
        self.assertNotIn(b"Northwind Digital", page.data)

        home = self.client.get("/")
        self.assertIn(b"Engineer and builder", home.data)
        self.assertIn(b"I ship software", home.data)
        self.assertIn(b"Python", home.data)
        self.assertIn(b"Acme", home.data)

        with self.app.app_context():
            role = Experience.query.filter_by(company="Acme").one()
            role.display_override = "CUSTOM WORDING STAYS"
            role.use_custom_text = True
            flask_skill = Skill.query.filter_by(name="Flask").one()
            flask_id = flask_skill.id
            db.session.commit()

        hidden = self.client.post(f"/admin/skills/{flask_id}/toggle", follow_redirects=True)
        self.assertIn(b"Hidden", hidden.data)

        second = _zip({"Positions.csv": POSITIONS_UPDATED, "Skills.csv": SKILLS_UPDATED})
        again = self._upload("LinkedInExport.zip", second, update_profile=False)
        self.assertIn(b"LinkedIn sync updated", again.data)
        self.assertIn(b"Hidden", again.data)

        page = self.client.get("/experience")
        self.assertIn(b"Senior Engineer", page.data)
        self.assertIn(b"CUSTOM WORDING STAYS", page.data)
        self.assertNotIn(b"Brand new linkedin text", page.data)
        self.assertIn(b"Go", page.data)
        self.assertNotIn(b"Flask", page.data)
        self.assertIn(b"Cape Town", page.data)

        home = self.client.get("/")
        self.assertIn(b"Engineer and builder", home.data)
        self.assertIn(b"Senior Engineer", home.data)

        with self.app.app_context():
            self.assertEqual(Experience.query.filter_by(company="Acme").count(), 1)
            role = Experience.query.filter_by(company="Acme").one()
            self.assertEqual(role.linkedin_raw, "Brand new linkedin text")
            self.assertEqual(role.title, "Senior Engineer")
            self.assertTrue(role.is_current)
            self.assertEqual(Skill.query.filter_by(name="Flask").one().is_published, False)
            self.assertEqual(Skill.query.filter_by(name="Go").one().is_published, True)
            self.assertEqual(Experience.query.filter_by(company="Northwind Digital").count(), 0)

    def test_skills_file_does_not_remove_roles(self):
        self._upload("export.zip", _zip({"Positions.csv": POSITIONS, "Skills.csv": SKILLS}))
        only_skills = io.BytesIO(SKILLS_UPDATED.encode())
        response = self.client.post(
            "/admin/linkedin",
            data={
                "action": "sync_export",
                "linkedin_export": (only_skills, "Skills.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"skills", response.data)
        page = self.client.get("/experience")
        self.assertIn(b"Acme", page.data)
        self.assertIn(b"Go", page.data)

    def test_rejects_unrelated_file(self):
        response = self.client.post(
            "/admin/linkedin",
            data={
                "action": "sync_export",
                "linkedin_export": (io.BytesIO(b"hello"), "notes.txt"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Positions.csv", response.data)
        self.assertIn(b"Northwind", self.client.get("/experience").data)
