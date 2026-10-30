from datetime import date
import re


def course_name(value: str) -> str:
    name = value.strip()
    if not 1 <= len(name) <= 200:
        raise ValueError("Course name must contain 1 to 200 characters.")
    return name


def assignment_title(value: str) -> str:
    title = value.strip()
    if not 1 <= len(title) <= 200:
        raise ValueError("Assignment title must contain 1 to 200 characters.")
    return title


def task_title(value: str) -> str:
    title = value.strip()
    if not 1 <= len(title) <= 200:
        raise ValueError("Task title must contain 1 to 200 characters.")
    return title


def assignment_progress(completed: int, total: int) -> dict:
    return {"completed": completed, "total": total, "percent": 100 * completed // total if total else 0}


def repository_owner(value: str) -> str:
    if not 1 <= len(value) <= 39 or re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", value) is None:
        raise ValueError("GitHub owner must contain 1 to 39 letters or digits, with single internal hyphens.")
    return value.lower()


def repository_name(value: str) -> str:
    if not 1 <= len(value) <= 100 or value in (".", "..") or re.fullmatch(r"[A-Za-z0-9._-]+", value) is None:
        raise ValueError("Repository name must contain 1 to 100 letters, digits, dots, underscores, or hyphens, and cannot be '.' or '..'.")
    return value.lower()


def assignment_due_date(value: str | None) -> str | None:
    if value is None:
        return None
    message = "Due date must be a real date in YYYY-MM-DD form."
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(message) from None
    if parsed.isoformat() != value:
        raise ValueError(message)
    return value
