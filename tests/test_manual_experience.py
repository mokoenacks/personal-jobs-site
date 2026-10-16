"""Roles and skills are entered in admin."""

import tempfile
import unittest
from pathlib import Path

from config import Config
from app import create_app
from app.extensions import db


def _make_app(db_path: Path):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        ADMIN_USERNAME = "admin"
        ADMIN_PASSWORD = "changeme"
        GITHUB_USERNAME = ""
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path.as_posix()

    return create_app(TestConfig)


class ManualExperienceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.app = _make_app(Path(self._tmp.name) / "manual.db")
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

    def test_add_role_and_skill(self):
        self.assertEqual(self.client.get("/admin/linkedin").status_code, 404)
        created = self.client.post(
            "/admin/experience/new",
            data={
                "company": "Acme",
                "title": "Developer",
                "description": "Built data tools.",
                "start_date": "2022-03",
                "is_current": "1",
                "is_published": "1",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Developer", created.data)
        self.client.post("/admin/skills", data={"name": "C#"}, follow_redirects=True)
        page = self.client.get("/experience")
        self.assertIn(b"Acme", page.data)
        self.assertIn(b"Built data tools.", page.data)
        self.assertIn(b"C#", page.data)
        self.assertNotIn(b"Northwind", page.data)
