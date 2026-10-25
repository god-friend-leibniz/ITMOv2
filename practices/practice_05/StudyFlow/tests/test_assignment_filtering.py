from datetime import date
import re
import sqlite3
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


@pytest.fixture
def dated_course(tmp_path):
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: date(2026, 10, 25),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        other = client.post("/api/courses", json={"name": "Physics"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        assignments = []
        for title, due_date, total, completed in [
            ("Undated empty", None, 0, 0),
            ("Future", "2026-10-26", 0, 0),
            ("Past partial", "2026-10-24", 2, 1),
            ("Past empty", "2026-10-24", 0, 0),
            ("Earlier done", "2026-10-23", 1, 1),
            ("Today", "2026-10-25", 1, 0),
            ("Undated done", None, 1, 1),
        ]:
            assignment = client.post(listing, json={"title": title, "due_date": due_date}).json()
            for index in range(total):
                task = client.post(f"/api/assignments/{assignment['id']}/tasks", json={"title": f"Step {index}"}).json()
                if index < completed:
                    client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
            assignments.append(assignment)
        client.post(f"/api/courses/{other['id']}/assignments", json={
            "title": "Foreign", "due_date": "2026-01-01",
        })
        yield client, course, assignments


def test_course_html_orders_dates_then_undated_with_id_ties(dated_course):
    client, course, assignments = dated_course
    page = client.get(f"/courses/{course['id']}")
    assert page.status_code == 200
    assert assignment_links(page.text) == [
        f"/assignments/{assignments[index]['id']}" for index in [4, 2, 3, 5, 1, 0, 6]
    ]


@pytest.mark.parametrize("mode, indices", [
    ("incomplete", [2, 3, 5, 1, 0]),
    ("completed", [4, 6]),
])
def test_completion_modes_use_deadline_order_without_changing_progress(dated_course, mode, indices):
    client, course, assignments = dated_course
    listing = f"/api/courses/{course['id']}/assignments"
    before = client.get(listing).json()
    page = client.get(f"/courses/{course['id']}?completion={mode}")
    assert assignment_links(page.text) == [f"/assignments/{assignments[index]['id']}" for index in indices]
    assert client.get(listing).json() == before


@pytest.mark.parametrize("query", ["?completion=all", "?completion=unexpected", "?completion=", "?completion"])
def test_course_fallback_keeps_deadline_order(dated_course, query):
    client, course, assignments = dated_course
    page = client.get(f"/courses/{course['id']}{query}")
    assert page.status_code == 200
    assert page.context["completion"] == "all"
    assert assignment_links(page.text) == [
        f"/assignments/{assignments[index]['id']}" for index in [4, 2, 3, 5, 1, 0, 6]
    ]


def test_overdue_uses_the_computers_local_calendar_date(tmp_path):
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: date(2026, 10, 25),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        past = client.post(listing, json={"title": "Past", "due_date": "2026-10-24"}).json()
        client.post(listing, json={"title": "Future", "due_date": "2026-10-26"})
        page = client.get(f"/courses/{course['id']}?completion=overdue")
        assert page.status_code == 200
        assert page.context["completion"] == "overdue"
        assert assignment_links(page.text) == [f"/assignments/{past['id']}"]


@pytest.mark.parametrize("due_date, total, completed, included", [
    ("2026-10-24", 0, 0, True),
    ("2026-10-24", 1, 0, True),
    ("2026-10-24", 2, 1, True),
    ("2026-10-24", 1, 1, False),
    ("2026-10-25", 0, 0, False),
    ("2026-10-25", 1, 0, False),
    ("2026-10-25", 2, 1, False),
    ("2026-10-25", 1, 1, False),
    ("2026-10-26", 0, 0, False),
    ("2026-10-26", 1, 0, False),
    ("2026-10-26", 2, 1, False),
    ("2026-10-26", 1, 1, False),
    (None, 0, 0, False),
    (None, 1, 0, False),
    (None, 2, 1, False),
    (None, 1, 1, False),
])
def test_overdue_membership_matches_deadline_and_checklist(tmp_path, due_date, total, completed, included):
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: date(2026, 10, 25),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Lab", "due_date": due_date,
        }).json()
        for index in range(total):
            task = client.post(f"/api/assignments/{assignment['id']}/tasks", json={"title": f"Step {index}"}).json()
            if index < completed:
                client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        page = client.get(f"/courses/{course['id']}?completion=overdue")
        assert page.status_code == 200
        expected = [f"/assignments/{assignment['id']}"] if included else []
        assert assignment_links(page.text) == expected


def test_overdue_is_ordered_course_scoped_and_stays_in_all_and_incomplete(dated_course):
    client, course, assignments = dated_course
    url = f"/courses/{course['id']}"
    expected = [f"/assignments/{assignments[index]['id']}" for index in [2, 3]]
    assert assignment_links(client.get(url + "?completion=overdue").text) == expected
    for mode in ("all", "incomplete"):
        links = assignment_links(client.get(url + f"?completion={mode}").text)
        for link in expected:
            assert links.count(link) == 1


@pytest.mark.parametrize("index", [2, 4])
def test_overdue_return_context_does_not_restrict_assignment_access(dated_course, index):
    client, course, assignments = dated_course
    page = client.get(f"/assignments/{assignments[index]['id']}?completion=overdue")
    assert page.status_code == 200
    expected = f"/courses/{course['id']}?completion=overdue"
    assert f'<a href="{expected}">Back to course</a>' in page.text
    assert f'data-course-url="{expected}"' in page.text


def test_each_course_result_uses_one_fresh_local_date_without_restart(tmp_path):
    current_day = date(2026, 10, 25)
    samples = []

    def local_day():
        samples.append(current_day)
        return current_day

    with TestClient(create_app(db_path=tmp_path / "coursework.sqlite3", local_date_provider=local_day)) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        today = client.post(listing, json={"title": "Today", "due_date": "2026-10-25"}).json()
        past = client.post(listing, json={"title": "Past", "due_date": "2026-10-24"}).json()
        url = f"/courses/{course['id']}?completion=overdue"
        assert samples == []
        assert assignment_links(client.get(url).text) == [f"/assignments/{past['id']}"]
        assert samples == [date(2026, 10, 25)]
        current_day = date(2026, 10, 26)
        assert assignment_links(client.get(url).text) == [
            f"/assignments/{past['id']}", f"/assignments/{today['id']}",
        ]
        assert samples == [date(2026, 10, 25), date(2026, 10, 26)]


@pytest.mark.parametrize("days", [
    [date(2026, 10, 31), date(2026, 11, 1)],
    [date(2026, 12, 31), date(2027, 1, 1)],
    [date(2028, 2, 28), date(2028, 2, 29)],
    [date(2028, 2, 29), date(2028, 3, 1)],
])
def test_overdue_calendar_boundaries_include_month_year_and_leap_day(tmp_path, days):
    dates = iter(days)
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: next(dates),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Lab", "due_date": days[0].isoformat(),
        }).json()
        url = f"/courses/{course['id']}?completion=overdue"
        assert assignment_links(client.get(url).text) == []
        assert assignment_links(client.get(url).text) == [f"/assignments/{assignment['id']}"]


def test_overdue_rechecks_saved_checklist_changes_including_empty_and_last_incomplete(tmp_path):
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: date(2026, 10, 25),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        assignment = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Lab", "due_date": "2026-10-24",
        }).json()
        detail = f"/assignments/{assignment['id']}"
        url = f"/courses/{course['id']}?completion=overdue"

        def expect_overdue(progress_text=None):
            page = client.get(url)
            assert assignment_links(page.text) == ([detail] if progress_text else [])
            if progress_text:
                assert progress_text in page.text

        expect_overdue("0 / 0 · 0%")
        task = client.post(f"/api{detail}/tasks", json={"title": "Solve"}).json()
        expect_overdue("0 / 1 · 0%")
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        expect_overdue()
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": False})
        expect_overdue("0 / 1 · 0%")
        client.patch(f"/api/tasks/{task['id']}", json={"is_completed": True})
        added = client.post(f"/api{detail}/tasks", json={"title": "Review"}).json()
        expect_overdue("1 / 2 · 50%")
        client.delete(f"/api/tasks/{added['id']}")
        expect_overdue()
        client.delete(f"/api/tasks/{task['id']}")
        expect_overdue("0 / 0 · 0%")


def test_course_lists_recheck_edited_cleared_and_deleted_deadlines(dated_course):
    client, course, assignments = dated_course
    item = assignments[2]
    edit_url = f"/api/assignments/{item['id']}"
    url = f"/courses/{course['id']}"
    other_past = f"/assignments/{assignments[3]['id']}"
    for due_date, order in [
        ("2026-10-25", [4, 3, 2, 5, 1, 0, 6]),
        ("2026-10-27", [4, 3, 5, 1, 2, 0, 6]),
        (None, [4, 3, 5, 1, 0, 2, 6]),
    ]:
        assert client.patch(edit_url, json={"due_date": due_date}).status_code == 200
        assert assignment_links(client.get(url + "?completion=overdue").text) == [other_past]
        assert assignment_links(client.get(url).text) == [
            f"/assignments/{assignments[index]['id']}" for index in order
        ]
    client.patch(edit_url, json={"due_date": "2026-10-22"})
    assert assignment_links(client.get(url + "?completion=overdue").text) == [
        f"/assignments/{item['id']}", other_past,
    ]
    assert client.delete(edit_url).status_code == 204
    assert assignment_links(client.get(url + "?completion=overdue").text) == [other_past]


@pytest.mark.parametrize("save_after_midnight", [False, True])
def test_create_from_old_page_uses_date_of_the_new_course_result(tmp_path, save_after_midnight):
    current_day = date(2026, 10, 25)
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: current_day,
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        url = f"/courses/{course['id']}?completion=overdue"
        opened_form = client.get(url)
        assert assignment_links(opened_form.text) == []
        assert opened_form.context["has_assignments"] is False
        if save_after_midnight:
            current_day = date(2026, 10, 26)
        response = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Saved lab", "due_date": "2026-10-25",
        })
        assert response.status_code == 201
        saved = response.json()
        assert saved["due_date"] == "2026-10-25"
        assert saved["progress"] == {"completed": 0, "total": 0, "percent": 0}
        current_day = date(2026, 10, 26)
        refreshed = client.get(url)
        assert refreshed.context["completion"] == "overdue"
        assert refreshed.context["has_assignments"] is True
        assert assignment_links(refreshed.text) == [f"/assignments/{saved['id']}"]


@pytest.mark.parametrize("mode", ["completed", "overdue"])
def test_first_hidden_creation_changes_empty_course_to_no_matches(tmp_path, mode):
    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", local_date_provider=lambda: date(2026, 10, 25),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        url = f"/courses/{course['id']}?completion={mode}"
        empty = client.get(url)
        assert empty.context["has_assignments"] is False
        assert "No assignments yet." in empty.text
        saved = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Hidden lab", "due_date": "2026-10-25",
        }).json()
        refreshed = client.get(url)
        assert refreshed.status_code == 200
        assert refreshed.context["has_assignments"] is True
        assert assignment_links(refreshed.text) == []
        assert "No assignments match this filter." in refreshed.text
        assert "No assignments yet." not in refreshed.text
        for page in (empty, refreshed):
            assert 'id="course-form"' in page.text
            assert 'id="assignment-form"' in page.text
        assert client.get(f"/api/courses/{course['id']}/assignments").json() == [saved]


@pytest.mark.parametrize("mode", ["all", "incomplete", "completed", "overdue"])
def test_course_html_does_not_cache_time_dependent_results(dated_course, mode):
    client, course, _ = dated_course
    page = client.get(f"/courses/{course['id']}?completion={mode}")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"


def test_confirmed_creation_survives_busy_course_reads_and_get_only_retry(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    with TestClient(create_app(
        db_path=path, local_date_provider=lambda: date(2026, 10, 25),
    ), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        created = client.post(listing, json={"title": "Saved", "due_date": "2026-10-24"})
        assert created.status_code == 201
        saved = created.json()
        task = client.post(f"/api/assignments/{saved['id']}/tasks", json={"title": "Solve"}).json()
        before = client.get(listing).json()
        url = f"/courses/{course['id']}?completion=overdue"
        with sqlite3.connect(path) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            try:
                for _ in range(2):
                    failed = client.get(url)
                    assert failed.status_code == 503
                    assert failed.json() == {"error": {
                        "code": "DATABASE_BUSY", "message": "The database is busy. Please try again.", "fields": {},
                    }}
            finally:
                lock.rollback()
        refreshed = client.get(url)
        assert refreshed.status_code == 200
        assert assignment_links(refreshed.text) == [f"/assignments/{saved['id']}"]
        assert client.get(listing).json() == before
        assert client.get(f"/api/assignments/{saved['id']}/tasks").json() == [task]


def test_confirmed_creation_survives_unexpected_read_failure_and_recovery(tmp_path):
    path = tmp_path / "coursework.sqlite3"
    backup = tmp_path / "saved.sqlite3"
    with TestClient(create_app(
        db_path=path, local_date_provider=lambda: date(2026, 10, 25),
    ), raise_server_exceptions=False) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        listing = f"/api/courses/{course['id']}/assignments"
        created = client.post(listing, json={"title": "Saved", "due_date": "2026-10-24"})
        assert created.status_code == 201
        saved = created.json()
        before = client.get(listing).json()
        url = f"/courses/{course['id']}?completion=overdue"
        path.rename(backup)
        path.mkdir()
        try:
            failed = client.get(url)
            assert failed.status_code == 500
            assert failed.json() == {"error": {
                "code": "INTERNAL_ERROR", "message": "The request could not be completed.", "fields": {},
            }}
        finally:
            path.rmdir()
            backup.rename(path)
        refreshed = client.get(url)
        assert refreshed.status_code == 200
        assert assignment_links(refreshed.text) == [f"/assignments/{saved['id']}"]
        assert client.get(listing).json() == before


def test_overdue_preserves_missing_pages_and_rejected_creation(dated_course):
    client, course, _ = dated_course
    listing = f"/api/courses/{course['id']}/assignments"
    before = client.get(listing).json()
    rejected = client.post(listing, json={"title": "Invalid date", "due_date": "2026-02-29"})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "due_date" in rejected.json()["error"]["fields"]
    assert client.get(listing).json() == before
    for path, message in [("/courses/999", "Course not found"), ("/assignments/999", "Assignment not found")]:
        missing = client.get(path + "?completion=overdue")
        assert missing.status_code == 404
        assert message in missing.text
        assert "No assignments match this filter." not in missing.text


def test_html_modes_leave_json_order_fields_headers_and_saved_resources_unchanged(dated_course):
    client, course, assignments = dated_course
    listing = f"/api/courses/{course['id']}/assignments"
    client.patch(f"/api/assignments/{assignments[2]['id']}", json={
        "repository": {"owner": "OctoCat", "repo": "Hello-World"},
    })
    before = client.get(listing).json()
    tasks_before = {
        item["id"]: client.get(f"/api/assignments/{item['id']}/tasks").json() for item in assignments
    }
    assert [item["id"] for item in before] == [item["id"] for item in assignments]
    assert before[2]["repository"] == {"owner": "octocat", "repo": "hello-world"}
    for item in before:
        assert set(item) == {"id", "course_id", "title", "description", "due_date", "repository", "progress"}
    for mode in ("all", "incomplete", "completed", "overdue", "unexpected", ""):
        assert client.get(f"/courses/{course['id']}?completion={mode}").status_code == 200
        response = client.get(listing + f"?completion={mode}")
        assert response.status_code == 200
        assert response.json() == before
        assert "cache-control" not in response.headers
    assert client.get(listing).json() == before
    for item in before:
        assert client.get(f"/api/assignments/{item['id']}").json() == item
        assert client.get(f"/api/assignments/{item['id']}/tasks").json() == tasks_before[item["id"]]


def test_course_reads_with_repository_reference_work_without_summary_service(tmp_path):
    async def unavailable_summary(owner, repo):
        raise AssertionError("Coursework reads must not request a repository summary.")

    with TestClient(create_app(
        db_path=tmp_path / "coursework.sqlite3", summary_reader=unavailable_summary,
        local_date_provider=lambda: date(2026, 10, 25),
    )) as client:
        course = client.post("/api/courses", json={"name": "Algorithms"}).json()
        created = client.post(f"/api/courses/{course['id']}/assignments", json={
            "title": "Lab", "due_date": "2026-10-24",
            "repository": {"owner": "octocat", "repo": "Hello-World"},
        })
        assert created.status_code == 201
        saved = created.json()
        page = client.get(f"/courses/{course['id']}?completion=overdue")
        assert page.status_code == 200
        assert assignment_links(page.text) == [f"/assignments/{saved['id']}"]
        assert client.get(f"/assignments/{saved['id']}?completion=overdue").status_code == 200
        assert client.get(f"/api/assignments/{saved['id']}").json() == saved
