"""Entry point: no arguments — TUI, with arguments — CLI."""

import sys
import threading


def main() -> None:
    if len(sys.argv) > 1:
        from pentool.cli.main import cli
        cli()
    else:
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
