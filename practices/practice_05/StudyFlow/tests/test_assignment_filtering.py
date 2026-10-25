import re
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from studyflow.web import create_app


def assignment_links(html):
    return [urlsplit(url).path for url in re.findall(r'href="(/assignments/\d+(?:\?[^\"]*)?)"', html)]


@pytest.fixture
def mixed_course(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        other = client.post("/api/courses", json={"name": "Physics"}).json()
        assignments = []
        for title, total, completed in [("Empty", 0, 0), ("Not started", 2, 0), ("Partial", 2, 1), ("Done", 2, 2)]:
            assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": title}).json()
            for index in range(total):
                task = client.post(f"/api/assignments/{assignment['id']}/tasks", json={"title": f"Step {index}"}).json()
                if index < completed:
                    client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
            assignments.append(assignment)
        foreign = client.post(f"/api/courses/{other['id']}/assignments", json={"title": "Foreign"}).json()
        task = client.post(f"/api/assignments/{foreign['id']}/tasks", json={"title": "Measure"}).json()
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        yield client, course, assignments


def test_completed_mode_shows_only_nonempty_completed_checklists_in_its_course(mixed_course):
    client, course, assignments = mixed_course
    page = client.get(f"/courses/{course['id']}?completion=completed")
    assert page.status_code == 200
    assert assignment_links(page.text) == [f"/assignments/{assignments[3]['id']}"]
    assert "2 / 2 · 100%" in page.text


def test_incomplete_mode_includes_empty_unstarted_and_partial_checklists(mixed_course):
    client, course, assignments = mixed_course
    before = client.get(f"/api/courses/{course['id']}/assignments").json()
    page = client.get(f"/courses/{course['id']}?completion=incomplete")
    assert assignment_links(page.text) == [f"/assignments/{item['id']}" for item in assignments[:3]]
    assert "0 / 0 · 0%" in page.text
    assert "0 / 2 · 0%" in page.text
    assert "1 / 2 · 50%" in page.text
    assert client.get(f"/api/courses/{course['id']}/assignments").json() == before


@pytest.mark.parametrize("query", ["", "?completion=all"])
def test_all_mode_preserves_course_order_and_unfiltered_json_contract(mixed_course, query):
    client, course, assignments = mixed_course
    listing = f"/api/courses/{course['id']}/assignments"
    before = client.get(listing).json()
    assert assignment_links(client.get(f"/courses/{course['id']}{query}").text) == [
        f"/assignments/{item['id']}" for item in assignments
    ]
    client.get(f"/courses/{course['id']}?completion=completed")
    assert client.get(listing).json() == before
    assert client.get(listing + "?completion=completed").json() == before
    assert [item["progress"] for item in before] == [
        {"completed": 0, "total": 0, "percent": 0},
        {"completed": 0, "total": 2, "percent": 0},
        {"completed": 1, "total": 2, "percent": 50},
        {"completed": 2, "total": 2, "percent": 100},
    ]
    assert set(before[0]) == {"id", "course_id", "title", "description", "due_date", "repository", "progress"}
    missing = client.get(f"/courses/999{query}")
    assert missing.status_code == 404
    assert "Course not found" in missing.text


@pytest.mark.parametrize("query", ["?completion=unexpected", "?completion=", "?completion"])
def test_unknown_or_empty_course_completion_means_all_without_validation_error(mixed_course, query):
    client, course, assignments = mixed_course
    page = client.get(f"/courses/{course['id']}{query}")
    assert page.status_code == 200
    assert assignment_links(page.text) == [f"/assignments/{item['id']}" for item in assignments]
    assert "unexpected" not in page.text
    assert f'<a href="/courses/{course["id"]}" aria-current="page">All</a>' in page.text
    missing = client.get(f"/courses/999{query}")
    assert missing.status_code == 404
    assert "Course not found" in missing.text


@pytest.mark.parametrize("query", ["", "?completion=all", "?completion=unexpected", "?completion=", "?completion"])
def test_assignment_return_context_normalizes_to_all_and_preserves_missing_pages(mixed_course, query):
    client, course, assignments = mixed_course
    page = client.get(f"/assignments/{assignments[0]['id']}{query}")
    assert page.status_code == 200
    expected = f"/courses/{course['id']}"
    assert f'<a href="{expected}">Back to course</a>' in page.text
    assert f'data-course-url="{expected}"' in page.text
    assert "unexpected" not in page.text
    missing = client.get(f"/assignments/999{query}")
    assert missing.status_code == 404
    assert "Assignment not found" in missing.text


def test_filter_membership_follows_completion_reopening_addition_and_task_deletion(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={"title": "Lab"}).json()
        url = f"/assignments/{assignment['id']}"
        tasks = [client.post(f"/api{url}/tasks", json={"title": title}).json() for title in ["Read", "Solve"]]

        def listed(mode):
            return assignment_links(client.get(f"/courses/{course['id']}?completion={mode}").text)

        client.patch(f"/api/tasks/{tasks[0]['id']}", json={"is_completed": True})
        assert listed("completed") == []
        client.patch(f"/api/tasks/{tasks[1]['id']}", json={"is_completed": True})
        assert listed("completed") == [url]
        assert listed("incomplete") == []
        client.patch(f"/api/tasks/{tasks[0]['id']}", json={"is_completed": False})
        assert listed("incomplete") == [url]
        assert listed("completed") == []
        client.patch(f"/api/tasks/{tasks[0]['id']}", json={"is_completed": True})
        assert listed("completed") == [url]
        added = client.post(f"/api{url}/tasks", json={"title": "Review"}).json()
        assert listed("incomplete") == [url]
        assert listed("completed") == []
        client.delete(f"/api/tasks/{added['id']}")
        assert listed("completed") == [url]
        client.delete(f"/api/tasks/{tasks[0]['id']}")
        assert listed("completed") == [url]
        client.delete(f"/api/tasks/{tasks[1]['id']}")
        assert listed("completed") == []
        assert listed("incomplete") == [url]
        assert client.get(f"/api{url}").json()["progress"] == {"completed": 0, "total": 0, "percent": 0}


def test_empty_course_and_filter_without_matches_have_distinct_messages_and_forms(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3")) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        url = f"/courses/{course['id']}"
        empty = client.get(url + "?completion=completed")
        assert "No assignments yet." in empty.text
        assignment = client.post(f"/api{url}/assignments", json={"title": "Lab"}).json()
        filtered = client.get(url + "?completion=completed")
        assert "No assignments match this filter." in filtered.text
        assert "No assignments yet." not in filtered.text
        assert assignment_links(filtered.text) == []
        for page in (empty, filtered):
            assert 'id="course-form"' in page.text
            assert 'id="assignment-form"' in page.text
            assert f'<a href="{url}"' in page.text
        assert assignment_links(client.get(url).text) == [f"/assignments/{assignment['id']}"]
