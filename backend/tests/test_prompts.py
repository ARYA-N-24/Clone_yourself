"""
Unit tests for backend/utils/prompts.py

Tests cover:
- load_prompt_template returns the correct template for each known name
- load_prompt_template raises ValueError for unknown names
- inject replaces a placeholder correctly
- inject handles multiple occurrences of the same placeholder
- inject is a no-op when the placeholder is absent
- inject does not mutate the original template string
"""

import pytest

from utils.prompts import inject, load_prompt_template

# ---------------------------------------------------------------------------
# Known template names
# ---------------------------------------------------------------------------

KNOWN_NAMES = [
    "email_classification",
    "reply_generation",
    "meeting_slot_suggestion",
    "daily_brief",
    "followup_suggestion",
]


class TestLoadPromptTemplate:
    def test_returns_string_for_each_known_name(self):
        for name in KNOWN_NAMES:
            result = load_prompt_template(name)
            assert isinstance(result, str), f"Expected str for '{name}'"
            assert len(result) > 0, f"Template '{name}' must not be empty"

    def test_email_classification_contains_json_instruction(self):
        tmpl = load_prompt_template("email_classification")
        assert '"classification"' in tmpl
        assert '"category"' in tmpl

    def test_email_classification_contains_valid_labels(self):
        tmpl = load_prompt_template("email_classification")
        for label in ("urgent", "normal", "low"):
            assert label in tmpl
        for category in ("meeting-request", "action-required", "info", "other"):
            assert category in tmpl

    def test_email_classification_contains_injection_warning(self):
        """Prompt must instruct GPT-4o to ignore injected instructions."""
        tmpl = load_prompt_template("email_classification")
        assert "Ignore" in tmpl or "ignore" in tmpl

    def test_reply_generation_contains_tone_placeholder(self):
        tmpl = load_prompt_template("reply_generation")
        assert "{{tone}}" in tmpl

    def test_reply_generation_contains_examples_placeholder(self):
        tmpl = load_prompt_template("reply_generation")
        assert "{{examples}}" in tmpl

    def test_meeting_slot_suggestion_returns_json_array_format(self):
        tmpl = load_prompt_template("meeting_slot_suggestion")
        assert "confidence_score" in tmpl
        assert "reason" in tmpl

    def test_daily_brief_contains_all_context_placeholders(self):
        tmpl = load_prompt_template("daily_brief")
        for placeholder in (
            "{{urgent_emails}}",
            "{{followups}}",
            "{{upcoming_events}}",
            "{{analytics}}",
        ):
            assert placeholder in tmpl, f"Missing placeholder {placeholder}"

    def test_daily_brief_specifies_exact_counts(self):
        tmpl = load_prompt_template("daily_brief")
        assert "3" in tmpl  # exactly 3 urgent items
        assert "2" in tmpl  # exactly 2 followups

    def test_followup_suggestion_contains_days_elapsed_placeholder(self):
        tmpl = load_prompt_template("followup_suggestion")
        assert "{{days_elapsed}}" in tmpl

    def test_followup_suggestion_contains_tone_placeholder(self):
        tmpl = load_prompt_template("followup_suggestion")
        assert "{{tone}}" in tmpl

    def test_raises_value_error_for_unknown_name(self):
        with pytest.raises(ValueError, match="Unknown prompt template"):
            load_prompt_template("nonexistent_template")

    def test_error_message_lists_valid_names(self):
        with pytest.raises(ValueError) as exc_info:
            load_prompt_template("bad_name")
        error_msg = str(exc_info.value)
        for name in KNOWN_NAMES:
            assert name in error_msg

    def test_raises_for_empty_string(self):
        with pytest.raises(ValueError):
            load_prompt_template("")

    def test_raises_for_case_mismatch(self):
        with pytest.raises(ValueError):
            load_prompt_template("Email_Classification")

    def test_each_call_returns_same_template(self):
        """load_prompt_template must be deterministic."""
        for name in KNOWN_NAMES:
            assert load_prompt_template(name) == load_prompt_template(name)


class TestInject:
    def test_replaces_placeholder_with_value(self):
        template = "Hello, {{name}}!"
        result = inject(template, "name", "Alice")
        assert result == "Hello, Alice!"

    def test_replaces_all_occurrences(self):
        template = "{{x}} and {{x}} again"
        result = inject(template, "x", "foo")
        assert result == "foo and foo again"

    def test_no_op_when_placeholder_absent(self):
        template = "No placeholders here."
        result = inject(template, "missing", "value")
        assert result == "No placeholders here."

    def test_does_not_mutate_original(self):
        template = "Tone: {{tone}}"
        original = template
        inject(template, "tone", "casual")
        assert template == original

    def test_inject_tone_into_reply_generation(self):
        tmpl = load_prompt_template("reply_generation")
        result = inject(tmpl, "tone", "formal")
        assert "{{tone}}" not in result
        assert "formal" in result

    def test_inject_examples_into_reply_generation(self):
        tmpl = load_prompt_template("reply_generation")
        examples = "Example 1: Hi there!\nExample 2: Thanks for reaching out."
        result = inject(tmpl, "examples", examples)
        assert "{{examples}}" not in result
        assert examples in result

    def test_inject_days_elapsed_into_followup(self):
        tmpl = load_prompt_template("followup_suggestion")
        result = inject(tmpl, "days_elapsed", "5")
        assert "{{days_elapsed}}" not in result
        assert "5" in result

    def test_inject_empty_value(self):
        template = "Before {{key}} after"
        result = inject(template, "key", "")
        assert result == "Before  after"

    def test_inject_value_containing_braces(self):
        """Values that look like placeholders should not cause recursion."""
        template = "{{outer}}"
        result = inject(template, "outer", "{{inner}}")
        assert result == "{{inner}}"

    def test_inject_multiple_different_keys_sequentially(self):
        tmpl = load_prompt_template("daily_brief")
        tmpl = inject(tmpl, "urgent_emails", "Email A, Email B")
        tmpl = inject(tmpl, "followups", "Followup 1")
        tmpl = inject(tmpl, "upcoming_events", "Meeting at 10am")
        tmpl = inject(tmpl, "analytics", "5 actions automated")
        assert "{{urgent_emails}}" not in tmpl
        assert "{{followups}}" not in tmpl
        assert "{{upcoming_events}}" not in tmpl
        assert "{{analytics}}" not in tmpl
        assert "Email A, Email B" in tmpl
