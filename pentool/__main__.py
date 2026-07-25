"""Точка входа: без аргументов — TUI, с аргументами — CLI."""

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from pentool.cli.main import cli
        cli()
    else:
        from pentool.tui.app import PentoolApp
        PentoolApp().run()


if __name__ == "__main__":
    main()
