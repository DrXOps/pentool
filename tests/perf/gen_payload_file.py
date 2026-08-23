"""Генератор гигантских файлов-пейлоадов для нагрузочных тестов Intruder.

Назначение: создать на диске файлы пейлоадов размером от десятков МБ до 1+ ГБ
таким образом, чтобы:
  - каждая строка была "качественной" по конвенции FilePayloadSource
    (непустая, не начинается с '#') — иначе ленивый источник её пропустит;
  - размер и число строк были детерминированными и воспроизводимыми;
  - запись шла бинарными чанками 4 МБ, держа память O(1) независимо от
    итогового размера файла (никаких промежуточных list[str] всего файла).

Строка имеет вид:  <hex-приставка>:<payload>
  - hex-приставка из произвольного префикса файла + монотонного счётчика
    делает строки уникальными (важно: Intruder/спайдер дедуплицируют URL,
    а cluster-bomb перечитывает наборы — повторы строк исказили бы замер);
  - <payload> — псевдо-случайный алфавит заданной длины.

Использование:
    python3 tests/perf/gen_payload_file.py --path tests/perf/_data/p_100MB.txt --target-size 100M
    python3 tests/perf/gen_payload_file.py --path ... --lines 10_000_000 --line-len 24
    python3 tests/perf/gen_payload_file.py --list          # показать уже сгенерированные

Управление размером:
  --target-size 100M / 1G  — удобно для тестов "файл X МБ в памяти O(1)".
  --lines N --line-len L   — точный контроль числа строк (для тестов,
                             где важен счётчик строк, а не байты).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_CHUNK = 4 * 1024 * 1024  # 4 МБ
_SEP = b":"
_LINE_END = b"\n"


def _parse_size(text: str) -> int:
    """'100M' -> 100*1024*1024; '1G' -> 1*1024**3; также голые int (байты)."""
    text = text.strip().upper()
    mult = 1
    if text.endswith("G"):
        mult = 1024 ** 3
        text = text[:-1]
    elif text.endswith("M"):
        mult = 1024 ** 2
        text = text[:-1]
    elif text.endswith("K"):
        mult = 1024
        text = text[:-1]
    text = text.replace("_", "").replace(",", "")
    return int(float(text) * mult)


def _line_for(i: int, line_len: int, prefix_len: int) -> bytes:
    """Одна строка-байт для индекса i."""
    # hex(i) — короткая приставка; добиваем до prefix_len букв '0', чтобы
    # сортировка/дедуп не зависели от длины числа.
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
    """Записать файл-пейлоад. Либо target_size, либо lines (не оба).

    Возвращает {'lines': N, 'bytes': B, 'elapsed_s': S, 'mib_per_s': X}.
    """
    path_p = Path(path)
    path_p.parent.mkdir(parents=True, exist_ok=True)
    if path_p.exists() and not overwrite:
        raise FileExistsError(
            f"{path} уже существует. Передайте --overwrite или другой --path."
        )

    if (target_size is not None) == (lines is not None):
        raise ValueError("Задайте ровно одно из --target-size / --lines (не оба).")

    t0 = time.monotonic()
    written = 0
    i = 0
    last_report = time.monotonic()
    with open(path_p, "wb") as f:
        # Писать можем большими чанками: набираем буфер, пока не упрёмся в
        # разумный предел (8 МБ), затем flush. Так Python реже входит в
        # write() на очень короткие строки (строка ~32 байта — write per
        # line был бы избыточен).
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
    return {"lines": i, "bytes": written, "elapsed_s": round(elapsed, 3),
            "mib_per_s": round(mib_per_s, 1)}


def list_generated(data_dir: str) -> list[tuple[str, int, int]]:
    """[(relpath, bytes, lines-guess)] для существующих файлов в _data/."""
    out = []
    dp = Path(data_dir)
    if dp.is_dir():
        for p in sorted(dp.iterdir()):
            if p.is_file():
                out.append((p.name, p.stat().st_size, 0))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=None, help="Путь к файлу (default: tests/perf/_data/payload.txt)")
    ap.add_argument("--target-size", type=_parse_size, default=None, help="Пример: 100M, 1G")
    ap.add_argument("--lines", type=int, default=None, help="Точное число строк")
    ap.add_argument("--line-len", type=int, default=32, help="Длина payload-строки (байт)")
    ap.add_argument("--overwrite", action="store_true", help="Перезаписать существующий файл")
    ap.add_argument("--list", action="store_true", dest="list_", help="Показать сгенерированные")
    args = ap.parse_args(argv)

    if args.list_:
        for name, size, _lines in list_generated(str(Path(__file__).parent / "_data")):
            print(f"{name:40s} {size/(1024*1024):8.1f} MiB")
        return 0

    base = Path(__file__).parent / "_data"
    path = args.path or str(base / "payload_generic.txt")

    def _progress(written: int, total: int, n_lines: int) -> None:
        if total:
            pct = 100.0 * written / total
        else:
            pct = 100.0
        print(f"\r  {pct:6.1f}%  {written/(1024*1024):8.1f} MiB  {n_lines:15,d} строк",
              end="", flush=True)

    try:
        res = generate(path, target_size=args.target_size, lines=args.lines,
                       line_len=args.line_len, overwrite=args.overwrite,
                       on_progress=_progress)
    except (FileExistsError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    print()
    print(f"Готово: {path}")
    print(f"  строк: {res['lines']:,}")
    print(f"  байт : {res['bytes']:,}  ({res['bytes']/(1024*1024):.1f} MiB)")
    print(f"  время: {res['elapsed_s']} с  ({res['mib_per_s']} MiB/с)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
