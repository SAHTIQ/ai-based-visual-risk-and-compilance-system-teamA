import sys
sys.stdout.reconfigure(encoding="utf-8")
content = open("static/css/style.css", encoding="utf-8").read()
lines = content.split("\n")
for i, line in enumerate(lines):
    if "sidebar-overlay" in line:
        for j in range(max(0, i-5), min(len(lines), i+15)):
            print(f"{j+1:4d}: {lines[j]}")
        break
