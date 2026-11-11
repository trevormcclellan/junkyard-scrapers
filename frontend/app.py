"""Flask application factory; import is safe without database credentials."""
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from junkyard.common import InventoryError


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object('frontend.config')
    if config:
        app.config.update(config)
    from frontend.main.routes import main_bp
    from frontend.utah.routes import utah_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(utah_bp, url_prefix='/utah')

    @app.get('/healthz')
    def health():
        return jsonify(status='ok')

    @app.errorhandler(InventoryError)
    def inventory_error(error):
        app.logger.warning('Upstream inventory unavailable: %s', error)
        return jsonify(error='This yard is temporarily unavailable. Please try again later.'), 502

    @app.errorhandler(HTTPException)
    def http_error(error):
        if '/api/' in request.path:
            return jsonify(error=error.description), error.code
        return error

    return app
