from flask import Flask
from flask_wtf.csrf import CSRFProtect
import os

# Initialize CSRF protection
csrf = CSRFProtect()

def create_app():
    """Factory function to create and configure the Flask app."""
    app = Flask(__name__)

    # Load configuration (e.g., from config.py or environment variables)
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.py')
    app.config.from_pyfile(config_path)

    # Initialize CSRF protection
    csrf.init_app(app)

    # Register blueprints (routes)
    from . import routes
    app.register_blueprint(routes.bp)

    return app