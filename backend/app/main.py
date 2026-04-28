"""BESS Sizing Tool — Flask Application Factory"""
import json
import logging
import os
import time
import uuid

from flask import Flask, g, request as flask_request


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for Zero Script QA."""

    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "service": "bess-api",
            "request_id": getattr(record, 'request_id', 'N/A'),
            "message": record.getMessage(),
        }
        if hasattr(record, 'data'):
            log_entry["data"] = record.data
        return json.dumps(log_entry, default=str)


def _setup_logging(app):
    """Configure structured JSON logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.DEBUG)
    # Suppress default werkzeug request log to avoid duplication
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


def _register_request_hooks(app):
    """Add before/after request hooks for request tracking."""

    @app.before_request
    def before_request():
        g.request_id = flask_request.headers.get(
            'X-Request-ID', f'req_{uuid.uuid4().hex[:8]}'
        )
        g.start_time = time.time()
        app.logger.info(
            "Request started",
            extra={
                'request_id': g.request_id,
                'data': {
                    'method': flask_request.method,
                    'path': flask_request.path,
                    'query': flask_request.query_string.decode('utf-8', errors='replace'),
                },
            },
        )

    @app.after_request
    def after_request(response):
        duration_ms = round((time.time() - g.get('start_time', time.time())) * 1000, 2)
        app.logger.info(
            "Request completed",
            extra={
                'request_id': g.get('request_id', 'N/A'),
                'data': {
                    'status': response.status_code,
                    'duration_ms': duration_ms,
                    'method': flask_request.method,
                    'path': flask_request.path,
                },
            },
        )
        response.headers['X-Request-ID'] = g.get('request_id', '')
        return response


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder='../../frontend/templates',
        static_folder='../../frontend/static',
    )
    app.config['SECRET_KEY'] = os.environ.get(
        'FLASK_SECRET_KEY', 'bess-sizing-tool-dev'
    )

    # Structured JSON logging
    _setup_logging(app)
    _register_request_hooks(app)

    # SQLite database path
    db_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'db')
    os.makedirs(db_dir, exist_ok=True)
    app.config['DATABASE'] = os.path.join(db_dir, 'sizing.db')

    # Initialise database schemas
    from .models import init_db
    init_db(app.config['DATABASE'])

    from .shared_models import init_shared_db
    init_shared_db(app.config['DATABASE'])

    # Register blueprints
    from . import routes
    app.register_blueprint(routes.bp)

    from .auth import auth_bp
    app.register_blueprint(auth_bp)

    from .shared_routes import shared_bp
    app.register_blueprint(shared_bp)

    # Healthcheck (Docker/로드밸런서용, 인증 불필요)
    @app.route('/health')
    def health():
        return {'status': 'ok'}, 200

    return app
