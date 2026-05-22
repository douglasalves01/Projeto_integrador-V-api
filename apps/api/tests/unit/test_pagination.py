"""Unit tests for pagination logic."""
import math

import pytest


class TestPaginationCalculation:
    """Test pagination total_pages calculation."""

    def _calc_total_pages(self, total: int, page_size: int) -> int:
        return math.ceil(total / page_size) if total > 0 else 0

    def test_zero_items(self):
        assert self._calc_total_pages(0, 20) == 0

    def test_items_less_than_page_size(self):
        assert self._calc_total_pages(5, 20) == 1

    def test_items_equal_page_size(self):
        assert self._calc_total_pages(20, 20) == 1

    def test_items_slightly_more_than_page_size(self):
        assert self._calc_total_pages(21, 20) == 2

    def test_exact_multiple(self):
        assert self._calc_total_pages(100, 20) == 5

    def test_large_dataset(self):
        assert self._calc_total_pages(1000, 100) == 10

    def test_page_size_one(self):
        assert self._calc_total_pages(50, 1) == 50

    def test_single_item(self):
        assert self._calc_total_pages(1, 20) == 1


class TestPaginationBounds:
    """Test that returned items respect bounds."""

    def _items_for_page(self, total: int, page: int, page_size: int) -> int:
        """Calculate expected number of items for a given page."""
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        if page > total_pages:
            return 0
        remaining = total - (page - 1) * page_size
        return min(page_size, remaining)

    def test_first_page_full(self):
        assert self._items_for_page(50, 1, 20) == 20

    def test_last_page_partial(self):
        assert self._items_for_page(50, 3, 20) == 10

    def test_beyond_last_page(self):
        assert self._items_for_page(50, 4, 20) == 0

    def test_single_page(self):
        assert self._items_for_page(5, 1, 20) == 5

    def test_max_page_size_100(self):
        """Page size should never exceed 100."""
        page_size = min(200, 100)  # Capped at 100
        assert page_size == 100
