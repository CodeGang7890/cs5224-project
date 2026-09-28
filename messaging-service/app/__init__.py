from flask import Flask


def create_app(config: dict | None = None) -> Flask:
    """Application factory: builds and configures the Flask app."""
    app = Flask(__name__)
    app.json.sort_keys = False  # keep JSON keys in the order we write them
    if config:
        app.config.update(config)

    from .routes import bp

    app.register_blueprint(bp)
    return app
