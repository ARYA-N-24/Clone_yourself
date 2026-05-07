"""
File Brain service for the Clone Yourself Platform.

Provides a simulated file organisation interface using mock data only.
No real filesystem operations are performed — this is purely a demo/preview
of what an AI-powered file organiser would look like.

Requirements: 14.1, 14.2
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------


class MockFile(TypedDict):
    """A mock file object used for demo purposes."""

    id: str
    name: str
    path: str
    size: int          # bytes
    type: str          # "document" | "image" | "spreadsheet" | "presentation" | "archive" | "code"
    category: str      # "work" | "personal" | "finance" | "media" | "misc"
    last_modified: str # ISO-8601 datetime string


class OrganizeResult(TypedDict):
    """Result of a simulated file organisation action."""

    file_id: str
    original_name: str
    suggested_name: str
    suggested_category: str
    suggested_folder: str
    confidence_score: float
    reason: str


# ---------------------------------------------------------------------------
# Mock file data
# ---------------------------------------------------------------------------

def _utc_iso(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc).isoformat()


_MOCK_FILES: list[MockFile] = [
    # --- Documents ---
    {
        "id": "file-001",
        "name": "q3_report_draft_v2_FINAL.pdf",
        "path": "/Users/me/Downloads/q3_report_draft_v2_FINAL.pdf",
        "size": 2_457_600,
        "type": "document",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 10, 14, 32),
    },
    {
        "id": "file-002",
        "name": "meeting_notes_july_15.docx",
        "path": "/Users/me/Desktop/meeting_notes_july_15.docx",
        "size": 45_056,
        "type": "document",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 15, 10, 5),
    },
    {
        "id": "file-003",
        "name": "NDA_partnerco_unsigned.pdf",
        "path": "/Users/me/Downloads/NDA_partnerco_unsigned.pdf",
        "size": 312_320,
        "type": "document",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 15, 11, 50),
    },
    {
        "id": "file-004",
        "name": "tax_return_2023.pdf",
        "path": "/Users/me/Documents/tax_return_2023.pdf",
        "size": 1_024_000,
        "type": "document",
        "category": "finance",
        "last_modified": _utc_iso(2024, 4, 3, 9, 0),
    },
    {
        "id": "file-005",
        "name": "recipe_pasta_carbonara.docx",
        "path": "/Users/me/Desktop/recipe_pasta_carbonara.docx",
        "size": 28_672,
        "type": "document",
        "category": "personal",
        "last_modified": _utc_iso(2024, 6, 20, 19, 15),
    },
    # --- Spreadsheets ---
    {
        "id": "file-006",
        "name": "budget_2024_v3.xlsx",
        "path": "/Users/me/Documents/budget_2024_v3.xlsx",
        "size": 98_304,
        "type": "spreadsheet",
        "category": "finance",
        "last_modified": _utc_iso(2024, 7, 1, 8, 45),
    },
    {
        "id": "file-007",
        "name": "sales_pipeline_Q3.xlsx",
        "path": "/Users/me/Downloads/sales_pipeline_Q3.xlsx",
        "size": 204_800,
        "type": "spreadsheet",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 12, 16, 0),
    },
    {
        "id": "file-008",
        "name": "gym_tracker_june.csv",
        "path": "/Users/me/Desktop/gym_tracker_june.csv",
        "size": 8_192,
        "type": "spreadsheet",
        "category": "personal",
        "last_modified": _utc_iso(2024, 6, 30, 21, 0),
    },
    # --- Images ---
    {
        "id": "file-009",
        "name": "IMG_20240714_beach_holiday.jpg",
        "path": "/Users/me/Downloads/IMG_20240714_beach_holiday.jpg",
        "size": 4_718_592,
        "type": "image",
        "category": "personal",
        "last_modified": _utc_iso(2024, 7, 14, 17, 22),
    },
    {
        "id": "file-010",
        "name": "screenshot_2024-07-10_bug_report.png",
        "path": "/Users/me/Desktop/screenshot_2024-07-10_bug_report.png",
        "size": 512_000,
        "type": "image",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 10, 11, 3),
    },
    {
        "id": "file-011",
        "name": "logo_draft_v1.png",
        "path": "/Users/me/Downloads/logo_draft_v1.png",
        "size": 256_000,
        "type": "image",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 8, 15, 40),
    },
    # --- Presentations ---
    {
        "id": "file-012",
        "name": "investor_deck_seed_round.pptx",
        "path": "/Users/me/Documents/investor_deck_seed_round.pptx",
        "size": 8_388_608,
        "type": "presentation",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 5, 13, 0),
    },
    {
        "id": "file-013",
        "name": "onboarding_slides_new_hires.pptx",
        "path": "/Users/me/Downloads/onboarding_slides_new_hires.pptx",
        "size": 5_242_880,
        "type": "presentation",
        "category": "work",
        "last_modified": _utc_iso(2024, 6, 28, 10, 30),
    },
    # --- Archives ---
    {
        "id": "file-014",
        "name": "project_backup_2024_06.zip",
        "path": "/Users/me/Downloads/project_backup_2024_06.zip",
        "size": 52_428_800,
        "type": "archive",
        "category": "work",
        "last_modified": _utc_iso(2024, 6, 30, 23, 59),
    },
    {
        "id": "file-015",
        "name": "old_photos_2022.tar.gz",
        "path": "/Users/me/Downloads/old_photos_2022.tar.gz",
        "size": 1_073_741_824,
        "type": "archive",
        "category": "personal",
        "last_modified": _utc_iso(2023, 1, 5, 12, 0),
    },
    # --- Code ---
    {
        "id": "file-016",
        "name": "scraper_prototype.py",
        "path": "/Users/me/Desktop/scraper_prototype.py",
        "size": 12_288,
        "type": "code",
        "category": "work",
        "last_modified": _utc_iso(2024, 7, 13, 22, 10),
    },
    {
        "id": "file-017",
        "name": "config_backup.json",
        "path": "/Users/me/Downloads/config_backup.json",
        "size": 4_096,
        "type": "code",
        "category": "misc",
        "last_modified": _utc_iso(2024, 7, 9, 9, 0),
    },
]

# Build a lookup dict for O(1) access by id
_FILES_BY_ID: dict[str, MockFile] = {f["id"]: f for f in _MOCK_FILES}


# ---------------------------------------------------------------------------
# Suggestion rules (pure data — no ML, no external calls)
# ---------------------------------------------------------------------------

# Maps (file_type, category) → (suggested_folder, name_template, reason)
_SUGGESTION_RULES: dict[tuple[str, str], tuple[str, str, str]] = {
    ("document", "work"):     ("~/Documents/Work/Reports",       "{stem}_organised.pdf",  "Work document detected; moved to Reports folder"),
    ("document", "finance"):  ("~/Documents/Finance",            "{stem}_finance.pdf",    "Financial document; moved to Finance folder"),
    ("document", "personal"): ("~/Documents/Personal",           "{stem}_personal.docx",  "Personal document; moved to Personal folder"),
    ("spreadsheet", "work"):  ("~/Documents/Work/Spreadsheets",  "{stem}_work.xlsx",      "Work spreadsheet; moved to Work/Spreadsheets"),
    ("spreadsheet", "finance"):("~/Documents/Finance/Sheets",    "{stem}_finance.xlsx",   "Finance spreadsheet; moved to Finance/Sheets"),
    ("spreadsheet", "personal"):("~/Documents/Personal",         "{stem}_personal.csv",   "Personal spreadsheet; moved to Personal folder"),
    ("image", "personal"):    ("~/Pictures/Personal",            "{stem}_personal.jpg",   "Personal photo; moved to Pictures/Personal"),
    ("image", "work"):        ("~/Documents/Work/Assets",        "{stem}_asset.png",      "Work image/screenshot; moved to Work/Assets"),
    ("presentation", "work"): ("~/Documents/Work/Presentations", "{stem}_presentation.pptx", "Work presentation; moved to Work/Presentations"),
    ("archive", "work"):      ("~/Documents/Work/Archives",      "{stem}_backup.zip",     "Work archive; moved to Work/Archives"),
    ("archive", "personal"):  ("~/Documents/Personal/Archives",  "{stem}_archive.tar.gz", "Personal archive; moved to Personal/Archives"),
    ("code", "work"):         ("~/Developer/Work",               "{stem}_script.py",      "Code file; moved to Developer/Work"),
    ("code", "misc"):         ("~/Developer/Misc",               "{stem}_config.json",    "Misc code/config; moved to Developer/Misc"),
}

_DEFAULT_RULE = ("~/Documents/Misc", "{stem}_organised", "File categorised as miscellaneous")

# Confidence scores per file type (simulates AI certainty)
_CONFIDENCE_BY_TYPE: dict[str, float] = {
    "document":     0.91,
    "spreadsheet":  0.88,
    "image":        0.85,
    "presentation": 0.93,
    "archive":      0.79,
    "code":         0.82,
}


def _stem(filename: str) -> str:
    """Return the filename without its extension."""
    if "." in filename:
        return filename.rsplit(".", 1)[0]
    return filename


def _ai_rename(original_name: str, template: str) -> str:
    """Apply the name template to produce an AI-style suggested filename."""
    stem = _stem(original_name)
    # Normalise: lowercase, replace spaces/special chars with underscores
    clean_stem = stem.lower().replace(" ", "_").replace("-", "_")
    # Remove duplicate underscores
    while "__" in clean_stem:
        clean_stem = clean_stem.replace("__", "_")
    return template.format(stem=clean_stem)


# ---------------------------------------------------------------------------
# FileBrain service
# ---------------------------------------------------------------------------


class FileBrain:
    """
    Demo-mode File Brain service.

    All operations are purely simulated — no real files are read, written,
    moved, or deleted at any point.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_demo_files(self) -> list[MockFile]:
        """
        Return the full list of mock file objects.

        Each object contains: id, name, path, size, type, category,
        last_modified.

        Satisfies requirement 14.1 — displays a simulated file organisation
        interface using mock data.
        """
        return list(_MOCK_FILES)

    def simulate_organize(self, file_id: str) -> OrganizeResult:
        """
        Simulate an AI-based file rename and categorisation for *file_id*.

        Looks up the file from the mock dataset and returns a result dict
        describing what an AI organiser would do, without touching any real
        files.

        Args:
            file_id: The ``id`` field of a mock file (e.g. ``"file-001"``).

        Returns:
            An :class:`OrganizeResult` dict with keys:
            ``file_id``, ``original_name``, ``suggested_name``,
            ``suggested_category``, ``suggested_folder``,
            ``confidence_score``, ``reason``.

        Raises:
            KeyError: If *file_id* is not found in the mock dataset.

        Satisfies requirement 14.2 — simulates AI-based file renaming and
        categorisation without modifying any real files.
        """
        if file_id not in _FILES_BY_ID:
            raise KeyError(f"File '{file_id}' not found in demo dataset.")

        file = _FILES_BY_ID[file_id]
        file_type = file["type"]
        category = file["category"]

        rule_key = (file_type, category)
        suggested_folder, name_template, reason = _SUGGESTION_RULES.get(
            rule_key, _DEFAULT_RULE
        )

        suggested_name = _ai_rename(file["name"], name_template)
        confidence_score = _CONFIDENCE_BY_TYPE.get(file_type, 0.75)

        return OrganizeResult(
            file_id=file_id,
            original_name=file["name"],
            suggested_name=suggested_name,
            suggested_category=category,
            suggested_folder=suggested_folder,
            confidence_score=confidence_score,
            reason=reason,
        )
