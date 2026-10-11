"""GitHub profile links drive public projects. Freelance projects are entered by hand."""

import tempfile
import unittest
from pathlib import Path

from config import Config
from app import create_app
from app.extensions import db
from app.services.github import canonical_github_url, parse_github_username


def _make_app(db_path: Path):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        ADMIN_USERNAME = "admin"
        ADMIN_PASSWORD = "changeme"
        GITHUB_USERNAME = ""
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path.as_posix()

    return create_app(TestConfig)


class GithubLinkTest(unittest.TestCase):
    def test_parse_profile_link(self):
        self.assertEqual(parse_github_username("https://github.com/mokoenacks"), "mokoenacks")
        self.assertEqual(parse_github_username("https://github.com/mokoenacks/"), "mokoenacks")
        self.assertEqual(canonical_github_url("mokoenacks"), "https://github.com/mokoenacks")


class FreelanceTabTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.app = _make_app(Path(self._tmp.name) / "freelance.db")
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

    def test_add_edit_hide_and_delete(self):
        empty = self.client.get("/freelance")
        self.assertIn(b"No freelance projects yet", empty.data)

        created = self.client.post(
            "/admin/freelance/new",
            data={
                "title": "Warehouse scanner",
                "summary": "Private inventory tool for a client.",
                "client": "",
                "start_date": "2024-02",
                "is_current": "1",
                "is_published": "1",
                "sort_order": "10",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Warehouse scanner", created.data)

        public = self.client.get("/freelance")
        self.assertIn(b"Warehouse scanner", public.data)
        self.assertIn(b"Private inventory tool", public.data)
        self.assertIn(b"Present", public.data)

        with self.app.app_context():
            from app.models import FreelanceProject

            project_id = FreelanceProject.query.filter_by(title="Warehouse scanner").one().id

        edited = self.client.post(
            f"/admin/freelance/{project_id}/edit",
            data={
                "title": "Warehouse scanner",
                "summary": "Updated private summary.",
                "client": "North client",
                "start_date": "2024-02",
                "sort_order": "10",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Draft", edited.data)
        hidden = self.client.get("/freelance")
        self.assertNotIn(b"Warehouse scanner", hidden.data)

        self.client.post(f"/admin/freelance/{project_id}/delete", follow_redirects=True)
        gone = self.client.get("/admin/freelance")
        self.assertNotIn(b"Warehouse scanner", gone.data)
