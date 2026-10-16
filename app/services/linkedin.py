"""Sync work experience and skills from the member's own LinkedIn data export.

LinkedIn does not include roles or skills in a public profile URL, and this
app does not log in or collect the live page. The member downloads their data
from LinkedIn and uploads the .zip (or Positions.csv / Skills.csv / Profile.csv).
Each upload updates the portfolio so it matches that export.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

import requests
from flask import current_app

from app.extensions import db
from app.models import Experience, Profile, SiteMeta, Skill

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_CSV_BYTES = 5 * 1024 * 1024
_EXPORT_NAMES = {"positions.csv": "positions", "skills.csv": "skills", "skill.csv": "skills", "profile.csv": "profile"}
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_SEED_ROLES = {
    ("northwind digital", "software engineer"),
    ("cedar labs", "junior developer"),
    ("campus build guild", "project lead (volunteer)"),
}
_POSITION_COLUMNS = {
    "company": ("company name", "company", "organization"),
    "title": ("title", "role"),
    "description": ("description", "summary"),
    "location": ("location",),
    "start": ("started on", "start date", "started"),
    "end": ("finished on", "end date", "finished"),
}
_SKILL_COLUMNS = ("name", "skill", "skill name")
_PROFILE_COLUMNS = {
    "headline": ("headline",),
    "summary": ("summary", "about"),
    "location": ("geo location", "location"),
}


def _set_meta(key: str, value: str) -> None:
    row = SiteMeta.query.filter_by(key=key).first()
    if not row:
        row = SiteMeta(key=key)
        db.session.add(row)
    row.value = value


def get_meta(key: str, default: str = "") -> str:
    row = SiteMeta.query.filter_by(key=key).first()
    return row.value if row else default


def sync_status() -> dict[str, str]:
    return {
        "last_sync": get_meta("linkedin_last_sync"),
        "last_status": get_meta("linkedin_last_status", "never"),
        "last_error": get_meta("linkedin_last_error"),
        "summary": get_meta("linkedin_last_summary"),
    }


def _clip(value: str, limit: int) -> str:
    return (value or "").strip()[:limit]


def _norm_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\ufeff", "").strip().lower())


def _decode_csv(data: bytes) -> str:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8-sig")
    except UnicodeError:
        return data.decode("latin-1")


def _csv_rows(data: bytes) -> list[dict[str, str]]:
    if len(data) > MAX_CSV_BYTES:
        raise ValueError("A file in that export is too large.")
    text = _decode_csv(data)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    rows = []
    for raw in reader:
        mapped = {}
        for key, value in raw.items():
            if key is None:
                continue
            mapped[_norm_header(key)] = (value or "").strip()
        if any(mapped.values()):
            rows.append(mapped)
    return rows


def _pick(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return value
    return ""


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if not value or value.lower() in {"present", "current", "now"}:
        return ""
    match = re.match(r"^(\d{4})-(\d{2})", value)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = re.match(r"^([A-Za-z]+)\s+(\d{4})$", value)
    if match:
        month = _MONTHS.get(match.group(1)[:3].lower())
        if month:
            return f"{match.group(2)}-{month:02d}"
    if re.match(r"^\d{4}$", value):
        return value
    return value[:40]


def _experience_id(company: str, start: str, title: str) -> str:
    raw = "|".join([company.strip().casefold(), start.strip(), title.strip().casefold()])
    return "li:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def parse_position_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    items = []
    for row in rows:
        company = _pick(row, _POSITION_COLUMNS["company"])
        title = _pick(row, _POSITION_COLUMNS["title"])
        if not company or not title:
            continue
        start = normalize_date(_pick(row, _POSITION_COLUMNS["start"]))
        end_raw = _pick(row, _POSITION_COLUMNS["end"])
        is_current = not end_raw or end_raw.lower() in {"present", "current", "now"}
        end = "" if is_current else normalize_date(end_raw)
        items.append(
            {
                "external_id": _experience_id(company, start, title),
                "company": _clip(company, 160),
                "title": _clip(title, 160),
                "location": _clip(_pick(row, _POSITION_COLUMNS["location"]), 120),
                "start_date": _clip(start, 40),
                "end_date": _clip(end, 40),
                "is_current": is_current,
                "description": _clip(_pick(row, _POSITION_COLUMNS["description"]), 8000),
            }
        )
    items.sort(key=lambda item: item.get("start_date") or "", reverse=True)
    return items


def parse_skill_rows(rows: list[dict[str, str]]) -> list[str]:
    names = []
    seen = set()
    for row in rows:
        name = _clip(_pick(row, _SKILL_COLUMNS), 160)
        if not name:
            # Single-column files sometimes use the first header as the skill itself.
            if len(row) == 1:
                name = _clip(next(iter(row.values())), 160)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def parse_profile_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {}
    row = rows[0]
    return {
        "headline": _clip(_pick(row, _PROFILE_COLUMNS["headline"]), 255),
        "summary": _clip(_pick(row, _PROFILE_COLUMNS["summary"]), 8000),
        "location": _clip(_pick(row, _PROFILE_COLUMNS["location"]), 120),
    }


def _parse_named_csv(filename: str, data: bytes, found: dict[str, bytes]) -> None:
    base = filename.replace("\\", "/").split("/")[-1].lower()
    kind = _EXPORT_NAMES.get(base)
    if not kind:
        return
    if kind == "skills" and "skills" in found and base != "skills.csv":
        return
    found[kind] = data


def parse_zip(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("That export is too large.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("That file is not a valid .zip export.") from exc
    found: dict[str, bytes] = {}
    total = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        base = info.filename.replace("\\", "/").split("/")[-1].lower()
        if base not in _EXPORT_NAMES:
            continue
        if info.file_size > MAX_CSV_BYTES:
            raise ValueError(f"{base} is unexpectedly large.")
        total += info.file_size
        if total > MAX_CSV_BYTES * 3:
            raise ValueError("The export spreadsheets are unexpectedly large.")
        _parse_named_csv(base, archive.read(info), found)
    return found


def parse_export_files(uploads: list[tuple[str, bytes]]) -> dict[str, Any]:
    if not uploads:
        raise ValueError("Choose your LinkedIn data export (.zip or .csv).")
    if len(uploads) > 10:
        raise ValueError("Upload the archive, or just Positions.csv, Skills.csv, and Profile.csv.")

    found: dict[str, bytes] = {}
    for filename, data in uploads:
        name = (filename or "").strip()
        lower = name.lower()
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("That file is too large.")
        if lower.endswith(".zip"):
            for kind, payload in parse_zip(data).items():
                found[kind] = payload
        elif lower.endswith(".csv"):
            _parse_named_csv(name, data, found)
        else:
            raise ValueError("Upload a .zip export, or Positions.csv, Skills.csv, and Profile.csv.")

    if not found:
        raise ValueError(
            "No Positions.csv, Skills.csv, or Profile.csv was in that upload. "
            "Download those files from LinkedIn and try again."
        )

    return {
        "positions": parse_position_rows(_csv_rows(found["positions"])) if "positions" in found else [],
        "skills": parse_skill_rows(_csv_rows(found["skills"])) if "skills" in found else [],
        "profile": parse_profile_rows(_csv_rows(found["profile"])) if "profile" in found else {},
        "saw_positions": "positions" in found,
        "saw_skills": "skills" in found,
        "saw_profile": "profile" in found,
    }


def parse_import_payload(raw: str | dict | list) -> list[dict[str, Any]]:
    """Normalize API/structured JSON into experience dicts (API path only)."""
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        data = json.loads(raw)
    else:
        data = raw

    if isinstance(data, dict):
        if "experiences" in data:
            items = data["experiences"]
        elif "elements" in data:
            items = data["elements"]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Unexpected payload shape.")

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue

        company_val = item.get("company")
        if isinstance(company_val, dict):
            company = company_val.get("name", "")
        else:
            company = company_val or item.get("companyName") or ""

        title = item.get("title") or item.get("role") or ""
        if not company and not title:
            continue

        start = item.get("start_date") or item.get("startDate") or ""
        end = item.get("end_date") or item.get("endDate") or ""
        if isinstance(start, dict):
            start = f"{start.get('year', '')}-{start.get('month', '')}".strip("-")
        if isinstance(end, dict):
            end = f"{end.get('year', '')}-{end.get('month', '')}".strip("-")

        normalized.append(
            {
                "external_id": str(
                    item.get("external_id") or item.get("id") or item.get("entityUrn") or ""
                ),
                "company": str(company),
                "title": str(title),
                "location": str(item.get("location") or item.get("geoLocationName") or ""),
                "start_date": str(start),
                "end_date": str(end),
                "is_current": bool(item.get("is_current") or item.get("isCurrent") or False),
                "description": str(
                    item.get("description") or item.get("summary") or item.get("linkedin_raw") or ""
                ),
            }
        )
    return normalized


def _find_experience(item: dict[str, Any]) -> Experience | None:
    ext_id = item.get("external_id") or ""
    if ext_id:
        experience = Experience.query.filter_by(linkedin_external_id=ext_id).first()
        if experience:
            return experience

    company = (item.get("company") or "").strip()
    title = (item.get("title") or "").strip()
    start = item.get("start_date") or ""
    if company and start:
        same_start = Experience.query.filter(
            db.func.lower(Experience.company) == company.lower(),
            Experience.start_date == start,
            Experience.linkedin_external_id.startswith("li:"),
        ).all()
        if len(same_start) == 1 and same_start[0].title != title:
            return same_start[0]

    if company and title:
        return Experience.query.filter_by(company=company, title=title, start_date=start).first()
    return None


def import_experiences(
    items: list[dict[str, Any]],
    *,
    overwrite_raw: bool = True,
    preserve_overrides: bool = True,
    prefer_source_text: bool = False,
    sync_fields: bool = False,
    reset_sort: bool = False,
    commit: bool = True,
) -> dict:
    """Upsert experiences. Custom public wording is kept when it is already set."""
    created = 0
    updated = 0
    ids: list[str] = []

    for index, item in enumerate(items):
        experience = _find_experience(item)
        ext_id = item.get("external_id") or ""
        if not experience:
            experience = Experience(
                company=item["company"],
                title=item["title"],
                use_custom_text=not prefer_source_text,
                is_published=True,
            )
            db.session.add(experience)
            created += 1
        else:
            updated += 1

        experience.company = item["company"] or experience.company
        experience.title = item["title"] or experience.title
        if sync_fields:
            experience.location = item.get("location") or ""
            experience.start_date = item.get("start_date") or ""
            experience.end_date = item.get("end_date") or ""
            experience.is_current = bool(item.get("is_current"))
        else:
            experience.location = item.get("location") or experience.location
            experience.start_date = item.get("start_date") or experience.start_date
            experience.end_date = item.get("end_date") or experience.end_date
            experience.is_current = bool(item.get("is_current"))
        if overwrite_raw:
            experience.linkedin_raw = item.get("description") or ""
        if ext_id:
            experience.linkedin_external_id = ext_id
            ids.append(ext_id)
        if reset_sort:
            experience.sort_order = (index + 1) * 10
        elif experience.sort_order is None or experience.sort_order == 0:
            experience.sort_order = (index + 1) * 10

        if not prefer_source_text:
            override = (experience.display_override or "").strip()
            if not override and experience.linkedin_raw:
                experience.display_override = experience.linkedin_raw
                experience.use_custom_text = True
            elif not preserve_overrides and not override:
                experience.display_override = experience.linkedin_raw
                experience.use_custom_text = True

    if commit:
        db.session.commit()
    return {"created": created, "updated": updated, "total": created + updated, "ids": ids}


def _drop_sample_roles() -> None:
    for role in Experience.query.all():
        if role.linkedin_external_id:
            continue
        key = ((role.company or "").strip().lower(), (role.title or "").strip().lower())
        if key in _SEED_ROLES:
            db.session.delete(role)


def _unpublish_missing_roles(seen_ids: set[str]) -> int:
    hidden = 0
    rows = Experience.query.filter(Experience.linkedin_external_id.startswith("li:")).all()
    for role in rows:
        if role.linkedin_external_id not in seen_ids and role.is_published:
            role.is_published = False
            hidden += 1
    return hidden


def import_skills(names: list[str], *, commit: bool = True) -> dict:
    created = 0
    updated = 0
    seen = set()
    for index, name in enumerate(names):
        key = name.casefold()
        seen.add(key)
        skill = Skill.query.filter(db.func.lower(Skill.name) == name.lower()).first()
        if not skill:
            skill = Skill(name=name, source="linkedin", is_published=True)
            db.session.add(skill)
            created += 1
        else:
            updated += 1
            skill.name = name
            skill.source = "linkedin"
        skill.sort_order = (index + 1) * 10
    hidden = 0
    for skill in Skill.query.filter_by(source="linkedin").all():
        if skill.name.casefold() not in seen and skill.is_published:
            skill.is_published = False
            hidden += 1
    if commit:
        db.session.commit()
    return {"created": created, "updated": updated, "hidden": hidden}


def _apply_profile(fields: dict[str, str]) -> bool:
    profile = Profile.query.first()
    if not profile or not fields:
        return False
    changed = False
    if fields.get("headline"):
        profile.headline = fields["headline"]
        changed = True
    if fields.get("summary"):
        profile.bio = fields["summary"]
        changed = True
    if fields.get("location"):
        profile.location = fields["location"]
        changed = True
    return changed


def summarize_sync(result: dict[str, Any]) -> str:
    parts = []
    if result.get("saw_positions"):
        roles = result["positions_created"] + result["positions_updated"]
        parts.append(f"{roles} role{'s' if roles != 1 else ''}")
    if result.get("saw_skills"):
        skills = result["skills_created"] + result["skills_updated"]
        parts.append(f"{skills} skill{'s' if skills != 1 else ''}")
    if result.get("profile_updated"):
        parts.append("profile text")
    if not result.get("saw_positions") and not result.get("saw_skills"):
        message = (
            "That download only has your profile"
            + (", which was updated." if result.get("profile_updated") else ".")
            + " Roles and skills are not in the quick file named Basic_LinkedInDataExport."
            " On LinkedIn, open Settings, Data privacy, Get a copy of your data,"
            " and request the larger data archive. When that email arrives, upload that zip."
        )
    elif not parts:
        message = "Nothing new was in that export."
    else:
        message = "LinkedIn sync updated " + ", ".join(parts) + ". The public site matches this export."
    if result.get("roles_hidden"):
        message += f" Unpublished {result['roles_hidden']} role(s) missing from the file."
    if result.get("skills_hidden"):
        message += f" Unpublished {result['skills_hidden']} skill(s) missing from the file."
    if result.get("warnings"):
        message += " " + " ".join(result["warnings"])
    return message


def sync_linkedin_export(uploads: list[tuple[str, bytes]], *, update_profile: bool = False) -> dict[str, Any]:
    parsed = parse_export_files(uploads)
    warnings = []
    result: dict[str, Any] = {
        "positions_created": 0,
        "positions_updated": 0,
        "skills_created": 0,
        "skills_updated": 0,
        "skills_hidden": 0,
        "roles_hidden": 0,
        "profile_updated": False,
        "saw_positions": parsed["saw_positions"],
        "saw_skills": parsed["saw_skills"],
        "warnings": warnings,
    }
    try:
        if parsed["saw_positions"]:
            if not parsed["positions"]:
                warnings.append("Positions.csv had no roles, so existing roles were left unchanged.")
            else:
                imported = import_experiences(
                    parsed["positions"],
                    prefer_source_text=True,
                    sync_fields=True,
                    reset_sort=True,
                    commit=False,
                )
                result["positions_created"] = imported["created"]
                result["positions_updated"] = imported["updated"]
                _drop_sample_roles()
                result["roles_hidden"] = _unpublish_missing_roles(set(imported["ids"]))
        if parsed["saw_skills"]:
            if not parsed["skills"]:
                warnings.append("Skills.csv had no skills, so existing skills were left unchanged.")
            else:
                imported_skills = import_skills(parsed["skills"], commit=False)
                result["skills_created"] = imported_skills["created"]
                result["skills_updated"] = imported_skills["updated"]
                result["skills_hidden"] = imported_skills["hidden"]
        if update_profile and parsed["saw_profile"]:
            result["profile_updated"] = _apply_profile(parsed["profile"])

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        summary = summarize_sync(result)
        _set_meta("linkedin_last_sync", now)
        _set_meta("linkedin_last_status", "ok")
        _set_meta("linkedin_last_error", "")
        _set_meta("linkedin_last_summary", summary)
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def fetch_linkedin_api() -> list[dict[str, Any]]:
    """Optional API fetch when credentials exist. Not the default path."""
    token = current_app.config.get("LINKEDIN_ACCESS_TOKEN") or ""
    person_urn = current_app.config.get("LINKEDIN_PERSON_URN") or ""
    if not token or not person_urn:
        raise RuntimeError(
            "LinkedIn API credentials are not configured. "
            "Upload your LinkedIn data export under Admin → LinkedIn."
        )

    url = "https://api.linkedin.com/v2/positions"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    params = {"q": "people", "people": person_urn}
    response = requests.get(url, headers=headers, params=params, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(
            f"LinkedIn API returned {response.status_code}. "
            "Upload your LinkedIn data export to sync roles and skills."
        )
    return parse_import_payload(response.json())
