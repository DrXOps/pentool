"""Точка входа: без аргументов — TUI, с аргументами — CLI."""

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
            # Отправляем анонимный отчёт об ошибке (если не отключено в настройках)
            try:
                from pentool.core.crash_reporter import send_crash
                send_crash(exc)
            except Exception:
                pass
            raise


if __name__ == "__main__":
    main()
