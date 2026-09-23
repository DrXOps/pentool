"""Unit tests for pentool/tui/widgets/search_bar.py."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

from textual.widgets import Button

from pentool.tui.widgets.search_bar import SearchBar


def _make_bar() -> SearchBar:
    with patch("textual.widget.Widget.__init__", return_value=None):
        b = SearchBar.__new__(SearchBar)
    b._classes = set()
    b.styles = MagicMock()
    b._closing = False
    b._closed = False
    b._pruning = False
    b._regex_enabled = False
    b._search_target = "request"
    b.display = False
    return b


class TestInit:
    def test_css_loaded(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            b = SearchBar.__new__(SearchBar)
        assert len(b.DEFAULT_CSS) > 0

    def test_initial_state(self) -> None:
        b = _make_bar()
        assert b._regex_enabled is False
        assert b._search_target == "request"


class TestShowHide:
    def test_show_sets_display(self) -> None:
        b = _make_bar()
        b.display = False
        b.call_after_refresh = MagicMock()
        b.show()
        assert b.display is True

    def test_hide_sets_display_and_posts(self) -> None:
        b = _make_bar()
        with patch.object(SearchBar, "post_message") as pm:
            b.hide()
            assert b.display is False
            pm.assert_called_once()
            assert isinstance(pm.call_args[0][0], SearchBar.Closed)


class TestFireSearch:
    def test_fire_search_posts_message(self) -> None:
        b = _make_bar()
        inp = MagicMock()
        inp.value = "test"
        b.query_one = lambda sel, cls=None: inp if sel == "#search-input" else MagicMock()
        b.post_message = MagicMock()
        b._fire_search(1)
        b.post_message.assert_called_once()
        msg = b.post_message.call_args[0][0]
        assert isinstance(msg, SearchBar.Search)
        assert msg.query == "test"
        assert msg.regex is False
        assert msg.direction == 1

    def test_fire_search_empty_no_message(self) -> None:
        b = _make_bar()
        inp = MagicMock()
        inp.value = ""
        b.query_one = MagicMock(return_value=inp)
        b.post_message = MagicMock()
        b._fire_search(1)
        b.post_message.assert_not_called()

    def test_fire_search_with_regex(self) -> None:
        b = _make_bar()
        b._regex_enabled = True
        inp = MagicMock()
        inp.value = r"\d+"
        b.query_one = MagicMock(return_value=inp)
        b.post_message = MagicMock()
        b._fire_search(-1)
        msg = b.post_message.call_args[0][0]
        assert msg.regex is True
        assert msg.direction == -1

    def test_fire_search_query_failure(self) -> None:
        b = _make_bar()
        b.query_one = Mock(side_effect=Exception("boom"))
        b.post_message = MagicMock()
        b._fire_search(1)
        b.post_message.assert_not_called()


class TestToggleTarget:
    def test_toggle_switches_to_response(self) -> None:
        b = _make_bar()
        b._search_target = "request"
        tgt = MagicMock()
        b.query_one = lambda sel, cls=None: tgt if sel == "#search-target-toggle" else MagicMock()
        b.toggle_target()
        assert b._search_target == "response"
        tgt.update.assert_called_with("Resp")

    def test_toggle_switches_back(self) -> None:
        b = _make_bar()
        b._search_target = "response"
        tgt = MagicMock()
        b.query_one = lambda sel, cls=None: tgt if sel == "#search-target-toggle" else MagicMock()
        b.toggle_target()
        assert b._search_target == "request"
        tgt.update.assert_called_with("Req")

    def test_toggle_tolerates_exception(self) -> None:
        b = _make_bar()
        b._search_target = "request"
        b.query_one = Mock(side_effect=Exception("boom"))
        b.toggle_target()
        assert b._search_target == "response"


class TestRegexToggle:
    def test_toggle_regex_on(self) -> None:
        b = _make_bar()
        b._regex_enabled = False
        widget = MagicMock()
        widget.id = "search-regex-toggle"
        event = MagicMock()
        event.widget = widget
        b.on_static_click(event)
        assert b._regex_enabled is True
        widget.add_class.assert_called_once_with("-active")

    def test_toggle_regex_off(self) -> None:
        b = _make_bar()
        b._regex_enabled = True
        widget = MagicMock()
        widget.id = "search-regex-toggle"
        widget.classes = {"-active"}
        event = MagicMock()
        event.widget = widget
        b.on_static_click(event)
        assert b._regex_enabled is False
        widget.remove_class.assert_called_once_with("-active")


class TestInputSubmitted:
    def test_input_submitted_fires_search(self) -> None:
        b = _make_bar()
        b._fire_search = MagicMock()
        event = MagicMock()
        event.input.id = "search-input"
        b.on_input_submitted(event)
        b._fire_search.assert_called_once_with(1)

    def test_other_input_ignored(self) -> None:
        b = _make_bar()
        b._fire_search = MagicMock()
        event = MagicMock()
        event.input.id = "other"
        b.on_input_submitted(event)
        b._fire_search.assert_not_called()


class TestButtonPressed:
    def test_next_fires_forward(self) -> None:
        b = _make_bar()
        b._fire_search = MagicMock()
        event = MagicMock()
        event.button.id = "btn-next"
        b.on_button_pressed(event)
        b._fire_search.assert_called_once_with(1)

    def test_prev_fires_backward(self) -> None:
        b = _make_bar()
        b._fire_search = MagicMock()
        event = MagicMock()
        event.button.id = "btn-prev"
        b.on_button_pressed(event)
        b._fire_search.assert_called_once_with(-1)

    def test_other_button_ignored(self) -> None:
        b = _make_bar()
        b._fire_search = MagicMock()
        event = MagicMock()
        event.button.id = "other"
        b.on_button_pressed(event)
        b._fire_search.assert_not_called()


class TestSetCount:
    def test_set_count_shows_match(self) -> None:
        b = _make_bar()
        label = MagicMock()
        b.query_one = lambda sel, cls=None: label if sel == "#search-count" else MagicMock()
        b.set_count(3, 10)
        label.update.assert_called_once_with("3/10")

    def test_set_count_no_matches(self) -> None:
        b = _make_bar()
        label = MagicMock()
        b.query_one = lambda sel, cls=None: label if sel == "#search-count" else MagicMock()
        b.set_count(0, 0)
        label.update.assert_called_once_with("No matches")

    def test_set_count_tolerates_exception(self) -> None:
        b = _make_bar()
        b.query_one = Mock(side_effect=Exception("boom"))
        b.set_count(0, 0)


class TestMessages:
    def test_search_message(self) -> None:
        msg = SearchBar.Search("test", regex=True, direction=-1)
        assert msg.query == "test"
        assert msg.regex is True
        assert msg.direction == -1

    def test_target_toggle_message(self) -> None:
        msg = SearchBar.TargetToggle()
        assert isinstance(msg, SearchBar.TargetToggle)

    def test_closed_message(self) -> None:
        msg = SearchBar.Closed()
        assert isinstance(msg, SearchBar.Closed)


class TestKey:
    def test_escape_hides(self) -> None:
        b = _make_bar()
        b.hide = MagicMock()
        ev = _fake_key("escape")
        b.on_key(ev)
        b.hide.assert_called_once()

    def test_enter_fires_search(self) -> None:
        b = _make_bar()
        b._fire_search = MagicMock()
        ev = _fake_key("enter")
        b.on_key(ev)
        b._fire_search.assert_called_once_with(1)

    def test_tab_toggles_target(self) -> None:
        b = _make_bar()
        b.toggle_target = MagicMock()
        b.post_message = MagicMock()
        ev = _fake_key("tab")
        b.on_key(ev)
        b.toggle_target.assert_called_once()
        b.post_message.assert_called_once()



def _fake_key(key: str) -> MagicMock:
    ev = MagicMock()
    ev.key = key
    return ev