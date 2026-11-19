from fastapi.testclient import TestClient
import pytest
import sqlite3

from studyflow.web import create_app


def test_created_assignment_appears_only_in_its_course_with_empty_progress(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        other = client.post("/api/courses", json={"name": "Physics"}).json()
        response = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set 1", "description": "Sorting exercises",
        })
        assert response.status_code == 201
        assignment = response.json()
        assert assignment == {
            "id": 1, "course_id": course["id"], "title": "Problem set 1",
            "description": "Sorting exercises", "due_date": None, "repository": None,
            "progress": {"completed": 0, "total": 0, "percent": 0},
        }
        assert client.get(f"/api/courses/{course['id']}/assignments").json() == [assignment]
        assert client.get(f"/api/courses/{other['id']}/assignments").json() == []


@pytest.mark.parametrize("method, arguments", [("get", {}), ("post", {"json": {"title": "Problem set"}})])
def test_assignments_require_an_existing_course(tmp_path, method, arguments):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        response = client.request(method, "/api/courses/999/assignments", **arguments)
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Course not found.", "fields": {}}}


@pytest.mark.parametrize("title, status", [("  Problem set 1  ", 201), ("   ", 422), ("x" * 201, 422)])
def test_assignment_titles_are_trimmed_and_must_be_nonblank_and_bounded(tmp_path, title, status):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3"), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        url = f"/api/courses/{course['id']}/assignments"
        response = client.post(url, json={"title": title})
        assert response.status_code == status
        if status == 201:
            assert response.json()["title"] == "Problem set 1"
        else:
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
            assert "title" in response.json()["error"]["fields"]
            assert client.get(url).json() == []


@pytest.mark.parametrize("due_date", ["2000-01-01", "2028-02-29"])
def test_assignment_accepts_optional_calendar_date_including_past_and_leap_day(tmp_path, due_date):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        url = f"/api/courses/{course['id']}/assignments"
        response = client.post(url, json={"title": "Problem set", "due_date": due_date})
        assert response.status_code == 201
        assert response.json()["due_date"] == due_date
        assert response.json()["description"] == ""
        assert client.get(url).json() == [response.json()]


@pytest.mark.parametrize("due_date", ["2026-02-29", "2026-13-01", "20260101", "2026-1-01", "2026-01-01T12:00:00", ""])
def test_invalid_assignment_due_date_is_rejected_without_creating_assignment(tmp_path, due_date):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        url = f"/api/courses/{course['id']}/assignments"
        response = client.post(url, json={"title": "Problem set", "due_date": due_date})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "due_date" in response.json()["error"]["fields"]
        assert client.get(url).json() == []


def test_assignment_details_and_parent_survive_app_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set 1", "description": "Sorting exercises", "due_date": "2028-02-29",
        }).json()
        response = client.get(f"/api/assignments/{assignment['id']}")
        assert response.status_code == 200
        assert response.json() == assignment
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f"/api/assignments/{assignment['id']}").json() == assignment
        assert restarted.get(f"/api/courses/{course['id']}").json() == course


@pytest.mark.parametrize("method, arguments", [("get", {}), ("patch", {"json": {"title": "Problem set"}}), ("delete", {})])
def test_missing_assignment_returns_normalized_not_found(tmp_path, method, arguments):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        response = client.request(method, "/api/assignments/999", **arguments)
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Assignment not found.", "fields": {}}}


def test_missing_assignment_page_is_readable_and_links_back_to_courses(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        response = client.get("/assignments/999")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert "Assignment not found" in response.text
        assert '<a href="/">All courses</a>' in response.text


def test_assignment_edit_preserves_omissions_clears_date_and_survives_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set 1", "description": "Sorting exercises", "due_date": "2028-02-29",
        }).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.patch(url, json={"title": "  Advanced sorting  "})
        assert response.status_code == 200
        assert response.json() == {**assignment, "title": "Advanced sorting"}
        cleared = client.patch(url, json={"description": "", "due_date": None})
        assert cleared.status_code == 200
        assert cleared.json() == {**assignment, "title": "Advanced sorting", "description": "", "due_date": None}
        rescheduled = client.patch(url, json={"due_date": "2029-01-15"})
        assert rescheduled.status_code == 200
        assert rescheduled.json() == {**assignment, "title": "Advanced sorting", "description": "", "due_date": "2029-01-15"}
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(url).json() == rescheduled.json()
        assert restarted.get(f"/api/courses/{course['id']}/assignments").json() == [rescheduled.json()]


def test_empty_assignment_patch_is_rejected_without_changing_saved_assignment(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.patch(url, json={})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "body" in response.json()["error"]["fields"]
        assert client.get(url).json() == assignment


@pytest.mark.parametrize("invalid", [
    {"title": "   "}, {"title": None}, {"title": 42},
    {"description": None}, {"description": "x" * 5001},
    {"due_date": "2026-02-29"}, {"due_date": True},
    {"course_id": 999}, {"id": 999}, {"progress": {"percent": 100}}, {"unknown": "value"},
])
def test_invalid_assignment_edit_is_rejected_without_partial_changes(tmp_path, invalid):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "description": "Original notes", "due_date": "2028-02-29",
        }).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.patch(url, json={"title": "Advanced sorting", **invalid})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert next(iter(invalid)) in response.json()["error"]["fields"]
        assert client.get(url).json() == assignment


def test_deleting_assignment_preserves_course_and_other_assignments_across_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        assignment = client.post(listing, json={"title": "Problem set 1"}).json()
        other = client.post(listing, json={"title": "Problem set 2"}).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.delete(url)
        assert response.status_code == 204
        assert response.content == b""
        assert client.get(listing).json() == [other]
        assert client.get(f"/api/courses/{course['id']}").json() == course
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(listing).json() == [other]
        assert restarted.get(url).status_code == 404
        repeated = restarted.delete(url)
        assert repeated.status_code == 404
        assert repeated.json()["error"]["code"] == "NOT_FOUND"


def test_deleting_course_removes_all_its_assignments_and_preserves_other_courses_after_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        other_course = client.post("/api/courses", json={"name": "Physics"}).json()
        assignments = [client.post(f"/api/courses/{course['id']}/assignments", json={"title": title}).json()
                       for title in ["Problem set 1", "Problem set 2"]]
        other = client.post(f"/api/courses/{other_course['id']}/assignments", json={"title": "Lab"}).json()
        response = client.delete(f"/api/courses/{course['id']}")
        assert response.status_code == 204
        assert response.content == b""
        for assignment in assignments:
            assert client.get(f"/api/assignments/{assignment['id']}").status_code == 404
        assert client.get(f"/api/courses/{course['id']}/assignments").status_code == 404
    with TestClient(create_app(db_path=path)) as restarted:
        for assignment in assignments:
            assert restarted.get(f"/api/assignments/{assignment['id']}").status_code == 404
        assert restarted.get(f"/api/courses/{other_course['id']}/assignments").json() == [other]
        assert restarted.get(f"/api/courses/{other_course['id']}").json() == other_course


def test_existing_course_only_database_is_upgraded_without_losing_coursework(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    # Version 1 is the persisted format from the preceding course-only slices.
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
                description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 5000)
            );
            INSERT INTO courses (id, name, description) VALUES (7, 'Algorithms', 'Existing notes');
            PRAGMA user_version = 1;
        """)
    with TestClient(create_app(db_path=path)) as client:
        assert client.get("/api/courses/7").json() == {"id": 7, "name": "Algorithms", "description": "Existing notes"}
        response = client.post("/api/courses/7/assignments", json={"title": "Problem set"})
        assert response.status_code == 201
        assignment = response.json()
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get("/api/courses/7/assignments").json() == [assignment]
        assert restarted.get("/api/courses/7").json()["description"] == "Existing notes"


def test_assignment_text_is_escaped_in_course_list_and_detail_form(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": '<script>alert("title")</script>',
            "description": '</textarea><script>alert("notes")</script>',
        }).json()
        for url in [f"/courses/{course['id']}", f"/assignments/{assignment['id']}"]:
            response = client.get(url)
            assert response.status_code == 200
            assert "&lt;script&gt;alert(&#34;title&#34;)&lt;/script&gt;" in response.text
            assert "&lt;/textarea&gt;&lt;script&gt;alert(&#34;notes&#34;)&lt;/script&gt;" in response.text
            assert assignment["title"] not in response.text
            assert assignment["description"] not in response.text
