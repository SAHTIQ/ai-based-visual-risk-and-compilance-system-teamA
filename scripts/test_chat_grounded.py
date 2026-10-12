"""
Test suite for the grounded "Ask Your Data" chatbot system.
Verifies:
1. Router / Planning tool selection
2. Disambiguation (maybe_clarify) heuristics
3. Deterministic local fallback synthesis
4. Chart widget specifications
5. Multi-provider configuration resolution
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.services.agent import maybe_clarify, _plan, _default_calls, TOOLS
from app.services.charts import (
    build_line_chart, build_bar_chart, habit_risk_chart,
    goal_progress_widget, cashflow_fan_widget
)
from app.services.fallback_engine import run_local_fallback_synthesis
from app.services.llm_client import resolve_config


class TestAskYourData(unittest.TestCase):

    def setUp(self):
        self.app = create_app()

    def test_disambiguation_heuristics(self):
        """Verify vague questions trigger domain clarification chips without LLM calls."""
        vague_queries = [
            "how am I doing?",
            "how can I improve?",
            "what should I focus on?",
            "give me advice",
            "where do I stand?",
            "overview"
        ]
        for q in vague_queries:
            res = maybe_clarify(q)
            self.assertIsNotNone(res, f"Expected clarification for: '{q}'")
            self.assertEqual(res["status"], "clarification_requested")
            self.assertEqual(len(res["widgets"]), 1)
            self.assertEqual(res["widgets"][0]["type"], "clarification_chips")
            options = res["widgets"][0]["payload"]["options"]
            self.assertGreaterEqual(len(options), 4)

    def test_default_tool_routing(self):
        """Verify sensible default tools when router fails or fallback is used."""
        fin = _default_calls("what is my budget and savings?")
        self.assertTrue(any(c["name"] == "get_financial_summary" for c in fin))

        habits = _default_calls("check my habit streaks")
        self.assertTrue(any(c["name"] == "get_habit_analysis" for c in habits))

        study = _default_calls("check my study productivity")
        self.assertTrue(any(c["name"] == "get_study_analysis" for c in study))

    def test_chart_widget_builders(self):
        """Verify chart specs produce compliant payloads for the frontend."""
        # Line chart
        line = build_line_chart(
            title="30-Day Expense Forecast",
            history=[{"date": "2026-10-01", "amount": 100}],
            forecast=[{"date": "2026-10-02", "amount": 120}],
            kind="currency"
        )
        self.assertEqual(line["type"], "line_chart")
        self.assertEqual(len(line["payload"]["history"]), 1)
        self.assertEqual(len(line["payload"]["forecast"]), 1)

        # Bar chart
        bar = build_bar_chart(
            title="Spending by Category",
            labels=["Food", "Tech"],
            values=[2500, 4000],
            kind="currency"
        )
        self.assertEqual(bar["type"], "bar_chart")
        self.assertEqual(bar["payload"]["labels"][0], "Tech")  # Sorted descending

        # Habit risk
        habits = habit_risk_chart([
            {"name": "Exercise", "churn_probability": 0.72, "risk_level": "High", "current_streak": 5}
        ])
        self.assertEqual(habits["type"], "habit_risk")
        self.assertEqual(habits["payload"]["habits"][0]["risk_level"], "High")

        # Goal progress
        goals = goal_progress_widget([
            {"title": "Emergency Fund", "progress_percentage": 65, "status": "active"}
        ])
        self.assertEqual(goals["type"], "goal_progress")
        self.assertEqual(goals["payload"]["goals"][0]["progress_percentage"], 65.0)

        # Fan chart
        fan = cashflow_fan_widget({
            "dates": ["2026-10-01", "2026-10-02"],
            "p5": [1000, 950],
            "p50": [1000, 1100],
            "p95": [1000, 1300],
            "prob_shortfall": 0.12
        })
        self.assertEqual(fan["type"], "fan_chart")
        self.assertEqual(fan["payload"]["prob_shortfall"], 12.0)

    def test_deterministic_fallback_synthesis(self):
        """Verify offline fallback produces real numbers and never crashes on empty profiles."""
        with self.app.app_context():
            res = run_local_fallback_synthesis("mock_user_123", "What did I spend this month?")
            self.assertIn("reply", res)
            self.assertTrue(res["fallback_used"])
            self.assertEqual(res["provider_used"], "Local Fallback Engine")

    def test_llm_config_resolution(self):
        """Verify LLM client can resolve API provider and router models."""
        cfg = resolve_config()
        self.assertIn("enabled", cfg)
        self.assertIn("base_url", cfg)
        self.assertIn("model", cfg)
        self.assertIn("planner_model", cfg)


if __name__ == "__main__":
    unittest.main()
