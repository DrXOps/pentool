"""Entry point: no arguments — TUI, with arguments — CLI."""

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
