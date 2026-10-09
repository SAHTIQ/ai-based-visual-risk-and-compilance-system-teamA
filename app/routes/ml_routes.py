from flask import Blueprint, jsonify, g
from app.middleware.auth import require_auth
from app.services.ml_service import forecast_finance, forecast_study, forecast_habit_churn, get_all_habit_risks, get_ml_metrics

ml_bp = Blueprint('ml_bp', __name__, url_prefix='/api/ml')

@ml_bp.route('/summary', methods=['GET'])
@require_auth
def get_ml_summary():
    try:
        finance = forecast_finance(g.uid)
        study = forecast_study(g.uid)
        habits = get_all_habit_risks(g.uid)
        
        return jsonify({
            "success": True,
            "data": {
                "finance": finance,
                "study": study,
                "habits": habits
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@ml_bp.route('/metrics', methods=['GET'])
@require_auth
def get_metrics():
    try:
        metrics = get_ml_metrics()
        return jsonify({"success": True, "data": metrics})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@ml_bp.route('/finance/forecast', methods=['GET'])
@require_auth
def get_finance_forecast():
    try:
        forecast = forecast_finance(g.uid)
        if forecast is None:
            return jsonify({"success": False, "error": "ML model not loaded"}), 503
            
        return jsonify({"success": True, "data": forecast})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@ml_bp.route('/study/forecast', methods=['GET'])
@require_auth
def get_study_forecast():
    try:
        forecast = forecast_study(g.uid)
        if forecast is None:
            return jsonify({"success": False, "error": "ML model not loaded"}), 503
            
        return jsonify({"success": True, "data": forecast})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@ml_bp.route('/habit/all/risk', methods=['GET'])
@require_auth
def get_all_habit_risk():
    try:
        risks = get_all_habit_risks(g.uid)
        if risks is None:
            return jsonify({"success": False, "error": "ML model not loaded"}), 503
            
        return jsonify({"success": True, "data": risks})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@ml_bp.route('/habit/<habit_id>/risk', methods=['GET'])
@require_auth
def get_habit_risk(habit_id):
    try:
        forecast = forecast_habit_churn(g.uid, habit_id)
        if forecast is None:
            return jsonify({"success": False, "error": "ML model not loaded or habit not found"}), 503
            
        return jsonify({"success": True, "data": forecast})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
