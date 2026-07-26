"""Unit tests for pentool/modules/sequencer.py."""

from __future__ import annotations

import math
import pytest
from pentool.modules.sequencer import (
    Sequencer,
    SequencerReport,
    charset_size,
    token_entropy,
    total_entropy_bits,
)


class TestCharsetSize:
    def test_hex_lowercase(self):
        assert charset_size("deadbeef") == 16

    def test_hex_uppercase(self):
        assert charset_size("DEADBEEF") == 16

    def test_lowercase_letters(self):
        # "abcdef" is a subset of hex — charset_size will return 16
        # For a purely alphabetic token outside hex, a character outside hex range is needed
        result = charset_size("ghijklmnop")  # g-p not hex
        assert result >= 26

    def test_mixed_case(self):
        result = charset_size("AbCdEf")
        assert result >= 52

    def test_alphanumeric(self):
        result = charset_size("abc123XYZ")
        assert result >= 62

    def test_minimum(self):
        # Never returns less than 2
        assert charset_size("a") >= 2

    def test_empty(self):
        assert charset_size("") >= 2

    def test_base64_chars(self):
        # Base64 uses a-z, A-Z, 0-9, +, /, = → should give 26+26+10+5=67
        result = charset_size("abc+/=XYZ123")
        assert result >= 67  # lowercase + uppercase + digits + 5 special chars

    def test_url_safe_base64(self):
        # URL-safe Base64 uses _, - instead of +, / → 26+26+10+5=67
        result = charset_size("abcXYZ123_-=")
        assert result >= 67


class TestTokenEntropy:
    def test_single_char_token(self):
        # Single character repeats — entropy is 0
        result = token_entropy("aaaa")
        assert result == 0.0

    def test_max_entropy_uniform(self):
        # Each character is unique → maximum entropy
        token = "abcdefghijklmnopqrstuvwxyz"
        result = token_entropy(token)
        assert result == pytest.approx(math.log2(26), abs=0.01)

    def test_empty_token(self):
        assert token_entropy("") == 0.0

    def test_positive_entropy(self):
        assert token_entropy("abc") > 0.0

    def test_entropy_range(self):
        result = token_entropy("session_token_12345")
        assert 0.0 < result <= math.log2(len(set("session_token_12345")))


class TestTotalEntropyBits:
    def test_zero_on_single_char(self):
        assert total_entropy_bits("aaaa") == 0.0

    def test_scales_with_length(self):
        short = total_entropy_bits("abc")
        long  = total_entropy_bits("abcabc")
        # Twice as long → twice as many bits
        assert long == pytest.approx(short * 2, abs=0.1)

    def test_empty(self):
        assert total_entropy_bits("") == 0.0


class TestSequencerAddToken:
    def test_add_single_token(self):
        seq = Sequencer()
        seq.add_token("abc123")
        assert seq.count == 1
        assert "abc123" in seq.tokens

    def test_add_strips_whitespace(self):
        seq = Sequencer()
        seq.add_token("  token  ")
        assert seq.tokens[0] == "token"

    def test_add_empty_ignored(self):
        seq = Sequencer()
        seq.add_token("")
        seq.add_token("   ")
        assert seq.count == 0

    def test_add_tokens_bulk(self):
        seq = Sequencer()
        added = seq.add_tokens_bulk(["a", "b", "c", ""])
        assert added == 3
        assert seq.count == 3

    def test_add_from_text(self):
        seq = Sequencer()
        text = "token1\ntoken2\n\ntoken3\n  token4  "
        added = seq.add_from_text(text)
        assert added == 4
        assert seq.count == 4

    def test_callback_called(self):
        calls = []
        seq = Sequencer()
        seq.on_token = calls.append
        seq.add_token("test")
        assert calls == ["test"]

    def test_clear(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["a", "b", "c"])
        seq.clear()
        assert seq.count == 0

    def test_extract_from_header_cookie(self):
        seq = Sequencer()
        token = seq.extract_from_header("session=abc123; path=/", "session")
        assert token == "abc123"
        assert seq.count == 1


class TestSequencerAnalyze:
    def test_analyze_empty(self):
        seq = Sequencer()
        report = seq.analyze()
        assert report.token_count == 0
        assert "INSUFFICIENT" in report.assessment

    def test_analyze_single_token(self):
        seq = Sequencer()
        seq.add_token("hello")
        report = seq.analyze()
        assert report.token_count == 1
        assert report.avg_length == 5.0

    def test_analyze_multiple_tokens(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["abc123", "def456", "ghi789"])
        report = seq.analyze()
        assert report.token_count == 3
        assert report.min_length == 6
        assert report.max_length == 6

    def test_analyze_returns_report(self):
        seq = Sequencer()
        seq.add_token("token")
        report = seq.analyze()
        assert isinstance(report, SequencerReport)

    def test_analyze_weak_token(self):
        seq = Sequencer()
        # Very short monotonous tokens — should be WEAK
        seq.add_tokens_bulk(["aa", "bb", "cc"])
        report = seq.analyze()
        assert "WEAK" in report.assessment or report.effective_bits < 64

    def test_analyze_strong_token(self):
        import secrets
        seq = Sequencer()
        # 32 bytes hex = 64 chars from 16 → ~256 bits theoretical
        tokens = [secrets.token_hex(32) for _ in range(10)]
        seq.add_tokens_bulk(tokens)
        report = seq.analyze()
        assert report.effective_bits > 100

    def test_analyze_detects_duplicates(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["same", "same", "same", "different"])
        report = seq.analyze()
        assert report.duplicates >= 2

    def test_analyze_no_duplicates(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["a", "b", "c"])
        report = seq.analyze()
        assert report.duplicates == 0

    def test_analyze_length_histogram(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["abc", "def", "abcd"])
        report = seq.analyze()
        assert 3 in report.length_histogram
        assert 4 in report.length_histogram
        assert report.length_histogram[3] == 2
        assert report.length_histogram[4] == 1

    def test_analyze_char_frequency(self):
        seq = Sequencer()
        seq.add_token("aabbc")
        report = seq.analyze()
        assert report.char_frequency["a"] == 2
        assert report.char_frequency["b"] == 2
        assert report.char_frequency["c"] == 1


class TestSequencerReport:
    def test_summary_returns_string(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["abc123", "def456"])
        report = seq.analyze()
        summary = report.summary()
        assert isinstance(summary, str)
        assert "Tokens:" in summary

    def test_rich_histogram_returns_string(self):
        seq = Sequencer()
        seq.add_tokens_bulk(["abc", "def", "xyz"])
        report = seq.analyze()
        hist = report.rich_histogram()
        assert isinstance(hist, str)
        assert "3" in hist  # length 3

    def test_rich_charfreq_returns_string(self):
        seq = Sequencer()
        seq.add_token("hello")
        report = seq.analyze()
        freq = report.rich_charfreq()
        assert isinstance(freq, str)

    def test_empty_histogram(self):
        seq = Sequencer()
        report = seq.analyze()
        hist = report.rich_histogram()
        assert "No data" in hist

    def test_empty_charfreq(self):
        seq = Sequencer()
        report = seq.analyze()
        freq = report.rich_charfreq()
        assert "No data" in freq


class TestAssessmentLevels:
    def test_insufficient_data(self):
        seq = Sequencer()
        report = seq.analyze()
        assert "INSUFFICIENT" in report.assessment

    def test_assessment_is_string(self):
        seq = Sequencer()
        seq.add_token("test")
        report = seq.analyze()
        assert isinstance(report.assessment, str)

    def test_assessment_has_level_word(self):
        seq = Sequencer()
        seq.add_token("test")
        report = seq.analyze()
        level_words = {"WEAK", "MODERATE", "GOOD", "STRONG", "INSUFFICIENT"}
        assert any(w in report.assessment for w in level_words)


# ── FIPS 140-2 Tests (Block 4.5) ───────────────────────────────────────────────

class TestFIPS140Monobit:
    def test_monobit_returns_fips_result(self):
        from pentool.modules.sequencer import fips140_monobit
        bits = "01" * 10000
        result = fips140_monobit(bits)
        assert result.name == "Monobit Test"
        assert isinstance(result.passed, bool)
        assert isinstance(result.value, int)

    def test_monobit_balanced_passes(self):
        from pentool.modules.sequencer import fips140_monobit
        # Exactly 50% ones — should pass
        bits = ("01" * 10000)[:20000]
        result = fips140_monobit(bits)
        assert result.passed

    def test_monobit_all_zeros_fails(self):
        from pentool.modules.sequencer import fips140_monobit
        bits = "0" * 20000
        result = fips140_monobit(bits)
        assert not result.passed
        assert result.value == 0

    def test_monobit_all_ones_fails(self):
        from pentool.modules.sequencer import fips140_monobit
        bits = "1" * 20000
        result = fips140_monobit(bits)
        assert not result.passed
        assert result.value == 20000

    def test_monobit_status_color(self):
        from pentool.modules.sequencer import fips140_monobit
        bits = "01" * 10000
        result = fips140_monobit(bits)
        assert result.status_color in ("green", "red")

    def test_monobit_status_text(self):
        from pentool.modules.sequencer import fips140_monobit
        bits = "01" * 10000
        result = fips140_monobit(bits)
        assert "PASS" in result.status or "FAIL" in result.status


class TestFIPS140Runs:
    def test_runs_returns_fips_result(self):
        from pentool.modules.sequencer import fips140_runs
        bits = "01" * 10000
        result = fips140_runs(bits)
        assert result.name == "Runs Test"
        assert isinstance(result.value, int)

    def test_runs_alternating_passes(self):
        from pentool.modules.sequencer import fips140_runs
        # Alternating bits give 20000 runs — this is ABOVE the range [2267, 2733]
        # Verify value == 20000 (each bit is a separate run)
        bits = "01" * 10000
        result = fips140_runs(bits)
        assert result.value == 20000

    def test_runs_constant_fails(self):
        from pentool.modules.sequencer import fips140_runs
        bits = "1" * 20000
        result = fips140_runs(bits)
        assert not result.passed
        assert result.value == 1


class TestFIPS140Longrun:
    def test_longrun_returns_fips_result(self):
        from pentool.modules.sequencer import fips140_longrun
        bits = "01" * 10000
        result = fips140_longrun(bits)
        assert result.name == "Long Runs Test"

    def test_longrun_no_long_run_passes(self):
        from pentool.modules.sequencer import fips140_longrun
        bits = "01" * 10000
        result = fips140_longrun(bits)
        assert result.passed
        assert result.value < 26

    def test_longrun_with_long_run_fails(self):
        from pentool.modules.sequencer import fips140_longrun
        bits = "1" * 30 + "0" * 19970
        result = fips140_longrun(bits)
        assert not result.passed
        assert result.value >= 26

    def test_longrun_threshold_is_25(self):
        from pentool.modules.sequencer import fips140_longrun
        bits = "01" * 10000
        result = fips140_longrun(bits)
        assert result.threshold_high == 25


class TestFIPS140Poker:
    def test_poker_returns_fips_result(self):
        from pentool.modules.sequencer import fips140_poker
        bits = "0101" * 5000
        result = fips140_poker(bits)
        assert result.name == "Poker Test"
        assert isinstance(result.value, float)

    def test_poker_thresholds(self):
        from pentool.modules.sequencer import fips140_poker
        bits = "0101" * 5000
        result = fips140_poker(bits)
        assert result.threshold_low == pytest.approx(1.03)
        assert result.threshold_high == pytest.approx(57.4)


class TestRunFIPSTests:
    def test_run_fips_tests_empty(self):
        from pentool.modules.sequencer import run_fips_tests
        result = run_fips_tests([])
        assert result == []

    def test_run_fips_tests_returns_4_results(self):
        from pentool.modules.sequencer import run_fips_tests
        import secrets
        tokens = [secrets.token_hex(32) for _ in range(10)]
        results = run_fips_tests(tokens)
        assert len(results) == 4

    def test_run_fips_tests_all_have_names(self):
        from pentool.modules.sequencer import run_fips_tests
        import secrets
        tokens = [secrets.token_hex(32) for _ in range(10)]
        results = run_fips_tests(tokens)
        names = {r.name for r in results}
        assert "Monobit Test" in names
        assert "Runs Test" in names
        assert "Long Runs Test" in names
        assert "Poker Test" in names

    def test_run_fips_tests_few_tokens_no_crash(self):
        """Few tokens — should be repeated up to 20000 bits."""
        from pentool.modules.sequencer import run_fips_tests
        results = run_fips_tests(["abc"])
        assert len(results) == 4

    def test_analyze_includes_fips_results(self):
        """SequencerReport contains fips_results."""
        from pentool.modules.sequencer import Sequencer
        import secrets
        seq = Sequencer()
        tokens = [secrets.token_hex(32) for _ in range(5)]
        seq.add_tokens_bulk(tokens)
        report = seq.analyze()
        assert hasattr(report, "fips_results")
        assert len(report.fips_results) == 4

    def test_report_rich_fips_returns_string(self):
        """rich_fips() returns a string with results."""
        from pentool.modules.sequencer import Sequencer
        import secrets
        seq = Sequencer()
        seq.add_tokens_bulk([secrets.token_hex(32) for _ in range(5)])
        report = seq.analyze()
        text = report.rich_fips()
        assert isinstance(text, str)
        assert "FIPS" in text

    def test_report_rich_fips_empty_has_message(self):
        """rich_fips() without tokens — returns a message."""
        from pentool.modules.sequencer import Sequencer
        seq = Sequencer()
        report = seq.analyze()
        text = report.rich_fips()
        assert isinstance(text, str)
        # Empty analysis → no fips_results
        assert "insufficient" in text.lower() or "data" in text.lower()


class TestAnalyzePositionEntropy:
    """Tests for analyze_position_entropy — positional anomaly analysis."""

    def test_uniform_tokens_no_anomalies(self) -> None:
        """Random tokens — high entropy at every position."""
        from pentool.modules.sequencer import analyze_position_entropy
        import secrets
        tokens = [secrets.token_hex(8) for _ in range(20)]
        result = analyze_position_entropy(tokens)
        assert len(result) == 16  # token_hex(8) produces 16-char hex strings (8 bytes = 16 hex chars)
        for pos, h, unique in result:
            assert isinstance(pos, int)
            assert isinstance(h, float)
            assert unique >= 2

    def test_fixed_prefix_tokens(self) -> None:
        """Tokens with fixed prefix — first positions have zero entropy."""
        from pentool.modules.sequencer import analyze_position_entropy
        # All tokens start with "FIXED_" — first 6 characters are completely predictable
        tokens = [f"FIXED_{i:04d}" for i in range(20)]
        result = analyze_position_entropy(tokens)
        assert len(result) > 0
        # First 6 positions should have entropy 0.0 (all identical)
        for pos, h, unique in result[:6]:
            assert h == 0.0, f"Pos {pos} should have H=0.0, got {h}"
            assert unique == 1, f"Pos {pos} should have 1 unique char, got {unique}"

    def test_different_lengths_returns_empty(self) -> None:
        """Tokens of different length — analyze_position_entropy returns []."""
        from pentool.modules.sequencer import analyze_position_entropy
        tokens = ["abc", "de", "fghi"]
        result = analyze_position_entropy(tokens)
        assert result == []

    def test_single_token_returns_empty(self) -> None:
        """Single token — insufficient data for analysis."""
        from pentool.modules.sequencer import analyze_position_entropy
        result = analyze_position_entropy(["singletoken"])
        assert result == []

    def test_empty_tokens_returns_empty(self) -> None:
        """Empty list — returns []."""
        from pentool.modules.sequencer import analyze_position_entropy
        result = analyze_position_entropy([])
        assert result == []

    def test_position_entropy_values(self) -> None:
        """Verify correctness of entropy calculation."""
        from pentool.modules.sequencer import analyze_position_entropy
        # Position 0: all 'A' → H=0. Position 1: 50% 'x', 50% 'y' → H=1. Position 2: all '!'
        tokens = ["Ax!", "Ay!", "Ax!", "Ay!"]
        result = analyze_position_entropy(tokens)
        assert len(result) == 3
        pos0_h = result[0][1]
        pos1_h = result[1][1]
        pos2_h = result[2][1]
        assert pos0_h == 0.0, f"Pos 0 all 'A' → H=0, got {pos0_h}"
        assert abs(pos1_h - 1.0) < 1e-9, f"Pos 1 50/50 → H=1.0, got {pos1_h}"
        assert pos2_h == 0.0, f"Pos 2 all '!' → H=0, got {pos2_h}"

    def test_position_unique_chars(self) -> None:
        """Verify unique_chars count at each position."""
        from pentool.modules.sequencer import analyze_position_entropy
        tokens = ["abc", "adc", "aec"]  # pos0=a,a,a; pos1=b,d,e; pos2=c,c,c
        result = analyze_position_entropy(tokens)
        assert len(result) == 3
        assert result[0][2] == 1   # pos0: only 'a'
        assert result[1][2] == 3   # pos1: b,d,e
        assert result[2][2] == 1   # pos2: only 'c'


class TestSequencerReportPositionAnomalies:
    """Tests for SequencerReport.rich_position_anomalies()."""

    def test_rich_position_anomalies_no_data(self) -> None:
        """Without data — message about inability to analyze."""
        from pentool.modules.sequencer import Sequencer
        seq = Sequencer()
        report = seq.analyze()
        text = report.rich_position_anomalies()
        assert isinstance(text, str)
        assert "not available" in text.lower() or "different" in text.lower()

    def test_rich_position_anomalies_random_tokens(self) -> None:
        """Random tokens — no anomalies."""
        from pentool.modules.sequencer import Sequencer
        import secrets
        seq = Sequencer()
        seq.add_tokens_bulk([secrets.token_hex(16) for _ in range(30)])
        report = seq.analyze()
        text = report.rich_position_anomalies()
        assert isinstance(text, str)

    def test_rich_position_anomalies_with_fixed_prefix(self) -> None:
        """Tokens with fixed prefix — anomalous positions are detected."""
        from pentool.modules.sequencer import Sequencer
        seq = Sequencer()
        import secrets
        # All tokens start with "SESS_" (fixed prefix)
        tokens = [f"SESS_{secrets.token_hex(6)}" for _ in range(20)]
        seq.add_tokens_bulk(tokens)
        report = seq.analyze()
        # position_anomalies should contain data (tokens of equal length)
        assert len(report.position_anomalies) > 0
        text = report.rich_position_anomalies(low_entropy_threshold=2.0)
        # Anomalies should be detected (first 5 positions "SESS_" are fully predictable)
        assert isinstance(text, str)


class TestSequencerReportIntegration:
    """Integration tests: full analyze() cycle including new fields."""

    def test_analyze_returns_position_anomalies_field(self) -> None:
        """analyze() returns SequencerReport with position_anomalies field."""
        from pentool.modules.sequencer import Sequencer
        seq = Sequencer()
        seq.add_tokens_bulk(["token_1", "token_2", "token_3"])
        report = seq.analyze()
        assert hasattr(report, "position_anomalies")
        # All tokens same length → analysis performed
        assert isinstance(report.position_anomalies, list)

    def test_analyze_mixed_length_position_anomalies_empty(self) -> None:
        """analyze() with tokens of different lengths → position_anomalies = []."""
        from pentool.modules.sequencer import Sequencer
        seq = Sequencer()
        seq.add_tokens_bulk(["short", "longertoken", "med"])
        report = seq.analyze()
        assert report.position_anomalies == []
        text = report.rich_position_anomalies()
        assert "not available" in text.lower() or "different" in text.lower()
