import sys
sys.stdout.reconfigure(encoding="utf-8")
content = open("static/js/dashboard.js", encoding="utf-8").read()
lines = content.split("\n")
for i, line in enumerate(lines):
    if "function renderExpenseChart" in line or "function renderIncomeChart" in line:
        for j in range(i, min(len(lines), i+30)):
            print(f"{j+1:4d}: {lines[j]}")
        print("="*40)
