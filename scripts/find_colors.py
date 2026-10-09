import os, re

color_pattern = re.compile(r'color:\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)|white)', re.IGNORECASE)

files_to_check = ['static/css/style.css']
for r, d, fs in os.walk('static/js'):
    for f in fs:
        if f.endswith('.js'):
            files_to_check.append(os.path.join(r, f))

for fpath in files_to_check:
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    matches = []
    for i, line in enumerate(lines):
        for m in color_pattern.finditer(line):
            matches.append((i+1, m.group(0), line.strip()[:90]))
    if matches:
        print(f"=== {fpath} ({len(matches)} color rules) ===")
        for line_num, color_val, text in matches[:10]:
            print(f"  L{line_num}: {color_val} -> {text}")
        if len(matches) > 10:
            print(f"  ... and {len(matches)-10} more")
        print()
