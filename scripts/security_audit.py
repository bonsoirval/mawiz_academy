"""Perform lightweight static checks for common project security hygiene issues.

Notes
-----
This complements, but does not replace, dependency scanning and formal review.
"""

import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
errors = []
for path in ROOT.rglob('*.py'):
    if any(part in {'.venv','venv','__pycache__'} for part in path.parts):
        continue
    try:
        ast.parse(path.read_text(encoding='utf-8'))
    except Exception as exc:
        errors.append(f"Syntax error: {path}: {exc}")
    text = path.read_text(encoding='utf-8')
    if ('SECRET_KEY' in text and 'dev-only-change-me-please' in text and path.name not in {'config.py', 'security_audit.py'}
            and 'SECRET_KEY =' in text):
        errors.append(f"Potential hard-coded development secret: {path}")
    if 'ChangeMe!Admin123' in text and path.name not in {'seed.py', 'security_audit.py'}:
        errors.append(f"Potential demo password outside seed data: {path}")
if errors:
    print('Security audit FAILED'); print('\n'.join(errors)); raise SystemExit(1)
print('Security audit passed: syntax and basic secret-hygiene checks passed.')
