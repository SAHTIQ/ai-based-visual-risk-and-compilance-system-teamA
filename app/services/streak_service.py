"""
Digital Twin AI — Streak & Gamification Service

Handles daily check-ins, XP, levels, streak tracking,
and achievement badges stored in the users Firestore document.
"""
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Level definitions
# ---------------------------------------------------------------------------
LEVELS = [
    {"level": 1, "title": "Rookie",    "min_xp": 0,    "max_xp": 99,   "color": "#6c757d", "icon": "bi-person"},
    {"level": 2, "title": "Explorer",  "min_xp": 100,  "max_xp": 299,  "color": "#0d6efd", "icon": "bi-compass"},
    {"level": 3, "title": "Achiever",  "min_xp": 300,  "max_xp": 599,  "color": "#6f42c1", "icon": "bi-star"},
    {"level": 4, "title": "Champion",  "min_xp": 600,  "max_xp": 999,  "color": "#fd7e14", "icon": "bi-award"},
    {"level": 5, "title": "Legend",    "min_xp": 1000, "max_xp": 9999, "color": "#ffc107", "icon": "bi-trophy-fill"},
]

# Streak milestone bonuses
STREAK_MILESTONES = {
    3:   {"xp": 20,  "label": "3-Day Streak!"},
    7:   {"xp": 50,  "label": "One Week Warrior!"},
    14:  {"xp": 100, "label": "Two Week Titan!"},
    30:  {"xp": 200, "label": "Monthly Master!"},
    60:  {"xp": 400, "label": "60 Day Champion!"},
    100: {"xp": 500, "label": "Century Legend!"},
}

# Achievements (checked on each check-in)
ACHIEVEMENTS = [
    {"id": "first_login",   "icon": "bi-door-open",   "color": "#0d6efd", "label": "First Login",        "desc": "You started your journey!",     "condition": lambda d: d["total_checkins"] >= 1},
    {"id": "streak_3",      "icon": "bi-fire",        "color": "#fd7e14", "label": "3-Day Streak",        "desc": "3 days in a row! Keep it up!",  "condition": lambda d: d["longest_streak"] >= 3},
    {"id": "streak_7",      "icon": "bi-fire",        "color": "#dc3545", "label": "Week Warrior",        "desc": "7-day streak achieved!",        "condition": lambda d: d["longest_streak"] >= 7},
    {"id": "streak_30",     "icon": "bi-stars",       "color": "#ffc107", "label": "Monthly Master",      "desc": "30 days in a row!",             "condition": lambda d: d["longest_streak"] >= 30},
    {"id": "checkins_10",   "icon": "bi-calendar-check", "color": "#198754", "label": "Consistent 10",  "desc": "10 total check-ins!",           "condition": lambda d: d["total_checkins"] >= 10},
    {"id": "level_2",       "icon": "bi-compass",     "color": "#0d6efd", "label": "Explorer",           "desc": "Reached Level 2!",              "condition": lambda d: d["level"] >= 2},
    {"id": "level_3",       "icon": "bi-star-fill",   "color": "#6f42c1", "label": "Achiever",           "desc": "Reached Level 3!",              "condition": lambda d: d["level"] >= 3},
    {"id": "xp_100",        "icon": "bi-lightning-fill", "color": "#0dcaf0","label": "100 XP Club",      "desc": "Earned 100+ XP!",               "condition": lambda d: d["xp"] >= 100},
]


def compute_level(xp: int) -> dict:
    """Return the level dict for the given XP amount."""
    current = LEVELS[0]
    for lv in LEVELS:
        if xp >= lv["min_xp"]:
            current = lv
    return current


def get_streak_data(uid: str, db) -> dict:
    """Fetch current streak data for the user. Returns defaults if not set."""
    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()
    data = snap.to_dict() or {} if snap.exists else {}

    xp = data.get("xp", 0)
    level_info = compute_level(xp)

    return {
        "streak_count":    data.get("streak_count", 0),
        "longest_streak":  data.get("longest_streak", 0),
        "total_checkins":  data.get("total_checkins", 0),
        "last_checkin":    data.get("last_checkin", None),
        "checkin_history": data.get("checkin_history", []),
        "xp":              xp,
        "level":           level_info["level"],
        "level_title":     level_info["title"],
        "level_color":     level_info["color"],
        "level_icon":      level_info["icon"],
        "next_level_xp":   level_info["max_xp"] + 1 if level_info["level"] < 5 else None,
        "levels":          LEVELS,
        "achievements":    _get_achievements(data),
    }


def daily_checkin(uid: str, db) -> dict:
    """
    Perform today's daily check-in.
    - Increments streak if user logged in yesterday.
    - Resets streak to 1 if they missed a day.
    - Awards XP for check-in and any streak milestones.
    - Returns the updated streak data plus bonus info.
    """
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()
    data = snap.to_dict() or {} if snap.exists else {}

    last_checkin = data.get("last_checkin")

    # Already checked in today
    if last_checkin == today:
        xp = data.get("xp", 0)
        level_info = compute_level(xp)
        return {
            "already_checked_in": True,
            "streak_count":   data.get("streak_count", 0),
            "xp":             xp,
            "xp_gained":      0,
            "level":          level_info["level"],
            "level_title":    level_info["title"],
            "level_color":    level_info["color"],
            "level_icon":     level_info["icon"],
            "milestone":      None,
            "achievements":   _get_achievements(data),
        }

    # Calculate new streak
    if last_checkin == yesterday:
        new_streak = data.get("streak_count", 0) + 1
    else:
        new_streak = 1  # Reset

    longest_streak = max(data.get("longest_streak", 0), new_streak)
    total_checkins = data.get("total_checkins", 0) + 1
    old_xp = data.get("xp", 0)

    # Base XP for check-in
    xp_gained = 10
    milestone = None

    # Streak milestone bonus
    if new_streak in STREAK_MILESTONES:
        bonus = STREAK_MILESTONES[new_streak]
        xp_gained += bonus["xp"]
        milestone = bonus["label"]

    new_xp = old_xp + xp_gained

    # Checkin history (last 30 days)
    history = data.get("checkin_history", [])
    if today not in history:
        history.append(today)
    history = sorted(history)[-30:]

    level_info = compute_level(new_xp)

    updated = {
        "last_checkin":    today,
        "streak_count":    new_streak,
        "longest_streak":  longest_streak,
        "total_checkins":  total_checkins,
        "xp":              new_xp,
        "level":           level_info["level"],
        "checkin_history": history,
    }

    user_ref.set(updated, merge=True)

    return {
        "already_checked_in": False,
        "streak_count":   new_streak,
        "longest_streak": longest_streak,
        "total_checkins": total_checkins,
        "xp":             new_xp,
        "xp_gained":      xp_gained,
        "level":          level_info["level"],
        "level_title":    level_info["title"],
        "level_color":    level_info["color"],
        "level_icon":     level_info["icon"],
        "milestone":      milestone,
        "checkin_history": history,
        "achievements":   _get_achievements(updated),
    }


def _get_achievements(data: dict) -> list:
    """Return list of unlocked achievements based on user data."""
    unlocked = data.get("achievements_unlocked", [])
    result = []
    for ach in ACHIEVEMENTS:
        earned = ach["id"] in unlocked or ach["condition"](data)
        result.append({
            "id":      ach["id"],
            "icon":    ach["icon"],
            "color":   ach["color"],
            "label":   ach["label"],
            "desc":    ach["desc"],
            "earned":  earned,
        })
    return result
