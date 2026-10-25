from fastapi.testclient import TestClient
from importlib.resources import files
import pytest
import sqlite3

from studyflow.web import create_app


def test_created_task_is_incomplete_and_appears_only_in_its_assignment(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignments = f"/api/courses/{course['id']}/assignments"
        assignment = client.post(assignments, json={"title": "Problem set"}).json()
        other = client.post(assignments, json={"title": "Lab"}).json()
        tasks = f"/api/assignments/{assignment['id']}/tasks"
        response = client.post(tasks, json={"title": "Read chapter"})
        assert response.status_code == 201
        task = response.json()
        assert task == {"id": 1, "assignment_id": assignment["id"], "title": "Read chapter", "is_completed": False}
        assert client.get(tasks).json() == [task]
        assert client.get(f"/api/assignments/{other['id']}/tasks").json() == []


@pytest.mark.parametrize("method, arguments", [("get", {}), ("post", {"json": {"title": "Read chapter"}})])
def test_tasks_require_an_existing_assignment(tmp_path, method, arguments):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        response = client.request(method, "/api/assignments/999/tasks", **arguments)
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Assignment not found.", "fields": {}}}


@pytest.mark.parametrize("title, status", [("  Read chapter  ", 201), ("   ", 422), ("x" * 201, 422)])
def test_task_title_is_trimmed_nonblank_and_bounded(tmp_path, title, status):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3"), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        tasks = f"/api/assignments/{assignment['id']}/tasks"
        response = client.post(tasks, json={"title": title})
        assert response.status_code == status
        if status == 201:
            assert response.json()["title"] == "Read chapter"
        else:
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
            assert "title" in response.json()["error"]["fields"]
            assert client.get(tasks).json() == []


def test_adding_incomplete_tasks_updates_assignment_detail_and_list_progress(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        assignment = client.post(listing, json={"title": "Problem set"}).json()
        other = client.post(listing, json={"title": "Lab"}).json()
        tasks = f"/api/assignments/{assignment['id']}/tasks"
        client.post(tasks, json={"title": "Read chapter"})
        assert client.get(f"/api/assignments/{assignment['id']}").json()["progress"] == {"completed": 0, "total": 1, "percent": 0}
        client.post(tasks, json={"title": "Solve exercises"})
        assert client.get(listing).json() == [
            {**assignment, "progress": {"completed": 0, "total": 2, "percent": 0}}, other,
        ]


def test_renaming_task_preserves_identity_parent_and_completion_after_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        listing = f"/api/assignments/{assignment['id']}/tasks"
        task = client.post(listing, json={"title": "Read chapter"}).json()
        response = client.patch(f"/api/tasks/{task['id']}", json={"title": "  Read two chapters  "})
        assert response.status_code == 200
        assert response.json() == {**task, "title": "Read two chapters"}
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(listing).json() == [{**task, "title": "Read two chapters"}]


def test_completing_one_of_three_tasks_derives_33_percent_in_detail_and_list_after_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        assignment = client.post(listing, json={"title": "Problem set"}).json()
        tasks_url = f"/api/assignments/{assignment['id']}/tasks"
        tasks = [client.post(tasks_url, json={"title": title}).json()
                 for title in ["Read chapter", "Solve exercises", "Check answers"]]
        response = client.patch(f"/api/tasks/{tasks[0]['id']}", json={"is_completed": True})
        assert response.status_code == 200
        assert response.json() == {**tasks[0], "is_completed": True}
        assert client.get(f"/api/assignments/{assignment['id']}").json() == {
            **assignment, "progress": {"completed": 1, "total": 3, "percent": 33},
        }
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(listing).json() == [{**assignment, "progress": {"completed": 1, "total": 3, "percent": 33}}]
        assert restarted.get(tasks_url).json() == [{**tasks[0], "is_completed": True}, *tasks[1:]]


def test_empty_task_patch_is_rejected_without_changing_task(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        listing = f"/api/assignments/{assignment['id']}/tasks"
        task = client.post(listing, json={"title": "Read chapter"}).json()
        response = client.patch(f"/api/tasks/{task['id']}", json={})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "body" in response.json()["error"]["fields"]
        assert client.get(listing).json() == [task]


def test_assignment_edit_response_retains_current_checklist_progress(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        task = client.post(f"/api/assignments/{assignment['id']}/tasks", json={"title": "Read chapter"}).json()
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        url = f"/api/assignments/{assignment['id']}"
        response = client.patch(url, json={"description": "Updated notes"})
        assert response.status_code == 200
        assert response.json() == {
            **assignment, "description": "Updated notes", "progress": {"completed": 1, "total": 1, "percent": 100},
        }
        assert client.get(url).json() == response.json()


def test_deleting_tasks_recomputes_progress_and_deleting_last_task_restores_empty_checklist(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        tasks_url = f"/api/assignments/{assignment['id']}/tasks"
        tasks = [client.post(tasks_url, json={"title": title}).json()
                 for title in ["Read chapter", "Solve exercises", "Check answers"]]
        client.patch(f"/api/tasks/{tasks[0]['id']}", json={"is_completed": True})
        response = client.delete(f"/api/tasks/{tasks[2]['id']}")
        assert response.status_code == 204
        assert response.content == b""
        assert client.get(f"/api/assignments/{assignment['id']}").json()["progress"] == {"completed": 1, "total": 2, "percent": 50}
        client.delete(f"/api/tasks/{tasks[0]['id']}")
        assert client.get(f"/api/assignments/{assignment['id']}").json()["progress"] == {"completed": 0, "total": 1, "percent": 0}
        client.delete(f"/api/tasks/{tasks[1]['id']}")
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(tasks_url).json() == []
        assert restarted.get(f"/api/assignments/{assignment['id']}").json() == assignment
        repeated = restarted.delete(f"/api/tasks/{tasks[1]['id']}")
        assert repeated.status_code == 404
        assert repeated.json() == {"error": {"code": "NOT_FOUND", "message": "Task not found.", "fields": {}}}


def test_progress_handles_completion_reopening_repeated_requests_and_new_incomplete_tasks(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        url = f"/api/assignments/{assignment['id']}"
        tasks = [client.post(url + "/tasks", json={"title": title}).json()
                 for title in ["Read chapter", "Solve exercises", "Check answers"]]
        for task, progress in zip(tasks, [
            {"completed": 1, "total": 3, "percent": 33},
            {"completed": 2, "total": 3, "percent": 66},
            {"completed": 3, "total": 3, "percent": 100},
        ]):
            assert client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True}).status_code == 200
            assert client.get(url).json()["progress"] == progress
        task_url = f"/api/tasks/{tasks[0]['id']}"
        client.patch(task_url, json={"is_completed": True})
        renamed = client.patch(task_url, json={"title": "Read two chapters"})
        assert renamed.json() == {**tasks[0], "title": "Read two chapters", "is_completed": True}
        assert client.get(url).json()["progress"] == {"completed": 3, "total": 3, "percent": 100}
        for _ in range(2):
            reopened = client.patch(task_url, json={"is_completed": False})
            assert reopened.json() == {**tasks[0], "title": "Read two chapters", "is_completed": False}
            assert client.get(url).json()["progress"] == {"completed": 2, "total": 3, "percent": 66}
        client.post(url + "/tasks", json={"title": "Review feedback"})
        assert client.get(url).json()["progress"] == {"completed": 2, "total": 4, "percent": 50}
        updated = client.patch(task_url, json={"title": "Read final chapter", "is_completed": True})
        assert updated.json() == {**tasks[0], "title": "Read final chapter", "is_completed": True}
        assert client.get(url).json()["progress"] == {"completed": 3, "total": 4, "percent": 75}


@pytest.mark.parametrize("method, body, field", [
    ("post", {}, "title"), ("post", {"title": None}, "title"), ("post", {"title": 42}, "title"),
    ("post", {"title": "New task", "is_completed": True}, "is_completed"),
    ("patch", {"title": None}, "title"), ("patch", {"title": "   "}, "title"),
    ("patch", {"title": "x" * 201}, "title"), ("patch", {"title": 42}, "title"),
    ("patch", {"title": "Changed", "is_completed": "true"}, "is_completed"),
    ("patch", {"title": "Changed", "is_completed": 1}, "is_completed"),
    ("patch", {"title": "Changed", "is_completed": 0}, "is_completed"),
    ("patch", {"title": "Changed", "is_completed": None}, "is_completed"),
    ("patch", {"title": "Changed", "assignment_id": 999}, "assignment_id"),
    ("patch", {"title": "Changed", "id": 999}, "id"),
    ("patch", {"title": "Changed", "progress": 100}, "progress"),
    ("patch", {"title": "Changed", "description": "Not a task field"}, "description"),
])
def test_invalid_task_writes_are_rejected_without_partial_changes(tmp_path, method, body, field):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        listing = f"/api/assignments/{assignment['id']}/tasks"
        task = client.post(listing, json={"title": "Read chapter"}).json()
        url = listing if method == "post" else f"/api/tasks/{task['id']}"
        response = client.request(method, url, json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert field in response.json()["error"]["fields"]
        assert client.get(listing).json() == [task]
        assert client.get(f"/api/assignments/{assignment['id']}").json()["progress"] == {"completed": 0, "total": 1, "percent": 0}


@pytest.mark.parametrize("parent", ["assignment", "course"])
def test_parent_deletion_cascades_to_tasks_and_preserves_unrelated_checklists_after_restart(tmp_path, parent):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        other_course = client.post("/api/courses", json={"name": "Physics"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        sibling = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Lab"}).json()
        other = client.post(f"/api/courses/{other_course['id']}/assignments", json={"title": "Experiment"}).json()
        task = client.post(f"/api/assignments/{assignment['id']}/tasks", json={"title": "Read chapter"}).json()
        sibling_task = client.post(f"/api/assignments/{sibling['id']}/tasks", json={"title": "Write report"}).json()
        other_task = client.post(f"/api/assignments/{other['id']}/tasks", json={"title": "Measure"}).json()
        url = f"/api/assignments/{assignment['id']}" if parent == "assignment" else f"/api/courses/{course['id']}"
        assert client.delete(url).status_code == 204
    with TestClient(create_app(db_path=path)) as restarted:
        missing = restarted.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        assert missing.status_code == 404
        assert missing.json() == {"error": {"code": "NOT_FOUND", "message": "Task not found.", "fields": {}}}
        assert restarted.get(f"/api/assignments/{assignment['id']}/tasks").status_code == 404
        assert restarted.get(f"/api/assignments/{other['id']}/tasks").json() == [other_task]
        if parent == "assignment":
            assert restarted.get(f"/api/assignments/{sibling['id']}/tasks").json() == [sibling_task]
            assert restarted.get(f"/api/courses/{course['id']}").json() == course
        else:
            assert restarted.delete(f"/api/tasks/{sibling_task['id']}").status_code == 404
            assert restarted.get(f"/api/courses/{course['id']}").status_code == 404


def test_existing_assignment_database_is_upgraded_without_losing_saved_work(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    migrations = files("studyflow").joinpath("migrations")
    with sqlite3.connect(path) as connection:
        connection.executescript(
            migrations.joinpath("001_courses.sql").read_text()
            + migrations.joinpath("002_assignments.sql").read_text()
            + """
                INSERT INTO courses (id, name, description) VALUES (7, 'Algorithms', 'Existing course');
                INSERT INTO assignments (id, course_id, title, description, due_date)
                VALUES (8, 7, 'Problem set', 'Existing assignment', '2028-02-29');
                PRAGMA user_version = 2;
            """
        )
    with TestClient(create_app(db_path=path)) as client:
        assignment = client.get("/api/assignments/8").json()
        assert assignment == {
            "id": 8, "course_id": 7, "title": "Problem set", "description": "Existing assignment",
            "due_date": "2028-02-29", "repository": None, "progress": {"completed": 0, "total": 0, "percent": 0},
        }
        response = client.post("/api/assignments/8/tasks", json={"title": "Read chapter"})
        assert response.status_code == 201
        task = response.json()
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get("/api/assignments/8/tasks").json() == [task]
        assert restarted.get("/api/assignments/8").json() == {**assignment, "progress": {"completed": 0, "total": 1, "percent": 0}}
        assert restarted.get("/api/courses/7").json() == {"id": 7, "name": "Algorithms", "description": "Existing course"}


def test_duplicate_task_titles_at_the_length_limit_have_separate_identities_and_stable_order(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        listing = f"/api/assignments/{assignment['id']}/tasks"
        first = client.post(listing, json={"title": "x" * 200})
        second = client.post(listing, json={"title": "x" * 200})
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] != second.json()["id"]
        assert client.get(listing).json() == [first.json(), second.json()]


def test_task_text_is_escaped_in_checkbox_rename_field_and_deletion_confirmation_data(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Problem set"}).json()
        title = '\"><script>alert("task")</script>'
        response = client.post(f"/api/assignments/{assignment['id']}/tasks", json={"title": title})
        assert response.status_code == 201
        page = client.get(f"/assignments/{assignment['id']}")
        assert page.status_code == 200
        assert '&#34;&gt;&lt;script&gt;alert(&#34;task&#34;)&lt;/script&gt;' in page.text
        assert title not in page.text
