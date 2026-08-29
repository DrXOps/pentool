"""Regression guard: notify() must never receive severity POSITIONALLY.

NotificationsMixin.notify(message, *, title, severity, timeout, ...) has
severity as a keyword-only arg. Passing it positionally (e.g.
app.notify("<msg>", "information")) raises TypeError at runtime — which, when
it happens inside a try block, surfaces to the user as a bogus
"…failed: …mixin.notify" error toast instead of the real message.

Real case (Этап 5.1): app.py on_send_to_repeater called
self.notify("→ Repeater", "information") — the toast never showed and every
Send-to-Repeater logged a failure. Fix: severity="information".

This test statically scans the source tree so a regressions anywhere else
fails the suite instead of silently producing a broken toast.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# notify call where a literal string in the second position would bind to the
# (keyword-only) `severity` param → TypeError.
_SEV = r"(information|success|warning|error|critical)"
# matches: .notify("<literal…>", "<severity>") — second positional arg
_POSITIONAL_SEV = re.compile(r'notify\(\s*["\'][^"\']*["\']\s*,\s*["\']' + _SEV + r'["\']\s*\)')

def _iter_notify_calls():
    # test path: <repo>/pentool/tests/unit/tui/test_notify_severity_arg.py
    # parents: 0=file,1=tui,2=unit,3=tests,4=<repo>/pentool -> the Python package.
    # test path: <repo>/pentool/tests/...  parents[3] = <repo> root.
    # The application package is <repo>/pentool (the inner package with tui/, modules/, …).
    pkg = Path(__file__).resolve().parents[3] / "pentool"
    scan = pkg
    for py in scan.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        # skip vendored/pro-scope if any
        if "/pro/" in str(py):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in _POSITIONAL_SEV.finditer(text):
            yield py, text.count("\n", 0, m.start()) + 1


def test_no_positional_severity_in_notify_calls():
    offenders = list(_iter_notify_calls())
    assert not offenders, (
        "notify() severity passed POSITIONALLY (keyword-only) → TypeError at "
        "runtime → 'failed …mixin.notify' toast. Fix to severity='…': "
        + "; ".join(f"{p}:{ln}" for p, ln in offenders)
    )
