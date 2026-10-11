from pathlib import Path

from flask import Flask

from config import Config
from app.extensions import db, login_manager


def create_app(config_object=Config):
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_object)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    # Prefer instance/site.db unless DATABASE_URL explicitly set to something else
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
        db_path = Path(app.instance_path) / "site.db"
        if "site.db" in app.config["SQLALCHEMY_DATABASE_URI"] or not Path(
            app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        ).is_absolute():
            app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.blueprints.public import public_bp
    from app.blueprints.admin import admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    with app.app_context():
        from app.seed import seed_database

        seed_database()

    @app.context_processor
    def inject_globals():
        from app.models import Profile

        profile = Profile.query.first()
        return {
            "site_name": (profile.name if profile else app.config.get("SITE_OWNER_NAME")),
            "profile": profile,
        }

    return app
