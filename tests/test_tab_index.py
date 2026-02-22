"""Tests for TabIndex enum."""

from vdj_manager.ui.constants import TabIndex


class TestTabIndex:
    """Tests for the TabIndex IntEnum."""

    def test_values_are_sequential(self):
        """Tab indices should be 0-6."""
        assert int(TabIndex.DATABASE) == 0
        assert int(TabIndex.NORMALIZATION) == 1
        assert int(TabIndex.FILES) == 2
        assert int(TabIndex.ANALYSIS) == 3
        assert int(TabIndex.EXPORT) == 4
        assert int(TabIndex.PLAYER) == 5
        assert int(TabIndex.WORKFLOW) == 6

    def test_works_as_int(self):
        """TabIndex values should be usable as plain integers."""
        assert TabIndex.PLAYER == 5
        assert TabIndex.DATABASE + 1 == TabIndex.NORMALIZATION

    def test_all_members_count(self):
        """Should have exactly 7 tab indices."""
        assert len(TabIndex) == 7
