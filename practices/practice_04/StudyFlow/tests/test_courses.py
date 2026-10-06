from fastapi.testclient import TestClient
import pytest
import sqlite3

from studyflow.web import create_app


def test_created_course_appears_in_course_list(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        response = client.post(
            "/api/courses",
            json={"name": "Algorithms", "description": "University coursework"},
        )

        assert response.status_code == 201
        course = response.json()
        assert course == {
            "id": 1,
            "name": "Algorithms",
            "description": "University coursework",
        }
        listing = client.get("/api/courses")
        assert listing.status_code == 200
        assert listing.json() == [course]


def test_home_page_displays_courses_and_creation_form(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        client.post("/api/courses", json={"name": "Algorithms", "description": "<script>unsafe()</script>"})

        page = client.get("/")

        assert page.status_code == 200
        assert "Algorithms" in page.text
        assert "&lt;script&gt;unsafe()&lt;/script&gt;" in page.text
        assert '<label for="name">Course name</label>' in page.text
        assert '<label for="description">Description</label>' in page.text
        assert 'type="submit"' in page.text


@pytest.mark.parametrize("payload, field", [
    ({"name": "   "}, "name"),
    ({"name": "x" * 201}, "name"),
    ({"name": None}, "name"),
    ({"name": 123}, "name"),
    ({}, "name"),
    ({"name": "Algorithms", "description": "x" * 5001}, "description"),
    ({"name": "Algorithms", "description": None}, "description"),
    ({"name": "Algorithms", "id": 42}, "id"),
])
def test_invalid_course_is_rejected_without_creating_a_record(tmp_path, payload, field):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3"), raise_server_exceptions=False) as client:
        response = client.post("/api/courses", json=payload)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert field in error["fields"]
        assert client.get("/api/courses").json() == []


def test_locked_database_returns_recoverable_error_without_partial_course(tmp_path):
    path = tmp_path / "courses.sqlite3"
    with TestClient(create_app(db_path=path), raise_server_exceptions=False) as client:
        with sqlite3.connect(path) as locked:
            locked.execute("BEGIN EXCLUSIVE")
            response = client.post("/api/courses", json={"name": "Algorithms"})
            assert response.status_code == 503
            assert response.json() == {"error": {
                "code": "DATABASE_BUSY", "message": "The database is busy. Please try again.", "fields": {},
            }}
        assert client.get("/api/courses").json() == []
