"""Entry point: no arguments — TUI, with arguments — CLI."""

import os
import sys
import threading

# Escape hatch for local development: let the TUI start even when the
# installed PRO package is stale/version-mismatched (see
# pentool.core.license.is_pro_package_compatible). Intentionally verbose and
# scary-looking rather than a short flag like "-f" — this bypasses a check
# that exists specifically because loading a mismatched PRO build can
# segfault the process, so an accidental/muscle-memory use should be hard.
# NOT meant for end users — only for developers iterating on FREE-only code
# who don't want to rebuild/reactivate PRO for every unrelated test run.
#
# Note this does NOT force-load the mismatched PRO package itself — that
# refusal (pentool.__init__._bootstrap_pro) runs unconditionally at import
# time, before this flag is even parsed, and always prints its own warning
# when it skips a mismatched PRO install. This flag only bypasses the
# separate hard stop below that would otherwise refuse to start the TUI at
# all in that situation — with it, the TUI still starts, just with PRO
# features unavailable (same as if no PRO package were installed).
_UNSAFE_SKIP_PRO_CHECK_FLAG = "--unsafe-skip-pro-compat-check"

# Top-level one-shot mode flags handled by _run_target_mode (a click.group
# can't take bare options without a subcommand, so we intercept these here).
_URL_FLAGS = ("--url",)


def _run_target_mode(argv: list[str]) -> None:
    """Handle `pentool --url <url> [--headless] [--output file] [--real]`.

    Headless       → run an active scan and emit a report (CI/CD).
    --real         → launch the TUI, proxy on, and actually fetch the target
                     through the proxy so real traffic lands in the project.
    Otherwise      → launch the TUI pre-seeded with the URL(s).
    """
    urls: list[str] = []
    headless = False
    real = False
    output: str | None = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in _URL_FLAGS:
            if i + 1 < len(argv):
                urls.append(argv[i + 1])
                i += 2
            else:
                urls.append("")
                i += 1
        elif arg == "--headless":
            headless = True
            i += 1
        elif arg == "--real":
            real = True
            i += 1
        elif arg == "--output":
            if i + 1 < len(argv):
                output = argv[i + 1]
                i += 2
            else:
                i += 1
        else:
            i += 1

    urls = [u for u in urls if u]
    if not urls:
        print("Error: --url requires at least one URL.", file=sys.stderr)
        raise SystemExit(2)

    if headless:
        from pentool.cli.headless import run_headless_scan
        sys.exit(run_headless_scan(urls, output))
    else:
        from pentool.tui.app import PentoolApp
        app = PentoolApp()
        app._pending_start_urls = urls
        app._pending_start_real = real
        app.run()


def _kill_orphaned_pentool() -> None:
    """Kill orphaned pentool processes left behind by a previous run.

    When `pentool` is killed forcefully (kill -9 / crash / terminal closed
    mid-scan), its ProcessPoolExecutor workers (fork'd) survive as orphans
    (PPID=1) and keep the proxy's 8080 listener fd open — the next launch
    then fails with "address already in use" until they are killed manually.
    This scans /proc for live processes whose command is our own pentool
    entrypoint, whose PPID is 1 (orphaned), and that are not the current
    process, and SIGKILLs them so the port is free before this instance
    starts. Cheap, safe (only touches our own binary), and idempotent.

    Kept deliberate: it runs only on script entry, before any proxy bind, so
    it can't kill a legitimately-running proxy of a *concurrent* session we
    don't want to disturb? No — it kills orphans only (PPID==1), never a
    running foreground session (PPID != 1). A real second session has a live
    parent and won't match.
    """
    try:
        self_pid = os.getpid()
        exe_basename = os.path.basename(sys.argv[0])
        killed = 0
        for pid_dir in os.listdir("/proc"):
            if not pid_dir.isdigit():
                continue
            pid = int(pid_dir)
            if pid == self_pid:
                continue
            try:
                stat = open(f"/proc/{pid}/stat", "r").read().split(") ", 1)
                ppid = int((stat[1].split(" "))[1]) if len(stat) > 1 else -1
                if ppid != 1:
                    continue  # has a live parent — not an orphan
                cmdline = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
                # Match our own binary name in the command line (e.g. .../pentool)
                if exe_basename and exe_basename not in cmdline and "pentool" not in cmdline:
                    continue
                # Ignore the current process tree's own helpers we never spawn as
                # orphans — only kill pentool entrypoints.
                if "pentool" not in cmdline:
                    continue
                import signal
                os.kill(pid, signal.SIGKILL)
                killed += 1
            except (OSError, ValueError, IndexError, FileNotFoundError):
                continue
        if killed:
            sys.stderr.write(f"[pentool] cleaned up {killed} orphaned pentool process(es)\n")
    except Exception:
        pass  # never block startup on cleanup


def main() -> None:
    unsafe_skip_pro_check = _UNSAFE_SKIP_PRO_CHECK_FLAG in sys.argv
    if unsafe_skip_pro_check:
        sys.argv.remove(_UNSAFE_SKIP_PRO_CHECK_FLAG)

    if len(sys.argv) > 1 and "--url" in sys.argv:
        # One-shot target mode: `pentool --url <url> [--headless] [--output f]`.
        # A click.group requires a subcommand, so top-level flags alone would
        # die with "Missing command" — intercept them here and handle directly.
        _run_target_mode(sys.argv[1:])
        return

    if len(sys.argv) > 1:
        from pentool.cli.main import cli
        cli()
    else:
        # Refuse to start the TUI at all if a PRO package is installed but
        # was built for a different (or unknown) FREE version — e.g. FREE
        # was upgraded via `pip install --upgrade pentool` / `pentool
        # update`, but the PRO package's own re-sync afterwards failed or
        # never ran (offline, or an unrelated check — like the GitHub
        # release lookup used for the FREE version check — errored out
        # first and stopped `pentool update` before it reached the PRO
        # sync step). The PRO package bundles a compiled Cython extension;
        # importing a mismatched build can segfault the process with no
        # log output at all, which is exactly the silent, unexplained
        # crash this check exists to prevent. Bail out here, before any
        # Textual app or PRO import is attempted, with a clear message and
        # a fix instead of a mystery crash.
        try:
            from pentool.core.license import is_pro_package_compatible
            compatible, warning = is_pro_package_compatible()
        except Exception:
            compatible, warning = True, ""  # never block startup over this check itself

        if not compatible:
            # Try to self-heal BEFORE deciding to exit. check_and_update_pro_
            # package() is normally only reached from inside a running TUI
            # session (on_mount's background worker) or from `pentool
            # update`/`--upgrade` — but a bare `pentool` launch with an
            # incompatible package used to bail out via SystemExit below
            # before ever getting a chance to call it, so a broken install
            # could never repair itself from a plain `pentool` invocation:
            # the user was stuck needing `pentool license activate <key>`
            # even though the exact same license key/machine_id could have
            # fixed it automatically. Attempt one repair pass here first.
            try:
                import asyncio

                from pentool.core.license import check_and_update_pro_package
                result = asyncio.run(check_and_update_pro_package())
                if result.updated:
                    print(
                        "[pentool] PRO package was out of sync — "
                        "re-downloaded successfully.",
                        file=sys.stderr,
                    )
                    compatible, warning = True, ""
                elif not result.warning:
                    # No warning back means check_and_update_pro_package()
                    # itself now considers things fine (e.g. it just healed
                    # a previously-broken package with a matching build_id).
                    compatible, warning = is_pro_package_compatible()
            except Exception:
                pass  # fall through to the original warning/exit below

        if not compatible:
            if unsafe_skip_pro_check:
                print(
                    "[pentool] UNSAFE: --unsafe-skip-pro-compat-check set — "
                    "starting anyway despite the PRO version mismatch above. "
                    "PRO features stay disabled (as already reported), but "
                    "be aware this bypass is unpredictable if anything in "
                    "this session still ends up touching the mismatched "
                    "PRO package. Do not use this outside local development.",
                    file=sys.stderr,
                )
            else:
                print(f"[pentool] {warning}", file=sys.stderr)
                raise SystemExit(1)

        # Anonymous install-counter ping (fire-and-forget, one increment per
        # machine — dedup happens server-side). Runs in a background thread —
        # send_first_run_ping() opens a network connection with an 8s
        # timeout, which must never delay the TUI actually starting when
        # the network is slow/unreachable.
        try:
            from pentool.core.crash_reporter import send_first_run_ping
            threading.Thread(target=send_first_run_ping, daemon=True).start()
        except Exception:
            pass

        # AI first-run dialog: ask user to install LLM if not set up yet
        try:
            from pentool.services.ai.factory import (
                ai_setup_required,
                get_ai_system_requirements,
                get_model_size_mb,
            )
            if ai_setup_required():
                ts = get_ai_system_requirements()
                print()
                print("╔══════════════════════════════════════════════════════════╗")
                print("║ 🔮 AI assistant                                         ║")
                print("║                                                         ║")
                print("║ AI can assist during scanning:                         ║")
                print("║   • pick relevant checks for a target                  ║")
                print("║   • bypass WAF with generated payloads                 ║")
                print("║   • discover hidden endpoints                          ║")
                print("║                                                         ║")
                print("║  Model: LFM2.5-350M-heretic                            ║")
                print(f"║  Size:  ~{get_model_size_mb()} MB  |  Context: {ts['context_len']} tokens             ║")
                print(f"║  RAM:   {ts['ram']}  |  CPU-only, no GPU required           ║")
                print("║                                                         ║")
                print("║ The model will be downloaded and converted to GGUF at  ║")
                print("║ install time. This may take a while depending on your  ║")
                print("║ connection speed.                                      ║")
                print("║                                                         ║")
                print("║ Install the AI assistant?                              ║")
                print("║                                                         ║")
                print("║  [Y] Yes  [N] No, thanks  [S] Skip                    ║")
                print("╚══════════════════════════════════════════════════════════╝")
                choice = input("> ").strip().lower()
                if choice == "y":
                    print("\nInstalling AI assistant...")
                    import asyncio

                    from pentool.core.config import get_config
                    from pentool.services.ai.factory import install_ai_components
                    asyncio.run(install_ai_components(get_config()))
                    print("\n✅ AI assistant installed. MCP server is started from the Dashboard.")
                    print("  Or via the command: pentool ai start\n")
                elif choice == "n":
                    print("\nOK. You can install the AI assistant later:\n")
                    print("  pentool ai setup\n")
                else:
                    print("\nSkipped. Install later:\n")
                    print("  pentool ai setup\n")
        except Exception:
            pass

        # Free the proxy port from any orphaned pentool processes left by a
        # previous hard-killed run (their ProcessPoolExecutor workers survive
        # with PPID=1 and hold fd 8080). Do this right before the TUI starts
        # so a fresh launch doesn't fail with "address already in use".
        _kill_orphaned_pentool()

        from pentool.tui.app import PentoolApp
        try:
            PentoolApp().run()
        except (KeyboardInterrupt, SystemExit):
            # Let the interpreter shut down normally on signals/explicit exits
            # (PEP 8: never swallow these). The non-daemon-thread hang fix
            # below only targets the clean-return path (the `else` branch).
            raise
        except Exception as exc:
            # Send anonymous crash report (if not disabled in settings)
            try:
                from pentool.core.crash_reporter import send_crash
                send_crash(exc)
            except Exception:
                pass
            raise
        else:
            # `run()` returned cleanly — but NOT through `action_quit` (which
            # does its own os._exit deep inside the app). Observed: under a
            # wall-of-traffic refresh the app finished, app.run() returned,
            # and the interpreter then hung forever in threading._shutdown
            # waiting on never-closed non-daemon threads — several aiosqlite
            # _connection_worker threads plus the still-alive proxy thread.
            # Those only get closed inside action_quit; if it never ran, a
            # plain return would leave a zombie "TUI vanished, terminal hangs".
            #
            # Diagnostic: dump EVERY thread's Python stack to the log right
            # now, i.e. the exact moment app.run() returned cleanly under load.
            # This is the "TUI just vanished with no traceback" case — the
            # all-thread dump shows what the main loop / proxy / sqlite were
            # doing as the run() collapsed, instead of the usual post-mortem
            # proxy-only stacks.
            #
            # NOTE: Uses sys._current_frames() (always works) as primary + old
            # faulthandler as a secondary. The file is APPENDED (not overwritten)
            # so casual 'script -qc ...' capturing stdout to the same path
            # doesn't erase it.
            import io, sys as _sys, time as _time, traceback as _tb
            from pentool.core.config import DEFAULT_CONFIG_DIR
            _log_path = str(DEFAULT_CONFIG_DIR / "pentool_exit_dump.log")
            try:
                _buf = io.StringIO()
                _buf.write(f"--- run() returned cleanly, {_time.strftime('%Y-%m-%d %H:%M:%S')} "
                           f"pid={os.getpid()} ---\n")
                # If the app captured an exception or exit() call-site, log it here.
                try:
                    from pentool.tui.app import PentoolApp
                    _exit_stack = getattr(PentoolApp, '_exit_caller_stack', '')
                    if _exit_stack:
                        label = ("TEXTUAL UNHANDLED EXCEPTION"
                                 if "TEXTUAL UNHANDLED EXCEPTION" in _exit_stack
                                 else "app.exit() caller")
                        _buf.write(f"\n--- {label} ---\n{_exit_stack}\n")
                except Exception:
                    pass
                for _tid, _frame in _sys._current_frames().items():
                    _buf.write(f"\n--- Thread 0x{_tid:x} ---\n")
                    _tb.print_stack(_frame, file=_buf)
                # If there's still a running event loop, dump its pending tasks.
                try:
                    import asyncio as _aio
                    try:
                        _aloop = _aio.get_running_loop()
                    except RuntimeError:
                        _aloop = None
                    if _aloop is not None:
                        _tasks = _aio.all_tasks(_aloop)
                        if _tasks:
                            _buf.write(f"\n--- Pending asyncio tasks ({len(_tasks)}) ---\n")
                            for _t in sorted(_tasks, key=lambda t: str(getattr(t, "_coro", ""))):
                                _coro = getattr(_t, "_coro", _t)
                                _buf.write(f"  Task {_t.get_name()} (done={_t.done()}, "
                                           f"cancelled={_t.cancelled()}): {_coro!r:.200}\n")
                                _tb.print_stack(_coro, file=_buf, limit=5)
                                _buf.write("\n")
                except Exception:
                    pass
                # Extra: also try faulthandler (may be a no-op if signals conflict)
                try:
                    import faulthandler
                    _fbuf = io.StringIO()
                    faulthandler.dump_traceback(file=_fbuf, all_threads=True)
                    _faul = _fbuf.getvalue().strip()
                    if _faul:
                        _buf.write(f"\n--- faulthandler supplement ---\n{_faul}\n")
                except Exception:
                    _buf.write("(faulthandler unavailable)\n")
                # ── py-spy snapshot (external sampler, captures every thread) ──
                try:
                    import subprocess as _sp
                    _ps_r = _sp.run(
                        ["py-spy", "dump", "--pid", str(os.getpid()),
                         "--non-interactive"],
                        capture_output=True, timeout=10,
                    )
                    _ps_out = _ps_r.stdout.decode("utf-8", errors="replace")
                    if _ps_out.strip():
                        _buf.write(f"\n--- py-spy all-thread dump ---\n{_ps_out}\n")
                except Exception:
                    pass

                with open(_log_path, "a") as _f:
                    _f.write(_buf.getvalue())
                    _f.flush()
            except Exception as _exc:
                # Don't swallow — write whatever we can to stderr so the user
                # sees if the dump itself failed.
                try:
                    msg = f"[pentool] EXIT-DUMP-FAILED: {_exc}"
                    print(msg, file=_sys.stderr)
                except Exception:
                    pass  # bare print has no business failing — but if it does, die silently
            import os as _os
            _os._exit(0)


if __name__ == "__main__":
    main()
