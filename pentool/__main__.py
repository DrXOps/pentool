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

# CI/CD флаги — не проверять обновления при запуске / автообновлять без диалога
_NO_CHECK_UPDATES_FLAG = "--no-check-updates"
_AUTO_UPDATE_FLAG = "--auto-update"

# Top-level one-shot mode flags handled by _run_target_mode (a click.group
# can't take bare options without a subcommand, so we intercept these here).
_URL_FLAGS = ("--url",)


def _ensure_lightpanda() -> None:
    """Auto-install Lightpanda binary if not present.

    Runs synchronously before the event loop starts. Prints progress to stderr.
    Silently falls back if download fails — callers check is_lightpanda_available().
    """
    from pentool.utils.lightpanda import ensure_lightpanda_installed_sync
    ensure_lightpanda_installed_sync()


def _run_target_mode(argv: list[str]) -> None:
    """Handle ``pentool --url <url> [options]``.

    Headless flags (CI/CD):
      --headless        Run without TUI
      --output PATH     Save report to file
      --check NAMES     Comma-separated check names
      --threads N       Parallel threads (default 10)
      --delay SEC       Delay between requests (default 0.0)
      --use-ai          Enable AI-assisted scanning
      --crawl           Crawl target before scanning
      --depth N         Crawl depth (default 3)
      --max-pages N     Max crawl pages (default 100)
      --format FORMAT   Report format: json, html, csv (default: auto)

    TUI flags:
      --real            Launch TUI, proxy on, fetch target through proxy
    """
    urls: list[str] = []
    headless = False
    real = False
    output: str | None = None
    checks: list[str] = []
    threads: int = 10
    delay: float = 0.0
    use_ai = False
    crawl = False
    crawl_depth: int = 3
    max_pages: int = 100
    report_format: str = "auto"

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in _URL_FLAGS:
            if i + 1 < len(argv):
                urls.append(argv[i + 1])
                i += 2
            else:
                print(f"Error: {arg} requires a URL value", file=sys.stderr)
                sys.exit(1)
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
        elif arg == "--check" and i + 1 < len(argv):
            for c in argv[i + 1].split(","):
                c = c.strip()
                if c:
                    checks.append(c)
            i += 2
        elif arg == "--threads" and i + 1 < len(argv):
            try:
                threads = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg == "--delay" and i + 1 < len(argv):
            try:
                delay = float(argv[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg == "--use-ai":
            use_ai = True
            i += 1
        elif arg == "--crawl":
            crawl = True
            i += 1
        elif arg == "--depth" and i + 1 < len(argv):
            try:
                crawl_depth = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg == "--max-pages" and i + 1 < len(argv):
            try:
                max_pages = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg == "--format" and i + 1 < len(argv):
            report_format = argv[i + 1].lower()
            i += 2
        else:
            i += 1

    urls = [u for u in urls if u]
    if not urls:
        print("Error: --url requires at least one URL.", file=sys.stderr)
        raise SystemExit(2)

    if headless:
        from pentool.cli.headless import run_headless_scan
        sys.exit(run_headless_scan(
            urls,
            output=output,
            check_names=checks or None,
            concurrency=threads,
            delay=delay,
            use_ai=use_ai,
            crawl=crawl,
            crawl_depth=crawl_depth,
            max_pages=max_pages,
            report_format=report_format,
        ))
    else:
        # Auto-install Lightpanda binary if missing — needed for --real
        # capture, JS crawl, and technology detection.
        _ensure_lightpanda()
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
                # Resolve the target process's executable path and match it
                # against our own binary name (pentool). Do NOT match on
                # cmdline substring — "vi pentool_notes.md" or "man pentool"
                # would be SIGKILL'd.
                try:
                    exe_path = os.readlink(f"/proc/{pid}/exe")
                except (OSError, FileNotFoundError):
                    continue
                if os.path.basename(exe_path) != exe_basename:
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


def _log_exit_reason(reason: str) -> None:
    """Append a short, unambiguous line to pentool_exit_dump.log naming WHY the
    process is exiting — signal/SystemExit, an exception (crash), or the
    clean-return path. Without this, a runaway/quiet exit produced only the
    thread dump with no explicit cause, and it wasn't clear whether the app
    quit normally or crashed silently.

    Non-fatal: failures here must never mask the actual shutdown path.
    """
    try:
        from pentool.core.config import DEFAULT_CONFIG_DIR
        from pathlib import Path
        (DEFAULT_CONFIG_DIR / "pentool_exit_dump.log").open("a").write(
            f"--- EXIT: {reason} ({__import__('time').strftime('%Y-%m-%d %H:%M:%S')}) ---\n"
        )
    except Exception:
        pass  # best-effort logging


def _ensure_pro_compatible(
    unsafe_skip: bool = False,
    auto_update: bool = False,
    no_check: bool = False,
) -> None:
    """Check PRO package compatibility and self-heal if possible.

    *auto_update* — молча обновить без диалога (CI/CD режим).
    *no_check* — пропустить проверку полностью.
    Exits with SystemExit(1) if the mismatch cannot be resolved.
    """
    if no_check:
        return

    try:
        from pentool.core.license import is_pro_package_compatible
        compatible, warning = is_pro_package_compatible()
    except Exception:
        compatible, warning = True, ""

    if not compatible:
        if auto_update:
            # CI/CD: молча обновляем без диалога
            try:
                import asyncio
                from pentool.core.license import check_and_update_pro_package
                result = asyncio.run(check_and_update_pro_package())
                if result.updated:
                    print("[pentool] PRO package was out of sync — auto-updated.", file=sys.stderr)
                    compatible, warning = True, ""
                elif not result.warning:
                    compatible, warning = is_pro_package_compatible()
            except Exception:
                pass
        else:
            # Интерактивный режим: спросить пользователя
            try:
                import asyncio
                from pentool.core.license import check_and_update_pro_package
                _warn_pro_mismatch(warning)
                choice = input("> ").strip().lower()
                if choice in ("y", "yes"):
                    result = asyncio.run(check_and_update_pro_package())
                    if result.updated:
                        print("[pentool] PRO package updated. Restart to use it.", file=sys.stderr)
                        raise SystemExit(0)
                    elif not result.warning:
                        compatible, warning = is_pro_package_compatible()
                elif choice in ("n", "no"):
                    pass  # продолжить без PRO
                elif choice in ("s", "skip"):
                    print("[pentool] Skipping PRO check. Use --no-check-updates to silence.", file=sys.stderr)
                    return  # вообще пропустить проверку в этой сессии
            except Exception:
                pass

    if not compatible:
        if not unsafe_skip:
            print(f"[pentool] {warning}", file=sys.stderr)
            raise SystemExit(1)
        else:
            print("[pentool] UNSAFE: --unsafe-skip-pro-compat-check set — starting anyway. "
                  "PRO features stay disabled.", file=sys.stderr)


def _warn_pro_mismatch(warning: str) -> None:
    """Показать диалог PRO mismatch в терминале."""
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║ ⚠ PRO package version mismatch                 ║")
    print(f"║  {warning[:56]:56s} ║")
    print("║                                                ║")
    print("║  [Y] Yes — update PRO now and restart          ║")
    print("║  [N] No  — start without PRO features          ║")
    print("║  [S] Skip — skip check this time               ║")
    print("║                                                ║")
    print("║  (Use --auto-update for CI/CD mode)            ║")
    print("╚══════════════════════════════════════════════════╝")


def _start_tui() -> None:
    """Start the Pentool TUI with ancillary setup (AI dialog, ping, kill orphans)."""

    # Anonymous install-counter ping (fire-and-forget)
    try:
        from pentool.core.crash_reporter import send_first_run_ping
        threading.Thread(target=send_first_run_ping, daemon=True).start()
    except Exception:
        pass

    # AI first-run dialog: prompt to install LLM if not set up yet
    try:
        from pentool.services.ai.factory import ai_setup_required, get_ai_system_requirements, get_model_size_mb
        if ai_setup_required():
            ts = get_ai_system_requirements()
            print()
            print("╔════════════════════════════════════════╗")
            print("║ 🔮 AI assistant                       ║")
            print(f"║  Model: LFM2.5-350M-heretic  ~{get_model_size_mb()} MB       ║")
            print(f"║  RAM:   {ts['ram']}  |  CPU-only               ║")
            print("║                                        ║")
            print("║ Install AI assistant?                  ║")
            print("║  [Y] Yes  [N] No  [S] Skip            ║")
            print("╚════════════════════════════════════════╝")
            choice = input("> ").strip().lower()
            if choice == "y":
                print("\nInstalling AI assistant...")
                import asyncio
                from pentool.core.config import get_config
                from pentool.services.ai.factory import install_ai_components
                asyncio.run(install_ai_components(get_config()))
                print("\n✅ AI assistant installed. MCP server starts from Dashboard.")
            elif choice == "n":
                print("\nOK. Install later: pentool ai setup\n")
            else:
                print("\nSkipped. Install later: pentool ai setup\n")
    except Exception:
        pass

    _kill_orphaned_pentool()

    from pentool.tui.app import PentoolApp
    _app: PentoolApp | None = None
    try:
        _app = PentoolApp()
        _app.run()
    except (KeyboardInterrupt, SystemExit):
        _log_exit_reason("signal/SystemExit")
        raise
    except Exception as exc:
        _log_exit_reason(f"crash: {type(exc).__name__}: {exc}")
        try:
            from pentool.core.crash_reporter import send_crash
            send_crash(exc)
        except Exception:
            pass
        raise
    else:
        _log_exit_reason("run() returned cleanly (not via action_quit)")
        if _app is not None:
            try:
                _app._stop_proxy()
            except Exception:
                pass
        _dump_threads_and_exit()


def _dump_threads_and_exit() -> None:
    """Dump all thread stacks to exit dump log, then hard-exit."""
    import io, time as _time, traceback as _tb
    from pentool.core.config import DEFAULT_CONFIG_DIR
    log_path = str(DEFAULT_CONFIG_DIR / "pentool_exit_dump.log")
    try:
        buf = io.StringIO()
        buf.write(f"--- run() returned cleanly, {_time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} ---\n")
        try:
            import threading as _threading
            summaries = []
            for th in _threading.enumerate():
                try:
                    nm = getattr(th, "name", "?")
                    tg = getattr(th, "_target", None)
                    tg_name = getattr(tg, "__qualname__", None) or getattr(tg, "__name__", None) or repr(tg)
                    summaries.append(f"  ident={getattr(th,'ident',None)} name={nm!r} daemon={getattr(th,'daemon','?')} target={tg_name}")
                except Exception:
                    continue
            if summaries:
                buf.write("\n--- live threads (summary) ---\n" + "\n".join(summaries) + "\n")
        except Exception:
            pass
        for tid, frame in sys._current_frames().items():
            buf.write(f"\n--- Thread 0x{tid:x} ---\n")
            _tb.print_stack(frame, file=buf)
        try:
            import faulthandler
            fbuf = io.StringIO()
            faulthandler.dump_traceback(file=fbuf, all_threads=True)
            if (faul := fbuf.getvalue().strip()):
                buf.write(f"\n--- faulthandler ---\n{faul}\n")
        except Exception:
            pass
        with open(log_path, "a") as f:
            f.write(buf.getvalue())
    except Exception:
        pass
    os._exit(0)


def main() -> None:
    # The unsafe flag is removed from argv before CLI dispatch because
    # click would reject the unknown option; _ensure_pro_compatible must
    # receive the skip flag as an explicit argument.
    unsafe_skip_pro_check = _UNSAFE_SKIP_PRO_CHECK_FLAG in sys.argv
    if unsafe_skip_pro_check:
        sys.argv.remove(_UNSAFE_SKIP_PRO_CHECK_FLAG)

    # CI/CD флаги
    no_check_updates = _NO_CHECK_UPDATES_FLAG in sys.argv
    auto_update = _AUTO_UPDATE_FLAG in sys.argv
    for _flag in (_NO_CHECK_UPDATES_FLAG, _AUTO_UPDATE_FLAG):
        while _flag in sys.argv:
            sys.argv.remove(_flag)

    if len(sys.argv) > 1 and "--url" in sys.argv:
        _run_target_mode(sys.argv[1:])
        return

    if len(sys.argv) > 1:
        from pentool.cli.main import cli
        cli()
    else:
        _ensure_pro_compatible(
            unsafe_skip=unsafe_skip_pro_check,
            auto_update=auto_update,
            no_check=no_check_updates,
        )
        _start_tui()


if __name__ == "__main__":
    main()
