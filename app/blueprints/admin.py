from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import Experience, FreelanceProject, Profile, Skill, User
from app.services import github as github_service
from app.services import linkedin as linkedin_service

admin_bp = Blueprint("admin", __name__)


def _normalize_linkedin_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Welcome back.", "success")
            next_url = request.args.get("next") or url_for("admin.dashboard")
            return redirect(next_url)
        flash("Invalid username or password.", "error")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out.", "success")
    return redirect(url_for("public.home"))


@admin_bp.route("/")
@login_required
def dashboard():
    profile = Profile.query.first()
    exp_count = Experience.query.count()
    published = Experience.query.filter_by(is_published=True).count()
    skill_count = Skill.query.filter_by(is_published=True).count()
    project_count = github_service.list_public_projects()
    github_status = _github_status()
    freelance_count = FreelanceProject.query.filter_by(is_published=True).count()
    return render_template(
        "admin/dashboard.html",
        profile=profile,
        exp_count=exp_count,
        published=published,
        skill_count=skill_count,
        project_count=len(project_count),
        github_status=github_status,
        linkedin_status=linkedin_service.sync_status(),
        freelance_count=freelance_count,
    )


@admin_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile_edit():
    profile = Profile.query.first()
    if not profile:
        profile = Profile(name=current_app.config.get("SITE_OWNER_NAME", "C.k.s Mokoena"))
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        profile.name = (request.form.get("name") or profile.name).strip()
        profile.headline = (request.form.get("headline") or "").strip()
        profile.bio = (request.form.get("bio") or "").strip()
        profile.location = (request.form.get("location") or "").strip()
        profile.email = (request.form.get("email") or "").strip()
        profile.linkedin_url = (request.form.get("linkedin_url") or "").strip()
        profile.github_url = github_service.canonical_github_url(
            request.form.get("github_url") or ""
        )
        profile.github_username = github_service.parse_github_username(profile.github_url)
        profile.cta_label = (request.form.get("cta_label") or "See my work").strip()
        profile.cta_href = (request.form.get("cta_href") or "/experience").strip()
        db.session.commit()
        if profile.github_username:
            status = github_service.sync_github_projects(force=True, use_mock=False)
            if status.get("ok"):
                flash(status["message"], "success")
            else:
                flash(status.get("message") or "GitHub sync failed.", "error")
        flash("Profile updated.", "success")
        return redirect(url_for("admin.profile_edit"))

    return render_template("admin/profile.html", profile=profile)


@admin_bp.route("/experience")
@login_required
def experience_list():
    roles = Experience.query.order_by(
        Experience.sort_order.asc(), Experience.start_date.desc()
    ).all()
    return render_template("admin/experience_list.html", roles=roles)


@admin_bp.route("/experience/new", methods=["GET", "POST"])
@login_required
def experience_new():
    if request.method == "POST":
        role = Experience(
            company=(request.form.get("company") or "").strip(),
            title=(request.form.get("title") or "").strip(),
            location=(request.form.get("location") or "").strip(),
            start_date=(request.form.get("start_date") or "").strip(),
            end_date=(request.form.get("end_date") or "").strip(),
            is_current=bool(request.form.get("is_current")),
            linkedin_raw=(request.form.get("linkedin_raw") or "").strip(),
            display_override=(request.form.get("display_override") or "").strip(),
            use_custom_text=bool(request.form.get("use_custom_text")),
            sort_order=int(request.form.get("sort_order") or 0),
            is_published=bool(request.form.get("is_published")),
        )
        if not role.company or not role.title:
            flash("Company and title are required.", "error")
            return render_template("admin/experience_form.html", role=role, is_new=True)
        db.session.add(role)
        db.session.commit()
        flash("Experience created.", "success")
        return redirect(url_for("admin.experience_list"))
    return render_template(
        "admin/experience_form.html",
        role=Experience(use_custom_text=True, is_published=True),
        is_new=True,
    )


@admin_bp.route("/experience/<int:role_id>/edit", methods=["GET", "POST"])
@login_required
def experience_edit(role_id):
    role = Experience.query.get_or_404(role_id)
    if request.method == "POST":
        role.company = (request.form.get("company") or "").strip()
        role.title = (request.form.get("title") or "").strip()
        role.location = (request.form.get("location") or "").strip()
        role.start_date = (request.form.get("start_date") or "").strip()
        role.end_date = (request.form.get("end_date") or "").strip()
        role.is_current = bool(request.form.get("is_current"))
        role.linkedin_raw = (request.form.get("linkedin_raw") or "").strip()
        role.display_override = (request.form.get("display_override") or "").strip()
        role.use_custom_text = bool(request.form.get("use_custom_text"))
        role.sort_order = int(request.form.get("sort_order") or 0)
        role.is_published = bool(request.form.get("is_published"))
        if not role.company or not role.title:
            flash("Company and title are required.", "error")
            return render_template("admin/experience_form.html", role=role, is_new=False)
        db.session.commit()
        flash("Experience saved. Public text uses your override when enabled.", "success")
        return redirect(url_for("admin.experience_list"))
    return render_template("admin/experience_form.html", role=role, is_new=False)


@admin_bp.route("/experience/<int:role_id>/delete", methods=["POST"])
@login_required
def experience_delete(role_id):
    role = Experience.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash("Experience deleted.", "success")
    return redirect(url_for("admin.experience_list"))


def _linkedin_context(profile):
    has_api = bool(
        current_app.config.get("LINKEDIN_ACCESS_TOKEN")
        and current_app.config.get("LINKEDIN_PERSON_URN")
    )
    skills = Skill.query.order_by(Skill.sort_order.asc(), Skill.name.asc()).all()
    return {
        "profile": profile,
        "has_api": has_api,
        "skills": skills,
        "linkedin_status": linkedin_service.sync_status(),
    }


@admin_bp.route("/linkedin", methods=["GET", "POST"])
@login_required
def linkedin_settings():
    """Save the public profile URL and sync roles and skills from a LinkedIn export."""
    profile = Profile.query.first()
    if not profile:
        profile = Profile(name=current_app.config.get("SITE_OWNER_NAME", "C.k.s Mokoena"))
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        action = request.form.get("action") or "save_url"

        if action == "api_fetch":
            try:
                items = linkedin_service.fetch_linkedin_api()
                result = linkedin_service.import_experiences(items)
                flash(
                    f"API import complete ({result['created']} new, {result['updated']} updated).",
                    "success",
                )
                return redirect(url_for("admin.experience_list"))
            except Exception as exc:
                flash(str(exc), "error")
                return redirect(url_for("admin.linkedin_settings"))

        if action == "sync_export":
            uploads = []
            for storage in request.files.getlist("linkedin_export"):
                if storage and storage.filename:
                    uploads.append((storage.filename, storage.read()))
            try:
                result = linkedin_service.sync_linkedin_export(
                    uploads,
                    update_profile=bool(request.form.get("update_profile")),
                )
                flash(linkedin_service.summarize_sync(result), "success")
            except ValueError as exc:
                flash(str(exc), "error")
            except Exception:
                flash("Could not read that export. Upload the .zip from LinkedIn, or the CSV files.", "error")
            return redirect(url_for("admin.linkedin_settings"))

        url = _normalize_linkedin_url(request.form.get("linkedin_url") or "")
        if url and "linkedin.com" not in url.lower():
            flash("Please paste a LinkedIn profile URL (linkedin.com/in/...).", "error")
            return render_template("admin/linkedin.html", **_linkedin_context(profile))
        profile.linkedin_url = url
        db.session.commit()
        flash(
            "LinkedIn link saved. It appears on the public site. "
            "Upload your data export above to sync roles and skills.",
            "success",
        )
        return redirect(url_for("admin.linkedin_settings"))

    return render_template("admin/linkedin.html", **_linkedin_context(profile))


@admin_bp.route("/skills/<int:skill_id>/toggle", methods=["POST"])
@login_required
def skill_toggle(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    skill.is_published = not skill.is_published
    db.session.commit()
    flash(
        f"{skill.name} is {'on' if skill.is_published else 'hidden from'} the public site.",
        "success",
    )
    return redirect(url_for("admin.linkedin_settings"))


def _github_status():
    return {
        "last_sync": github_service.get_meta("github_last_sync"),
        "last_status": github_service.get_meta("github_last_status", "never"),
        "source": github_service.get_meta("github_source", "—"),
        "last_error": github_service.get_meta("github_last_error"),
    }


@admin_bp.route("/github", methods=["GET", "POST"])
@login_required
def github_manage():
    profile = Profile.query.first()
    if not profile:
        profile = Profile(name=current_app.config.get("SITE_OWNER_NAME", "C.k.s Mokoena"))
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        action = request.form.get("action") or "sync"
        if action == "save_url":
            profile.github_url = github_service.canonical_github_url(
                request.form.get("github_url") or ""
            )
            profile.github_username = github_service.parse_github_username(profile.github_url)
            db.session.commit()
            if not profile.github_username:
                flash("Paste a GitHub profile link, such as https://github.com/your-handle.", "error")
                return redirect(url_for("admin.github_manage"))
        status = github_service.sync_github_projects(force=True, use_mock=False)
        if status.get("ok"):
            flash(status["message"], "success")
        else:
            flash(status.get("message") or "GitHub sync failed.", "error")
        return redirect(url_for("admin.github_manage"))

    return render_template(
        "admin/github.html",
        status=_github_status(),
        projects=github_service.list_public_projects(),
        profile=profile,
    )


def _blank_freelance():
    return FreelanceProject(is_published=True, is_current=False, sort_order=0)


@admin_bp.route("/freelance")
@login_required
def freelance_list():
    projects = FreelanceProject.query.order_by(
        FreelanceProject.sort_order.asc(), FreelanceProject.title.asc()
    ).all()
    return render_template("admin/freelance_list.html", projects=projects)


@admin_bp.route("/freelance/new", methods=["GET", "POST"])
@login_required
def freelance_new():
    project = _blank_freelance()
    if request.method == "POST":
        _apply_freelance_form(project)
        if not project.title:
            flash("A project title is required.", "error")
            return render_template("admin/freelance_form.html", project=project, is_new=True)
        db.session.add(project)
        db.session.commit()
        flash("Freelance project added.", "success")
        return redirect(url_for("admin.freelance_list"))
    return render_template("admin/freelance_form.html", project=project, is_new=True)


@admin_bp.route("/freelance/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def freelance_edit(project_id):
    project = FreelanceProject.query.get_or_404(project_id)
    if request.method == "POST":
        _apply_freelance_form(project)
        if not project.title:
            flash("A project title is required.", "error")
            return render_template("admin/freelance_form.html", project=project, is_new=False)
        db.session.commit()
        flash("Freelance project saved.", "success")
        return redirect(url_for("admin.freelance_list"))
    return render_template("admin/freelance_form.html", project=project, is_new=False)


@admin_bp.route("/freelance/<int:project_id>/delete", methods=["POST"])
@login_required
def freelance_delete(project_id):
    project = FreelanceProject.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash("Freelance project deleted.", "success")
    return redirect(url_for("admin.freelance_list"))


def _apply_freelance_form(project: FreelanceProject) -> None:
    project.title = (request.form.get("title") or "").strip()
    project.summary = (request.form.get("summary") or "").strip()
    project.client = (request.form.get("client") or "").strip()
    project.technologies = (request.form.get("technologies") or "").strip()
    project.project_url = (request.form.get("project_url") or "").strip()
    project.start_date = (request.form.get("start_date") or "").strip()
    project.end_date = (request.form.get("end_date") or "").strip()
    project.is_current = bool(request.form.get("is_current"))
    try:
        project.sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        project.sort_order = 0
    project.is_published = bool(request.form.get("is_published"))
