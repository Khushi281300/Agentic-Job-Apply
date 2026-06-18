import ast
import pathlib

errors = []
files = sorted(pathlib.Path("packages").rglob("*.py")) + sorted(pathlib.Path("cli").rglob("*.py"))
for f in files:
    try:
        ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"SYNTAX ERROR: {f} line {e.lineno}: {e.msg}")

if errors:
    for e in errors:
        print(e)
    raise SystemExit(1)
else:
    print(f"All {len(files)} Python files pass syntax check")
