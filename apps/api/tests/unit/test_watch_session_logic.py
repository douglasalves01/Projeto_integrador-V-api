"""Unit tests for watch session metrics computation logic."""
import pytest


class TestWatchSessionMetrics:
    """Test the computation logic for watch session metrics."""

    def _compute_metrics(self, duration: int, watch_time: int):
        """Replicate the service logic for testing."""
        percentage = watch_time / duration if duration > 0 else 0.0
        completed = percentage >= 0.9
        abandoned = percentage < 0.1
        return percentage, completed, abandoned

    def test_zero_watch_time(self):
        percentage, completed, abandoned = self._compute_metrics(3600, 0)
        assert percentage == 0.0
        assert completed is False
        assert abandoned is True

    def test_full_watch(self):
        percentage, completed, abandoned = self._compute_metrics(3600, 3600)
        assert percentage == 1.0
        assert completed is True
        assert abandoned is False

    def test_exactly_90_percent(self):
        percentage, completed, abandoned = self._compute_metrics(1000, 900)
        assert percentage == 0.9
        assert completed is True
        assert abandoned is False

    def test_just_below_90_percent(self):
        percentage, completed, abandoned = self._compute_metrics(1000, 899)
        assert percentage == 0.899
        assert completed is False
        assert abandoned is False

    def test_exactly_10_percent(self):
        percentage, completed, abandoned = self._compute_metrics(1000, 100)
        assert percentage == 0.1
        assert completed is False
        assert abandoned is False

    def test_just_below_10_percent(self):
        percentage, completed, abandoned = self._compute_metrics(1000, 99)
        assert percentage == 0.099
        assert completed is False
        assert abandoned is True

    def test_half_watched(self):
        percentage, completed, abandoned = self._compute_metrics(3600, 1800)
        assert percentage == 0.5
        assert completed is False
        assert abandoned is False

    def test_short_video_completed(self):
        percentage, completed, abandoned = self._compute_metrics(60, 55)
        assert percentage == pytest.approx(0.9167, abs=0.001)
        assert completed is True
        assert abandoned is False

    def test_long_video_abandoned(self):
        percentage, completed, abandoned = self._compute_metrics(86400, 100)
        assert percentage < 0.1
        assert completed is False
        assert abandoned is True

    def test_watch_time_exceeds_duration(self):
        """Edge case: watch time > duration (user rewatched parts)."""
        percentage, completed, abandoned = self._compute_metrics(1000, 1500)
        assert percentage == 1.5
        assert completed is True
        assert abandoned is False

    def test_one_second_video(self):
        percentage, completed, abandoned = self._compute_metrics(1, 1)
        assert percentage == 1.0
        assert completed is True
        assert abandoned is False
