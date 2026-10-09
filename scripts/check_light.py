import os, re

with open('static/css/style.css', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'data-theme="light"' in line or 'data-theme=\'light\'' in line:
        print(f"{i+1}: {line.strip()[:100]}")
