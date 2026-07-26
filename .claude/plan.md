# Plan: TUI Refactoring — Phases 1–5 + Scanner _fill_* methods

## Scope

Confirmed by user: proceed with phases 1–5 plus scanner refactoring.
Note for later: DataTableWidget universal — todo after this refactoring.

---

## Phase 1 — BaseModuleScreen + absorb TabRenameMixin

### What

Create `tui/screens/base.py` with `BaseModuleScreen(Widget)` that:
- Contains all logic from `TabRenameMixin` (on_click double-click, on_input_submitted, on_input_blur)
- Adds abstract hooks `_start_rename(tab_id)` and `_rename_tab(tab_id, new_name)` (raise NotImplementedError)
- Adds `_get_tab_state_by_id(tab_id)` helper (returns generic state with `.name` attr — just a duck type, not generic)
- Common `action_close_tab_safe(tabs_widget_id, min_tabs=1, notify_msg)` — optional helper

`RepeaterScreen` and `ScannerScreen`:
- Change MRO: remove `TabRenameMixin`, inherit `BaseModuleScreen` instead
- Remove the `_rename_input_id / _rename_tab_prefix / _rename_tabs_widget_id` class attrs (moved into base or kept as class attrs in subclasses — keep them as class attrs since they differ per screen)

Delete `tui/mixins/tab_rename.py`.

### Key constraints

- `_rename_tab_prefix` and `_rename_tabs_widget_id` still set as class attrs in each screen (they differ: `"tab-"` vs `"scan-tab-"`, `"repeater-tabs"` vs `"scanner-tabs"`) — BaseModuleScreen reads them via `self._rename_tab_prefix` etc.
- `TabRenameMixin.on_click` → `BaseModuleScreen.on_click` — same code, verbatim copy
- No change to `_start_rename` / `_rename_tab` body in each screen

### Files touched
- CREATE `pentool/tui/screens/base.py`
- MODIFY `pentool/tui/screens/repeater/screen.py` — change MRO, remove import
- MODIFY `pentool/tui/screens/scanner/screen.py` — change MRO, remove import
- DELETE `pentool/tui/mixins/tab_rename.py`
- MODIFY `pentool/tui/mixins/__init__.py` — remove TabRenameMixin export if any

### Savings estimate: ~90 lines (89 lines of tab_rename.py, duplicate class attr blocks)

---

## Phase 2 — Extract ProjectManager from app.py

### What

Create `tui/project_manager.py` with class `ProjectManager`:
- Constructor: `__init__(self, app: "PentoolApp")` — stores `self._app = app`
- Move these methods verbatim from `PentoolApp`:
  - `action_new_project` → `new_project`
  - `action_open_project` → `open_project`
  - `action_save_project` → `save_project`
  - `action_save_project_json` → `save_project_json`
  - `action_open_project_json` → `open_project_json`
  - `_do_save_project_json` → `_do_save`
  - `_do_load_project_json` → `_do_load`
  - `_collect_spider_sessions` → `_collect_spider_sessions`
  - `_switch_project_db` → `switch_project_db`
  - `_reload_project_screens` → `_reload_screens`
  - `_init_new_db` → `_init_new_db`
  - `_switch_storage_db` → `_switch_storage_db`
  - `_open_project_sequence` → `_open_sequence`
  - `_update_project_name` → `update_project_name`
  - `action_open_ca_cert` — stays in app.py (unrelated to project management)

In `ProjectManager`, replace `self.` references to app state with `self._app.`:
- `self._project_path` → `self._app._project_path`
- `self._cfg` → `self._app._cfg`
- `self._proxy` → `self._app._proxy`
- `self._proxy_service` → `self._app._proxy_service`
- `self._project_loaded` → `self._app._project_loaded`
- `self._loop` → `self._app._loop`
- `self.notify(...)` → `self._app.notify(...)`
- `self.push_screen(...)` → `self._app.push_screen(...)`
- `self.post_message(...)` → `self._app.post_message(...)`
- `self.run_worker(...)` → `self._app.run_worker(...)`
- `self.query_one(...)` → `self._app.query_one(...)`

In `PentoolApp`:
- Add `self._pm = ProjectManager(self)` in `__init__`
- Replace action methods with one-line delegates:
  ```python
  def action_new_project(self)  -> None: self._pm.new_project()
  def action_open_project(self) -> None: self._pm.open_project()
  # etc.
  ```
- `_switch_project_db` used in `_auto_open_last_project` and keybindings — delegate stays public via `self._pm.switch_project_db(...)`

### Files touched
- CREATE `pentool/tui/project_manager.py`
- MODIFY `pentool/tui/app.py` — remove ~400 lines, add ~20 delegate lines, add `self._pm`

### Savings estimate: ~380 lines from app.py (1451 → ~1090)

---

## Phase 3 — Intruder FilterBar unification

### What

`IntruderScreen` has a custom inline filter (50 lines): `_filter_status`, `_filter_len_gt`, `_filter_len_lt`, `_apply_filter`, `_reset_filter`, `_passes_filter`.

The existing `FilterBar` widget is HTTP-centric (host, method, status range, FTS search, scope).
Instead of extending `FilterBar` (wrong semantics), we keep IntruderScreen's inline filter
but **extract it to a small dedicated widget** `IntruderFilterBar(Widget)` inside `intruder/screen.py`
(or the same file, below the screen class).

This is a lighter refactor: extract the filter row from `_compose_results` into a proper widget
with `FilterChanged` message — exactly like FilterBar's contract. The `_apply_filter` / `_reset_filter`
/ `_passes_filter` logic stays in `IntruderScreen` but the UI is isolated.

Actually — reading the code more carefully:
- `_apply_filter` reads from widgets `#filter-status`, `#filter-len-gt`, `#filter-len-lt`
- Filter row is already yielded in `_compose_results` as inline widgets
- This is a low-risk cleanup

**Decision**: Extract the filter row (3 Input widgets + 2 Button widgets) into a small
`_IntruderFilterBar(Widget)` class with a `FilterChanged` message, move `_apply_filter` logic
into it as `_build_filters() -> dict`, and let `IntruderScreen.on__intruder_filter_bar_filter_changed`
call `_redraw_results`. This gives cleaner separation and removes inline widget IDs from the screen.

### Files touched
- MODIFY `pentool/tui/screens/intruder/screen.py` — extract filter row to inner widget

### Savings estimate: ~30 lines net (slight increase in widget def, decrease in screen)

---

## Phase 4 — Audit and remove menu_bar.py / menu.py dead code

### What (already confirmed in app.py)

`app.py` line 69: `from pentool.tui.widgets.menu import ModuleSelected, SideMenu`
- `ModuleSelected` IS used: `@on(ModuleSelected)` on line 418
- `SideMenu` IS used: `self.query_one(SideMenu).select_module(module_id)` on line 425
  BUT SideMenu is NOT in compose() — the query_one will always except.
  That except is swallowed. So SideMenu is effectively dead in the DOM,
  but the import and the try-except remain.

`menu_bar.py` (238 lines) — confirmed removed from DOM (R-12 comment).
`menu.py` (86 lines) — `SideMenu` not in DOM; `ModuleSelected` message IS used.

**Action**:
1. Move `ModuleSelected` message class from `menu.py` to `tui/messages.py`
2. Delete `tui/widgets/menu.py`
3. Delete `tui/widgets/menu_bar.py`
4. Update imports in `app.py`: `from pentool.tui.messages import ModuleSelected` (remove SideMenu)
5. Remove the dead `self.query_one(SideMenu).select_module(module_id)` try-except in `action_switch_module`
6. Update `tui/widgets/__init__.py` if it exports these

### Files touched
- MODIFY `pentool/tui/messages.py` — add `ModuleSelected`
- MODIFY `pentool/tui/app.py` — update imports, remove dead SideMenu call
- DELETE `pentool/tui/widgets/menu.py`
- DELETE `pentool/tui/widgets/menu_bar.py`
- MODIFY `pentool/tui/widgets/__init__.py` — remove dead exports

### Savings: 324 lines deleted (238 + 86)

---

## Phase 5 — Debounce in ProxyScreen

### What

`ProxyScreen._append_row_to_table` is called per-request (fast path when no filters active).
Each call does `table.backend = ArrowBackend(...)` + `table.refresh()`.
At high traffic (>20 req/s) this causes visual jitter.

Add a simple debounce:
- `_debounce_timer: Timer | None = None` in `__init__`
- `_pending_rows: list[tuple[InterceptedRequest, int]] = []` — batch buffer
- `_append_row_to_table` → add to `_pending_rows`, if no timer running: start `set_timer(0.15, _flush_pending_rows)`
- `_flush_pending_rows` — process all `_pending_rows` in one ArrowBackend rebuild, clear `_pending_rows`, clear timer ref

No new class needed — 15 lines added to existing ProxyScreen.

### Files touched
- MODIFY `pentool/tui/screens/proxy/screen.py`

### Savings: 0 lines, +performance at high traffic

---

## Phase 6 — Scanner backward-compat properties cleanup

### What

`scanner/screen.py` lines 121–305: 185 lines of property boilerplate.

Each property/setter is a 6-line pattern:
```python
@property
def _scanning(self) -> bool:
    t = self._active_tab
    return t.scanning if t else False

@_scanning.setter
def _scanning(self, v: bool):
    t = self._active_tab
    if t: t.scanning = v
```

These exist for "backward compatibility" with the rest of the screen that uses `self._scanning`
instead of `self._active_tab.scanning`. But there are 66 usages of these properties in the
file — they ARE needed for conciseness.

**Decision**: Keep the properties but compress them. The boilerplate is 6 lines each;
they can be compressed to 2 lines each using a helper:

```python
def _t(self):
    """Return active tab state, or None."""
    return self._active_tab

# Replace all @property / @setter pairs with single-line access via _active_tab
# in the methods that use them — NO, this would make them worse to read.
```

Actually the better approach: replace the 185-line block with `__getattr__` / `__setattr__`
delegation — but that's fragile with Textual's reactive system.

**Revised decision**: Leave the backward-compat properties as-is. They are
compressed as much as possible already. Instead, focus on the _fill_* methods
which are a clearer win.

**Scanner _fill_* refactoring** (user confirmed scanner is tested and works):
The nested `call_after_refresh` chain in scanner:
`_mount_tab_content` → `_fill_tab_body` → `_fill_settings` + `_fill_results` → `_fill_upper_row` + `_fill_detail_panel`

This is 5 levels of deferred mounting. Each level adds latency.
The issue: child widgets don't exist until parent is mounted.

**Optimization**: Reduce nesting depth by pre-constructing containers AND their children
together in one mount operation. Instead of mounting an empty `Vertical` and then
deferring to fill it, construct the full subtree in one pass.

Specifically: `_fill_settings` and `_fill_results` can each be called directly from
`_fill_tab_body` in the same `call_after_refresh` (they both have the parent `body` mounted).
The split into `_fill_upper_row` and `_fill_detail_panel` inside `_fill_results` needs one
more defer because `results` Vertical needs to mount first.

So the chain becomes:
1. `_mount_tab_content` → mount `body` → `call_after_refresh(_fill_tab_content_all, ...)`
2. `_fill_tab_content_all` → mount settings + results + resize + call `_fill_settings_inline`
   + `call_after_refresh(_fill_results_inline, ...)`
3. `_fill_results_inline` → mount upper + detail + resize + `call_after_refresh(_setup_tab_table + _load_tab_passive_findings)`

Reduces from 5 defers to 3 defers. Also consolidates some of the duplicated `try/except logger.debug` blocks.

**Savings**: ~60–80 lines, fewer async defers = faster tab open.

### Files touched
- MODIFY `pentool/tui/screens/scanner/screen.py`

---

## Execution order

1. Phase 4 (delete dead files — no risk, isolated)
2. Phase 1 (BaseModuleScreen — foundation for 2 screens)
3. Phase 2 (ProjectManager — biggest win, isolated)
4. Phase 3 (IntruderFilterBar — small, isolated)
5. Phase 5 (Proxy debounce — small, isolated)
6. Phase 6 (Scanner _fill_* — scan confirmed working)

Run tests after each phase: `python3 -m pytest tests/unit/ -x -q`

---

## Memory note

After this refactoring, update wiki/module_status.md with new line counts and
add a note about DataTableWidget universal being a future task.
