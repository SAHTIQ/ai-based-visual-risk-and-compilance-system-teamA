import sys
sys.stdout.reconfigure(encoding="utf-8")
content = open("static/js/dashboard.js", encoding="utf-8").read()
lines = content.split("\n")
for i, line in enumerate(lines):
    if "setText" in line:
        print(f"{i+1:4d}: {line}")
