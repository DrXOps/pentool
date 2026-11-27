"""TabRegistry: the bookkeeping half of a document-tab screen (step 11, stage 1).

It has to be correct on its own before any screen adopts it: order, active tab after closing,
restore, and refusal to invent semantics the screens do not have (the last tab is not silently
protected — the screen decides).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from pentool.tui.widgets.tab_registry import TabRegistry


@dataclass
class _State:
    name: str


def test_new_tab_becomes_active_and_order_is_kept() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    registry.add("t1", _State("Request 1"))
    registry.add("t2", _State("Request 2"))

    assert registry.ids == ["t1", "t2"]
    assert registry.active_id == "t2"
    assert registry.active is not None and registry.active.name == "Request 2"


def test_add_without_activation_keeps_the_current_tab() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    registry.add("t1", _State("a"))
    registry.add("t2", _State("b"), activate=False)

    assert registry.active_id == "t1"


def test_closing_the_active_tab_moves_to_the_left_neighbour() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    for tab_id in ("t1", "t2", "t3"):
        registry.add(tab_id, _State(tab_id))

    closed = registry.close("t3")

    assert closed is not None and closed.name == "t3"
    assert registry.active_id == "t2", "активной должна стать соседняя слева вкладка"


def test_closing_a_background_tab_keeps_the_active_one() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    registry.add("t1", _State("a"))
    registry.add("t2", _State("b"))

    registry.close("t1")

    assert registry.active_id == "t2"


def test_closing_the_last_tab_leaves_no_active_tab() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    registry.add("only", _State("a"))

    registry.close("only")

    assert registry.active_id is None
    assert registry.ids == []


def test_unknown_tab_is_reported_not_invented() -> None:
    registry: TabRegistry[_State] = TabRegistry()

    assert registry.close("nope") is None
    assert registry.rename("nope", "x") is None
    with pytest.raises(KeyError):
        registry.activate("nope")
    with pytest.raises(ValueError):
        registry.add("dup", _State("a"))
        registry.add("dup", _State("b"))


def test_rename_writes_the_name_when_the_state_has_one() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    registry.add("t1", _State("old"))

    registry.rename("t1", "new")

    assert registry.get("t1") is not None and registry.get("t1").name == "new"


def test_rename_ignores_states_without_a_name_field() -> None:
    registry: TabRegistry[SimpleNamespace] = TabRegistry()
    registry.add("t1", SimpleNamespace())

    assert registry.rename("t1", "new") is not None  # no attribute to write, no crash


def test_restore_sets_the_given_active_tab_or_falls_back_to_the_last() -> None:
    registry: TabRegistry[_State] = TabRegistry()
    registry.replace_all([("a", _State("a")), ("b", _State("b"))], active="a")
    assert registry.active_id == "a"

    registry.replace_all([("c", _State("c")), ("d", _State("d"))], active="missing")
    assert registry.active_id == "d", "неизвестная активная вкладка откатывается на последнюю"
