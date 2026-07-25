"""Sequencer — анализ энтропии токенов (сессионных ID, CSRF-токенов и т.д.)."""

from __future__ import annotations

import math
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

__all__ = [
    "Sequencer", "SequencerReport", "token_entropy", "charset_size",
    "fips140_monobit", "fips140_runs", "fips140_longrun", "fips140_poker",
    "run_fips_tests", "analyze_position_entropy",
]


def charset_size(token: str) -> int:
    """Определить размер алфавита токена."""
    if not token:
        return 2

    has_lower = any(c in string.ascii_lowercase for c in token)
    has_upper = any(c in string.ascii_uppercase for c in token)
    has_digit = any(c in string.digits for c in token)
    has_spec  = any(c in "+/=_-" for c in token)

    # Чисто hex-строка (только 0-9, a-f или 0-9, A-F)
    lower_hex = set("0123456789abcdef")
    upper_hex = set("0123456789ABCDEF")
    token_set = set(token)
    if token_set <= lower_hex or token_set <= upper_hex:
        return 16

    cs = 0
    if has_lower:
        cs += 26
    if has_upper:
        cs += 26
    if has_digit:
        cs += 10
    if has_spec:
        cs += 5  # "+/=_-" — 5 символов
    return max(cs, 2)


def token_entropy(token: str) -> float:
    """Вычислить энтропию токена в битах на символ.

    Формула: H = log2(charset_size) * len(token) / len(token)
    Уточнённая: считаем фактическое распределение символов.
    """
    if not token:
        return 0.0
    freq = Counter(token)
    total = len(token)
    entropy = 0.0
    for count in freq.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def total_entropy_bits(token: str) -> float:
    """Общая энтропия токена в битах = H * len."""
    return token_entropy(token) * len(token)


# ── FIPS 140-2 Statistical Tests ─────────────────────────────────────────────

def _tokens_to_bitstring(tokens: list[str]) -> str:
    """Преобразовать список токенов в битовую строку для FIPS-тестов."""
    bits = []
    for token in tokens:
        for ch in token:
            byte = ord(ch) & 0xFF
            bits.append(f"{byte:08b}")
    return "".join(bits)


@dataclass
class FIPSTestResult:
    """Результат одного FIPS 140-2 теста."""
    name: str
    passed: bool
    value: float | int
    threshold_low: float | int | None
    threshold_high: float | int | None
    description: str

    @property
    def status(self) -> str:
        return "PASS ✓" if self.passed else "FAIL ✗"

    @property
    def status_color(self) -> str:
        return "green" if self.passed else "red"


def fips140_monobit(bits: str) -> FIPSTestResult:
    """FIPS 140-2 Test 1: Monobit Test.

    Подсчитывает количество единиц в 20000 битах.
    Тест проходит если: 9654 < count_ones < 10346.
    """
    sample = bits[:20000].ljust(20000, "0")
    count_ones = sample.count("1")
    passed = 9654 < count_ones < 10346
    return FIPSTestResult(
        name="Monobit Test",
        passed=passed,
        value=count_ones,
        threshold_low=9654,
        threshold_high=10346,
        description="Count of 1-bits in 20000 bits (FIPS threshold: 9654–10346)",
    )


def fips140_runs(bits: str) -> FIPSTestResult:
    """FIPS 140-2 Test 3: Runs Test.

    Подсчитывает количество серий (runs) единиц и нулей.
    Тест проходит если количество серий в диапазоне [2267, 2733].
    """
    sample = bits[:20000].ljust(20000, "0")
    runs = 1
    for i in range(1, len(sample)):
        if sample[i] != sample[i - 1]:
            runs += 1
    passed = 2267 <= runs <= 2733
    return FIPSTestResult(
        name="Runs Test",
        passed=passed,
        value=runs,
        threshold_low=2267,
        threshold_high=2733,
        description="Number of runs (consecutive identical bits) in 20000 bits",
    )


def fips140_longrun(bits: str) -> FIPSTestResult:
    """FIPS 140-2 Test 4: Long Runs Test.

    Проверяет наличие серий длиной >= 26.
    Тест проходит если таких серий нет.
    """
    sample = bits[:20000].ljust(20000, "0")
    max_run = 0
    cur_run = 1
    for i in range(1, len(sample)):
        if sample[i] == sample[i - 1]:
            cur_run += 1
            max_run = max(max_run, cur_run)
        else:
            cur_run = 1
    passed = max_run < 26
    return FIPSTestResult(
        name="Long Runs Test",
        passed=passed,
        value=max_run,
        threshold_low=None,
        threshold_high=25,
        description="Longest run of identical bits (must be < 26)",
    )


def fips140_poker(bits: str) -> FIPSTestResult:
    """FIPS 140-2 Test 2: Poker Test.

    Делит 20000 бит на 5000 4-битных групп и проверяет их распределение.
    X = (16/5000) * sum(ni^2) - 5000
    Тест проходит если 1.03 < X < 57.4.
    """
    sample = bits[:20000].ljust(20000, "0")
    # Разбить на 4-битные группы
    groups: dict[str, int] = {}
    for i in range(0, 20000, 4):
        nibble = sample[i:i + 4]
        groups[nibble] = groups.get(nibble, 0) + 1
    total_groups = 5000
    x = (16.0 / total_groups) * sum(v * v for v in groups.values()) - total_groups
    passed = 1.03 < x < 57.4
    return FIPSTestResult(
        name="Poker Test",
        passed=passed,
        value=round(x, 3),
        threshold_low=1.03,
        threshold_high=57.4,
        description="Poker statistic X for 5000 4-bit groups (FIPS threshold: 1.03–57.4)",
    )


def run_fips_tests(tokens: list[str]) -> list[FIPSTestResult]:
    if not tokens:
        return []
    bits = _tokens_to_bitstring(tokens)
    if len(bits) < 20000:
        # Повторяем биты циклически до 20000 (для малых наборов токенов)
        reps = math.ceil(20000 / len(bits))
        bits = (bits * reps)[:20000]
    return [
        fips140_monobit(bits),
        fips140_poker(bits),
        fips140_runs(bits),
        fips140_longrun(bits),
    ]


def analyze_position_entropy(tokens: list[str]) -> list[tuple[int, float, int]]:
    """Анализ энтропии по позиции для fixed-length токенов.

    Для каждой позиции вычисляет энтропию (разнообразие символов).
    Позиции с низкой энтропией — потенциальные аномалии (слабые позиции).

    Args:
        tokens: Список токенов одинаковой длины.

    Returns:
        Список кортежей (position, entropy_bits, unique_chars).
        Возвращает пустой список если токены разной длины или < 2 токенов.
    """
    if len(tokens) < 2:
        return []
    lengths = {len(t) for t in tokens}
    if len(lengths) != 1:
        return []  # Разная длина — анализ по позиции невозможен
    token_len = lengths.pop()
    result = []
    for pos in range(token_len):
        chars = [t[pos] for t in tokens if pos < len(t)]
        if not chars:
            continue
        counter = Counter(chars)
        unique = len(counter)
        total = len(chars)
        # Энтропия Шеннона по символам в позиции
        h = 0.0
        for count in counter.values():
            p = count / total
            if p > 0:
                h -= p * math.log2(p)
        result.append((pos, h, unique))
    return result


@dataclass
class SequencerReport:
    """Результат анализа набора токенов."""

    tokens: list[str]
    token_count: int
    avg_length: float
    min_length: int
    max_length: int
    charset_estimate: int
    mean_entropy: float         # средняя H бит/символ
    mean_total_bits: float      # среднее H * len
    effective_bits: float       # оценка реальной стойкости
    assessment: str             # WEAK / MODERATE / GOOD / STRONG
    length_histogram: dict[int, int]     # len → count
    char_frequency: dict[str, int]       # char → count
    duplicates: int
    fips_results: list[FIPSTestResult] = field(default_factory=list)  # FIPS 140-2 тесты
    position_anomalies: list[tuple[int, float, int]] = field(default_factory=list)
    # (position, entropy_bits, unique_chars) — для fixed-length токенов

    def summary(self) -> str:
        """Однострочное резюме для UI."""
        dup_str = f"  ⚠ {self.duplicates} dupes" if self.duplicates else ""
        return (
            f"Tokens: {self.token_count}  "
            f"Len: {self.min_length}–{self.max_length} (avg {self.avg_length:.1f})  "
            f"Charset: ~{self.charset_estimate}  "
            f"Entropy: {self.mean_entropy:.2f} bits/char  "
            f"Total: {self.mean_total_bits:.0f} bits  "
            f"[{self.assessment}]{dup_str}"
        )

    def rich_histogram(self, width: int = 30) -> str:
        """Гистограмма длин токенов в Rich markup."""
        if not self.length_histogram:
            return "[dim]No data[/dim]"
        max_count = max(self.length_histogram.values())
        lines = ["[bold]── Length Distribution ──[/bold]"]
        for length in sorted(self.length_histogram):
            cnt = self.length_histogram[length]
            bar_len = int((cnt / max_count) * width)
            bar = "█" * bar_len
            lines.append(f"[cyan]{length:3d}[/cyan] [green]{bar:<{width}}[/green] {cnt}")
        return "\n".join(lines)

    def rich_fips(self) -> str:
        """Таблица FIPS 140-2 результатов в Rich markup."""
        if not self.fips_results:
            return "[dim]FIPS 140-2: insufficient data (need more tokens)[/dim]"
        lines = ["[bold]── FIPS 140-2 Statistical Tests ──[/bold]"]
        all_pass = all(r.passed for r in self.fips_results)
        for r in self.fips_results:
            color = r.status_color
            lo = f"{r.threshold_low}" if r.threshold_low is not None else "—"
            hi = f"{r.threshold_high}" if r.threshold_high is not None else "—"
            lines.append(
                f"  [{color}]{r.status}[/{color}]  "
                f"[yellow]{r.name:<22}[/yellow] "
                f"value=[cyan]{r.value}[/cyan]  "
                f"range=[dim]{lo}–{hi}[/dim]"
            )
        overall = "[bold green]ALL PASS ✓[/bold green]" if all_pass else "[bold red]SOME TESTS FAILED ✗[/bold red]"
        lines.append(f"\n  Overall: {overall}")
        return "\n".join(lines)

    def rich_charfreq(self, top_n: int = 20) -> str:
        """Топ символов по частоте в Rich markup."""
        if not self.char_frequency:
            return "[dim]No data[/dim]"
        total = sum(self.char_frequency.values())
        sorted_chars = sorted(self.char_frequency.items(), key=lambda x: -x[1])[:top_n]
        lines = ["[bold]── Character Frequency (top) ──[/bold]"]
        for ch, cnt in sorted_chars:
            pct = cnt / total * 100
            bar = "▪" * max(1, int(pct / 2))
            display = repr(ch) if ch in "\n\r\t" else ch
            lines.append(f"[yellow]{display}[/yellow]  [green]{bar:<20}[/green]  {cnt} ({pct:.1f}%)")
        return "\n".join(lines)

    def rich_position_anomalies(self, low_entropy_threshold: float = 1.0) -> str:
        """Таблица аномалий по позициям (для fixed-length токенов).

        Args:
            low_entropy_threshold: Порог энтропии в битах ниже которого
                позиция считается аномальной (мало разнообразия символов).

        Returns:
            Rich markup строка с таблиц��й или сообщение что анализ невозможен.
        """
        if not self.position_anomalies:
            return "[dim]Position analysis: not available (tokens have different lengths or insufficient data)[/dim]"

        anomalies = [(pos, h, u) for pos, h, u in self.position_anomalies if h < low_entropy_threshold]
        if not anomalies:
            return "[bold green]── Position Analysis: No anomalies ✓ ──[/bold green]"

        lines = [f"[bold red]── Position Anomalies ({len(anomalies)} weak positions) ──[/bold red]"]
        lines.append(f"[dim]Threshold: H < {low_entropy_threshold:.1f} bits (low entropy = predictable chars)[/dim]")
        lines.append("")
        for pos, h, unique in anomalies:
            bar_len = max(1, int(unique / 2))
            bar = "░" * bar_len
            color = "red" if h < 0.5 else "yellow"
            lines.append(
                f"  pos [cyan]{pos:4d}[/cyan]: H=[{color}]{h:.3f}[/{color}] bits  "
                f"unique=[yellow]{unique:3d}[/yellow]  [{color}]{bar}[/{color}]"
            )
        return "\n".join(lines)


class Sequencer:
    """Захват и анализ токенов для оценки их стойкости."""

    def __init__(self) -> None:
        self._tokens: list[str] = []
        self.on_token: Callable[[str | None, None]] = None  # коллбэк при добавлении

    # ── Захват токенов ────────────────────────────────────────────────────────

    def add_token(self, token: str) -> None:
        token = token.strip()
        if token:
            self._tokens.append(token)
            if self.on_token:
                self.on_token(token)

    def add_tokens_bulk(self, tokens: list[str]) -> int:
        added = 0
        for t in tokens:
            t = t.strip()
            if t:
                self._tokens.append(t)
                added += 1
        return added

    def add_from_text(self, text: str) -> int:
        """Извлечь токены из многострочного текста (по одному на строку)."""
        tokens = [line.strip() for line in text.splitlines() if line.strip()]
        return self.add_tokens_bulk(tokens)

    def extract_from_header(self, header_value: str, param: str) -> str | None:
        """Попытаться извлечь значение параметра из строки заголовка/Cookie.

        Например: 'session=abc123; path=/' с param='session' → 'abc123'
        """
        # Cookie-style: key=value; ...
        pattern = re.compile(rf"(?:^|[;&\s]){re.escape(param)}=([^;&\s]+)")
        m = pattern.search(header_value)
        if m:
            self.add_token(m.group(1))
            return m.group(1)
        # Просто всё значение
        self.add_token(header_value)
        return header_value

    def clear(self) -> None:
        self._tokens.clear()

    @property
    def count(self) -> int:
        return len(self._tokens)

    @property
    def tokens(self) -> list[str]:
        return list(self._tokens)

    # ── Анализ ───────────────────────────────────────────────────────────────

    def analyze(self) -> SequencerReport:
        """Проанализировать накопленные токены и вернуть отчёт."""
        tokens = self._tokens
        if not tokens:
            return SequencerReport(
                tokens=[], token_count=0, avg_length=0.0,
                min_length=0, max_length=0, charset_estimate=0,
                mean_entropy=0.0, mean_total_bits=0.0, effective_bits=0.0,
                assessment="INSUFFICIENT DATA",
                length_histogram={}, char_frequency={}, duplicates=0,
            )

        lengths = [len(t) for t in tokens]
        avg_len = sum(lengths) / len(lengths)
        min_len = min(lengths)
        max_len = max(lengths)

        charsets = [charset_size(t) for t in tokens]
        avg_charset = int(sum(charsets) / len(charsets))

        entropies = [token_entropy(t) for t in tokens]
        total_bits_list = [total_entropy_bits(t) for t in tokens]
        mean_H = sum(entropies) / len(entropies)
        mean_bits = sum(total_bits_list) / len(total_bits_list)

        # Реальная стойкость: min от теоретической и фактической
        theoretical_bits = math.log2(avg_charset) * avg_len if avg_charset > 1 else 0
        effective = min(mean_bits, theoretical_bits)

        # Оценка
        if effective < 32:
            assessment = "WEAK ⚠️"
        elif effective < 64:
            assessment = "MODERATE ⚡"
        elif effective < 128:
            assessment = "GOOD ✓"
        else:
            assessment = "STRONG 🔒"

        # Гистограмма длин
        hist: dict[int, int] = {}
        for ln in lengths:
            hist[ln] = hist.get(ln, 0) + 1

        # Частота символов
        char_freq: dict[str, int] = {}
        for t in tokens:
            for ch in t:
                char_freq[ch] = char_freq.get(ch, 0) + 1

        # Дубликаты
        duplicates = len(tokens) - len(set(tokens))

        # FIPS 140-2 тесты
        fips = run_fips_tests(list(tokens))

        # Анализ аномалий по позициям (только для fixed-length токенов)
        pos_anomalies = analyze_position_entropy(list(tokens))

        return SequencerReport(
            tokens=list(tokens),
            token_count=len(tokens),
            avg_length=avg_len,
            min_length=min_len,
            max_length=max_len,
            charset_estimate=avg_charset,
            mean_entropy=mean_H,
            mean_total_bits=mean_bits,
            effective_bits=effective,
            assessment=assessment,
            length_histogram=hist,
            char_frequency=char_freq,
            duplicates=duplicates,
            fips_results=fips,
            position_anomalies=pos_anomalies,
        )
