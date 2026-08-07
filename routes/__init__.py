"""Enregistrement de tous les blueprints Flask."""
from routes.accounts import bp as accounts_bp
from routes.benchmark import bp as benchmark_bp
from routes.claude import bp as claude_bp
from routes.data import bp as data_bp
from routes.dividendes import bp as dividendes_bp
from routes.export import bp as export_bp
from routes.positions import bp as positions_bp
from routes.quotes import bp as quotes_bp
from routes.settings import bp as settings_bp
from routes.stats import bp as stats_bp
from routes.telegram import bp as telegram_bp


def register_blueprints(app):
    for bp in (accounts_bp, positions_bp, data_bp, stats_bp, dividendes_bp,
               quotes_bp, benchmark_bp, settings_bp, claude_bp, export_bp, telegram_bp):
        app.register_blueprint(bp)
