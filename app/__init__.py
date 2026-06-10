"""
Application factory untuk Sistem Informasi Forecasting Permintaan LPG.
"""
import os
from flask import Flask, render_template
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ---- Blueprints -----------------------------------------------------
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.data_management import data_bp
    from app.routes.forecasting import forecast_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(api_bp)

    # ---- Context processor: tahun aktif, dsb -----------------------------
    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from flask import session
        return {
            "current_year": datetime.now().year,
            "is_logged_in": "admin_id" in session,
            "admin_name": session.get("admin_name"),
        }

    # ---- Error handlers ---------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app
