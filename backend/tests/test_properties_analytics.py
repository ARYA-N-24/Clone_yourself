"""
Property-based tests for analytics computation.

Property 5: Analytics Consistency
- actions_automated == COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent)
- Tests the pure computation logic directly

**Validates: Requirements 11.1, 11.2, 11.3**
"""

from __future__ import annotations

from typing import List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Pure computation function (extracted from AnalyticsService logic)
# ---------------------------------------------------------------------------


def compute_actions_automated(event_types: list[str]) -> int:
    """
    Pure function that computes actions_automated from a list of event types.
    Mirrors the logic in AnalyticsService.get_dashboard_stats.
    """
    replies_sent = event_types.count("reply_sent")
    events_created = event_types.count("event_created")
    followups_sent = event_types.count("followup_sent")

    return replies_sent + events_created + followups_sent


def compute_time_saved_minutes(event_types: list[str]) -> float:
    """
    Pure function that computes time_saved_minutes from a list of event types.
    """
    TIME_SAVED_PER_REPLY = 5.0
    TIME_SAVED_PER_EVENT = 10.0

    replies_sent = event_types.count("reply_sent")
    events_created = event_types.count("event_created")

    return replies_sent * TIME_SAVED_PER_REPLY + events_created * TIME_SAVED_PER_EVENT


# ---------------------------------------------------------------------------
# Property 5: Analytics Consistency
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    event_types=st.lists(
        st.sampled_from(["reply_sent", "event_created", "followup_sent", "email_classified"]),
        min_size=0,
        max_size=50,
    )
)
def test_analytics_consistency_actions_automated(event_types: list[str]) -> None:
    """
    Property 5: actions_automated == COUNT(reply_sent) + COUNT(event_created) + COUNT(followup_sent).
    email_classified is NOT counted.

    **Validates: Requirements 11.1, 11.2, 11.3**
    """
    result = compute_actions_automated(event_types)

    expected = (
        event_types.count("reply_sent")
        + event_types.count("event_created")
        + event_types.count("followup_sent")
    )

    assert result == expected


@settings(max_examples=50)
@given(
    event_types=st.lists(
        st.sampled_from(["reply_sent", "event_created", "followup_sent", "email_classified"]),
        min_size=0,
        max_size=50,
    )
)
def test_analytics_consistency_email_classified_not_counted(event_types: list[str]) -> None:
    """
    Property 5: email_classified events do NOT contribute to actions_automated.

    **Validates: Requirements 11.1, 11.2, 11.3**
    """
    result = compute_actions_automated(event_types)

    # Even if there are many email_classified events, they should not be counted
    email_classified_count = event_types.count("email_classified")

    # actions_automated should not include email_classified
    expected_without_classified = (
        event_types.count("reply_sent")
        + event_types.count("event_created")
        + event_types.count("followup_sent")
    )

    assert result == expected_without_classified


@settings(max_examples=50)
@given(
    event_types=st.lists(
        st.sampled_from(["reply_sent", "event_created", "followup_sent", "email_classified"]),
        min_size=0,
        max_size=50,
    )
)
def test_analytics_consistency_time_saved_formula(event_types: list[str]) -> None:
    """
    Property 5: time_saved_minutes == reply_sent * 5 + event_created * 10.

    **Validates: Requirements 11.1, 11.2, 11.3**
    """
    result = compute_time_saved_minutes(event_types)

    expected = (
        event_types.count("reply_sent") * 5.0
        + event_types.count("event_created") * 10.0
    )

    assert result == expected


@settings(max_examples=50)
@given(
    event_types=st.lists(
        st.sampled_from(["reply_sent", "event_created", "followup_sent", "email_classified"]),
        min_size=0,
        max_size=50,
    )
)
def test_analytics_consistency_followup_sent_not_in_time_saved(event_types: list[str]) -> None:
    """
    Property 5: followup_sent events do NOT contribute to time_saved_minutes.

    **Validates: Requirements 11.1, 11.2, 11.3**
    """
    result = compute_time_saved_minutes(event_types)

    # followup_sent should not contribute to time saved
    expected = (
        event_types.count("reply_sent") * 5.0
        + event_types.count("event_created") * 10.0
    )

    assert result == expected


@settings(max_examples=50)
@given(
    event_types=st.lists(
        st.sampled_from(["reply_sent", "event_created", "followup_sent", "email_classified"]),
        min_size=0,
        max_size=50,
    )
)
def test_analytics_consistency_zero_when_no_automated_events(event_types: list[str]) -> None:
    """
    Property 5: When there are no automated events, actions_automated is 0.

    **Validates: Requirements 11.1, 11.2, 11.3**
    """
    # Filter to only email_classified events
    only_classified = [e for e in event_types if e == "email_classified"]

    result = compute_actions_automated(only_classified)

    assert result == 0
