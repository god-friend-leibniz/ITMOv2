import socket
from functools import partial
from pathlib import Path
import sys
import threading
import time

from playwright.sync_api import expect
import pytest
import uvicorn
from mcp.client.stdio import StdioServerParameters

from studyflow.github_mcp_client import get_repository_summary
from studyflow.web import create_app


@pytest.fixture
def course_server(tmp_path, request):
    options = {}
    if getattr(request, "param", None) == "mcp":
        options["summary_reader"] = partial(get_repository_summary, server_parameters=StdioServerParameters(
            command=sys.executable, args=[str(Path(__file__).parent / "fixtures/github_server.py")],
        ))
    app = create_app(db_path=tmp_path / "browser.sqlite3", **options)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    pytest.fail("Course server did not start")
                time.sleep(0.01)
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=5)


@pytest.mark.browser
@pytest.mark.parametrize("course_server", ["mcp"], indirect=True)
def test_student_explicitly_loads_and_refreshes_repository_summary_without_persisting_it(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
    }).json()
    requests = []
    page.route(f"{course_server}/api/assignments/{assignment['id']}/repository-summary", lambda route: (requests.append(route.request), route.continue_()))
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    load = page.get_by_role("button", name="Load repository summary", exact=True)
    expect(load).to_be_visible(timeout=2000)
    assert requests == []
    load.click()
    expect(page.get_by_text("Coursework examples", exact=True)).to_be_visible()
    expect(page.get_by_text("Default branch: main", exact=True)).to_be_visible()
    expect(page.get_by_text("Primary languages: Python", exact=True)).to_be_visible()
    expect(page.get_by_text("Last push: 2026-01-02T03:04:05Z", exact=True)).to_be_visible()
    expect(page.locator("#repository-summary")).to_contain_text("Fetched:")
    refresh = page.get_by_role("button", name="Refresh repository summary", exact=True)
    refresh.click()
    expect(refresh).to_be_enabled()
    assert len(requests) == 2
    page.reload()
    expect(load).to_be_visible()
    expect(page.get_by_text("Coursework examples", exact=True)).to_have_count(0)
    assert len(requests) == 2
    assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}").json() == assignment


@pytest.mark.browser
@pytest.mark.parametrize("course_server", ["mcp"], indirect=True)
def test_missing_repository_panel_preserves_coursework_and_allows_reference_correction(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "missing"},
    }).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_label("Assignment description", exact=True).fill("Unsaved notes")
    page.get_by_role("button", name="Load repository summary", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("Repository not found or unavailable.", timeout=2000)
    expect(page.get_by_role("alert")).to_contain_text("Check the saved reference")
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Unsaved notes")
    expect(page.get_by_role("button", name="Load repository summary", exact=True)).to_be_enabled()
    assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}").json() == assignment
    page.get_by_label("GitHub repository name", exact=True).fill("hello-world")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    page.get_by_role("button", name="Load repository summary", exact=True).click()
    expect(page.get_by_text("Coursework examples", exact=True)).to_be_visible()


@pytest.mark.browser
@pytest.mark.parametrize("course_server", ["mcp"], indirect=True)
@pytest.mark.parametrize("failure", ["network", "rate_limit"])
def test_failed_refresh_clears_old_summary_preserves_input_and_allows_retry(page, course_server, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
    }).json()
    url = f"{course_server}/api/assignments/{assignment['id']}"
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_role("button", name="Load repository summary", exact=True).click()
    expect(page.get_by_text("Coursework examples", exact=True)).to_be_visible()
    page.get_by_label("Assignment description", exact=True).fill("Unsaved notes")
    requests = []
    page.route(url + "/repository-summary", lambda route: requests.append(route))
    button = page.locator("#load-repository")
    button.click()
    try:
        expect(button).to_be_disabled()
        expect(page.get_by_role("status")).to_have_text("Loading repository summary…")
        button.evaluate("element => element.click()")
        assert len(requests) == 1
    finally:
        for request in requests:
            if failure == "network":
                request.abort()
                message = "Could not load repository information. Please try again."
            else:
                message = "GitHub rate limit reached. Please retry later. Retry after 8 seconds."
                request.fulfill(status=503, headers={"Retry-After": "8"}, json={"error": {
                    "code": "RATE_LIMITED", "message": "GitHub rate limit reached. Please retry later.", "fields": {},
                }})
    expect(page.get_by_role("alert")).to_have_text(message, timeout=2000)
    expect(page.get_by_text("Coursework examples", exact=True)).to_have_count(0)
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Unsaved notes")
    expect(button).to_be_enabled()
    assert page.request.get(url).json() == assignment
    page.unroute(url + "/repository-summary")
    button.click()
    expect(page.get_by_text("Coursework examples", exact=True)).to_be_visible()


@pytest.mark.browser
@pytest.mark.parametrize("status", [200, 404])
def test_repository_response_is_discarded_after_reference_changes_while_pending(page, course_server, status):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
    }).json()
    url = f"{course_server}/api/assignments/{assignment['id']}/repository-summary"
    requests = []
    page.route(url, lambda route: requests.append(route))
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    button = page.locator("#load-repository")
    button.click()
    try:
        expect(button).to_be_disabled()
        page.get_by_label("GitHub repository name", exact=True).fill("lab_2")
        expect(page.get_by_role("status")).to_have_text("Save reference changes before loading a summary.", timeout=2000)
    finally:
        for request in requests:
            payload = {
                "owner": "octocat", "name": "Hello-World", "url": "https://github.com/octocat/Hello-World",
                "description": "Outdated response", "default_branch": "main", "primary_languages": [],
                "last_push_at": None, "fetched_at": "2026-01-02T03:04:05Z",
            } if status == 200 else {"error": {"code": "REPOSITORY_NOT_FOUND", "message": "Outdated error", "fields": {}}}
            request.fulfill(status=status, json=payload)
    page.get_by_label("GitHub repository name", exact=True).fill("hello-world")
    expect(button).to_be_enabled()
    expect(page.get_by_text("Outdated response", exact=True)).to_have_count(0)
    expect(page.get_by_role("alert")).to_have_count(0)
    expect(page.get_by_role("status")).to_have_text("Repository summary has not been loaded.")


@pytest.mark.browser
@pytest.mark.parametrize("description", [None, "<img src=x onerror=alert(1)> & coursework"])
def test_repository_panel_renders_plain_text_and_discards_loaded_data_on_replace_and_remove(page, course_server, description):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
    }).json()
    url = f"{course_server}/api/assignments/{assignment['id']}/repository-summary"
    page.route(url, lambda route: route.fulfill(json={
        "owner": "octocat", "name": "Hello-World", "url": "https://github.com/octocat/Hello-World",
        "description": description, "default_branch": None, "primary_languages": [],
        "last_push_at": None, "fetched_at": "2026-01-02T03:04:05Z",
    }))
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_role("button", name="Load repository summary", exact=True).click()
    expect(page.get_by_text(description if description is not None else "No description.", exact=True)).to_be_visible()
    expect(page.locator("#repository-summary img")).to_have_count(0)
    expect(page.get_by_text("Default branch: Unavailable", exact=True)).to_be_visible()
    expect(page.get_by_text("Primary languages: None", exact=True)).to_be_visible()
    expect(page.get_by_text("Last push: Unavailable", exact=True)).to_be_visible()
    page.get_by_label("GitHub repository name", exact=True).fill("lab_2")
    expect(page.locator("#repository-summary")).to_be_hidden()
    expect(page.get_by_role("button", name="Load repository summary", exact=True)).to_be_disabled()
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator("#repository-summary")).to_be_hidden()
    expect(page.get_by_role("button", name="Load repository summary", exact=True)).to_be_enabled()
    page.get_by_label("GitHub owner", exact=True).fill("")
    page.get_by_label("GitHub repository name", exact=True).fill("")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("button", name="Load repository summary", exact=True)).to_have_count(0)
    expect(page.locator("#repository-panel")).to_have_count(0)


@pytest.mark.browser
def test_assignment_detail_shows_saved_repository_link(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "OctoCat", "repo": "Hello-World"},
    }).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    link = page.get_by_role("link", name="octocat/hello-world", exact=True)
    expect(link).to_have_attribute("href", "https://github.com/octocat/hello-world", timeout=2000)
    page.reload()
    expect(link).to_be_visible()


@pytest.mark.browser
def test_student_can_create_assignment_with_repository_reference_in_browser(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    page.get_by_label("Assignment title", exact=True).fill("Problem set")
    page.get_by_label("GitHub owner", exact=True).fill("  OctoCat  ", timeout=2000)
    page.get_by_label("GitHub repository name", exact=True).fill("  Hello-World.git  ")
    page.get_by_role("button", name="Add assignment", exact=True).click()
    page.get_by_role("link", name="Problem set", exact=True).click()
    expect(page.get_by_role("link", name="octocat/hello-world.git", exact=True)).to_have_attribute("href", "https://github.com/octocat/hello-world.git")
    expect(page.get_by_label("GitHub owner", exact=True)).to_have_value("octocat")
    expect(page.get_by_label("GitHub repository name", exact=True)).to_have_value("hello-world.git")
    page.reload()
    expect(page.get_by_label("GitHub repository name", exact=True)).to_have_value("hello-world.git")


@pytest.mark.browser
@pytest.mark.parametrize("initial_reference", [None, {"owner": "octocat", "repo": "hello-world"}])
def test_student_can_attach_replace_and_clear_reference_without_changing_progress(page, course_server, initial_reference):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "description": "Keep notes", "due_date": "2028-02-29", "repository": initial_reference,
    }).json()
    url = f"{course_server}/api/assignments/{assignment['id']}"
    task = page.request.post(url + "/tasks", data={"title": "Read chapter"}).json()
    page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    owner = page.get_by_label("GitHub owner", exact=True)
    repo = page.get_by_label("GitHub repository name", exact=True)
    expect(owner).to_have_value(initial_reference["owner"] if initial_reference else "")
    expect(repo).to_have_value(initial_reference["repo"] if initial_reference else "")
    owner.fill("Student-1")
    repo.fill("Lab_2")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("link", name="student-1/lab_2", exact=True)).to_have_attribute("href", "https://github.com/student-1/lab_2")
    expect(page.get_by_role("link", name="octocat/hello-world", exact=True)).to_have_count(0)
    page.get_by_label("Assignment description", exact=True).fill("Updated notes")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Updated notes")
    expect(owner).to_have_value("student-1")
    expect(repo).to_have_value("lab_2")
    owner.fill("")
    repo.fill("")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_text("No repository linked.", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="student-1/lab_2", exact=True)).to_have_count(0)
    page.reload()
    expect(owner).to_have_value("")
    expect(repo).to_have_value("")
    expect(page.get_by_text("1 / 1 · 100%", exact=True)).to_be_visible()
    assert page.request.get(url).json() == {
        **assignment, "description": "Updated notes", "repository": None,
        "progress": {"completed": 1, "total": 1, "percent": 100},
    }
    assert page.request.get(url + "/tasks").json() == [{**task, "is_completed": True}]


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["create", "edit"])
@pytest.mark.parametrize("owner_value, repo_value, message", [
    ("bad--owner", "Lab_2", "GitHub owner must contain"),
    ("  OctoCat  ", "", "Repository name must contain"),
])
def test_repository_form_validation_preserves_input_and_saved_assignment(page, course_server, operation, owner_value, repo_value, message):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    assignment = page.request.post(listing, data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
    }).json()
    path = f"courses/{course['id']}" if operation == "create" else f"assignments/{assignment['id']}"
    page.goto(f"{course_server}/{path}")
    page.get_by_label("Assignment title", exact=True).fill("Unsaved title")
    page.get_by_label("GitHub owner", exact=True).fill(owner_value)
    page.get_by_label("GitHub repository name", exact=True).fill(repo_value)
    button = "Add assignment" if operation == "create" else "Save changes"
    page.get_by_role("button", name=button, exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text(message)
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("Unsaved title")
    expect(page.get_by_label("GitHub owner", exact=True)).to_have_value(owner_value)
    expect(page.get_by_label("GitHub repository name", exact=True)).to_have_value(repo_value)
    expect(page.get_by_role("button", name=button, exact=True)).to_be_enabled()
    assert page.request.get(listing).json() == [assignment]


@pytest.mark.browser
@pytest.mark.parametrize("failure", ["network", "database_busy"])
def test_failed_reference_save_preserves_link_and_input_and_allows_retry(page, course_server, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set", "repository": {"owner": "octocat", "repo": "hello-world"},
    }).json()
    url = f"{course_server}/api/assignments/{assignment['id']}"
    task = page.request.post(url + "/tasks", data={"title": "Read chapter"}).json()
    page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    saved = page.request.get(url).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_label("GitHub owner", exact=True).fill("Student-1")
    page.get_by_label("GitHub repository name", exact=True).fill("Lab_2")
    requests = []
    page.route(url, lambda route: requests.append(route))
    save = page.get_by_role("button", name="Save changes", exact=True)
    save.click()
    try:
        expect(save).to_be_disabled()
        expect(page.get_by_role("button", name="Delete assignment", exact=True)).to_be_disabled()
        assert len(requests) == 1
        assert requests[0].request.method == "PATCH"
    finally:
        for request in requests:
            if failure == "network":
                request.abort()
                message = "Could not save the assignment. Please try again."
            else:
                message = "The database is busy. Please try again."
                request.fulfill(status=503, json={"error": {"code": "DATABASE_BUSY", "message": message, "fields": {}}})
    expect(page.get_by_role("alert")).to_have_text(message)
    expect(page.get_by_role("link", name="octocat/hello-world", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="student-1/lab_2", exact=True)).to_have_count(0)
    expect(page.get_by_label("GitHub owner", exact=True)).to_have_value("Student-1")
    expect(page.get_by_label("GitHub repository name", exact=True)).to_have_value("Lab_2")
    expect(save).to_be_enabled()
    expect(page.get_by_role("button", name="Delete assignment", exact=True)).to_be_enabled()
    assert page.request.get(url).json() == saved
    page.unroute(url)
    save.click()
    expect(page.get_by_role("link", name="student-1/lab_2", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="octocat/hello-world", exact=True)).to_have_count(0)
    expect(page.get_by_text("1 / 1 · 100%", exact=True)).to_be_visible()


@pytest.mark.browser
def test_student_can_add_task_and_see_checklist_progress_after_reload(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_label("Task title", exact=True).fill("Read chapter", timeout=2000)
    page.get_by_role("button", name="Add task", exact=True).click()
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).not_to_be_checked()
    expect(page.get_by_text("0 / 1 · 0%", exact=True)).to_be_visible()
    expect(page.get_by_text("No tasks", exact=True)).to_have_count(0)
    page.reload()
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).not_to_be_checked()
    expect(page.get_by_text("0 / 1 · 0%", exact=True)).to_be_visible()


@pytest.mark.browser
def test_student_can_complete_and_reopen_tasks_and_see_progress_on_course_page(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    for title in ["Read chapter", "Solve exercises", "Check answers"]:
        page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": title})
    page.goto(f"{course_server}/courses/{course['id']}")
    page.get_by_role("link", name="Problem set", exact=True).click()
    page.get_by_role("checkbox", name="Read chapter", exact=True).focus()
    page.keyboard.press("Space")
    expect(page.get_by_text("1 / 3 · 33%", exact=True)).to_be_visible(timeout=2000)
    page.get_by_role("checkbox", name="Solve exercises", exact=True).check()
    expect(page.get_by_text("2 / 3 · 66%", exact=True)).to_be_visible()
    page.get_by_role("checkbox", name="Check answers", exact=True).check()
    expect(page.get_by_text("3 / 3 · 100%", exact=True)).to_be_visible()
    page.get_by_role("checkbox", name="Read chapter", exact=True).uncheck()
    expect(page.get_by_text("2 / 3 · 66%", exact=True)).to_be_visible()
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page.get_by_text("2 / 3 · 66%", exact=True)).to_be_visible()
    expect(page.get_by_text("No tasks", exact=True)).to_have_count(0)
    page.get_by_role("link", name="Problem set", exact=True).click()
    page.reload()
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).not_to_be_checked()
    expect(page.get_by_role("checkbox", name="Check answers", exact=True)).to_be_checked()


@pytest.mark.browser
def test_student_can_rename_completed_task_without_reopening_it(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": "Read chapter"}).json()
    page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_label("Rename Read chapter", exact=True).fill("  Read two chapters  ", timeout=2000)
    page.get_by_role("button", name="Rename task", exact=True).click()
    expect(page.get_by_role("checkbox", name="Read two chapters", exact=True)).to_be_checked()
    expect(page.get_by_text("1 / 1 · 100%", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_label("Rename Read two chapters", exact=True)).to_have_value("Read two chapters")


@pytest.mark.browser
def test_task_deletion_requires_confirmation_and_last_deletion_shows_empty_progress(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    listing = f"{course_server}/api/assignments/{assignment['id']}/tasks"
    task = page.request.post(listing, data={"title": "Read chapter"}).json()
    page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    messages = []

    def cancel(dialog):
        messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", cancel)
    page.get_by_role("button", name="Delete task Read chapter", exact=True).click(timeout=2000)
    assert "Read chapter" in messages[0]
    assert "cannot be undone" in messages[0]
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).to_be_checked()
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete task Read chapter", exact=True).click()
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).to_have_count(0)
    expect(page.get_by_text("0 / 0 · 0%", exact=True)).to_be_visible()
    expect(page.get_by_text("No tasks", exact=True)).to_be_visible()
    assert page.request.get(listing).json() == []
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page.get_by_text("0 / 0 · 0%", exact=True)).to_be_visible()
    expect(page.get_by_text("No tasks", exact=True)).to_be_visible()


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["create", "rename"])
def test_task_form_preserves_invalid_input_and_displays_field_error(page, course_server, operation):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    listing = f"{course_server}/api/assignments/{assignment['id']}/tasks"
    task = page.request.post(listing, data={"title": "Read chapter"}).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    field = "Task title" if operation == "create" else "Rename Read chapter"
    button = "Add task" if operation == "create" else "Rename task"
    page.get_by_label(field, exact=True).fill("   ")
    page.get_by_role("button", name=button, exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("Task title must contain 1 to 200 characters.")
    expect(page.get_by_label(field, exact=True)).to_have_value("   ")
    assert page.request.get(listing).json() == [task]


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["create", "rename"])
def test_task_form_prevents_repeat_mutations_and_recovers_from_network_failure(page, course_server, operation):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    listing = f"{course_server}/api/assignments/{assignment['id']}/tasks"
    task = page.request.post(listing, data={"title": "Read chapter"}).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    field = "Task title" if operation == "create" else "Rename Read chapter"
    button_name = "Add task" if operation == "create" else "Rename task"
    url = listing if operation == "create" else f"{course_server}/api/tasks/{task['id']}"
    page.get_by_label(field, exact=True).fill("Check answers")
    requests = []
    page.route(url, lambda route: requests.append(route))
    save = page.get_by_role("button", name=button_name, exact=True)
    save.click()
    expect(save).to_be_disabled()
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Delete task Read chapter", exact=True)).to_be_disabled()
    assert len(requests) == 1
    requests[0].abort()
    expect(page.get_by_role("alert")).to_have_text("Could not save the task. Please try again.")
    expect(page.get_by_label(field, exact=True)).to_have_value("Check answers")
    expect(save).to_be_enabled()
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).to_be_enabled()
    assert page.request.get(listing).json() == [task]
    page.unroute(url)
    save.click()
    expect(page.get_by_role("checkbox", name="Check answers", exact=True)).to_be_visible()


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["complete", "reopen", "delete"])
@pytest.mark.parametrize("failure", ["network", "database_busy"])
def test_failed_checklist_mutation_restores_saved_state_and_allows_retry(page, course_server, operation, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    listing = f"{course_server}/api/assignments/{assignment['id']}/tasks"
    task = page.request.post(listing, data={"title": "Read chapter"}).json()
    url = f"{course_server}/api/tasks/{task['id']}"
    if operation == "reopen":
        task = page.request.patch(url, data={"is_completed": True}).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_label("Rename Read chapter", exact=True).fill("Unsaved title")
    requests = []
    page.route(url, lambda route: requests.append(route))
    checkbox = page.get_by_role("checkbox", name="Read chapter", exact=True)
    delete = page.get_by_role("button", name="Delete task Read chapter", exact=True)
    if operation == "delete":
        page.once("dialog", lambda dialog: dialog.accept())
        delete.click()
    else:
        checkbox.click()
    try:
        expect(checkbox).to_be_disabled()
        expect(delete).to_be_disabled()
        expect(page.get_by_role("button", name="Add task", exact=True)).to_be_disabled()
        assert len(requests) == 1
        assert requests[0].request.method == ("DELETE" if operation == "delete" else "PATCH")
    finally:
        # Release the intercepted request even when a pending-control assertion fails.
        for request in requests:
            if failure == "network":
                request.abort()
                verb = "delete" if operation == "delete" else "save"
                message = f"Could not {verb} the task. Please try again."
            else:
                message = "The database is busy. Please try again."
                request.fulfill(status=503, json={"error": {"code": "DATABASE_BUSY", "message": message, "fields": {}}})
    expect(page.get_by_role("alert")).to_have_text(message)
    if task["is_completed"]:
        expect(checkbox).to_be_checked()
    else:
        expect(checkbox).not_to_be_checked()
    expect(page.get_by_label("Rename Read chapter", exact=True)).to_have_value("Unsaved title")
    expect(checkbox).to_be_enabled()
    expect(delete).to_be_enabled()
    assert page.request.get(listing).json() == [task]
    page.unroute(url)
    if operation == "delete":
        page.once("dialog", lambda dialog: dialog.accept())
        delete.click()
        expect(page.get_by_text("No tasks", exact=True)).to_be_visible()
    else:
        checkbox.click()
        progress = "1 / 1 · 100%" if operation == "complete" else "0 / 1 · 0%"
        expect(page.get_by_text(progress, exact=True)).to_be_visible()


@pytest.mark.browser
def test_student_can_create_assignment_and_see_empty_checklist_progress(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    expect(page.get_by_text("No assignments yet.", exact=True)).to_be_visible(timeout=2000)
    page.get_by_label("Assignment title", exact=True).fill("Problem set 1")
    page.get_by_label("Assignment description", exact=True).fill("Sorting exercises")
    page.get_by_role("button", name="Add assignment", exact=True).click()

    expect(page.get_by_role("heading", name="Problem set 1", exact=True)).to_be_visible()
    expect(page.get_by_text("0 / 0 · 0%", exact=True)).to_be_visible()
    expect(page.get_by_text("No tasks", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_role("heading", name="Problem set 1", exact=True)).to_be_visible()


@pytest.mark.browser
def test_student_can_create_assignment_with_visible_due_date(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    page.get_by_label("Assignment title", exact=True).fill("Problem set 1")
    page.get_by_label("Due date", exact=True).fill("2028-02-29", timeout=2000)
    page.get_by_role("button", name="Add assignment", exact=True).click()
    expect(page.get_by_text("Due 2028-02-29", exact=True)).to_be_visible()
    assert page.request.get(f"{course_server}/api/courses/{course['id']}/assignments").json()[0]["due_date"] == "2028-02-29"


@pytest.mark.browser
def test_student_can_open_assignment_details_and_return_to_course(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set 1", "description": "Sorting exercises", "due_date": "2028-02-29",
    }).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    page.get_by_role("link", name="Problem set 1", exact=True).click(timeout=2000)
    expect(page).to_have_url(f"{course_server}/assignments/{assignment['id']}")
    expect(page.get_by_role("heading", name="Problem set 1", exact=True)).to_be_visible()
    expect(page.get_by_role("article").get_by_text("Sorting exercises", exact=True)).to_be_visible()
    expect(page.get_by_text("Due 2028-02-29", exact=True)).to_be_visible()
    expect(page.get_by_text("0 / 0 · 0%", exact=True)).to_be_visible()
    expect(page.get_by_text("No tasks", exact=True)).to_be_visible()
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")


@pytest.mark.browser
def test_student_can_edit_assignment_and_clear_optional_fields(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Problem set 1", "description": "Sorting exercises", "due_date": "2028-02-29",
    }).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("Problem set 1", timeout=2000)
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Sorting exercises")
    expect(page.get_by_label("Due date", exact=True)).to_have_value("2028-02-29")
    page.get_by_label("Assignment title", exact=True).fill("  Advanced sorting  ")
    page.get_by_label("Assignment description", exact=True).fill("")
    page.get_by_label("Due date", exact=True).fill("")
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("heading", name="Advanced sorting", exact=True)).to_be_visible()
    expect(page.get_by_text("Due 2028-02-29", exact=True)).to_have_count(0)
    page.reload()
    expect(page.get_by_label("Due date", exact=True)).to_have_value("")
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page.get_by_role("link", name="Advanced sorting", exact=True)).to_be_visible()


@pytest.mark.browser
def test_assignment_deletion_requires_confirmation_and_returns_to_owning_course(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    assignment = page.request.post(listing, data={"title": "Problem set 1"}).json()
    other = page.request.post(listing, data={"title": "Problem set 2"}).json()
    task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": "Read chapter"}).json()
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    messages = []

    def cancel(dialog):
        messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", cancel)
    page.get_by_role("button", name="Delete assignment", exact=True).click(timeout=2000)
    assert "Problem set 1" in messages[0]
    assert "tasks" in messages[0]
    assert "cannot be undone" in messages[0]
    assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}").status == 200
    expect(page.get_by_role("checkbox", name="Read chapter", exact=True)).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete assignment", exact=True).click()
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")
    expect(page.get_by_role("link", name="Problem set 1", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="Problem set 2", exact=True)).to_be_visible()
    assert page.request.get(listing).json() == [other]
    assert page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True}).status == 404


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["create", "edit"])
def test_assignment_form_preserves_input_and_shows_validation_errors(page, course_server, operation):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    if operation == "edit":
        assignment = page.request.post(listing, data={"title": "Problem set"}).json()
        page.goto(f"{course_server}/assignments/{assignment['id']}")
        button = "Save changes"
    else:
        page.goto(f"{course_server}/courses/{course['id']}")
        button = "Add assignment"
    page.get_by_label("Assignment title", exact=True).fill("   ")
    page.get_by_label("Assignment description", exact=True).fill("Keep these notes")
    page.get_by_label("Due date", exact=True).fill("2028-02-29")
    page.get_by_role("button", name=button, exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("Assignment title must contain 1 to 200 characters.")
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Keep these notes")
    expect(page.get_by_label("Due date", exact=True)).to_have_value("2028-02-29")
    if operation == "edit":
        assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}").json() == assignment
    else:
        assert page.request.get(listing).json() == []


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["create", "edit"])
def test_assignment_form_blocks_repeat_mutations_and_recovers_from_network_failure(page, course_server, operation):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    if operation == "edit":
        assignment = page.request.post(listing, data={"title": "Problem set"}).json()
        url = f"{course_server}/api/assignments/{assignment['id']}"
        page.goto(f"{course_server}/assignments/{assignment['id']}")
        button = "Save changes"
    else:
        url = listing
        page.goto(f"{course_server}/courses/{course['id']}")
        button = "Add assignment"
    page.get_by_label("Assignment title", exact=True).fill("Advanced sorting")
    requests = []
    page.route(url, lambda route: requests.append(route))
    save = page.get_by_role("button", name=button, exact=True)
    save.click()
    expect(save).to_be_disabled()
    if operation == "edit":
        expect(page.get_by_role("button", name="Delete assignment", exact=True)).to_be_disabled()
    assert len(requests) == 1
    requests[0].abort()

    expect(page.get_by_role("alert")).to_have_text("Could not save the assignment. Please try again.")
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("Advanced sorting")
    expect(save).to_be_enabled()
    if operation == "edit":
        expect(page.get_by_role("button", name="Delete assignment", exact=True)).to_be_enabled()
        assert page.request.get(url).json() == assignment
    else:
        assert page.request.get(listing).json() == []


@pytest.mark.browser
@pytest.mark.parametrize("failure", ["network", "database_busy"])
def test_failed_assignment_deletion_preserves_input_and_allows_retry(page, course_server, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    url = f"{course_server}/api/assignments/{assignment['id']}"
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_label("Assignment description", exact=True).fill("Unsaved notes")
    requests = []
    page.route(url, lambda route: requests.append(route))
    page.once("dialog", lambda dialog: dialog.accept())
    delete = page.get_by_role("button", name="Delete assignment", exact=True)
    save = page.get_by_role("button", name="Save changes", exact=True)
    delete.click()
    expect(delete).to_be_disabled()
    expect(save).to_be_disabled()
    assert len(requests) == 1
    assert requests[0].request.method == "DELETE"
    if failure == "network":
        requests[0].abort()
        message = "Could not delete the assignment. Please try again."
    else:
        message = "The database is busy. Please try again."
        requests[0].fulfill(status=503, json={"error": {"code": "DATABASE_BUSY", "message": message, "fields": {}}})
    expect(page.get_by_role("alert")).to_have_text(message)
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Unsaved notes")
    expect(delete).to_be_enabled()
    expect(save).to_be_enabled()
    assert page.request.get(url).json() == assignment


@pytest.mark.browser
def test_student_can_open_course_details_from_list(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={
        "name": "Algorithms", "description": "Weekly problem sets",
    }).json()
    page.goto(course_server)
    page.get_by_role("link", name="Algorithms", exact=True).click(timeout=2000)

    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")
    expect(page.get_by_role("heading", name="Algorithms", exact=True)).to_be_visible()
    expect(page.get_by_role("article").get_by_text("Weekly problem sets", exact=True)).to_be_visible()
    page.get_by_role("link", name="All courses", exact=True).click()
    expect(page).to_have_url(f"{course_server}/")


@pytest.mark.browser
def test_student_can_edit_course_and_clear_description(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={
        "name": "Algorithms", "description": "Weekly problem sets",
    }).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    expect(page.get_by_label("Course name", exact=True)).to_have_value("Algorithms", timeout=2000)
    expect(page.get_by_label("Description", exact=True)).to_have_value("Weekly problem sets")
    page.get_by_label("Course name", exact=True).fill("  Advanced algorithms  ")
    page.get_by_label("Description", exact=True).fill("")
    page.get_by_role("button", name="Save changes", exact=True).click()

    expect(page.get_by_role("heading", name="Advanced algorithms", exact=True)).to_be_visible()
    expect(page.get_by_text("Weekly problem sets", exact=True)).to_have_count(0)
    page.reload()
    expect(page.get_by_label("Course name", exact=True)).to_have_value("Advanced algorithms")
    expect(page.get_by_label("Description", exact=True)).to_have_value("")
    page.get_by_role("link", name="All courses", exact=True).click()
    expect(page.get_by_role("link", name="Advanced algorithms", exact=True)).to_be_visible()


@pytest.mark.browser
def test_deleting_course_requires_confirmation_and_returns_to_list(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    other = page.request.post(f"{course_server}/api/courses", data={"name": "Physics"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Problem set"}).json()
    task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": "Read chapter"}).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    messages = []

    def cancel(dialog):
        messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", cancel)
    page.get_by_role("button", name="Delete course", exact=True).click(timeout=2000)
    assert len(messages) == 1
    assert "Algorithms" in messages[0]
    assert "assignments and tasks" in messages[0]
    assert "cannot be undone" in messages[0]
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")
    assert page.request.get(f"{course_server}/api/courses/{course['id']}").status == 200
    assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}").status == 200
    assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}/tasks").json() == [task]

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete course", exact=True).click()
    expect(page).to_have_url(f"{course_server}/")
    assert page.request.get(f"{course_server}/api/assignments/{assignment['id']}").status == 404
    assert page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True}).status == 404
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    expect(page.get_by_role("heading", name="Assignment not found", exact=True)).to_be_visible()
    page.get_by_role("link", name="All courses", exact=True).click()
    expect(page.get_by_role("link", name="Algorithms", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="Physics", exact=True)).to_be_visible()
    assert page.request.get(f"{course_server}/api/courses").json() == [other]


@pytest.mark.browser
@pytest.mark.parametrize("failure", ["network", "busy"])
def test_failed_deletion_preserves_form_and_allows_retry(page, course_server, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    page.get_by_label("Description", exact=True).fill("Unsaved notes")
    requests = []
    page.route(f"**/api/courses/{course['id']}", lambda route: requests.append(route))
    page.once("dialog", lambda dialog: dialog.accept())
    delete = page.get_by_role("button", name="Delete course", exact=True)
    save = page.get_by_role("button", name="Save changes", exact=True)
    delete.click()

    expect(delete).to_be_disabled()
    expect(save).to_be_disabled()
    assert len(requests) == 1
    assert requests[0].request.method == "DELETE"
    if failure == "network":
        requests[0].abort()
        message = "Could not delete the course. Please try again."
    else:
        message = "The database is busy. Please try again."
        requests[0].fulfill(status=503, json={"error": {"code": "DATABASE_BUSY", "message": message, "fields": {}}})
    expect(page.get_by_role("alert")).to_have_text(message)
    expect(page.get_by_label("Description", exact=True)).to_have_value("Unsaved notes")
    expect(delete).to_be_enabled()
    expect(save).to_be_enabled()
    assert page.request.get(f"{course_server}/api/courses/{course['id']}").json() == course


@pytest.mark.browser
def test_edit_form_blocks_delete_while_saving_and_recovers_from_network_failure(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    page.goto(f"{course_server}/courses/{course['id']}")
    page.get_by_label("Course name", exact=True).fill("Advanced algorithms")
    requests = []
    page.route(f"**/api/courses/{course['id']}", lambda route: requests.append(route))
    save = page.get_by_role("button", name="Save changes", exact=True)
    delete = page.get_by_role("button", name="Delete course", exact=True)
    save.click()
    expect(save).to_be_disabled()
    expect(delete).to_be_disabled()
    assert len(requests) == 1
    assert requests[0].request.method == "PATCH"
    requests[0].abort()

    expect(page.get_by_role("alert")).to_have_text("Could not save the course. Please try again.")
    expect(page.get_by_label("Course name", exact=True)).to_have_value("Advanced algorithms")
    expect(save).to_be_enabled()
    expect(delete).to_be_enabled()
    assert page.request.get(f"{course_server}/api/courses/{course['id']}").json() == course


@pytest.mark.browser
def test_student_can_create_and_list_course_in_browser(page, course_server):
    page.goto(course_server)
    expect(page.get_by_text("No courses yet. Add your first course to get started.")).to_be_visible()
    page.get_by_label("Course name", exact=True).fill("Algorithms")
    page.get_by_label("Description", exact=True).fill("Weekly problem sets")
    page.get_by_role("button", name="Add course", exact=True).click()

    expect(page.get_by_role("heading", name="Algorithms", exact=True)).to_be_visible()
    expect(page.get_by_text("Weekly problem sets", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_role("heading", name="Algorithms", exact=True)).to_be_visible()


@pytest.mark.browser
@pytest.mark.parametrize("operation", ["create", "edit"])
def test_course_form_preserves_input_and_displays_validation_errors(page, course_server, operation):
    if operation == "edit":
        course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
        page.goto(f"{course_server}/courses/{course['id']}")
        button_name = "Save changes"
    else:
        page.goto(course_server)
        button_name = "Add course"
    page.get_by_label("Course name", exact=True).fill("   ")
    page.get_by_label("Description", exact=True).fill("Keep these notes")
    page.get_by_role("button", name=button_name, exact=True).click()

    expect(page.get_by_role("alert")).to_contain_text("Course name must contain 1 to 200 characters.")
    expect(page.get_by_label("Description", exact=True)).to_have_value("Keep these notes")
    expect(page.get_by_role("button", name=button_name, exact=True)).to_be_enabled()
    if operation == "edit":
        assert page.request.get(f"{course_server}/api/courses/{course['id']}").json() == course


@pytest.mark.browser
def test_course_form_prevents_repeat_submissions_and_recovers_from_network_failure(page, course_server):
    requests = []
    page.route("**/api/courses", lambda route: requests.append(route))
    page.goto(course_server)
    page.get_by_label("Course name", exact=True).fill("Algorithms")
    submit = page.get_by_role("button", name="Add course", exact=True)
    submit.click()

    expect(submit).to_be_disabled()
    requests[0].abort()
    expect(page.get_by_role("alert")).to_contain_text("Could not save the course. Please try again.")
    expect(page.get_by_label("Course name", exact=True)).to_have_value("Algorithms")
    expect(submit).to_be_enabled()
