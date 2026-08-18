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
            from pentool.services.ai.factory import ai_setup_required, get_model_size_mb
            if ai_setup_required():
                print()
                print("╔══════════════════════════════════════════════════════════╗")
                print("║ 🔮 AI-помощник                                        ║")
                print("║                                                         ║")
                print("║ AI может помогать со сканированием:                    ║")
                print("║   • подбирать релевантные чеки под цель               ║")
                print("║   • обходить WAF сгенерированными payload'ами         ║")
                print("║   • находить скрытые эндпоинты                        ║")
                print("║                                                         ║")
                print(f"║ ⚠ LLM (~{get_model_size_mb()} MB) будет загружена при     ║")
                print("║   установке. Это займёт время в зависимости от        ║")
                print("║   скорости интернета.                                 ║")
                print("║                                                         ║")
                print("║ Хотите установить AI-помощника?                       ║")
                print("║                                                         ║")
                print("║  [Y] Да, установить  [N] Нет, спасибо  [S] Пропустить ║")
                print("╚══════════════════════════════════════════════════════════╝")
                choice = input("> ").strip().lower()
                if choice == "y":
                    print("\nУстановка AI-помощника...")
                    import asyncio
                    from pentool.core.config import get_config
                    from pentool.services.ai.factory import install_ai_components
                    asyncio.run(install_ai_components(get_config()))
                    print("\n✅ AI-помощник установлен. MCP-сервер запускается из Dashboard.")
                    print("  Или командой: pentool ai start\n")
                elif choice == "n":
                    print("\nOK. AI-помощник можно будет установить позже:\n")
                    print("  pentool ai setup\n")
                else:
                    print("\nПропущено. Установи позже:\n")
                    print("  pentool ai setup\n")
        except Exception:
            pass

        # Free the proxy port from any orphaned pentool processes left by a
        # previous hard-killed run (their ProcessPoolExecutor workers survive
        # with PPID=1 and hold fd 8080). Do this right before the TUI starts
        # so a fresh launch doesn't fail with "address already in use".
        _kill_orphaned_pentool()

        try:
            from pentool.tui.app import PentoolApp
            PentoolApp().run()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            # Send anonymous crash report (if not disabled in settings)
            try:
                from pentool.core.crash_reporter import send_crash
                send_crash(exc)
            except Exception:
                pass
            raise


if __name__ == "__main__":
    main()
