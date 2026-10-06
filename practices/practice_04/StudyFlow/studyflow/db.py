from contextlib import contextmanager
from importlib.resources import files
import os
from pathlib import Path
import sqlite3


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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="StudyFlow database maintenance")
    parser.add_argument("command", choices=["migrate"])
    parser.parse_args()
    migrate(database_path())
