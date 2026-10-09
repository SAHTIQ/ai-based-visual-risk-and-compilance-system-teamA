import sys
sys.stdout.reconfigure(encoding="utf-8")
content = open("templates/dashboard.html", encoding="utf-8").read()
ids = ["total-income", "total-expenses", "net-savings", "study-hours", "active-goals", "fitness-sessions", "fin-health-score"]
for i in ids:
    print(f"{i}: {'FOUND' if i in content else 'NOT FOUND'}")
