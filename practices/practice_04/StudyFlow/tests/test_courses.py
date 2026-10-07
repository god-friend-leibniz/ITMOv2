from fastapi.testclient import TestClient
import pytest
import sqlite3

from studyflow.web import create_app


def test_course_can_be_read_by_id(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms", "description": "Problem sets"}).json()
        response = client.get(f"/api/courses/{course['id']}")
        assert response.status_code == 200
        assert response.json() == course


def test_editing_course_preserves_omitted_fields_and_survives_restart(tmp_path):
    path = tmp_path / "courses.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms", "description": "Problem sets"}).json()
        response = client.patch(f"/api/courses/{course['id']}", json={"name": "  Advanced algorithms  "})
        assert response.status_code == 200
        assert response.json() == {"id": course["id"], "name": "Advanced algorithms", "description": "Problem sets"}

    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f"/api/courses/{course['id']}").json() == response.json()
        assert restarted.get("/api/courses").json() == [response.json()]


def test_empty_course_edit_is_rejected_without_changing_course(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms", "description": "Problem sets"}).json()
        response = client.patch(f"/api/courses/{course['id']}", json={})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "body" in response.json()["error"]["fields"]
        assert client.get(f"/api/courses/{course['id']}").json() == course


def test_description_can_be_cleared_without_changing_course_name(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms", "description": "Problem sets"}).json()
        response = client.patch(f"/api/courses/{course['id']}", json={"description": ""})
        assert response.status_code == 200
        assert response.json() == {"id": course["id"], "name": "Algorithms", "description": ""}
        assert client.get(f"/api/courses/{course['id']}").json() == response.json()


@pytest.mark.parametrize("payload, field", [
    ({"name": "   "}, "name"),
    ({"name": "x" * 201}, "name"),
    ({"name": None}, "name"),
    ({"name": 123}, "name"),
    ({"name": "Renamed", "description": "x" * 5001}, "description"),
    ({"name": "Renamed", "description": None}, "description"),
    ({"description": False}, "description"),
    ({"name": "Renamed", "id": 42}, "id"),
    ({"unknown": "value"}, "unknown"),
])
def test_invalid_course_edit_leaves_saved_course_unchanged(tmp_path, payload, field):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms", "description": "Problem sets"}).json()
        response = client.patch(f"/api/courses/{course['id']}", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert field in response.json()["error"]["fields"]
        assert client.get(f"/api/courses/{course['id']}").json() == course


@pytest.mark.parametrize("method, arguments", [("get", {}), ("patch", {"json": {"name": "Renamed"}})])
def test_missing_course_returns_not_found(tmp_path, method, arguments):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        response = client.request(method, "/api/courses/999", **arguments)
        assert response.status_code == 404
        assert response.json() == {"error": {
            "code": "NOT_FOUND", "message": "Course not found.", "fields": {},
        }}


def test_deleting_course_removes_only_that_course_and_survives_restart(tmp_path):
    path = tmp_path / "courses.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        other = client.post("/api/courses", json={"name": "Physics"}).json()
        response = client.delete(f"/api/courses/{course['id']}")
        assert response.status_code == 204
        assert response.content == b""
        assert client.get("/api/courses").json() == [other]

    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get("/api/courses").json() == [other]
        assert restarted.get(f"/api/courses/{course['id']}").status_code == 404
        response = restarted.delete(f"/api/courses/{course['id']}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_missing_course_page_has_readable_error_and_way_back(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "courses.sqlite3")) as client:
        response = client.get("/courses/999")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert "Course not found" in response.text
        assert '<a href="/">All courses</a>' in response.text


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
