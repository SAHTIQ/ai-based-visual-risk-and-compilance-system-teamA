import os, re

templates_dir = 'templates'
for fname in os.listdir(templates_dir):
    if not fname.endswith('.html'):
        continue
    fpath = os.path.join(templates_dir, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # find headers, cards, tables, lists, text elements
    headers = re.findall(r'<(h[1-6]|div|span|p|a|td|th)[^>]*class=["\']([^"\']*)["\'][^>]*>', content)
    print(f"=== {fname} ===")
    unique_classes = set()
    for tag, cls in headers:
        for c in cls.split():
            unique_classes.add(c)
    print("Classes used:", sorted(list(unique_classes)))
    print()
