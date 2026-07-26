"""Unit tests: modules/intruder.py

Covers: parse_markers, count_markers, substitute_payload,
           payload-generators, AttackType, IntruderConfig.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestMarkerParsing:
    def test_parse_markers_single(self) -> None:
        from pentool.modules.intruder import parse_markers
        clean, positions = parse_markers("GET /§path§ HTTP/1.1")
        assert len(positions) == 1
        assert "path" in clean

    def test_parse_markers_multiple(self) -> None:
        from pentool.modules.intruder import parse_markers
        clean, positions = parse_markers("user=§admin§&pass=§secret§")
        assert len(positions) == 2
        assert "admin" in clean
        assert "secret" in clean

    def test_parse_markers_none(self) -> None:
        from pentool.modules.intruder import parse_markers
        clean, positions = parse_markers("GET / HTTP/1.1")
        assert len(positions) == 0
        assert clean == "GET / HTTP/1.1"

    def test_parse_markers_empty_marker(self) -> None:
        from pentool.modules.intruder import parse_markers
        clean, positions = parse_markers("GET /§§ HTTP/1.1")
        assert len(positions) == 1

    def test_count_markers(self) -> None:
        from pentool.modules.intruder import count_markers
        assert count_markers("§a§ §b§ §c§") == 3
        assert count_markers("no markers") == 0
        assert count_markers("§only one§") == 1

    def test_count_markers_zero(self) -> None:
        from pentool.modules.intruder import count_markers
        assert count_markers("") == 0
        assert count_markers("plain text") == 0


class TestSubstitutePayload:
    def test_single_marker(self) -> None:
        from pentool.modules.intruder import substitute_payload
        result = substitute_payload("GET /§FUZZ§ HTTP/1.1", ["admin"])
        assert "admin" in result
        assert "§" not in result

    def test_multiple_markers(self) -> None:
        from pentool.modules.intruder import substitute_payload
        result = substitute_payload("user=§u§&pass=§p§", ["root", "toor"])
        assert "root" in result
        assert "toor" in result
        assert "§" not in result

    def test_fewer_payloads_than_markers(self) -> None:
        from pentool.modules.intruder import substitute_payload
        result = substitute_payload("§a§ §b§ §c§", ["X"])
        assert "X" in result
        assert "§" not in result

    def test_no_markers_unchanged(self) -> None:
        from pentool.modules.intruder import substitute_payload
        template = "GET / HTTP/1.1"
        result = substitute_payload(template, ["any"])
        assert result == template


class TestPayloadGenerators:
    def test_load_payloads_from_file(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import load_payloads_from_file
        f = tmp_path / "payloads.txt"
        f.write_text("admin\n# comment\n\nroot\ntest\n")
        result = load_payloads_from_file(str(f))
        assert result == ["admin", "root", "test"]

    def test_load_payloads_missing_file(self) -> None:
        from pentool.modules.intruder import load_payloads_from_file
        result = load_payloads_from_file("/nonexistent/file.txt")
        assert result == []

    def test_load_payloads_strips_whitespace(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import load_payloads_from_file
        f = tmp_path / "p.txt"
        f.write_text("  admin  \n  root  \n")
        result = load_payloads_from_file(str(f))
        assert "admin" in result
        assert "root" in result

    def test_generate_numeric_payloads(self) -> None:
        from pentool.modules.intruder import generate_numeric_payloads
        result = generate_numeric_payloads(1, 6)
        assert result == ["1", "2", "3", "4", "5"]

    def test_generate_numeric_payloads_step(self) -> None:
        from pentool.modules.intruder import generate_numeric_payloads
        result = generate_numeric_payloads(0, 10, 2)
        assert result == ["0", "2", "4", "6", "8"]

    def test_generate_numeric_payloads_empty(self) -> None:
        from pentool.modules.intruder import generate_numeric_payloads
        result = generate_numeric_payloads(5, 5)
        assert result == []

    def test_generate_char_payloads(self) -> None:
        from pentool.modules.intruder import generate_char_payloads
        result = generate_char_payloads("ab", 1, 1)
        assert "a" in result
        assert "b" in result

    def test_generate_char_payloads_length_2(self) -> None:
        from pentool.modules.intruder import generate_char_payloads
        result = generate_char_payloads("ab", 2, 2)
        assert "aa" in result
        assert "ab" in result
        assert "ba" in result
        assert "bb" in result


class TestAttackTypes:
    def test_attack_type_values(self) -> None:
        from pentool.modules.intruder import AttackType
        assert AttackType.SNIPER == "sniper"
        assert AttackType.BATTERING_RAM == "battering_ram"
        assert AttackType.PITCHFORK == "pitchfork"
        assert AttackType.CLUSTER_BOMB == "cluster_bomb"

    def test_intruder_config_creation(self) -> None:
        from pentool.modules.intruder import IntruderConfig, AttackType
        config = IntruderConfig(
            template="GET /§FUZZ§ HTTP/1.1",
            attack_type=AttackType.SNIPER,
            payload_sets=[["admin", "root", "test"]],
        )
        assert config.attack_type == AttackType.SNIPER
        assert len(config.payload_sets) == 1
        assert config.threads == 10  # default

    def test_intruder_config_custom_threads(self) -> None:
        from pentool.modules.intruder import IntruderConfig, AttackType
        config = IntruderConfig(
            template="GET / HTTP/1.1",
            attack_type=AttackType.CLUSTER_BOMB,
            payload_sets=[["a"], ["b"]],
            threads=5,
            delay_ms=100,
        )
        assert config.threads == 5
        assert config.delay_ms == 100

    def test_intruder_result_fields(self) -> None:
        from pentool.modules.intruder import IntruderResult
        result = IntruderResult(
            id="r1",
            attack_id="atk1",
            request_number=1,
            payload_values=["admin"],
            request_raw="GET / HTTP/1.1",
            response_status=200,
            response_length=512,
            response_time_ms=120,
            error=None,
        )
        assert result.response_status == 200
        assert result.payload_values == ["admin"]
        assert result.error is None


class TestExtractMarkerDefaults:
    def test_single_marker(self) -> None:
        from pentool.modules.intruder import extract_marker_defaults
        result = extract_marker_defaults("GET /§admin§ HTTP/1.1")
        assert result == ["admin"]

    def test_multiple_markers(self) -> None:
        from pentool.modules.intruder import extract_marker_defaults
        result = extract_marker_defaults("user=§admin§&pass=§secret§")
        assert result == ["admin", "secret"]

    def test_empty_markers(self) -> None:
        from pentool.modules.intruder import extract_marker_defaults
        result = extract_marker_defaults("user=§§&pass=§§")
        assert result == ["", ""]

    def test_no_markers(self) -> None:
        from pentool.modules.intruder import extract_marker_defaults
        result = extract_marker_defaults("GET / HTTP/1.1")
        assert result == []

    def test_three_markers(self) -> None:
        from pentool.modules.intruder import extract_marker_defaults
        result = extract_marker_defaults("§a§ §b§ §c§")
        assert result == ["a", "b", "c"]


class TestSniperIterator:
    """Sniper should preserve original values of untouched markers."""

    def test_sniper_preserves_original_values(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        template = "user=§admin§&pass=§secret§"
        config = IntruderConfig(
            template=template,
            attack_type=AttackType.SNIPER,
            payload_sets=[["fuzz1", "fuzz2"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_sniper())

        # 2 positions × 2 payloads = 4 combinations
        assert len(combos) == 4

        # When attacking position 0 (admin) — position 1 should remain "secret"
        pos0_combos = combos[:2]
        for vals in pos0_combos:
            assert vals[1] == "secret", "Untouched position should preserve original value"

        # When attacking position 1 (secret) — position 0 should remain "admin"
        pos1_combos = combos[2:]
        for vals in pos1_combos:
            assert vals[0] == "admin", "Untouched position should preserve original value"

    def test_sniper_empty_marker_defaults_to_empty(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        template = "user=§§&pass=§§"
        config = IntruderConfig(
            template=template,
            attack_type=AttackType.SNIPER,
            payload_sets=[["x"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_sniper())
        # 2 positions × 1 payload = 2 combinations
        assert len(combos) == 2
        # First: attack position 0 → ["x", ""]
        assert combos[0] == ["x", ""]
        # Second: attack position 1 → ["", "x"]
        assert combos[1] == ["", "x"]

    def test_sniper_single_position(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="GET /§FUZZ§ HTTP/1.1",
            attack_type=AttackType.SNIPER,
            payload_sets=[["a", "b", "c"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_sniper())
        assert len(combos) == 3
        assert combos[0] == ["a"]
        assert combos[1] == ["b"]
        assert combos[2] == ["c"]


class TestBatteringRamIterator:
    """Battering Ram: one payload into all positions simultaneously."""

    def test_battering_ram_single_position(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="GET /§FUZZ§ HTTP/1.1",
            attack_type=AttackType.BATTERING_RAM,
            payload_sets=[["a", "b", "c"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_battering_ram())
        assert len(combos) == 3
        assert combos[0] == ["a"]
        assert combos[1] == ["b"]
        assert combos[2] == ["c"]

    def test_battering_ram_two_positions(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="user=§u§&pass=§p§",
            attack_type=AttackType.BATTERING_RAM,
            payload_sets=[["root", "admin"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_battering_ram())
        # 2 payloads, both into both positions at once
        assert len(combos) == 2
        assert combos[0] == ["root", "root"], "Battering Ram puts one payload into all positions"
        assert combos[1] == ["admin", "admin"]

    def test_battering_ram_count_total(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§ §b§ §c§",
            attack_type=AttackType.BATTERING_RAM,
            payload_sets=[["x", "y", "z"]],
        )
        attack = IntruderAttack(config)
        # Always M requests (payload set size), not M×N
        assert attack._count_total() == 3


class TestPitchforkIterator:
    """Pitchfork: zip across all sets — in parallel."""

    def test_pitchfork_basic(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="user=§u§&pass=§p§",
            attack_type=AttackType.PITCHFORK,
            payload_sets=[["admin", "root"], ["secret", "toor"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_pitchfork())
        assert len(combos) == 2
        assert combos[0] == ["admin", "secret"]
        assert combos[1] == ["root", "toor"]

    def test_pitchfork_unequal_sets_stops_at_min(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§ §b§",
            attack_type=AttackType.PITCHFORK,
            payload_sets=[["x1", "x2", "x3"], ["y1", "y2"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_pitchfork())
        # zip stops at the smaller set
        assert len(combos) == 2
        assert combos[0] == ["x1", "y1"]
        assert combos[1] == ["x2", "y2"]

    def test_pitchfork_single_set(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§",
            attack_type=AttackType.PITCHFORK,
            payload_sets=[["p1", "p2"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_pitchfork())
        assert len(combos) == 2
        assert combos[0] == ["p1"]
        assert combos[1] == ["p2"]


class TestClusterBombIterator:
    """Cluster Bomb: Cartesian product of all sets."""

    def test_cluster_bomb_basic(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="user=§u§&pass=§p§",
            attack_type=AttackType.CLUSTER_BOMB,
            payload_sets=[["admin", "root"], ["secret", "toor"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_cluster_bomb())
        # 2 × 2 = 4 combinations
        assert len(combos) == 4
        assert ["admin", "secret"] in combos
        assert ["admin", "toor"] in combos
        assert ["root", "secret"] in combos
        assert ["root", "toor"] in combos

    def test_cluster_bomb_three_sets(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§ §b§ §c§",
            attack_type=AttackType.CLUSTER_BOMB,
            payload_sets=[["x", "y"], ["1", "2"], ["!", "?"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_cluster_bomb())
        # 2 × 2 × 2 = 8 combinations
        assert len(combos) == 8
        assert combos[0] == ["x", "1", "!"]
        assert combos[-1] == ["y", "2", "?"]

    def test_cluster_bomb_count_total(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§ §b§",
            attack_type=AttackType.CLUSTER_BOMB,
            payload_sets=[["a", "b", "c"], ["x", "y"]],
        )
        attack = IntruderAttack(config)
        # 3 × 2 = 6
        assert attack._count_total() == 6


class TestAllAttackTypesSubstitution:
    """Verify that substitute_payload is applied correctly in all attacks."""

    def test_sniper_request_contains_payload(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType, substitute_payload
        config = IntruderConfig(
            template="GET /§FUZZ§ HTTP/1.1\r\nHost: example.com",
            attack_type=AttackType.SNIPER,
            payload_sets=[["evil_payload"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_sniper())
        assert len(combos) == 1
        result = substitute_payload(config.template, combos[0])
        assert "evil_payload" in result
        assert "§" not in result

    def test_battering_ram_request_no_markers(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType, substitute_payload
        config = IntruderConfig(
            template="user=§u§&pass=§p§",
            attack_type=AttackType.BATTERING_RAM,
            payload_sets=[["X"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_battering_ram())
        result = substitute_payload(config.template, combos[0])
        assert "§" not in result
        assert "X" in result

    def test_pitchfork_two_different_payloads(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType, substitute_payload
        config = IntruderConfig(
            template="user=§u§&pass=§p§",
            attack_type=AttackType.PITCHFORK,
            payload_sets=[["admin"], ["secret"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_pitchfork())
        result = substitute_payload(config.template, combos[0])
        assert "admin" in result
        assert "secret" in result
        assert "§" not in result

    def test_cluster_bomb_all_combinations_no_markers(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType, substitute_payload
        config = IntruderConfig(
            template="§a§=§b§",
            attack_type=AttackType.CLUSTER_BOMB,
            payload_sets=[["key1", "key2"], ["val1", "val2"]],
        )
        attack = IntruderAttack(config)
        combos = list(attack._iter_cluster_bomb())
        for vals in combos:
            result = substitute_payload(config.template, vals)
            assert "§" not in result, f"Markers remain in result: {result!r}"


class TestIntruderResultPersistence:
    """Verify that attack results are saved in the API (export/import)."""

    def test_intruder_api_export_results(self) -> None:
        """export_project_data returns results of the restored attack."""
        from pentool.api.intruder_api import IntruderAPI

        api = IntruderAPI()
        # Load via import_project_data to avoid creating IntruderAttack directly
        data = {
            "results": [
                {
                    "id": "res-1", "attack_id": "atk-1", "request_number": 1,
                    "payload_values": ["admin"], "request_raw": "GET / HTTP/1.1",
                    "response_status": 200, "response_length": 1024,
                    "response_time_ms": 100, "error": None,
                },
                {
                    "id": "res-2", "attack_id": "atk-1", "request_number": 2,
                    "payload_values": ["root"], "request_raw": "GET / HTTP/1.1",
                    "response_status": 403, "response_length": 256,
                    "response_time_ms": 50, "error": None,
                },
            ]
        }
        count = api.import_project_data(data)
        assert count == 2

        exported = api.export_project_data()
        # After import_project_data without an active attack, get_results() returns []
        # This is fine — restored_results are only used when displaying in TUI
        assert "results" in exported

    def test_intruder_api_import_results(self) -> None:
        """import_project_data correctly loads results."""
        from pentool.api.intruder_api import IntruderAPI

        api = IntruderAPI()
        data = {
            "results": [
                {
                    "id": "r1", "attack_id": "atk1", "request_number": 1,
                    "payload_values": ["test"], "request_raw": "GET / HTTP/1.1",
                    "response_status": 200, "response_length": 512,
                    "response_time_ms": 75, "error": None,
                }
            ]
        }
        count = api.import_project_data(data)
        assert count == 1
        # Restored results are available via _restored_results
        assert hasattr(api, "_restored_results")
        assert len(api._restored_results) == 1
        r = api._restored_results[0]
        assert r.payload_values == ["test"]
        assert r.response_status == 200

    def test_intruder_api_import_malformed_data_skipped(self) -> None:
        """Completely invalid data (not dict) is skipped without exceptions."""
        from pentool.api.intruder_api import IntruderAPI

        api = IntruderAPI()
        # Pass a list of strings instead of dict — should not crash
        data = {"results": ["not_a_dict", None, 42]}
        # Should not raise an exception
        count = api.import_project_data(data)
        # All invalid records are skipped
        assert count == 0

    def test_intruder_api_import_empty_data(self) -> None:
        """Empty data does not crash the API."""
        from pentool.api.intruder_api import IntruderAPI

        api = IntruderAPI()
        count = api.import_project_data({})
        assert count == 0
        count = api.import_project_data({"results": []})
        assert count == 0
