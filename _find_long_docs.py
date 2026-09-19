import ast, subprocess, os

result = subprocess.run(
    ['find', 'pentool', '-name', '*.py', '-not', '-path', '*/test*', '-not', '-path', '*/__pycache__*', '-not', '-path', '*/.venv*', '-not', '-path', '*/venv*', '-not', '-path', '*/migrations*'],
    capture_output=True, text=True
)
files = [f for f in result.stdout.strip().split('\n') if f]

count = 0
for fpath in sorted(files):
    rel = os.path.relpath(fpath)
    with open(fpath, 'r') as f:
        content = f.read()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc and len(doc) > 200:
                if not any(kw in doc for kw in ['Args:', 'Returns:', 'Raises:', 'Attributes:', ':param']):
                    count += 1
                    print(f'{rel}:{node.lineno}: {node.name} ({len(doc)} chars) -> {doc.strip()[:80]}...')
print(f'\nTotal: {count}')