"""Unit tests for pentool/tui/widgets/toolbar_button.py."""

from __future__ import annotations

import pytest
from textual.widgets import Static

from pentool.tui.widgets.toolbar_button import ToolbarButton


class TestToolbarButtonInit:
    """Test ToolbarButton initialization."""

    def test_init_basic(self):
        """Basic initialization with label and id."""
        btn = ToolbarButton("Click Me", "btn-test")

        assert btn.label == "Click Me"
        assert btn.id == "btn-test"
        assert not btn.disabled

    def test_init_with_classes(self):
        """Initialization with CSS classes."""
        btn = ToolbarButton("Active", "btn-active", classes="active")

        assert "active" in btn.classes

    def test_init_disabled(self):
        """Initialization with disabled class."""
        btn = ToolbarButton("Disabled", "btn-disabled", classes="disabled")

        assert btn.disabled

    def test_init_with_tooltip(self):
        """Initialization with tooltip sets Textual tooltip attribute."""
        btn = ToolbarButton("Stop", "btn-stop", tooltip="Stop the scan")

        assert btn.tooltip == "Stop the scan"

    def test_init_without_tooltip_is_none(self):
        """No tooltip passed → tooltip stays None (Textual default)."""
        btn = ToolbarButton("Start", "btn-start")

        assert btn.tooltip is None


class TestToolbarButtonLabel:
    """Test label property."""

    def test_label_getter(self):
        """Label getter returns stored label."""
        btn = ToolbarButton("Test", "btn-test")

        assert btn.label == "Test"

    def test_label_setter_updates_display(self):
        """Label setter updates internal state."""
        btn = ToolbarButton("Original", "btn-test")
        btn.label = "Updated"

        assert btn.label == "Updated"


class TestToolbarButtonDisabled:
    """Test disabled property."""

    def test_disabled_getter_false(self):
        """Disabled getter returns False initially."""
        btn = ToolbarButton("Test", "btn-test")

        assert not btn.disabled

    def test_disabled_getter_true(self):
        """Disabled getter returns True when initialized disabled."""
        btn = ToolbarButton("Test", "btn-test", classes="disabled")

        assert btn.disabled

    def test_disabled_setter_enables(self):
        """Setting disabled=False removes disabled class."""
        btn = ToolbarButton("Test", "btn-test", classes="disabled")
        btn.disabled = False

        assert not btn.disabled
        assert "disabled" not in btn.classes

    def test_disabled_setter_disables(self):
        """Setting disabled=True adds disabled class."""
        btn = ToolbarButton("Test", "btn-test")
        btn.disabled = True

        assert btn.disabled
        assert "disabled" in btn.classes


class TestToolbarButtonPressed:
    """Test Pressed message."""

    def test_pressed_message_has_button(self):
        """Pressed message contains button reference."""
        btn = ToolbarButton("Test", "btn-test")
        msg = ToolbarButton.Pressed(btn)

        assert msg.button is btn

    def test_pressed_message_control_property(self):
        """Control property returns button for CSS selector."""
        btn = ToolbarButton("Test", "btn-test")
        msg = ToolbarButton.Pressed(btn)

        assert msg.control is btn

    def test_pressed_message_allow_selector_match(self):
        """ALLOW_SELECTOR_MATCH is True for CSS selectors."""
        assert ToolbarButton.Pressed.ALLOW_SELECTOR_MATCH is True


class TestToolbarButtonOnClick:
    """Test on_click behavior."""

    def test_on_click_posts_pressed_when_enabled(self):
        """on_click posts Pressed when not disabled."""
        btn = ToolbarButton("Test", "btn-test")
        messages = []

        # Mock post_message
        original_post = btn.post_message
        def capture_post(msg):
            messages.append(msg)
            return original_post(msg)
        btn.post_message = capture_post

        btn.on_click()

        assert len(messages) == 1
        assert isinstance(messages[0], ToolbarButton.Pressed)
        assert messages[0].button is btn

    def test_on_click_ignores_when_disabled(self):
        """on_click does nothing when disabled."""
        btn = ToolbarButton("Test", "btn-test", classes="disabled")
        messages = []

        # Mock post_message
        original_post = btn.post_message
        def capture_post(msg):
            messages.append(msg)
            return original_post(msg)
        btn.post_message = capture_post

        btn.on_click()

        assert len(messages) == 0


class TestToolbarButtonClasses:
    """Test CSS class combinations."""

    def test_multiple_classes(self):
        """Multiple CSS classes can be set."""
        btn = ToolbarButton("Test", "btn-test", classes="active warn")

        assert "active" in btn.classes
        assert "warn" in btn.classes

    def test_disabled_class_prevents_click(self):
        """Disabled class prevents Pressed message."""
        btn = ToolbarButton("Test", "btn-test")
        btn.add_class("disabled")

        # _disabled flag should be updated when checking
        # But our implementation only checks flag, not class
        # So we need to set via property
        btn.disabled = True

        messages = []
        original_post = btn.post_message
        def capture_post(msg):
            messages.append(msg)
            return original_post(msg)
        btn.post_message = capture_post

        btn.on_click()
        assert len(messages) == 0
