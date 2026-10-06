import socket
import threading
import time

from playwright.sync_api import expect
import pytest
import uvicorn

from studyflow.web import create_app


@pytest.fixture
def course_server(tmp_path):
    app = create_app(db_path=tmp_path / "browser.sqlite3")
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
def test_course_form_preserves_input_and_displays_validation_errors(page, course_server):
    page.goto(course_server)
    page.get_by_label("Course name", exact=True).fill("   ")
    page.get_by_label("Description", exact=True).fill("Keep these notes")
    page.get_by_role("button", name="Add course", exact=True).click()

    expect(page.get_by_role("alert")).to_contain_text("Course name must contain 1 to 200 characters.")
    expect(page.get_by_label("Description", exact=True)).to_have_value("Keep these notes")
    expect(page.get_by_role("button", name="Add course", exact=True)).to_be_enabled()


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
