import pytest

from app.buckets import (
    LimitError,
    boundary_burst,
    fixed_window_allows,
    fixed_window_check,
    headers,
    rate_per_second,
    refill,
    retry_after_fixed,
    retry_after_sliding,
    sliding_counter_allows,
    sliding_counter_estimate,
    sliding_log_allows,
    sliding_log_check,
    sliding_log_count,
    tier,
    trim,
    window_id,
    window_start,
)


def test_tier_lookup_is_case_insensitive():
    assert tier(" FREE ")["name"] == "free"
    assert tier("pro")["per_minute"] == 600


def test_unknown_tier_raises():
    with pytest.raises(LimitError):
        tier("unknown")


def test_rate_per_second():
    assert rate_per_second(60) == 1.0


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_rate_raises(value):
    with pytest.raises(LimitError):
        rate_per_second(value)


def test_window_start_and_id():
    assert window_start(125) == 120.0
    assert window_id(125) == 2


def test_invalid_window_raises():
    with pytest.raises(LimitError):
        window_start(10, 0)
    with pytest.raises(LimitError):
        window_id(10, -1)


def test_retry_after_at_start_is_full_window():
    assert retry_after_fixed(120) == 60.0


def test_fixed_window_allows_until_limit():
    assert fixed_window_allows(0, 5)
    assert fixed_window_allows(4, 5)
    assert not fixed_window_allows(5, 5)


def test_negative_fixed_limit_raises():
    with pytest.raises(LimitError):
        fixed_window_allows(0, -1)


def test_fixed_window_check_counts_current_window():
    result = fixed_window_check([1, 61, 62, 100], 100, 5)
    assert result["algorithm"] == "fixed"
    assert result["used"] == 3
    assert result["allowed"] is True
    assert result["remaining"] == 1


def test_boundary_burst_exposes_fixed_window_flaw():
    timestamps = boundary_burst(5)
    fixed_allowed = sum(
        fixed_window_check(timestamps[:i], now, 5)["allowed"]
        for i, now in enumerate(timestamps)
    )
    sliding_allowed = sum(
        sliding_log_check(timestamps[:i], now, 5)["allowed"]
        for i, now in enumerate(timestamps)
    )
    assert len(timestamps) == 10
    assert fixed_allowed > sliding_allowed


def test_trim_keeps_only_timestamps_inside_window():
    assert trim([1, 40, 41, 60], 100, 60) == [41.0, 60.0]


def test_sliding_log_count_and_allow():
    timestamps = [80, 90, 95]
    assert sliding_log_count(timestamps, 100, 60) == 3
    assert sliding_log_allows(timestamps, 100, 4, 60)
    assert not sliding_log_allows(timestamps, 100, 3, 60)


def test_sliding_log_check_denies_at_limit():
    result = sliding_log_check([80, 90, 95], 100, 3, 60)
    assert result["allowed"] is False
    assert result["used"] == 3
    assert result["retry_after"] == 40.0


def test_retry_after_sliding_when_slot_is_available():
    assert retry_after_sliding([95], 100, 3, 60) == 0.0


def test_sliding_counter_estimate():
    assert sliding_counter_estimate(10, 2, 90, 60) == 7.0


def test_sliding_counter_allowance():
    assert sliding_counter_allows(2, 1, 90, 5, 60)
    assert not sliding_counter_allows(10, 2, 90, 5, 60)


def test_refill_adds_tokens_and_caps_capacity():
    tokens, last_seen = refill(1, 0, 2, 60, 5)
    assert tokens == 3.0
    assert last_seen == 2.0

    tokens, _ = refill(4, 0, 10, 60, 5)
    assert tokens == 5.0


def test_refill_does_not_add_tokens_if_clock_moves_backwards():
    tokens, last_seen = refill(3, 10, 5, 60, 5)
    assert tokens == 3.0
    assert last_seen == 5.0


def test_refill_rejects_invalid_capacity():
    with pytest.raises(LimitError):
        refill(1, 0, 1, 60, 0)


def test_headers_include_retry_after_only_when_denied():
    allowed = headers({
        "limit": 5,
        "remaining": 4,
        "algorithm": "fixed",
        "allowed": True,
    })
    assert allowed["X-RateLimit-Limit"] == "5"
    assert allowed["X-RateLimit-Remaining"] == "4"
    assert "Retry-After" not in allowed

    denied = headers({
        "limit": 5,
        "remaining": 0,
        "algorithm": "sliding",
        "allowed": False,
        "retry_after": 0.2,
    })
    assert denied["Retry-After"] == "1"

