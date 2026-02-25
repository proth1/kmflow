"""Shared app category detection for task mining modules.

Used by both the graph ingestion service and the ML feature
extraction pipeline to ensure consistent categorization.
"""

from __future__ import annotations

# Ordered list of app categories (used for one-hot encoding in ML features)
APP_CATEGORIES: list[str] = [
    "spreadsheet",
    "browser",
    "email",
    "communication",
    "document",
    "crm",
    "project_management",
    "development",
    "other",
]


def detect_app_category(app_name: str) -> str:
    """Detect app category from application name.

    Heuristic keyword matching against known application types.

    Args:
        app_name: Application name or bundle ID.

    Returns:
        One of the values in APP_CATEGORIES.
    """
    lower = app_name.lower()
    if any(kw in lower for kw in ("excel", "sheets", "libreoffice calc", "numbers")):
        return "spreadsheet"
    if any(kw in lower for kw in ("chrome", "firefox", "safari", "edge", "browser")):
        return "browser"
    if any(kw in lower for kw in ("outlook", "mail", "thunderbird", "gmail")):
        return "email"
    if any(kw in lower for kw in ("slack", "teams", "zoom", "meet")):
        return "communication"
    if any(kw in lower for kw in ("word", "docs", "pages", "notepad")):
        return "document"
    if any(kw in lower for kw in ("salesforce", "dynamics", "hubspot")):
        return "crm"
    if any(kw in lower for kw in ("jira", "asana", "trello", "monday")):
        return "project_management"
    if any(kw in lower for kw in ("terminal", "iterm", "console", "powershell")):
        return "development"
    if any(kw in lower for kw in ("code", "intellij", "xcode", "pycharm", "vscode")):
        return "development"
    return "other"
