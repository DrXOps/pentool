"""Entry point: no arguments — TUI, with arguments — CLI."""

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from pentool.cli.main import cli
        cli()
    else:
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
