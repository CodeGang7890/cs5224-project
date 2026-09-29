from flask import Flask
from flask_smorest import Api

from . import config


def create_app(overrides: dict | None = None) -> Flask:
    """Application factory: builds and configures the Flask app."""
    app = Flask(__name__)
    app.json.sort_keys = False  # keep JSON keys in the order we write them
    app.config.update(
        # flask-smorest: OpenAPI spec at /openapi.json, Swagger UI at /docs
        API_TITLE=config.API_TITLE,
        API_VERSION=config.API_VERSION,
        OPENAPI_VERSION='3.0.3',
        OPENAPI_URL_PREFIX='/',
        OPENAPI_JSON_PATH='openapi.json',
        OPENAPI_SWAGGER_UI_PATH='/docs',
        OPENAPI_SWAGGER_UI_URL='https://cdn.jsdelivr.net/npm/swagger-ui-dist/',
    )
    if overrides:
        app.config.update(overrides)

    api = Api(app)

    from .chat import bp as chat_bp
    from .routes import bp as main_bp

    api.register_blueprint(main_bp)
    api.register_blueprint(chat_bp)
    return app
