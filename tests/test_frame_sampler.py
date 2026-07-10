"""Tests for seeded random frame sampling within rally windows (Phase F)."""

from src.pipeline.frame_sampler import sample_frame_indices


def test_returns_empty_list_for_no_ranges():
    assert sample_frame_indices([], count=10) == []


def test_returns_empty_list_for_non_positive_count():
    assert sample_frame_indices([(0, 100)], count=0) == []
    assert sample_frame_indices([(0, 100)], count=-5) == []


def test_returns_at_most_count_indices():
    result = sample_frame_indices([(0, 100)], count=10)
    assert len(result) == 10


def test_returns_fewer_than_count_when_span_is_smaller():
    result = sample_frame_indices([(0, 5)], count=100)
    assert len(result) == 5
    assert sorted(result) == list(range(0, 5))


def test_all_indices_fall_within_the_given_ranges():
    ranges = [(0, 20), (100, 110)]
    result = sample_frame_indices(ranges, count=15, seed=1)

    for idx in result:
        assert any(start <= idx < end for start, end in ranges)


def test_result_is_sorted():
    result = sample_frame_indices([(0, 50), (200, 250)], count=20, seed=7)
    assert result == sorted(result)


def test_same_seed_is_reproducible():
    ranges = [(0, 300)]
    first = sample_frame_indices(ranges, count=25, seed=42)
    second = sample_frame_indices(ranges, count=25, seed=42)
    assert first == second


def test_different_seeds_can_produce_different_samples():
    ranges = [(0, 1000)]
    first = sample_frame_indices(ranges, count=25, seed=1)
    second = sample_frame_indices(ranges, count=25, seed=2)
    assert first != second


def test_no_duplicate_indices():
    result = sample_frame_indices([(0, 30), (30, 60)], count=50, seed=3)
    assert len(result) == len(set(result))
