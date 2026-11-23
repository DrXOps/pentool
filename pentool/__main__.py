"""Entry point: no arguments — TUI, with arguments — CLI."""

import os
import sys
import threading

from pentool.core.logging import get_logger

logger = get_logger(__name__)

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

# CI/CD flags — skip the update check on start / update without a dialog
_NO_CHECK_UPDATES_FLAG = "--no-check-updates"
_AUTO_UPDATE_FLAG = "--auto-update"


# Top-level one-shot mode: handled by cli/main.py click group,
# not by a separate parser here. _run_target_mode was removed in
# the audit (P1.3) — it duplicated click's argument parsing.
def _kill_orphaned_pentool() -> None:
    """Kill orphaned pentool processes (PPID=1) so next launch doesn't hit 'address already in use'."""
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
        logger.warning("orphaned cleanup failed", exc_info=True)  # never block startup


def _log_exit_reason(reason: str) -> None:
    """Log exit reason to pentool_exit_dump.log (best-effort, non-fatal)."""
    try:
        from pentool.core.config import DEFAULT_CONFIG_DIR

        (DEFAULT_CONFIG_DIR / "pentool_exit_dump.log").open("a").write(
            f"--- EXIT: {reason} ({__import__('time').strftime('%Y-%m-%d %H:%M:%S')}) ---\n"
        )
    except Exception:
        logger.warning("exit dump log write failed", exc_info=True)  # best-effort


def _ensure_pro_compatible(
    unsafe_skip: bool = False,
    auto_update: bool = False,
    no_check: bool = False,
) -> None:
    """Check PRO compatibility; exit(1) if unresolvable mismatch."""
    if no_check:
        return

    try:
        from pentool.core.license import is_pro_package_compatible

        compatible, warning = is_pro_package_compatible()
    except Exception:
        logger.debug("PRO compatibility check failed, assuming compatible", exc_info=True)
        compatible, warning = True, ""

    if not compatible:
        if auto_update:
            # CI/CD: update silently, no dialog
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
                logger.debug("auto-update PRO attempt (interactive) failed", exc_info=True)
        else:
            # Interactive mode: ask the user
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
                    pass  # continue without PRO
                elif choice in ("s", "skip"):
                    print("[pentool] Skipping PRO check. Use --no-check-updates to silence.", file=sys.stderr)
                    return  # skip the check entirely for this session
            except Exception:
                logger.debug("interactive PRO prompt failed", exc_info=True)

    if not compatible:
        if not unsafe_skip:
            print(f"[pentool] {warning}", file=sys.stderr)
            raise SystemExit(1)
        else:
            print(
                "[pentool] UNSAFE: --unsafe-skip-pro-compat-check set — starting anyway. PRO features stay disabled.",
                file=sys.stderr,
            )


def _warn_pro_mismatch(warning: str) -> None:
    """Show the PRO mismatch dialog in the terminal."""
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


def _start_tui(open_last: bool = False) -> None:
    """Start the Pentool TUI with ancillary setup (AI dialog, ping, kill orphans).

    Args:
        open_last: auto-open the most recent project at startup.
    """

    # Anonymous install-counter ping (fire-and-forget)
    try:
        from pentool.core.crash_reporter import send_first_run_ping

        threading.Thread(target=send_first_run_ping, daemon=True).start()
    except Exception:
        logger.debug("first-run ping failed", exc_info=True)

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
        logger.debug("AI setup dialog failed", exc_info=True)

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
            logger.error("crash reporter failed", exc_info=True)
        raise
    else:
        _log_exit_reason("run() returned cleanly (not via action_quit)")
        if _app is not None:
            try:
                _app._stop_proxy()
            except Exception:
                logger.debug("proxy cleanup on exit failed", exc_info=True)
        _dump_threads_and_exit()


def _dump_threads_and_exit() -> None:
    """Dump all thread stacks to exit dump log, then hard-exit."""
    import io
    import time as _time
    import traceback as _tb

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
                    summaries.append(
                        f"  ident={getattr(th, 'ident', None)} name={nm!r} "
                        f"daemon={getattr(th, 'daemon', '?')} target={tg_name}"
                    )
                except Exception:
                    logger.debug("thread desc failed, skipping", exc_info=True)
                    continue
            if summaries:
                buf.write("\n--- live threads (summary) ---\n" + "\n".join(summaries) + "\n")
        except Exception:
            logger.debug("thread summary dump failed", exc_info=True)
        for tid, frame in sys._current_frames().items():
            buf.write(f"\n--- Thread 0x{tid:x} ---\n")
            _tb.print_stack(frame, file=buf)
        try:
            import faulthandler

            fbuf = io.StringIO()
            faulthandler.dump_traceback(file=fbuf, all_threads=True)
            if faul := fbuf.getvalue().strip():
                buf.write(f"\n--- faulthandler ---\n{faul}\n")
        except Exception:
            logger.debug("faulthandler dump failed", exc_info=True)
        with open(log_path, "a") as f:
            f.write(buf.getvalue())
    except Exception:
        logger.debug("exit dump final write failed", exc_info=True)
    os._exit(0)


def main() -> None:
    # The unsafe flag is removed from argv before CLI dispatch because
    # click would reject the unknown option; _ensure_pro_compatible must
    # receive the skip flag as an explicit argument.
    unsafe_skip_pro_check = _UNSAFE_SKIP_PRO_CHECK_FLAG in sys.argv
    if unsafe_skip_pro_check:
        sys.argv.remove(_UNSAFE_SKIP_PRO_CHECK_FLAG)

    # CI/CD flags
    no_check_updates = _NO_CHECK_UPDATES_FLAG in sys.argv
    auto_update = _AUTO_UPDATE_FLAG in sys.argv
    for _flag in (_NO_CHECK_UPDATES_FLAG, _AUTO_UPDATE_FLAG):
        while _flag in sys.argv:
            sys.argv.remove(_flag)

    if len(sys.argv) > 1:
        # Single launch path: click is the only parser. A shim
        # `_run_target_mode` used to sit here, searching argv for a literal
        # `--smart`, so the JS browser install sometimes ran and sometimes did
        # not (the `--real` flag did not enable it). The install now lives in
        # cli/main.py next to `--smart`.
        from pentool.cli.main import cli

        cli()
    else:
        _ensure_pro_compatible(
            unsafe_skip=unsafe_skip_pro_check,
            auto_update=auto_update,
            no_check=no_check_updates,
        )
        _start_tui(open_last="--last" in sys.argv)


if __name__ == "__main__":
    main()
