"""Tests for the centralized theme module."""

from vdj_manager.ui.theme import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeColors,
    ThemeManager,
    generate_stylesheet,
)


class TestThemeColors:
    """Tests for ThemeColors dataclass."""

    def test_dark_theme_has_all_fields(self):
        """DARK_THEME should have all color fields populated."""
        for field in ThemeColors.__dataclass_fields__:
            value = getattr(DARK_THEME, field)
            assert isinstance(value, str), f"{field} should be a string"
            assert len(value) > 0, f"{field} should not be empty"

    def test_light_theme_has_all_fields(self):
        """LIGHT_THEME should have all color fields populated."""
        for field in ThemeColors.__dataclass_fields__:
            value = getattr(LIGHT_THEME, field)
            assert isinstance(value, str), f"{field} should be a string"
            assert len(value) > 0, f"{field} should not be empty"

    def test_themes_have_same_fields(self):
        """Both themes should define the same set of fields."""
        dark_fields = set(ThemeColors.__dataclass_fields__.keys())
        # Light theme is also a ThemeColors instance
        light_fields = {f for f in ThemeColors.__dataclass_fields__ if hasattr(LIGHT_THEME, f)}
        assert dark_fields == light_fields

    def test_dark_and_light_differ(self):
        """Dark and light themes should have different primary colors."""
        assert DARK_THEME.bg_primary != LIGHT_THEME.bg_primary
        assert DARK_THEME.text_primary != LIGHT_THEME.text_primary

    def test_frozen(self):
        """ThemeColors should be immutable."""
        import pytest

        with pytest.raises(AttributeError):
            DARK_THEME.bg_primary = "#000000"  # type: ignore[misc]


class TestThemeManager:
    """Tests for the ThemeManager singleton."""

    def test_singleton(self):
        """ThemeManager should return the same instance."""
        a = ThemeManager()
        b = ThemeManager()
        assert a is b

    def test_default_theme_is_dark(self):
        """Default theme should be DARK_THEME."""
        mgr = ThemeManager()
        assert mgr.theme is DARK_THEME

    def test_set_theme(self):
        """Should be able to change the active theme."""
        mgr = ThemeManager()
        original = mgr.theme
        try:
            mgr.theme = LIGHT_THEME
            assert mgr.theme is LIGHT_THEME
        finally:
            mgr.theme = original

    def test_status_color_success(self):
        """Success statuses should return green."""
        mgr = ThemeManager()
        for s in ("success", "ok", "complete", "completed", "done"):
            assert mgr.status_color(s) == DARK_THEME.status_success

    def test_status_color_error(self):
        """Error statuses should return red."""
        mgr = ThemeManager()
        for s in ("error", "fail", "failed", "cancelled"):
            assert mgr.status_color(s) == DARK_THEME.status_error

    def test_status_color_warning(self):
        """Warning statuses should return orange."""
        mgr = ThemeManager()
        for s in ("warning", "paused", "partial"):
            assert mgr.status_color(s) == DARK_THEME.status_warning

    def test_status_color_info(self):
        """Info statuses should return blue."""
        mgr = ThemeManager()
        for s in ("info", "loading", "running", "active"):
            assert mgr.status_color(s) == DARK_THEME.status_info

    def test_status_color_unknown(self):
        """Unknown status should return text_secondary."""
        mgr = ThemeManager()
        assert mgr.status_color("unknown") == DARK_THEME.text_secondary

    def test_status_color_case_insensitive(self):
        """Status color lookup should be case-insensitive."""
        mgr = ThemeManager()
        assert mgr.status_color("SUCCESS") == mgr.status_color("success")
        assert mgr.status_color("Error") == mgr.status_color("error")


class TestGenerateStylesheet:
    """Tests for the QSS stylesheet generator."""

    def test_returns_non_empty_string(self):
        """generate_stylesheet should return a non-empty string."""
        qss = generate_stylesheet(DARK_THEME)
        assert isinstance(qss, str)
        assert len(qss) > 100

    def test_contains_expected_selectors(self):
        """QSS should contain key widget selectors."""
        qss = generate_stylesheet(DARK_THEME)
        expected = [
            "QMainWindow",
            "QPushButton",
            "QLabel",
            "QLineEdit",
            "QTabBar",
            "QTableView",
            "QScrollBar",
            "QProgressBar",
            "QMenu",
            "MiniPlayer",
            "QStatusBar",
        ]
        for sel in expected:
            assert sel in qss, f"Expected selector '{sel}' in stylesheet"

    def test_contains_theme_colors(self):
        """QSS should reference actual theme color values."""
        qss = generate_stylesheet(DARK_THEME)
        assert DARK_THEME.bg_primary in qss
        assert DARK_THEME.text_primary in qss
        assert DARK_THEME.accent in qss
        assert DARK_THEME.status_success in qss

    def test_default_theme(self):
        """generate_stylesheet() with no args should use DARK_THEME."""
        qss_default = generate_stylesheet()
        qss_dark = generate_stylesheet(DARK_THEME)
        assert qss_default == qss_dark

    def test_light_theme_produces_different_qss(self):
        """Light theme should produce different QSS than dark theme."""
        dark_qss = generate_stylesheet(DARK_THEME)
        light_qss = generate_stylesheet(LIGHT_THEME)
        assert dark_qss != light_qss
        assert LIGHT_THEME.bg_primary in light_qss

    def test_hover_and_pressed_states(self):
        """QSS should include hover and pressed pseudo-states."""
        qss = generate_stylesheet(DARK_THEME)
        assert ":hover" in qss
        assert ":pressed" in qss
        assert ":disabled" in qss

    def test_no_unresolved_placeholders(self):
        """QSS should not contain unresolved f-string placeholders like {t.xxx}."""
        import re

        qss = generate_stylesheet(DARK_THEME)
        # f-string placeholders would look like {t.something} or {variable}
        unresolved = re.findall(r"\{t\.\w+\}", qss)
        assert unresolved == [], f"Found unresolved placeholders: {unresolved}"
