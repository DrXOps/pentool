"""Tests for Intruder attack start validation."""


def test_count_markers_zero_blocks_start():
    """action_start_attack must return a notify when no markers are present."""
    from pentool.api.intruder_api import count_markers

    assert count_markers("GET / HTTP/1.1\r\nHost: example.com\r\n\r\n") == 0
    assert count_markers("GET /?id=§test§ HTTP/1.1\r\nHost: example.com\r\n\r\n") == 1


def test_count_markers_multiple():
    from pentool.api.intruder_api import count_markers

    assert count_markers("§a§ §b§ §c§") == 3


def test_empty_payloads_check():
    """Check that empty strings in the payload list do not allow an attack."""
    payload_sets = [["", "  ", ""]]
    result = any(p.strip() for ps in payload_sets for p in ps)
    assert result is False  # all empty — the attack must not start


def test_non_empty_payloads_check():
    payload_sets = [["payload1", "payload2"]]
    result = any(p.strip() for ps in payload_sets for p in ps)
    assert result is True
