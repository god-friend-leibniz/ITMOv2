import socket
import re
from datetime import date, datetime, timezone
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
def server_day():
    return {"value": date(2026, 10, 25)}


@pytest.fixture
def course_server(tmp_path, request, server_day):
    options = {"local_date_provider": lambda: server_day["value"]}
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
def test_course_completion_filter_is_keyboard_operable_and_survives_reload_and_shared_url(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    page.request.post(listing, data={"title": "Remaining work"})
    done = page.request.post(listing, data={"title": "Finished work"}).json()
    task = page.request.post(f"{course_server}/api/assignments/{done['id']}/tasks", data={"title": "Solve"}).json()
    page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    page.goto(f"{course_server}/courses/{course['id']}")
    filters = page.get_by_role("navigation", name="Assignment completion", exact=True)
    expect(filters).to_be_visible(timeout=2000)
    expect(filters.get_by_role("link", name="All", exact=True)).to_have_attribute("aria-current", "page")
    filters.get_by_role("link", name="Incomplete", exact=True).focus()
    page.keyboard.press("Enter")
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}?completion=incomplete")
    expect(page.get_by_role("link", name="Remaining work", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Finished work", exact=True)).to_have_count(0)
    filters.get_by_role("link", name="Completed", exact=True).focus()
    page.keyboard.press("Enter")
    expect(filters.get_by_role("link", name="Completed", exact=True)).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("link", name="Remaining work", exact=True)).to_have_count(0)
    page.reload()
    expect(page.get_by_role("link", name="Finished work", exact=True)).to_be_visible()
    expect(filters.get_by_role("link", name="Completed", exact=True)).to_have_attribute("aria-current", "page")
    with page.context.new_page() as shared:
        shared.goto(page.url)
        expect(shared.get_by_role("link", name="Finished work", exact=True)).to_be_visible()
        expect(shared.get_by_role("navigation", name="Assignment completion").get_by_role(
            "link", name="Completed", exact=True
        )).to_have_attribute("aria-current", "page")


@pytest.mark.browser
@pytest.mark.parametrize("completion", ["incomplete", "completed", "overdue"])
def test_return_to_course_keeps_completion_after_checklist_changes(page, course_server, completion):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Lab", "due_date": "2026-10-24"}).json()
    task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": "Write report"}).json()
    if completion == "completed":
        page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    course_url = f"{course_server}/courses/{course['id']}?completion={completion}"
    assignment_url = f"{course_server}/assignments/{assignment['id']}?completion={completion}"
    page.goto(course_url)
    page.get_by_role("link", name="Lab", exact=True).click()
    expect(page).to_have_url(assignment_url)
    page.get_by_role("checkbox", name="Write report", exact=True).set_checked(completion != "completed")
    expect(page.get_by_text("1 / 1 · 100%" if completion != "completed" else "0 / 1 · 0%", exact=True)).to_be_visible()
    expect(page).to_have_url(assignment_url)
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page).to_have_url(course_url)
    expect(page.get_by_role("link", name="Lab", exact=True)).to_have_count(0)
    expect(page.get_by_role("navigation", name="Assignment completion").get_by_role(
        "link", name=completion.capitalize(), exact=True
    )).to_have_attribute("aria-current", "page")
    page.goto(f"{course_server}/assignments/{assignment['id']}")
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")


@pytest.mark.browser
@pytest.mark.parametrize("completion", ["all", "incomplete", "completed", "overdue"])
def test_filtered_assignment_deletion_returns_to_the_same_completion_mode(page, course_server, completion):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Lab", "due_date": "2026-10-24"}).json()
    if completion == "completed":
        task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": "Done"}).json()
        page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    query = "" if completion == "all" else f"?completion={completion}"
    course_url = f"{course_server}/courses/{course['id']}{query}"
    page.goto(course_url)
    page.get_by_role("link", name="Lab", exact=True).click()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Delete assignment", exact=True).click()
    expect(page).to_have_url(f"{course_server}/assignments/{assignment['id']}{query}")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete assignment", exact=True).click()
    expect(page).to_have_url(course_url)
    expect(page.get_by_role("link", name="Lab", exact=True)).to_have_count(0)


@pytest.mark.browser
@pytest.mark.parametrize("has_completed", [False, True])
def test_hidden_assignment_creation_confirms_success_and_links_to_all_without_resetting_filter(page, course_server, has_completed):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    other = page.request.post(f"{course_server}/api/courses", data={"name": "Physics"}).json()
    page.request.post(f"{course_server}/api/courses/{other['id']}/assignments", data={"title": "Foreign work"})
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    existing = page.request.post(listing, data={"title": "Existing work"}).json()
    if has_completed:
        task = page.request.post(f"{course_server}/api/assignments/{existing['id']}/tasks", data={"title": "Solve"}).json()
        page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    url = f"{course_server}/courses/{course['id']}?completion=completed"
    page.goto(url)
    title = "New <b>lab</b>"
    page.get_by_label("Assignment title", exact=True).fill(title)
    page.get_by_role("button", name="Add assignment", exact=True).click()
    status = page.get_by_role("status")
    expect(status).to_be_visible(timeout=2000)
    expect(status).to_contain_text(f'Assignment “{title}” created.')
    expect(status).to_contain_text("hidden by the current filter")
    expect(status.locator("b")).to_have_count(0)
    expect(page).to_have_url(url)
    expect(page.get_by_role("navigation", name="Assignment completion").get_by_role(
        "link", name="Completed", exact=True
    )).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("link", name=title, exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Add assignment", exact=True)).to_be_enabled()
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("")
    if has_completed:
        expect(page.get_by_role("link", name="Existing work", exact=True)).to_be_visible()
    all_link = status.get_by_role("link", name="All", exact=True)
    expect(all_link).to_have_attribute("href", f"/courses/{course['id']}")
    all_link.focus()
    page.keyboard.press("Enter")
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")
    expect(page.get_by_role("link", name=title, exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Foreign work", exact=True)).to_have_count(0)
    created = page.request.get(listing).json()[-1]
    assert created["title"] == title
    assert created["progress"] == {"completed": 0, "total": 0, "percent": 0}


@pytest.mark.browser
def test_first_hidden_assignment_creation_updates_the_empty_course_message(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    url = f"{course_server}/courses/{course['id']}?completion=completed"
    page.goto(url)
    expect(page.get_by_text("No assignments yet.", exact=True)).to_be_visible()
    page.get_by_label("Assignment title", exact=True).fill("First lab")
    page.get_by_role("button", name="Add assignment", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("First lab")
    expect(page.get_by_text("No assignments match this filter.", exact=True)).to_be_visible(timeout=2000)
    expect(page.get_by_text("No assignments yet.", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="First lab", exact=True)).to_have_count(0)
    expect(page).to_have_url(url)


@pytest.mark.browser
@pytest.mark.parametrize("failure", ["network", "validation", "server"])
def test_hidden_creation_clears_previous_success_while_pending_and_recovers_from_failure(page, course_server, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    url = f"{course_server}/courses/{course['id']}?completion=completed"
    page.goto(url)
    title = page.get_by_label("Assignment title", exact=True)
    save = page.get_by_role("button", name="Add assignment", exact=True)
    title.fill("First lab")
    save.click()
    expect(page.get_by_role("status")).to_contain_text("First lab")
    requests = []
    page.route(listing, lambda route: requests.append(route))
    attempted_title = "   " if failure == "validation" else "Retry lab"
    title.fill(attempted_title)
    page.get_by_label("Assignment description", exact=True).fill("Keep these notes")
    save.click()
    expect(save).to_be_disabled()
    expect(page.get_by_role("status")).to_have_count(0, timeout=2000)
    title.press("Enter")
    assert len(requests) == 1
    if failure == "network":
        requests[0].abort()
        message = "Could not save the assignment. Please try again."
    elif failure == "validation":
        requests[0].continue_()
        message = "Assignment title must contain 1 to 200 characters."
    else:
        requests[0].fulfill(status=503, json={"error": {
            "code": "DATABASE_BUSY", "message": "The database is busy. Please try again.", "fields": {},
        }})
        message = "The database is busy. Please try again."
    expect(page.get_by_role("alert")).to_contain_text(message)
    expect(page.get_by_role("status")).to_have_count(0)
    expect(page).to_have_url(url)
    expect(title).to_have_value(attempted_title)
    expect(page.get_by_label("Assignment description", exact=True)).to_have_value("Keep these notes")
    expect(save).to_be_enabled()
    assert len(page.request.get(listing).json()) == 1
    page.unroute(listing)
    title.fill("Retry lab")
    save.click()
    expect(page.get_by_role("status")).to_contain_text("Retry lab")
    expect(page.get_by_role("status")).not_to_contain_text("First lab")
    expect(page).to_have_url(url)
    assert [item["title"] for item in page.request.get(listing).json()] == ["First lab", "Retry lab"]


@pytest.mark.browser
def test_course_can_still_be_edited_when_completion_filter_has_no_matches(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={"title": "Unstarted lab"})
    url = f"{course_server}/courses/{course['id']}?completion=completed"
    page.goto(url)
    expect(page.get_by_text("No assignments match this filter.", exact=True)).to_be_visible()
    page.get_by_label("Course name", exact=True).fill("Advanced algorithms")
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("heading", name="Advanced algorithms", exact=True)).to_be_visible()
    expect(page).to_have_url(url)
    expect(page.get_by_text("No assignments match this filter.", exact=True)).to_be_visible()
    assert page.request.get(f"{course_server}/api/courses/{course['id']}").json()["name"] == "Advanced algorithms"


@pytest.mark.browser
@pytest.mark.parametrize("completion", ["all", "incomplete"])
def test_visible_creation_and_detail_edit_keep_course_filter(page, course_server, completion):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Algorithms"}).json()
    course_url = f"{course_server}/courses/{course['id']}"
    if completion != "all":
        course_url += f"?completion={completion}"
    page.goto(course_url)
    page.get_by_label("Assignment title", exact=True).fill("Visible lab")
    page.get_by_role("button", name="Add assignment", exact=True).click()
    expect(page.get_by_role("link", name="Visible lab", exact=True)).to_be_visible()
    expect(page).to_have_url(course_url)
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("")
    page.get_by_role("link", name="Visible lab", exact=True).click()
    detail_url = page.url
    page.get_by_label("Assignment title", exact=True).fill("Edited lab")
    page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_role("heading", name="Edited lab", exact=True)).to_be_visible()
    expect(page).to_have_url(detail_url)
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page).to_have_url(course_url)
    expect(page.get_by_role("link", name="Edited lab", exact=True)).to_be_visible()


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


@pytest.mark.browser
def test_course_list_keeps_server_deadline_order_and_card_details(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Deadlines"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    assignments = [page.request.post(listing, data={
        "title": title, "due_date": due, "description": "Saved notes <b>plain</b>",
    }).json() for title, due in [
        ("Z undated", None), ("Later", "2026-10-27"), ("Z same", "2026-10-24"),
        ("A same", "2026-10-24"), ("A undated", None),
    ]]
    page.goto(f"{course_server}/courses/{course['id']}")
    section = page.locator("#course-assignment-list")
    expect(section).to_be_visible(timeout=2000)
    expect(section).to_have_attribute("data-course-id", str(course["id"]))
    expect(section).to_have_attribute("data-completion", "all")
    expect(section).to_have_attribute("data-has-assignments", "true")
    cards = section.locator("[data-assignment-id]")
    assert cards.evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == [
        str(assignments[i]["id"]) for i in [2, 3, 1, 0, 4]
    ]
    expect(cards.first.get_by_text("Saved notes <b>plain</b>", exact=True)).to_be_visible()
    expect(cards.first.locator("b")).to_have_count(0)
    expect(cards.first.locator("time")).to_have_attribute("datetime", "2026-10-24")
    expect(cards.first.get_by_text("0 / 0 · 0%", exact=True)).to_be_visible()
    expect(cards.first.get_by_text("No tasks", exact=True)).to_be_visible()
    expect(section.locator("form, script, #assignment-success")).to_have_count(0)
    expect(page.get_by_label("Assignment title", exact=True)).to_be_visible()


@pytest.mark.browser
def test_course_deadline_order_survives_filters_and_saved_edits(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Sorted filters"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    assignments = [page.request.post(listing, data={"title": f"Lab {i}", "due_date": due}).json()
                   for i, due in enumerate([None, "2026-10-27", "2026-10-24", "2026-10-24", None])]
    for i in [0, 2]:
        task = page.request.post(f"{course_server}/api/assignments/{assignments[i]['id']}/tasks", data={"title": "Done"}).json()
        page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
    for mode, indices in [("incomplete", [3, 1, 4]), ("completed", [2, 0])]:
        url = f"{course_server}/courses/{course['id']}?completion={mode}"
        page.goto(url)
        cards = page.locator("#course-assignment-list [data-assignment-id]")
        expect(cards).to_have_count(len(indices))
        assert cards.evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == [
            str(assignments[i]["id"]) for i in indices
        ]
    url = f"{course_server}/courses/{course['id']}?completion=incomplete"
    page.goto(url)
    page.get_by_role("link", name="Lab 1", exact=True).click()
    page.get_by_label("Due date", exact=True).fill("2026-10-20")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_label("Due date", exact=True)).to_have_value("2026-10-20")
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page.locator("[data-assignment-id]").first).to_have_attribute("data-assignment-id", str(assignments[1]["id"]))
    page.get_by_role("link", name="Lab 1", exact=True).click()
    page.get_by_label("Due date", exact=True).fill("")
    with page.expect_navigation():
        page.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.get_by_label("Due date", exact=True)).to_have_value("")
    page.get_by_role("link", name="Back to course", exact=True).click()
    assert page.locator("[data-assignment-id]").evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == [
        str(assignments[i]["id"]) for i in [3, 1, 4]
    ]


@pytest.mark.browser
def test_overdue_link_shows_server_membership_and_checklist_changes(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Overdue"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    assignments = []
    tasks = []
    for title, due, total, completed in [
        ("Empty past", "2026-10-24", 0, 0), ("Completed past", "2026-10-24", 1, 1),
        ("Partial past", "2026-10-23", 2, 1), ("Today", "2026-10-25", 1, 0),
        ("Future", "2026-10-26", 1, 0), ("Undated", None, 1, 0),
    ]:
        assignment = page.request.post(listing, data={"title": title, "due_date": due}).json()
        assignments.append(assignment)
        checklist = []
        for i in range(total):
            task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": f"Step {i}"}).json()
            checklist.append(task)
            if i < completed:
                page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": True})
        tasks.append(checklist)
    other = page.request.post(f"{course_server}/api/courses", data={"name": "Other"}).json()
    page.request.post(f"{course_server}/api/courses/{other['id']}/assignments", data={"title": "Foreign", "due_date": "2026-10-01"})
    url = f"{course_server}/courses/{course['id']}"
    page.goto(url)
    page.get_by_role("navigation", name="Assignment completion").get_by_role("link", name="Overdue", exact=True).click(timeout=2000)
    overdue_url = url + "?completion=overdue"
    expect(page).to_have_url(overdue_url)
    expect(page.get_by_role("link", name="Overdue", exact=True)).to_have_attribute("aria-current", "page")
    cards = page.locator("#course-assignment-list [data-assignment-id]")
    assert cards.evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == [str(assignments[i]["id"]) for i in [2, 0]]
    expect(cards.last.get_by_text("No tasks", exact=True)).to_be_visible()
    for mode in ["all", "incomplete"]:
        page.get_by_role("link", name=mode.capitalize(), exact=True).click()
        for i in [0, 2]:
            expect(page.locator(f'[data-assignment-id="{assignments[i]["id"]}"]')).to_have_count(1)
    page.goto(overdue_url)
    page.get_by_role("link", name="Partial past", exact=True).click()
    page.get_by_role("checkbox", name="Step 1", exact=True).check()
    expect(page.get_by_text("2 / 2 · 100%", exact=True)).to_be_visible()
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page.get_by_role("link", name="Partial past", exact=True)).to_have_count(0)
    page.goto(f"{course_server}/assignments/{assignments[2]['id']}?completion=overdue")
    page.get_by_role("checkbox", name="Step 1", exact=True).uncheck()
    expect(page.get_by_text("1 / 2 · 50%", exact=True)).to_be_visible()
    page.get_by_role("link", name="Back to course", exact=True).click()
    expect(page.get_by_role("link", name="Partial past", exact=True)).to_be_visible()
    page.request.delete(f"{course_server}/api/tasks/{tasks[2][1]['id']}")
    page.reload()
    expect(page.get_by_role("link", name="Partial past", exact=True)).to_have_count(0)
    page.request.delete(f"{course_server}/api/tasks/{tasks[2][0]['id']}")
    page.reload()
    expect(page.get_by_role("link", name="Partial past", exact=True)).to_be_visible()
    expect(page.locator(f'[data-assignment-id="{assignments[2]["id"]}"]').get_by_text("No tasks", exact=True)).to_be_visible()


@pytest.mark.browser
def test_four_modes_keep_keyboard_navigation_shared_urls_and_fallback(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Navigation"}).json()
    assignment = page.request.post(f"{course_server}/api/courses/{course['id']}/assignments", data={
        "title": "Past lab", "due_date": "2026-10-24",
    }).json()
    task = page.request.post(f"{course_server}/api/assignments/{assignment['id']}/tasks", data={"title": "Solve"}).json()
    base = f"{course_server}/courses/{course['id']}"
    page.set_viewport_size({"width": 360, "height": 900})
    page.goto(base)
    for mode in ["all", "incomplete", "completed", "overdue"]:
        page.request.patch(f"{course_server}/api/tasks/{task['id']}", data={"is_completed": mode == "completed"})
        filters = page.get_by_role("navigation", name="Assignment completion", exact=True)
        link = filters.get_by_role("link", name=mode.capitalize(), exact=True)
        link.focus()
        expect(link).to_be_focused()
        assert link.evaluate("el => getComputedStyle(el).outlineStyle") != "none"
        page.keyboard.press("Enter")
        url = base + ("" if mode == "all" else f"?completion={mode}")
        expect(page).to_have_url(url)
        expect(filters.locator('[aria-current="page"]')).to_have_count(1)
        expect(link).to_have_attribute("aria-current", "page")
        assert filters.evaluate("el => el.scrollWidth <= el.clientWidth")
        page.reload()
        expect(page.locator("#course-assignment-list")).to_have_attribute("data-completion", mode)
        with page.context.new_page() as shared:
            shared.goto(url)
            expect(shared.locator("#course-assignment-list")).to_have_attribute("data-completion", mode)
        filters.get_by_role("link", name="Overdue", exact=True).focus()
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Past lab", exact=True)).to_be_focused()
        with page.expect_navigation():
            page.keyboard.press("Enter")
        detail = page.url
        page.get_by_label("Assignment description", exact=True).fill(f"Edited in {mode}")
        with page.expect_navigation():
            page.get_by_role("button", name="Save changes", exact=True).click()
        expect(page).to_have_url(detail)
        page.get_by_role("link", name="Back to course", exact=True).click()
        expect(page).to_have_url(url)
    for query in ["", "?completion=", "?completion=unknown", "?completion"]:
        page.goto(base + query)
        expect(page.get_by_role("navigation", name="Assignment completion").get_by_role("link", name="All", exact=True)).to_have_attribute("aria-current", "page")
        page.goto(f"{course_server}/assignments/{assignment['id']}{query}")
        expect(page.get_by_role("link", name="Back to course", exact=True)).to_have_attribute("href", f"/courses/{course['id']}")
    for path in ["/courses/999999", "/assignments/999999"]:
        response = page.goto(course_server + path + "?completion=overdue")
        assert response.status == 404
        expect(page.locator("#assignments-empty")).to_have_count(0)


@pytest.mark.browser
def test_created_assignment_refreshes_only_server_list_and_keeps_forms(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Fresh list"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    later = page.request.post(listing, data={"title": "Later", "due_date": "2026-10-27"}).json()
    url = f"{course_server}/courses/{course['id']}"
    page.goto(url)
    page.get_by_label("Course name", exact=True).fill("Unsaved course name")
    reads, writes = [], []
    page.on("request", lambda request: writes.append(request) if request.method == "POST" and request.url == listing else None)
    page.route(url, lambda route: reads.append(route))
    title = page.get_by_label("Assignment title", exact=True)
    title.fill("New earlier lab")
    page.get_by_label("Due date", exact=True).fill("2026-10-24")
    page.get_by_role("button", name="Add assignment", exact=True).click(no_wait_after=True)
    expect(title).to_have_value("", timeout=2000)
    section = page.locator("#course-assignment-list")
    expect(section).to_have_attribute("aria-busy", "true")
    expect(page.locator("#assignment-refresh-status")).to_be_visible()
    expect(page.locator("#assignment-list-stale-note")).to_be_visible()
    expect(page.get_by_role("link", name="New earlier lab", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Add assignment", exact=True)).to_be_disabled()
    assert len(reads) == len(writes) == 1
    assert reads[0].request.resource_type == "fetch"
    assert reads[0].request.headers["accept"] == "text/html"
    title.fill("Next draft")
    title.press("Enter")
    assert len(writes) == len(reads) == 1
    reads[0].continue_()
    expect(page.get_by_role("link", name="New earlier lab", exact=True)).to_be_visible()
    created = page.request.get(listing).json()[-1]
    assert page.locator("[data-assignment-id]").evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == [str(created["id"]), str(later["id"])]
    expect(title).to_have_value("Next draft")
    expect(title).to_be_focused()
    expect(page.get_by_label("Course name", exact=True)).to_have_value("Unsaved course name")
    expect(page.locator("#assignment-form")).to_have_attribute("data-completion", "all")
    expect(page.locator("#assignment-refresh-status")).to_be_hidden()
    expect(page.locator("#assignment-list-stale-note")).to_be_hidden()
    expect(page.get_by_role("button", name="Add assignment", exact=True)).to_be_enabled()


@pytest.mark.browser
def test_creation_in_each_mode_uses_fresh_html_for_every_due_date(page, course_server):
    expected = {"all": [True] * 4, "incomplete": [True] * 4,
                "completed": [False] * 4, "overdue": [True, False, False, False]}
    for mode in expected:
        course = page.request.post(f"{course_server}/api/courses", data={"name": mode}).json()
        listing = f"{course_server}/api/courses/{course['id']}/assignments"
        url = f"{course_server}/courses/{course['id']}" + ("" if mode == "all" else f"?completion={mode}")
        page.goto(url)
        expect(page.get_by_text("No assignments yet.", exact=True)).to_be_visible()
        for i, due in enumerate(["2026-10-24", "2026-10-25", "2026-10-26", None]):
            title = f'{mode}-{i} <b>lab</b><script>window.unsafeTitle = true</script>'
            page.get_by_label("Assignment title", exact=True).fill(title)
            page.get_by_label("Due date", exact=True).fill(due or "")
            with page.expect_response(lambda response: response.request.method == "GET" and response.url == url and response.request.resource_type == "fetch") as refreshed:
                page.get_by_role("button", name="Add assignment", exact=True).click()
            assert refreshed.value.status == 200
            expect(page.locator("#assignment-success")).to_contain_text(f'Assignment “{title}” created.')
            saved = page.request.get(listing).json()[-1]
            card = page.locator(f'[data-assignment-id="{saved["id"]}"]')
            expect(card).to_have_count(1 if expected[mode][i] else 0)
            expect(page).to_have_url(url)
            expect(page.locator("#assignment-form")).to_have_attribute("data-completion", mode)
            expect(page.get_by_label("Assignment title", exact=True)).to_have_value("")
            expect(page.get_by_role("button", name="Add assignment", exact=True)).to_be_enabled()
            expect(page.locator("#assignment-success b, #assignment-success script")).to_have_count(0)
            assert page.evaluate("window.unsafeTitle === undefined")
            all_link = page.locator("#assignment-success").get_by_role("link", name="All", exact=True)
            if expected[mode][i]:
                expect(all_link).to_be_hidden()
                expect(card.locator("b, script")).to_have_count(0)
            else:
                expect(page.locator("#assignment-success")).to_contain_text("hidden by the current filter")
                expect(all_link).to_be_visible()
                expect(all_link).to_have_attribute("href", f"/courses/{course['id']}")
            expect(page.locator("#course-assignment-list")).to_have_attribute("data-has-assignments", "true")
            expect(page.get_by_text("No assignments yet.", exact=True)).to_have_count(0)
        if mode == "completed":
            expect(page.get_by_text("No assignments match this filter.", exact=True)).to_be_visible()
            page.locator("#assignment-success").get_by_role("link", name="All", exact=True).focus()
            page.keyboard.press("Enter")
            expect(page).to_have_url(f"{course_server}/courses/{course['id']}")
            expect(page.get_by_role("link", name=title, exact=True)).to_be_visible()
            page.reload()
            expect(page.locator("#assignment-success")).to_be_hidden()


@pytest.mark.browser
def test_saved_assignment_read_failure_keeps_stale_list_and_write_success(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Saved but stale"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    url = f"{course_server}/courses/{course['id']}?completion=overdue"
    page.goto(url)
    reads = []
    def fail_read(route):
        reads.append(route.request)
        route.abort()
    page.route(url, fail_read)
    page.get_by_label("Assignment title", exact=True).fill("Saved once")
    page.get_by_label("Due date", exact=True).fill("2026-10-24")
    page.get_by_role("button", name="Add assignment", exact=True).click()
    error = page.locator("#assignment-refresh-error")
    expect(error).to_have_text("Задание сохранено, но список обновить не удалось", timeout=2000)
    expect(error).to_be_visible()
    expect(error).to_have_attribute("role", "alert")
    expect(page.locator("#assignment-error")).to_be_hidden()
    expect(page.locator("#assignment-success")).to_be_hidden()
    expect(page.locator("#assignment-refresh-status")).to_be_hidden()
    expect(page.locator("#assignment-list-stale-note")).to_be_visible()
    section = page.locator("#course-assignment-list")
    expect(section).to_have_attribute("aria-busy", "false")
    expect(section).to_have_attribute("aria-describedby", "assignment-list-stale-note")
    expect(section).to_have_attribute("data-has-assignments", "false")
    expect(page.get_by_text("No assignments yet.", exact=True)).to_be_visible()
    expect(page.get_by_text("No assignments match this filter.", exact=True)).to_have_count(0)
    expect(section.locator("[data-assignment-id]")).to_have_count(0)
    retry = page.get_by_role("button", name="Обновить список", exact=True)
    expect(retry).to_be_visible()
    expect(retry).to_have_attribute("type", "button")
    expect(section.locator("#assignment-refresh-retry, #assignment-refresh-error")).to_have_count(0)
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("")
    expect(page.get_by_role("button", name="Add assignment", exact=True)).to_be_enabled()
    assert len(reads) == len(page.request.get(listing).json()) == 1
    expect(page).to_have_url(url)


@pytest.mark.browser
@pytest.mark.parametrize("failure", ["network", "not_found", "busy", "internal", "body"])
def test_refresh_retry_reads_only_and_recovers_after_repeated_failures(page, course_server, failure):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Read-only retry"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    url = f"{course_server}/courses/{course['id']}?completion=overdue"
    page.goto(url)
    reads, writes = [], []
    page.route(url, lambda route: reads.append(route))
    page.on("request", lambda request: writes.append(request) if request.url == listing and request.method == "POST" else None)
    def fail(route):
        if failure == "network":
            route.abort()
        elif failure == "not_found":
            route.fulfill(status=404, content_type="text/html", body="<h1>Course not found</h1>")
        elif failure == "body":
            route.fulfill(status=200, headers={"Content-Type": "text/html", "Content-Encoding": "gzip"}, body="not a gzip body")
        else:
            route.fulfill(status=503 if failure == "busy" else 500, json={"error": {
                "code": "DATABASE_BUSY" if failure == "busy" else "INTERNAL_ERROR", "message": "Safe read failure", "fields": {},
            }})
    page.get_by_label("Assignment title", exact=True).fill("Saved once")
    page.get_by_label("Due date", exact=True).fill("2026-10-24")
    save = page.get_by_role("button", name="Add assignment", exact=True)
    save.click()
    section = page.locator("#course-assignment-list")
    expect(section).to_have_attribute("aria-busy", "true")
    fail(reads[0])
    error = page.locator("#assignment-refresh-error")
    expect(error).to_be_visible()
    expect(page.locator("#assignment-error")).to_be_hidden()
    expect(page.locator("#assignment-success")).to_be_hidden()
    retry = page.get_by_role("button", name="Обновить список", exact=True)
    expect(retry).to_be_enabled()
    retry.click()
    expect(section).to_have_attribute("aria-busy", "true", timeout=2000)
    expect(page.locator("#assignment-refresh-status")).to_be_visible()
    expect(error).to_be_visible()
    expect(retry).to_be_disabled()
    expect(save).to_be_disabled()
    page.get_by_label("Assignment title", exact=True).press("Enter")
    retry.press("Enter")
    assert len(reads) == 2 and len(writes) == 1
    fail(reads[1])
    expect(retry).to_be_enabled()
    expect(error).to_be_visible()
    retry.click()
    expect(section).to_have_attribute("aria-busy", "true")
    assert len(reads) == 3
    reads[2].continue_()
    expect(page.get_by_role("link", name="Saved once", exact=True)).to_be_visible()
    expect(error).to_be_hidden()
    expect(retry).to_be_hidden()
    expect(page.locator("#assignment-list-stale-note")).to_be_hidden()
    expect(page.locator("#assignment-refresh-status")).to_be_hidden()
    expect(save).to_be_enabled()
    assert len(writes) == 1
    saved = page.request.get(listing).json()
    assert len(saved) == 1 and saved[0]["title"] == "Saved once"
    expect(section).to_have_attribute("data-has-assignments", "true")
    expect(page).to_have_url(url)


@pytest.mark.browser
def test_refresh_rejects_incompatible_html_before_replacing_list(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Validate list"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    page.request.post(listing, data={"title": "Existing", "due_date": "2026-10-23"})
    url = f"{course_server}/courses/{course['id']}?completion=overdue"
    for corruption in ["media", "status", "missing_container", "duplicate_container", "course", "course_zero",
                       "mode", "boolean", "missing_id", "bad_id", "duplicate_id", "nonempty_false",
                       "empty_extra", "empty_missing", "empty_duplicate", "form", "script"]:
        mode = "completed" if corruption in ["empty_missing", "empty_duplicate"] else "overdue"
        url = f"{course_server}/courses/{course['id']}?completion={mode}"
        page.goto(url)
        section = page.locator("#course-assignment-list")
        before = section.locator("[data-assignment-id]").evaluate_all("cards => cards.map(card => card.dataset.assignmentId)")
        def corrupt_read(route):
            upstream = route.fetch()
            body = upstream.text()
            headers = dict(upstream.headers)
            headers.pop("content-length", None)
            fragment = re.search(r'<section id="course-assignment-list"[\s\S]*?</section>', body).group()
            changed = fragment
            if corruption == "media":
                headers["content-type"] = "application/json"
            elif corruption == "missing_container":
                changed = fragment.replace('id="course-assignment-list"', 'id="missing-list"', 1)
            elif corruption == "duplicate_container":
                changed = fragment + fragment
            elif corruption in ["course", "course_zero"]:
                changed = re.sub(r'data-course-id="[^"]*"', 'data-course-id="999999"' if corruption == "course" else 'data-course-id="0"', fragment, count=1)
            elif corruption == "mode":
                changed = fragment.replace('data-completion="overdue"', 'data-completion="completed"', 1)
            elif corruption == "boolean":
                changed = fragment.replace('data-has-assignments="true"', 'data-has-assignments="yes"', 1)
            elif corruption == "missing_id":
                changed = re.sub(r' data-assignment-id="[^"]*"', '', fragment, count=1)
            elif corruption == "bad_id":
                changed = re.sub(r'data-assignment-id="[^"]*"', 'data-assignment-id="0"', fragment, count=1)
            elif corruption == "duplicate_id":
                ids = re.findall(r'data-assignment-id="([^"]*)"', fragment)
                changed = fragment.replace(f'data-assignment-id="{ids[1]}"', f'data-assignment-id="{ids[0]}"', 1)
            elif corruption == "nonempty_false":
                changed = fragment.replace('data-has-assignments="true"', 'data-has-assignments="false"', 1)
            elif corruption == "empty_extra":
                changed = fragment.replace('</section>', '<p id="assignments-empty">Wrong empty</p></section>', 1)
            elif corruption in ["empty_missing", "empty_duplicate"]:
                empty = re.search(r'<p class="empty" id="assignments-empty">.*?</p>', fragment).group()
                changed = fragment.replace(empty, '' if corruption == "empty_missing" else empty + empty, 1)
            elif corruption == "form":
                changed = fragment.replace('<h2 ', '<form></form><h2 ', 1)
            elif corruption == "script":
                changed = fragment.replace('<h2 ', '<script>window.unsafeFragment = true</script><h2 ', 1)
            body = body.replace(fragment, changed, 1)
            route.fulfill(response=upstream, headers=headers, body=body, status=201 if corruption == "status" else 200)
        page.route(url, corrupt_read)
        title = f"Saved {corruption}"
        page.get_by_label("Assignment title", exact=True).fill(title)
        page.get_by_label("Due date", exact=True).fill("2026-10-24")
        page.get_by_role("button", name="Add assignment", exact=True).click()
        expect(page.locator("#assignment-refresh-error")).to_be_visible(timeout=2000)
        expect(page.locator("#assignment-success")).to_be_hidden()
        assert section.locator("[data-assignment-id]").evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == before
        expect(page.get_by_role("link", name=title, exact=True)).to_have_count(0)
        expect(page.locator("#assignment-list-stale-note")).to_be_visible()
        expect(page.locator("#assignment-error")).to_be_hidden()
        expect(page.get_by_label("Assignment title", exact=True)).to_have_value("")
        page.unroute(url, corrupt_read)
        page.get_by_role("button", name="Обновить список", exact=True).click()
        if mode == "completed":
            expect(page.locator("#assignment-success")).to_contain_text(title)
            expect(page.get_by_text("No assignments match this filter.", exact=True)).to_be_visible()
        else:
            expect(page.get_by_role("link", name=title, exact=True)).to_be_visible()
        expect(page.locator("#assignment-refresh-error")).to_be_hidden()
        assert page.evaluate("window.unsafeFragment === undefined")
        assert len([item for item in page.request.get(listing).json() if item["title"] == title]) == 1


@pytest.mark.browser
@pytest.mark.parametrize("save_after_midnight", [False, True])
def test_creation_uses_new_server_date_when_form_and_browser_are_still_yesterday(page, course_server, server_day, save_after_midnight):
    page.clock.set_fixed_time(datetime(2026, 10, 25, 12, tzinfo=timezone.utc))
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Across midnight"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    earlier = page.request.post(listing, data={"title": "Earlier", "due_date": "2026-10-24"}).json()
    url = f"{course_server}/courses/{course['id']}?completion=overdue"
    page.goto(url)
    page.get_by_label("Assignment title", exact=True).fill("Yesterday at fresh read")
    page.get_by_label("Due date", exact=True).fill("2026-10-25")
    reads = []
    page.route(url, lambda route: reads.append(route))
    if save_after_midnight:
        server_day["value"] = date(2026, 10, 26)
    page.get_by_role("button", name="Add assignment", exact=True).click()
    expect(page.get_by_label("Assignment title", exact=True)).to_have_value("")
    expect(page.locator("#course-assignment-list")).to_have_attribute("aria-busy", "true")
    server_day["value"] = date(2026, 10, 26)
    assert len(reads) == 1
    reads[0].continue_()
    expect(page.get_by_role("link", name="Yesterday at fresh read", exact=True)).to_be_visible()
    expect(page.locator("#assignment-success")).not_to_contain_text("hidden")
    saved = page.request.get(listing).json()[-1]
    assert saved["due_date"] == "2026-10-25"
    assert page.locator("[data-assignment-id]").evaluate_all("cards => cards.map(card => card.dataset.assignmentId)") == [str(earlier["id"]), str(saved["id"])]
    assert page.evaluate("new Date().toISOString().slice(0, 10)") == "2026-10-25"
    expect(page).to_have_url(url)


@pytest.mark.browser
def test_refresh_feedback_and_retry_keep_keyboard_focus_and_plain_text(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Accessible refresh"}).json()
    url = f"{course_server}/courses/{course['id']}?completion=completed"
    page.goto(url)
    scripts, reads = [], []
    page.on("request", lambda request: scripts.append(request.url) if request.resource_type == "script" else None)
    page.route(url, lambda route: reads.append(route))
    success = page.locator("#assignment-success")
    success.evaluate("el => el.dataset.liveIdentity = 'same-region'")
    expect(success).to_have_attribute("role", "status")
    expect(page.locator("#assignment-refresh-status")).to_have_attribute("role", "status")
    expect(page.locator("#assignment-refresh-error")).to_have_attribute("role", "alert")
    expect(page.locator("#course-assignment-list [role=status], #course-assignment-list [role=alert], #course-assignment-list button")).to_have_count(0)
    title = '<img src=x onerror="window.unsafeTitle = true">'
    page.get_by_label("Assignment title", exact=True).fill(title)
    save = page.get_by_role("button", name="Add assignment", exact=True)
    save.click()
    expect(page.locator("#assignment-refresh-status")).to_be_visible()
    expect(success).to_be_hidden()
    reads[0].abort()
    error = page.locator("#assignment-refresh-error")
    expect(error).to_be_visible()
    retry = page.get_by_role("button", name="Обновить список", exact=True)
    page.get_by_label("GitHub repository name", exact=True).focus()
    page.keyboard.press("Tab")
    expect(retry).to_be_focused()
    assert retry.evaluate("el => getComputedStyle(el).outlineStyle") != "none"
    page.keyboard.press("Enter")
    expect(page.locator("#course-assignment-list")).to_have_attribute("aria-busy", "true")
    reads[1].abort()
    expect(retry).to_be_enabled()
    expect(retry).to_be_focused(timeout=2000)
    page.keyboard.press("Enter")
    expect(page.locator("#assignment-refresh-status")).to_be_visible()
    reads[2].continue_()
    expect(success).to_be_visible()
    expect(success).to_contain_text(title)
    expect(success).to_have_attribute("data-live-identity", "same-region")
    expect(success.locator("img")).to_have_count(0)
    expect(retry).to_be_hidden()
    expect(error).to_be_hidden()
    expect(save).to_be_focused(timeout=2000)
    assert scripts == []
    assert page.evaluate("window.unsafeTitle === undefined")
    success.get_by_role("link", name="All", exact=True).focus()
    page.keyboard.press("Enter")
    expect(page).to_have_url(f"{course_server}/courses/{course['id']}")
    expect(page.get_by_role("link", name=title, exact=True)).to_be_visible()
    expect(page.locator("#course-assignment-list img")).to_have_count(0)


@pytest.mark.browser
def test_failed_new_write_preserves_previous_saved_context_and_stale_error(page, course_server):
    course = page.request.post(f"{course_server}/api/courses", data={"name": "Independent outcomes"}).json()
    listing = f"{course_server}/api/courses/{course['id']}/assignments"
    url = f"{course_server}/courses/{course['id']}?completion=overdue"
    page.goto(url)
    reads, writes = [], []
    page.route(url, lambda route: reads.append(route))
    page.on("request", lambda request: writes.append(request) if request.url == listing and request.method == "POST" else None)
    title = page.get_by_label("Assignment title", exact=True)
    description = page.get_by_label("Assignment description", exact=True)
    save = page.get_by_role("button", name="Add assignment", exact=True)
    title.fill("First saved")
    page.get_by_label("Due date", exact=True).fill("2026-10-24")
    save.click()
    expect(page.locator("#course-assignment-list")).to_have_attribute("aria-busy", "true")
    reads[0].abort()
    refresh_error = page.locator("#assignment-refresh-error")
    expect(refresh_error).to_be_visible()
    title.fill("   ")
    description.fill("Keep invalid draft")
    save.click()
    write_error = page.locator("#assignment-error")
    expect(write_error).to_contain_text("Assignment title must contain 1 to 200 characters.")
    expect(refresh_error).to_be_visible()
    expect(title).to_have_value("   ")
    expect(description).to_have_value("Keep invalid draft")
    expect(page.locator("#assignment-success")).to_be_hidden()
    retry = page.get_by_role("button", name="Обновить список", exact=True)
    retry.click()
    expect(page.locator("#course-assignment-list")).to_have_attribute("aria-busy", "true")
    assert len(reads) == 2 and len(writes) == 2
    reads[1].continue_()
    expect(page.locator("#assignment-success")).to_contain_text("First saved")
    expect(refresh_error).to_be_hidden()
    expect(write_error).to_be_visible()
    expect(title).to_have_value("   ")
    expect(description).to_have_value("Keep invalid draft")
    assert [item["title"] for item in page.request.get(listing).json()] == ["First saved"]
    title.fill("Second saved")
    page.get_by_label("Due date", exact=True).fill("")
    save.click()
    expect(page.locator("#course-assignment-list")).to_have_attribute("aria-busy", "true")
    expect(title).to_have_value("")
    reads[2].abort()
    expect(refresh_error).to_be_visible()
    expect(write_error).to_be_hidden()
    retry.click()
    expect(page.locator("#course-assignment-list")).to_have_attribute("aria-busy", "true")
    reads[3].continue_()
    expect(page.locator("#assignment-success")).to_contain_text("Second saved")
    expect(page.locator("#assignment-success")).to_contain_text("hidden by the current filter")
    expect(page.locator("#assignment-success")).not_to_contain_text("First saved")
    assert len(writes) == 3
    assert [item["title"] for item in page.request.get(listing).json()] == ["First saved", "Second saved"]
    expect(page.get_by_role("link", name="First saved", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Second saved", exact=True)).to_have_count(0)
