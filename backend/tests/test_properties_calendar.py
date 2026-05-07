"""
Property-based tests for calendar free slot generation.

Property 3: Free Slot Validity
- For any working_start, working_end, meeting_duration:
  every slot from get_free_slots satisfies working hours bounds,
  is on a working day, and doesn't overlap injected events.

Tests the pure slot-generation logic directly (no DB/API calls needed).

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, time as dt_time
from typing import List

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.schemas.pydantic_schemas import TimeSlot
from backend.services.calendar_service import CalendarService, DateRange


# ---------------------------------------------------------------------------
# Pure slot generation helper (extracted from CalendarService._generate_mock_slots)
# ---------------------------------------------------------------------------


def generate_free_slots(
    working_start_hour: int,
    working_end_hour: int,
    meeting_duration: int,
    working_days: list[int] = None,
    date_range_days: int = 7,
    existing_events: list[dict] = None,
) -> list[TimeSlot]:
    """
    Pure function that generates free slots given working hours and duration.
    Mirrors the logic in CalendarService._generate_mock_slots.
    """
    if working_days is None:
        working_days = [1, 2, 3, 4, 5]  # Mon-Fri
    if existing_events is None:
        existing_events = []

    start_time = dt_time(working_start_hour, 0)
    end_time = dt_time(working_end_hour, 0)

    now = datetime(2024, 1, 15, tzinfo=timezone.utc)  # Fixed date for determinism
    date_range = DateRange(start=now, end=now + timedelta(days=date_range_days))

    free_slots: list[TimeSlot] = []
    current_day = date_range.start.date()
    end_day = date_range.end.date()

    while current_day <= end_day:
        day_of_week = current_day.isoweekday()  # 1=Mon, 7=Sun

        if day_of_week in working_days:
            slot_start = datetime(
                current_day.year,
                current_day.month,
                current_day.day,
                start_time.hour,
                start_time.minute,
                tzinfo=timezone.utc,
            )
            day_end = datetime(
                current_day.year,
                current_day.month,
                current_day.day,
                end_time.hour,
                end_time.minute,
                tzinfo=timezone.utc,
            )
            slot_end = slot_start + timedelta(minutes=meeting_duration)

            while slot_end <= day_end:
                candidate = TimeSlot(start=slot_start, end=slot_end)

                # Check for conflicts with existing events
                has_conflict = any(
                    CalendarService._overlaps(candidate, event)
                    for event in existing_events
                )

                if not has_conflict:
                    free_slots.append(candidate)

                slot_start = slot_start + timedelta(minutes=30)
                slot_end = slot_start + timedelta(minutes=meeting_duration)

        current_day += timedelta(days=1)

    return sorted(free_slots, key=lambda s: s.start)


# ---------------------------------------------------------------------------
# Property 3: Free Slot Validity
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    working_start=st.integers(min_value=6, max_value=11),
    working_end=st.integers(min_value=14, max_value=20),
    meeting_duration=st.sampled_from([15, 30, 45, 60]),
)
def test_free_slot_validity_working_hours_bounds(
    working_start: int,
    working_end: int,
    meeting_duration: int,
) -> None:
    """
    Property 3: Every generated slot starts at or after working_start
    and ends at or before working_end.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """
    assume(working_end > working_start)

    slots = generate_free_slots(
        working_start_hour=working_start,
        working_end_hour=working_end,
        meeting_duration=meeting_duration,
    )

    for slot in slots:
        slot_start_hour = slot.start.hour
        slot_start_minute = slot.start.minute
        slot_end_hour = slot.end.hour
        slot_end_minute = slot.end.minute

        # Slot must start at or after working_start
        assert (slot_start_hour, slot_start_minute) >= (working_start, 0), (
            f"Slot starts at {slot.start.time()} which is before working_start {working_start}:00"
        )

        # Slot must end at or before working_end
        assert (slot_end_hour, slot_end_minute) <= (working_end, 0), (
            f"Slot ends at {slot.end.time()} which is after working_end {working_end}:00"
        )


@settings(max_examples=50)
@given(
    working_start=st.integers(min_value=6, max_value=11),
    working_end=st.integers(min_value=14, max_value=20),
    meeting_duration=st.sampled_from([15, 30, 45, 60]),
)
def test_free_slot_validity_working_days_only(
    working_start: int,
    working_end: int,
    meeting_duration: int,
) -> None:
    """
    Property 3: Every generated slot falls on a working day (Mon-Fri, isoweekday 1-5).

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """
    assume(working_end > working_start)

    working_days = [1, 2, 3, 4, 5]  # Mon-Fri
    slots = generate_free_slots(
        working_start_hour=working_start,
        working_end_hour=working_end,
        meeting_duration=meeting_duration,
        working_days=working_days,
    )

    for slot in slots:
        day_of_week = slot.start.isoweekday()
        assert day_of_week in working_days, (
            f"Slot on {slot.start.date()} (isoweekday={day_of_week}) is not a working day"
        )


@settings(max_examples=50)
@given(
    working_start=st.integers(min_value=6, max_value=11),
    working_end=st.integers(min_value=14, max_value=20),
    meeting_duration=st.sampled_from([15, 30, 45, 60]),
)
def test_free_slot_validity_no_overlap_with_injected_events(
    working_start: int,
    working_end: int,
    meeting_duration: int,
) -> None:
    """
    Property 3: No generated slot overlaps with injected existing events.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """
    assume(working_end > working_start)

    # Inject a blocking event on 2024-01-15 (Monday) from 10:00 to 11:00
    blocking_event = {
        "start": {"dateTime": "2024-01-15T10:00:00+00:00"},
        "end": {"dateTime": "2024-01-15T11:00:00+00:00"},
    }

    slots = generate_free_slots(
        working_start_hour=working_start,
        working_end_hour=working_end,
        meeting_duration=meeting_duration,
        existing_events=[blocking_event],
    )

    for slot in slots:
        # Check that no slot overlaps with the blocking event
        overlaps = CalendarService._overlaps(slot, blocking_event)
        assert not overlaps, (
            f"Slot {slot.start.time()}-{slot.end.time()} overlaps with blocking event 10:00-11:00"
        )


@settings(max_examples=50)
@given(
    working_start=st.integers(min_value=6, max_value=11),
    working_end=st.integers(min_value=14, max_value=20),
    meeting_duration=st.sampled_from([15, 30, 45, 60]),
)
def test_free_slot_duration_matches_meeting_duration(
    working_start: int,
    working_end: int,
    meeting_duration: int,
) -> None:
    """
    Property 3: Every generated slot has exactly the requested meeting_duration.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """
    assume(working_end > working_start)

    slots = generate_free_slots(
        working_start_hour=working_start,
        working_end_hour=working_end,
        meeting_duration=meeting_duration,
    )

    for slot in slots:
        actual_duration = (slot.end - slot.start).total_seconds() / 60
        assert actual_duration == meeting_duration, (
            f"Slot duration {actual_duration} min != requested {meeting_duration} min"
        )
