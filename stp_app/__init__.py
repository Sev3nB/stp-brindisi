from flask import Flask

from config import BASE_DIR, DATABASE_URL


def create_app(test_config=None):
    app = Flask(
        __name__,
        instance_path=str(BASE_DIR / "instance"),
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_mapping(SECRET_KEY="dev-personal-only", DATABASE_URL=DATABASE_URL)
    if test_config:
        app.config.update(test_config)

    (BASE_DIR / "instance").mkdir(parents=True, exist_ok=True)

    from .routes import bp
    app.register_blueprint(bp)
    from .db import close_pool
    app.extensions["close_db_pool"] = close_pool
    return app
