"""Integrated university result-PDF workflow.

The module shares the parent application's database and authenticated users,
while keeping all imported result records in dedicated ``result_*`` tables.
"""

from flask import render_template, request
from flask_wtf.csrf import CSRFProtect


csrf = CSRFProtect()
_PROTECTED_BLUEPRINTS = {
    "result_data",
    "result_imports",
    "result_analysis",
    "result_exports",
}


def register_result_data_module(app) -> None:
    """Register the Result Data System inside the parent Flask application."""

    # Import models before db.create_all() can run so their tables are included.
    from . import models as _models  # noqa: F401
    from .routes.analysis_routes import analysis_bp
    from .routes.dashboard_routes import dashboard_bp
    from .routes.export_routes import exports_bp
    from .routes.import_routes import imports_bp

    csrf.init_app(app)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(exports_bp)
    app.register_blueprint(analysis_bp)

    @app.before_request
    def protect_result_data_writes():
        # The older Student Analysis forms are unchanged. New Result Data
        # write actions receive CSRF validation independently.
        if (
            request.blueprint in _PROTECTED_BLUEPRINTS
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        ):
            csrf.protect()

    @app.errorhandler(413)
    def result_file_too_large(_error):
        return render_template(
            "result_data/errors/413.html",
            max_upload_mb=app.config["MAX_UPLOAD_MB"],
        ), 413

