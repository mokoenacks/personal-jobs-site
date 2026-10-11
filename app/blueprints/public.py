from flask import Blueprint, render_template

from app.models import Experience, FreelanceProject, Profile, Skill
from app.services import linkedin as linkedin_service
from app.services import github as github_service

public_bp = Blueprint("public", __name__)


def _published_skills():
    return (
        Skill.query.filter_by(is_published=True)
        .order_by(Skill.sort_order.asc(), Skill.name.asc())
        .all()
    )


@public_bp.route("/")
def home():
    profile = Profile.query.first()
    featured = (
        Experience.query.filter_by(is_published=True)
        .order_by(Experience.sort_order.asc(), Experience.start_date.desc())
        .limit(2)
        .all()
    )
    return render_template(
        "public/home.html",
        profile=profile,
        featured=featured,
        skills=_published_skills(),
        linkedin_synced=bool(linkedin_service.get_meta("linkedin_last_sync")),
    )


@public_bp.route("/experience")
def experience():
    profile = Profile.query.first()
    roles = (
        Experience.query.filter_by(is_published=True)
        .order_by(Experience.sort_order.asc(), Experience.start_date.desc())
        .all()
    )
    skills = _published_skills()
    return render_template(
        "public/experience.html",
        profile=profile,
        roles=roles,
        skills=skills,
        empty=len(roles) == 0 and len(skills) == 0,
        linkedin_synced=bool(linkedin_service.get_meta("linkedin_last_sync")),
    )


@public_bp.route("/projects")
def projects():
    profile = Profile.query.first()
    status = github_service.sync_github_projects(force=False)
    projects_list = github_service.list_public_projects()
    loading = False  # sync is synchronous; template still supports a loading flag
    return render_template(
        "public/projects.html",
        profile=profile,
        projects=projects_list,
        status=status,
        loading=loading,
        empty=len(projects_list) == 0 and status.get("ok"),
        error=not status.get("ok"),
    )


@public_bp.route("/freelance")
def freelance():
    profile = Profile.query.first()
    projects = (
        FreelanceProject.query.filter_by(is_published=True)
        .order_by(FreelanceProject.sort_order.asc(), FreelanceProject.start_date.desc())
        .all()
    )
    return render_template(
        "public/freelance.html",
        profile=profile,
        projects=projects,
        empty=len(projects) == 0,
    )
