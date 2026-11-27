"""Fixed sub-tab sets go through one factory (T-030 part 2).

The plan still listed Utils/Settings/Recon as "in progress"; the code shows all three already use
`widgets/static_tabs` (`static_tabs`, `remembered_pane`). This test keeps them there: a new screen
with a fixed set of sub-tabs must use the factory, not hand-rolled TabbedContent plus its own
"remember the last tab" logic.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

FIXED_TAB_SCREENS = (
    "pentool/tui/screens/utils/screen.py",
    "pentool/tui/screens/settings/screen.py",
    "pro/pentool/tui/screens/recon/screen.py",
)


def test_fixed_subtab_screens_use_the_shared_factory() -> None:
    missing: list[str] = []
    for relative in FIXED_TAB_SCREENS:
        path = ROOT / relative
        if not path.is_file():
            continue  # PRO tree may be absent; the core screens still must comply
        text = path.read_text(encoding="utf-8")
        if "static_tabs" not in text and "remembered_pane" not in text and "remembered_tab" not in text:
            missing.append(relative)

    assert not missing, (
        "screens with a fixed set of sub-tabs must use widgets/static_tabs "
        "(otherwise the last-tab memory and the fallback are re-implemented):\n  " + "\n  ".join(missing)
    )
