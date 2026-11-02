from importlib.resources import files
import socket
import sqlite3

from fastapi.testclient import TestClient
import pytest

from studyflow.web import create_app


def test_assignment_can_be_created_with_repository_reference_and_read_after_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    reference = {"owner": "octocat", "repo": "hello-world"}
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        response = client.post(listing, json={"title": "Problem set", "repository": reference})
        assert response.status_code == 201
        assignment = response.json()
        assert assignment == {
            "id": 1, "course_id": course["id"], "title": "Problem set", "description": "",
            "due_date": None, "repository": reference, "progress": {"completed": 0, "total": 0, "percent": 0},
        }
        assert client.get(listing).json() == [assignment]
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f"/api/assignments/{assignment['id']}").json() == assignment


@pytest.mark.parametrize("reference, expected, invalid_field", [
    ({"owner": "OCTO-Cat", "repo": "Lab_1.GIT"}, {"owner": "octo-cat", "repo": "lab_1.git"}, None),
    ({"owner": "bad/owner", "repo": "lab"}, None, "owner"),
    ({"owner": " bad", "repo": "lab"}, None, "owner"),
    ({"owner": "bad\n", "repo": "lab"}, None, "owner"),
    ({"owner": "bad--owner", "repo": "lab"}, None, "owner"),
    ({"owner": "-bad", "repo": "lab"}, None, "owner"),
    ({"owner": "bad-", "repo": "lab"}, None, "owner"),
    ({"owner": "bad_owner", "repo": "lab"}, None, "owner"),
    ({"owner": "学生", "repo": "lab"}, None, "owner"),
    ({"owner": "", "repo": "lab"}, None, "owner"),
    ({"owner": "x" * 40, "repo": "lab"}, None, "owner"),
    ({"owner": "octocat", "repo": ""}, None, "repo"),
    ({"owner": "octocat", "repo": "."}, None, "repo"),
    ({"owner": "octocat", "repo": ".."}, None, "repo"),
    ({"owner": "octocat", "repo": "path/repo"}, None, "repo"),
    ({"owner": "octocat", "repo": "hello world"}, None, "repo"),
    ({"owner": "octocat", "repo": "repo\n"}, None, "repo"),
    ({"owner": "octocat", "repo": "https://github.com/octocat/repo"}, None, "repo"),
    ({"owner": "octocat", "repo": "x" * 101}, None, "repo"),
])
def test_repository_identifiers_are_normalized_and_validate_specified_syntax(tmp_path, reference, expected, invalid_field):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        response = client.post(listing, json={"title": "Problem set", "repository": reference})
        if invalid_field is None:
            assert response.status_code == 201
            assert response.json()["repository"] == expected
        else:
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
            assert f"repository.{invalid_field}" in response.json()["error"]["fields"]
            assert client.get(listing).json() == []


def test_reference_can_be_attached_replaced_and_preserved_during_unrelated_edits_after_restart(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        assignment = client.post(listing, json={"title": "Problem set", "description": "Original notes", "due_date": "2028-02-29"}).json()
        url = f"/api/assignments/{assignment['id']}"
        task = client.post(url + "/tasks", json={"title": "Read chapter"}).json()
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        attached = client.patch(url, json={"repository": {"owner": "OCTOCAT", "repo": "Hello-World"}})
        assert attached.status_code == 200
        assert attached.json() == {
            **assignment, "repository": {"owner": "octocat", "repo": "hello-world"},
            "progress": {"completed": 1, "total": 1, "percent": 100},
        }
        replaced = client.patch(url, json={"repository": {"owner": "Student-1", "repo": "LAB_2"}})
        assert replaced.status_code == 200
        assert replaced.json() == {**attached.json(), "repository": {"owner": "student-1", "repo": "lab_2"}}
        edited = client.patch(url, json={"description": "Updated notes"})
        assert edited.json() == {**replaced.json(), "description": "Updated notes"}
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(url).json() == edited.json()
        assert restarted.get(listing).json() == [edited.json()]
        assert restarted.get(url + "/tasks").json() == [{**task, "is_completed": True}]


def test_removing_reference_preserves_coursework_and_other_assignments_using_same_reference(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    reference = {"owner": "octocat", "repo": "hello-world"}
    with TestClient(create_app(db_path=path)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        assignment = client.post(listing, json={
            "title": "Problem set", "description": "Keep these notes", "due_date": "2028-02-29", "repository": reference,
        }).json()
        shared = client.post(listing, json={"title": "Another assignment", "repository": reference}).json()
        url = f"/api/assignments/{assignment['id']}"
        task = client.post(url + "/tasks", json={"title": "Read chapter"}).json()
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        response = client.patch(url, json={"repository": None})
        assert response.status_code == 200
        cleared = {**assignment, "repository": None, "progress": {"completed": 1, "total": 1, "percent": 100}}
        assert response.json() == cleared
        assert client.patch(url, json={"repository": None}).json() == cleared
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(listing).json() == [cleared, shared]
        assert restarted.get(url + "/tasks").json() == [{**task, "is_completed": True}]


@pytest.mark.parametrize("reference, invalid_field", [
    ({}, "repository.owner"),
    ({"owner": "octocat"}, "repository.repo"),
    ({"repo": "lab"}, "repository.owner"),
    ({"owner": None, "repo": "lab"}, "repository.owner"),
    ({"owner": 123, "repo": "lab"}, "repository.owner"),
    ({"owner": "octocat", "repo": False}, "repository.repo"),
    ({"owner": "bad--owner", "repo": "lab"}, "repository.owner"),
    ({"owner": "octocat", "repo": ".."}, "repository.repo"),
    ({"owner": "octocat", "repo": "lab", "id": 7}, "repository.id"),
    ([{"owner": "octocat", "repo": "lab"}], "repository"),
    ("https://github.com/octocat/lab", "repository"),
])
def test_invalid_reference_patch_leaves_all_assignment_fields_unchanged(tmp_path, reference, invalid_field):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
        }).json()
        url = f"/api/assignments/{assignment['id']}"
        response = client.patch(url, json={"title": "Must not be saved", "repository": reference})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert invalid_field in response.json()["error"]["fields"]
        assert client.get(url).json() == assignment


def test_reference_crud_works_without_network_connections_at_identifier_length_limits(tmp_path, monkeypatch):
    def network_forbidden(*args, **kwargs):
        pytest.fail("Saving or reading a repository reference must not open network connections.")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        response = client.post(listing, json={
            "title": "Problem set", "repository": {"owner": "S" * 39, "repo": "LAB_" + "X" * 92 + ".GIT"},
        })
        assert response.status_code == 201
        assignment = response.json()
        assert assignment["repository"] == {"owner": "s" * 39, "repo": "lab_" + "x" * 92 + ".git"}
        url = f"/api/assignments/{assignment['id']}"
        assert client.get(url).json() == assignment
        assert client.get(listing).json() == [assignment]
        assert client.get(f"/assignments/{assignment['id']}").status_code == 200
        replacement = client.patch(url, json={"repository": {"owner": "student", "repo": "..."}})
        assert replacement.status_code == 200
        assert replacement.json()["repository"] == {"owner": "student", "repo": "..."}
        assert client.patch(url, json={"repository": None}).json()["repository"] is None


def test_existing_checklist_database_is_upgraded_without_losing_coursework_or_cascade(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    migrations = files("studyflow").joinpath("migrations")
    with sqlite3.connect(path) as connection:
        connection.executescript(
            migrations.joinpath("001_courses.sql").read_text()
            + migrations.joinpath("002_assignments.sql").read_text()
            + migrations.joinpath("003_tasks.sql").read_text()
            + """
                INSERT INTO courses (id, name, description) VALUES (7, 'Algorithms', 'Existing course');
                INSERT INTO assignments (id, course_id, title, description, due_date)
                VALUES (8, 7, 'Problem set', 'Existing notes', '2028-02-29');
                INSERT INTO tasks (id, assignment_id, title, is_completed) VALUES (9, 8, 'Read chapter', 1);
                PRAGMA user_version = 3;
            """
        )
    assignment = {
        "id": 8, "course_id": 7, "title": "Problem set", "description": "Existing notes", "due_date": "2028-02-29",
        "repository": None, "progress": {"completed": 1, "total": 1, "percent": 100},
    }
    task = {"id": 9, "assignment_id": 8, "title": "Read chapter", "is_completed": True}
    with TestClient(create_app(db_path=path)) as client:
        assert client.get("/api/assignments/8").json() == assignment
        assert client.get("/api/assignments/8/tasks").json() == [task]
        assert client.get("/api/courses/7").json() == {"id": 7, "name": "Algorithms", "description": "Existing course"}
        reference = {"owner": "octocat", "repo": "hello-world"}
        response = client.patch("/api/assignments/8", json={"repository": reference})
        assert response.status_code == 200
        assert response.json() == {**assignment, "repository": reference}
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get("/api/assignments/8").json() == {**assignment, "repository": reference}
        assert restarted.get("/api/assignments/8/tasks").json() == [task]
        assert restarted.delete("/api/courses/7").status_code == 204
        assert restarted.get("/api/assignments/8").status_code == 404
        assert restarted.patch("/api/tasks/9", json={"title": "Gone"}).status_code == 404
