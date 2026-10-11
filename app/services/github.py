"""Fetch and cache public GitHub repositories with a mock fallback."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from app.extensions import db
from app.models import GitHubProject, SiteMeta


def parse_github_username(value: str) -> str:
    """Accept a profile URL, @handle, or bare username."""
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    if "github.com" in raw.lower():
        tail = raw.split("github.com", 1)[1].lstrip("/")
        raw = tail.split("/")[0].split("?")[0]
    if raw.startswith("@"):
        raw = raw[1:]
    raw = raw.split("/")[0].split("?")[0].strip()
    if raw.lower() in {"orgs", "features", "about", "settings", "marketplace"}:
        return ""
    return raw


def canonical_github_url(value: str) -> str:
    username = parse_github_username(value)
    if not username:
        return ""
    return f"https://github.com/{username}"


def _set_meta(key: str, value: str) -> None:
    row = SiteMeta.query.filter_by(key=key).first()
    if not row:
        row = SiteMeta(key=key)
        db.session.add(row)
    row.value = value


def get_meta(key: str, default: str = "") -> str:
    row = SiteMeta.query.filter_by(key=key).first()
    return row.value if row else default


def _upsert_repo(payload: dict) -> GitHubProject:
    project = GitHubProject.query.filter_by(github_id=payload["id"]).first()
    if not project:
        project = GitHubProject(github_id=payload["id"])
        db.session.add(project)
    project.name = payload.get("name") or "untitled"
    project.full_name = payload.get("full_name") or ""
    project.description = payload.get("description") or ""
    project.html_url = payload.get("html_url") or ""
    project.language = payload.get("language") or ""
    project.stars = int(payload.get("stargazers_count") or 0)
    project.forks = int(payload.get("forks_count") or 0)
    project.topics_json = json.dumps(payload.get("topics") or [])
    project.is_fork = bool(payload.get("fork"))
    project.pushed_at = payload.get("pushed_at") or ""
    project.synced_at = datetime.now(timezone.utc)
    if project.is_visible is None:
        project.is_visible = True
    return project


def sync_github_projects(force: bool = False, use_mock: bool | None = None) -> dict:
    """Sync repos into the local cache. Returns status dict for UI."""
    cache_minutes = current_app.config.get("GITHUB_CACHE_MINUTES", 30)
    last_sync = get_meta("github_last_sync")
    last_status = get_meta("github_last_status", "never")

    if not force and last_sync:
        try:
            synced_at = datetime.fromisoformat(last_sync)
            if synced_at.tzinfo is None:
                synced_at = synced_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - synced_at < timedelta(minutes=cache_minutes):
                count = GitHubProject.query.filter_by(is_visible=True).count()
                return {
                    "ok": True,
                    "source": get_meta("github_source", "cache"),
                    "message": "Using cached GitHub projects.",
                    "count": count,
                    "cached": True,
                    "last_sync": last_sync,
                    "last_status": last_status,
                }
        except ValueError:
            pass

    from app.models import Profile

    profile = Profile.query.first()
    username = ""
    if profile:
        username = parse_github_username(profile.github_url) or parse_github_username(
            profile.github_username
        )
    if not username:
        username = parse_github_username(current_app.config.get("GITHUB_USERNAME") or "")
    if not username or username.lower() == "octocat":
        return {
            "ok": False,
            "source": "none",
            "message": "Add your GitHub profile link under Admin → GitHub.",
            "count": 0,
            "cached": False,
            "last_sync": last_sync,
            "last_status": "error",
        }

    token = current_app.config.get("GITHUB_TOKEN") or ""
    if use_mock:
        return {
            "ok": False,
            "source": "none",
            "message": "Projects are loaded from your GitHub profile link.",
            "count": GitHubProject.query.filter_by(is_visible=True).count(),
            "cached": True,
            "last_sync": last_sync,
            "last_status": last_status,
        }

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cks-mokoena-personal-site",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/users/{username}/repos"
    params = {"sort": "updated", "per_page": 30, "type": "owner"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=12)
        if response.status_code != 200:
            raise RuntimeError(
                f"GitHub API returned {response.status_code}: {response.text[:200]}"
            )
        repos = response.json()
        if not isinstance(repos, list):
            raise RuntimeError("Unexpected GitHub response shape.")

        seen_ids = set()
        for repo in repos:
            if repo.get("fork"):
                continue
            _upsert_repo(repo)
            seen_ids.add(repo["id"])

        for project in GitHubProject.query.all():
            if project.github_id and project.github_id not in seen_ids:
                project.is_visible = False

        now = datetime.now(timezone.utc).isoformat()
        _set_meta("github_last_sync", now)
        _set_meta("github_last_status", "ok")
        _set_meta("github_source", "api")
        _set_meta("github_last_error", "")
        db.session.commit()
        visible = GitHubProject.query.filter_by(is_visible=True, is_fork=False).count()
        return {
            "ok": True,
            "source": "api",
            "message": f"Synced {visible} public repositories for @{username}.",
            "count": visible,
            "cached": False,
            "last_sync": now,
            "last_status": "ok",
        }
    except Exception as exc:
        now = datetime.now(timezone.utc).isoformat()
        _set_meta("github_last_sync", now)
        _set_meta("github_last_status", "error")
        _set_meta("github_source", "cache")
        _set_meta("github_last_error", str(exc)[:500])
        db.session.commit()
        count = GitHubProject.query.filter_by(is_visible=True, is_fork=False).count()
        return {
            "ok": False,
            "source": "cache" if count else "none",
            "message": "Could not refresh from GitHub. Showing the last saved public repositories.",
            "error": str(exc),
            "count": count,
            "cached": count > 0,
            "last_sync": now,
            "last_status": "error",
        }


def list_public_projects() -> list[GitHubProject]:
    return (
        GitHubProject.query.filter_by(is_visible=True, is_fork=False)
        .order_by(GitHubProject.pushed_at.desc(), GitHubProject.stars.desc())
        .all()
    )
