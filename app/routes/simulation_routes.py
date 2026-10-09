"""
Digital Twin AI — Simulation Routes (Milestone 3)

Exposes endpoints for running Monte-Carlo / what-if simulations and
comparing financial/lifestyle scenarios for the authenticated user.
"""
from flask import Blueprint, jsonify, g, request
from app.middleware.auth import require_auth
from app.services.simulation_service import run_simulation, compare_scenarios

simulation_bp = Blueprint('simulation_bp', __name__, url_prefix='/api/simulation')

VALID_SCENARIOS = {"current", "expected", "best", "risk", "custom"}


# ---------------------------------------------------------------------------
# POST /api/simulation/run
# ---------------------------------------------------------------------------
@simulation_bp.route('/run', methods=['POST'])
@require_auth
def simulation_run():
    """
    Run a single simulation scenario for the authenticated user.

    Request body (JSON):
        scenario         (str, required) — one of: current|expected|best|risk|custom
        horizon_days     (int, optional, default 90)
        scenario_delta   (dict, optional) — custom scenario parameters
    """
    try:
        data = request.get_json(silent=True) or {}

        # --- Validate scenario ---
        scenario = data.get('scenario')
        if not scenario:
            return jsonify({"success": False, "error": "Missing required field: scenario"}), 400
        if scenario not in VALID_SCENARIOS:
            return jsonify({
                "success": False,
                "error": f"Invalid scenario '{scenario}'. Must be one of: {', '.join(sorted(VALID_SCENARIOS))}"
            }), 400

        horizon_days = data.get('horizon_days', 90)
        scenario_delta = data.get('scenario_delta', {})

        result = run_simulation(
            uid=g.uid,
            scenario=scenario,
            scenario_delta=scenario_delta,
            horizon_days=horizon_days
        )

        return jsonify({"success": True, "data": result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /api/simulation/compare
# ---------------------------------------------------------------------------
@simulation_bp.route('/compare', methods=['POST'])
@require_auth
def simulation_compare():
    """
    Compare multiple simulation scenarios side-by-side.

    Request body (JSON):
        scenarios    (list[str], optional) — defaults to all 4 base scenarios
        horizon_days (int, optional, default 90)
    """
    try:
        data = request.get_json(silent=True) or {}

        scenarios = data.get('scenarios', ['current', 'expected', 'best', 'risk'])
        horizon_days = data.get('horizon_days', 90)

        result = compare_scenarios(g.uid, scenarios, horizon_days)
        return jsonify({"success": True, "data": result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# GET /api/simulation/scenarios
# ---------------------------------------------------------------------------
@simulation_bp.route('/scenarios', methods=['GET'])
@require_auth
def list_scenarios():
    """Return the static list of available scenario presets."""
    scenarios = [
        {
            "id": "current",
            "name": "Current Plan",
            "description": "Your existing behavior continues unchanged",
            "icon": "fas fa-minus",
            "color": "secondary",
        },
        {
            "id": "expected",
            "name": "Expected Outcome",
            "description": "Realistic projection based on historical patterns",
            "icon": "fas fa-chart-line",
            "color": "primary",
        },
        {
            "id": "best",
            "name": "Best Case",
            "description": "Optimistic but achievable outcome with positive changes",
            "icon": "fas fa-arrow-up",
            "color": "success",
        },
        {
            "id": "risk",
            "name": "Risk Case",
            "description": "Impact of financial shock or disruption",
            "icon": "fas fa-exclamation-triangle",
            "color": "danger",
        },
        {
            "id": "custom",
            "name": "What-If Lab",
            "description": "Define your own scenario with custom parameters",
            "icon": "fas fa-flask",
            "color": "warning",
        },
    ]
    return jsonify({"success": True, "data": scenarios})


# ---------------------------------------------------------------------------
# GET /api/simulation/health
# ---------------------------------------------------------------------------
@simulation_bp.route('/health', methods=['GET'])
@require_auth
def simulation_health():
    """Simple health-check for the simulation engine."""
    return jsonify({"success": True, "status": "ok", "service": "simulation_engine"})
