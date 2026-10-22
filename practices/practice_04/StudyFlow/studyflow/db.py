from contextlib import contextmanager
from importlib.resources import files
import os
from pathlib import Path
import sqlite3


ASSIGNMENT_SELECT = (
    "SELECT id, course_id, title, description, due_date, github_owner, github_repo, "
    "(SELECT count(*) FROM tasks WHERE assignment_id = assignments.id) AS total_tasks, "
    "(SELECT count(*) FROM tasks WHERE assignment_id = assignments.id AND is_completed = 1) AS completed_tasks "
    "FROM assignments "
)


def database_path():
    return Path(os.environ.get("STUDYFLOW_DB_PATH", "data/studyflow.sqlite3"))


@contextmanager
def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def migrate(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        for migration in sorted(files("studyflow").joinpath("migrations").iterdir(), key=lambda p: p.name):
            number = int(migration.name.split("_", 1)[0])
            if number > version:
                connection.executescript(
                    f"BEGIN;\n{migration.read_text()}\nPRAGMA user_version = {number};\nCOMMIT;"
                )


def insert_course(path, name, description):
    with connect(path) as connection:
        cursor = connection.execute(
            "INSERT INTO courses (name, description) VALUES (?, ?)", (name, description)
        )
        return {"id": cursor.lastrowid, "name": name, "description": description}


def list_courses(path):
    with connect(path) as connection:
        return [dict(row) for row in connection.execute("SELECT id, name, description FROM courses ORDER BY id")]


def get_course(path, course_id):
    with connect(path) as connection:
        row = connection.execute(
            "SELECT id, name, description FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        return dict(row) if row is not None else None


def update_course(path, course_id, changes):
    with connect(path) as connection:
        row = connection.execute(
            "UPDATE courses SET name = COALESCE(?, name), description = COALESCE(?, description) "
            "WHERE id = ? RETURNING id, name, description",
            (changes.get("name"), changes.get("description"), course_id),
        ).fetchone()
        return dict(row) if row is not None else None


def delete_course(path, course_id):
    with connect(path) as connection:
        return connection.execute("DELETE FROM courses WHERE id = ?", (course_id,)).rowcount > 0


def insert_assignment(path, course_id, title, description, due_date, repository):
    with connect(path) as connection:
        row = connection.execute(
            "INSERT INTO assignments (course_id, title, description, due_date, github_owner, github_repo) "
            "SELECT id, ?, ?, ?, ?, ? FROM courses WHERE id = ? "
            "RETURNING id, course_id, title, description, due_date, github_owner, github_repo",
            (title, description, due_date, repository["owner"] if repository else None,
             repository["repo"] if repository else None, course_id),
        ).fetchone()
        return dict(row) if row is not None else None


def list_assignments(path, course_id):
    with connect(path) as connection:
        return [dict(row) for row in connection.execute(
            ASSIGNMENT_SELECT + "WHERE course_id = ? ORDER BY id",
            (course_id,),
        )]


def get_assignment(path, assignment_id):
    with connect(path) as connection:
        row = connection.execute(
            ASSIGNMENT_SELECT + "WHERE id = ?", (assignment_id,)
        ).fetchone()
        return dict(row) if row is not None else None


def update_assignment(path, assignment_id, changes):
    repository = changes.get("repository")
    replace_repository = "repository" in changes
    with connect(path) as connection:
        connection.execute(
            "UPDATE assignments SET title = COALESCE(?, title), description = COALESCE(?, description), "
            "due_date = CASE WHEN ? THEN ? ELSE due_date END, "
            "github_owner = CASE WHEN ? THEN ? ELSE github_owner END, "
            "github_repo = CASE WHEN ? THEN ? ELSE github_repo END WHERE id = ?",
            (changes.get("title"), changes.get("description"), "due_date" in changes, changes.get("due_date"),
             replace_repository, repository["owner"] if repository else None,
             replace_repository, repository["repo"] if repository else None, assignment_id),
        )
        row = connection.execute(ASSIGNMENT_SELECT + "WHERE id = ?", (assignment_id,)).fetchone()
        return dict(row) if row is not None else None


def delete_assignment(path, assignment_id):
    with connect(path) as connection:
        return connection.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,)).rowcount > 0


def insert_task(path, assignment_id, title):
    with connect(path) as connection:
        row = connection.execute(
            "INSERT INTO tasks (assignment_id, title) SELECT id, ? FROM assignments WHERE id = ? "
            "RETURNING id, assignment_id, title, is_completed", (title, assignment_id),
        ).fetchone()
        return dict(row) if row is not None else None


def list_tasks(path, assignment_id):
    with connect(path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id, assignment_id, title, is_completed FROM tasks WHERE assignment_id = ? ORDER BY id",
            (assignment_id,),
        )]


def update_task(path, task_id, changes):
    with connect(path) as connection:
        row = connection.execute(
            "UPDATE tasks SET title = COALESCE(?, title), is_completed = COALESCE(?, is_completed) WHERE id = ? "
            "RETURNING id, assignment_id, title, is_completed",
            (changes.get("title"), changes.get("is_completed"), task_id),
        ).fetchone()
        return dict(row) if row is not None else None


def delete_task(path, task_id):
    with connect(path) as connection:
        return connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,)).rowcount > 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="StudyFlow database maintenance")
    parser.add_argument("command", choices=["migrate"])
    parser.parse_args()
    migrate(database_path())
