"""
Digital Twin AI — Application Factory

Creates and configures the Flask application with all blueprints,
Firebase initialization, and CORS support.
"""
import os
import traceback
from flask import Flask, jsonify
from flask_cors import CORS

from app.config import config_by_name
from app.services.firebase_service import init_firebase


def create_app(config_name=None):
    """
    Application factory for the Digital Twin AI Flask app.

    Args:
        config_name: Configuration profile ('development', 'production').
                     Defaults to FLASK_ENV or 'development'.

    Returns:
        Configured Flask application instance.
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(
        __name__,
        template_folder='../templates',
        static_folder='../static',
    )

    # Load configuration
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    # Enable CORS for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Initialize Firebase Admin SDK
    firebase_ok = False
    firebase_error = None
    try:
        init_firebase()
        firebase_ok = True
        print("[OK] Firebase Admin SDK initialized successfully.")
    except Exception as e:
        firebase_error = str(e)
        print(f"[ERROR] Firebase initialization FAILED: {e}")
        print("   -> Make sure serviceAccountKey.json exists in the project root.")
        print(f"   -> Expected path: {os.path.abspath('serviceAccountKey.json')}")

    # Register Blueprints
    _register_blueprints(app)

    # Global error handler — prints FULL traceback to terminal for debugging
    @app.errorhandler(Exception)
    def handle_exception(e):
        print("\n" + "="*60)
        print("[ERROR] UNHANDLED EXCEPTION:")
        traceback.print_exc()
        print("="*60 + "\n")
        return jsonify({"success": False, "error": str(e)}), 500


    # Health check endpoint
    @app.route('/health')
    def health_check():
        import firebase_admin
        fb_initialized = bool(firebase_admin._apps)
        return {
            'status': 'healthy' if fb_initialized else 'firebase_not_ready',
            'app': 'Digital Twin AI',
            'milestone': 1,
            'firebase_initialized': fb_initialized,
        }

    # Suppress favicon 404 noise in logs
    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    # Debug endpoint — shows config and Firebase status
    @app.route('/debug')
    def debug_info():
        import firebase_admin
        cred_path = os.path.abspath(
            os.getenv('FIREBASE_CREDENTIALS_PATH', 'serviceAccountKey.json')
        )
        return {
            'firebase_initialized': bool(firebase_admin._apps),
            'firebase_error': firebase_error,
            'credentials_path': cred_path,
            'credentials_file_exists': os.path.exists(cred_path),
            'project_id': os.getenv('FIREBASE_PROJECT_ID', 'NOT SET'),
            'flask_env': os.getenv('FLASK_ENV', 'development'),
        }

    # Prevent browser caching of API responses
    @app.after_request
    def prevent_caching(response):
        from flask import request
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    return app


def _register_blueprints(app):
    """Register all route blueprints."""
    from app.routes.page_routes import page_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.profile_routes import profile_bp
    from app.routes.income_routes import income_bp
    from app.routes.expense_routes import expense_bp
    from app.routes.savings_routes import savings_bp
    from app.routes.study_routes import study_bp
    from app.routes.academic_routes import academic_bp
    from app.routes.habit_routes import habit_bp
    from app.routes.fitness_routes import fitness_bp
    from app.routes.goal_routes import goal_bp
    from app.routes.activity_routes import activity_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.streak_routes import streak_bp
    from app.routes.ml_routes import ml_bp
    from app.routes.simulation_routes import simulation_bp
    from app.routes.seed_routes import seed_bp   # demo data seeder — disable in prod
    from app.routes.chat_routes import chat_bp

    app.register_blueprint(page_bp)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')
    app.register_blueprint(income_bp, url_prefix='/api/income')
    app.register_blueprint(expense_bp, url_prefix='/api/expenses')
    app.register_blueprint(savings_bp, url_prefix='/api/savings')
    app.register_blueprint(study_bp, url_prefix='/api/study')
    app.register_blueprint(academic_bp, url_prefix='/api/academics')
    app.register_blueprint(habit_bp, url_prefix='/api/habits')
    app.register_blueprint(fitness_bp, url_prefix='/api/fitness')
    app.register_blueprint(goal_bp, url_prefix='/api/goals')
    app.register_blueprint(activity_bp, url_prefix='/api/activities')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(streak_bp, url_prefix='/api/streak')
    app.register_blueprint(ml_bp, url_prefix='/api/ml')
    app.register_blueprint(simulation_bp)
    app.register_blueprint(seed_bp)              # no prefix — route is /api/seed-demo
    app.register_blueprint(chat_bp)              # /api/chat — Quanta Assistant
