"""Generator of giant payload files for Intruder load tests.

Purpose: create payload files on disk sized from tens of MB to 1+ GB
in such a way that:
  - every line is "high-quality" per the FilePayloadSource convention
    (non-empty, does not start with '#') — otherwise the lazy source skips it;
  - size and line count are deterministic and reproducible;
  - writing goes in binary 4 MB chunks, keeping memory O(1) regardless of
    the final file size (no intermediate list[str] of the whole file).

A line looks like:  <hex-prefix>:<payload>
  - the hex-prefix is built from an arbitrary file prefix + a monotonic counter,
    which makes lines unique (important: Intruder/spider deduplicate URLs,
    and cluster-bomb re-reads the sets — repeated lines would distort the measurement);
  - <payload> — a pseudo-random alphabet of the given length.

Usage:
    python3 tests/perf/gen_payload_file.py --path tests/perf/_data/p_100MB.txt --target-size 100M
    python3 tests/perf/gen_payload_file.py --path ... --lines 10_000_000 --line-len 24
    python3 tests/perf/gen_payload_file.py --list          # show already generated files

Size control:
  --target-size 100M / 1G  — handy for "file of X MB in O(1) memory" tests.
  --lines N --line-len L   — exact control of the line count (for tests
                             where the line counter matters, not the bytes).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_CHUNK = 4 * 1024 * 1024  # 4 MiB
_SEP = b":"
_LINE_END = b"\n"


def _parse_size(text: str) -> int:
    """'100M' -> 100*1024*1024; '1G' -> 1*1024**3; bare ints (bytes) too."""
    text = text.strip().upper()
    mult = 1
    if text.endswith("G"):
        mult = 1024**3
        text = text[:-1]
    elif text.endswith("M"):
        mult = 1024**2
        text = text[:-1]
    elif text.endswith("K"):
        mult = 1024
        text = text[:-1]
    text = text.replace("_", "").replace(",", "")
    return int(float(text) * mult)


def _line_for(i: int, line_len: int, prefix_len: int) -> bytes:
    """One line of bytes for index i."""
    # hex(i) — a short prefix; pad with '0' chars up to prefix_len so that
    # sorting/dedup does not depend on the length of the number.
    idx = hex(i)[2:]
    prefix = idx.rjust(max(prefix_len, len(idx)), "0")
    return prefix.encode("ascii") + _SEP + (b"a" * (line_len - prefix_len - 1))


def generate(
    path: str,
    *,
    target_size: int | None = None,
    lines: int | None = None,
    line_len: int = 32,
    prefix_len: int = 8,
    overwrite: bool = False,
    on_progress=None,
) -> dict:
    """Write a payload file. Either target_size or lines (not both).

    Returns {'lines': N, 'bytes': B, 'elapsed_s': S, 'mib_per_s': X}.
    """
    path_p = Path(path)
    path_p.parent.mkdir(parents=True, exist_ok=True)
    if path_p.exists() and not overwrite:
        raise FileExistsError(f"{path} уже существует. Передайте --overwrite или другой --path.")

    if (target_size is not None) == (lines is not None):
        raise ValueError("Задайте ровно одно из --target-size / --lines (не оба).")

    t0 = time.monotonic()
    written = 0
    i = 0
    last_report = time.monotonic()
    with open(path_p, "wb") as f:
        # We can write in large chunks: accumulate the buffer until it hits a
        # sensible limit (8 MB), then flush. That way Python enters write()
        # less often on very short lines (a line is ~32 bytes — a write per
        # line would be excessive).
        buf = bytearray()
        while lines is None or i < lines:
            line = _line_for(i, line_len, prefix_len) + _LINE_END
            buf += line
            i += 1
            written += len(line)
            if len(buf) >= _CHUNK * 2:
                f.write(bytes(buf))
                buf.clear()
            if target_size is not None and written >= target_size:
                break
            now = time.monotonic()
            if on_progress is not None and (now - last_report) >= 0.25:
                last_report = now
                on_progress(written, target_size or 0, i)
        if buf:
            f.write(bytes(buf))
    elapsed = time.monotonic() - t0
    mib_per_s = (written / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
    return {"lines": i, "bytes": written, "elapsed_s": round(elapsed, 3), "mib_per_s": round(mib_per_s, 1)}


def list_generated(data_dir: str) -> list[tuple[str, int, int]]:
    """[(relpath, bytes, lines-guess)] for the existing files in _data/."""
    out = []
    dp = Path(data_dir)
    if dp.is_dir():
        for p in sorted(dp.iterdir()):
            if p.is_file():
                out.append((p.name, p.stat().st_size, 0))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=None, help="Путь к файлу (default: tests/perf/_data/payload.txt)")
    ap.add_argument("--target-size", type=_parse_size, default=None, help="Пример: 100M, 1G")
    ap.add_argument("--lines", type=int, default=None, help="Точное число строк")
    ap.add_argument("--line-len", type=int, default=32, help="Длина payload-строки (байт)")
    ap.add_argument("--overwrite", action="store_true", help="Перезаписать существующий файл")
    ap.add_argument("--list", action="store_true", dest="list_", help="Показать сгенерированные")
    args = ap.parse_args(argv)

    if args.list_:
        for name, size, _lines in list_generated(str(Path(__file__).parent / "_data")):
            print(f"{name:40s} {size / (1024 * 1024):8.1f} MiB")
        return 0

    base = Path(__file__).parent / "_data"
    path = args.path or str(base / "payload_generic.txt")

    def _progress(written: int, total: int, n_lines: int) -> None:
        if total:
            pct = 100.0 * written / total
        else:
            pct = 100.0
        print(f"\r  {pct:6.1f}%  {written / (1024 * 1024):8.1f} MiB  {n_lines:15,d} строк", end="", flush=True)

    try:
        res = generate(
            path,
            target_size=args.target_size,
            lines=args.lines,
            line_len=args.line_len,
            overwrite=args.overwrite,
            on_progress=_progress,
        )
    except (FileExistsError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    print()
    print(f"Готово: {path}")
    print(f"  строк: {res['lines']:,}")
    print(f"  байт : {res['bytes']:,}  ({res['bytes'] / (1024 * 1024):.1f} MiB)")
    print(f"  время: {res['elapsed_s']} с  ({res['mib_per_s']} MiB/с)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
