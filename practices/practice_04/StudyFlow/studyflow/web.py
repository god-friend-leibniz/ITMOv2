from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from studyflow import coursework, db, domain
from studyflow.github_mcp_client import IntegrationError, get_repository_summary


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    description: str = Field(default="", max_length=5000)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        return domain.course_name(value)


class CoursePatch(CourseCreate):
    name: str = ""

    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class RepositoryReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner: str
    repo: str

    @field_validator("owner")
    @classmethod
    def valid_owner(cls, value):
        return domain.repository_owner(value)

    @field_validator("repo")
    @classmethod
    def valid_repo(cls, value):
        return domain.repository_name(value)


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str
    description: str = Field(default="", max_length=5000)
    due_date: str | None = None
    repository: RepositoryReference | None = None

    @field_validator("title")
    @classmethod
    def valid_title(cls, value):
        return domain.assignment_title(value)

    @field_validator("due_date")
    @classmethod
    def valid_due_date(cls, value):
        return domain.assignment_due_date(value)


class AssignmentPatch(AssignmentCreate):
    title: str = ""

    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str

    @field_validator("title")
    @classmethod
    def valid_title(cls, value):
        return domain.task_title(value)


class TaskPatch(TaskCreate):
    title: str = ""
    is_completed: bool = False

    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


def create_app(*, db_path=None, summary_reader=get_repository_summary):
    path = db_path if db_path is not None else db.database_path()

    @asynccontextmanager
    async def lifespan(app):
        db.migrate(path)
        yield

    app = FastAPI(title="StudyFlow", lifespan=lifespan)

    @app.exception_handler(coursework.RepositoryNotLinked)
    async def repository_not_linked(request, error):
        return JSONResponse(status_code=409, headers={"Cache-Control": "no-store"}, content={"error": {
            "code": "REPOSITORY_NOT_LINKED", "message": "Link a repository before loading its summary.", "fields": {},
        }})

    @app.exception_handler(IntegrationError)
    async def integration_error(request, error):
        headers = {"Cache-Control": "no-store"}
        if error.retry_after_seconds is not None:
            headers["Retry-After"] = str(error.retry_after_seconds)
        return JSONResponse(status_code=error.status_code, headers=headers, content={"error": {
            "code": error.code, "message": error.message, "fields": {},
        }})

    @app.exception_handler(coursework.CourseNotFound)
    async def course_not_found(request, error):
        if not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(request=request, name="not_found.html", status_code=404)
        return JSONResponse(status_code=404, content={"error": {
            "code": "NOT_FOUND", "message": "Course not found.", "fields": {},
        }})

    @app.exception_handler(coursework.AssignmentNotFound)
    async def assignment_not_found(request, error):
        if not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(
                request=request, name="not_found.html", status_code=404, context={"resource": "Assignment"}
            )
        headers = {"Cache-Control": "no-store"} if request.url.path.endswith("/repository-summary") else {}
        return JSONResponse(status_code=404, headers=headers, content={"error": {
            "code": "NOT_FOUND", "message": "Assignment not found.", "fields": {},
        }})

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, error):
        if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
            return JSONResponse(status_code=503, content={"error": {
                "code": "DATABASE_BUSY", "message": "The database is busy. Please try again.", "fields": {},
            }})
        return JSONResponse(status_code=500, content={"error": {
            "code": "INTERNAL_ERROR", "message": "The request could not be completed.", "fields": {},
        }})

    @app.exception_handler(coursework.TaskNotFound)
    async def task_not_found(request, error):
        return JSONResponse(status_code=404, content={"error": {
            "code": "NOT_FOUND", "message": "Task not found.", "fields": {},
        }})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        fields = {".".join(map(str, item["loc"][1:])) or "body": item["msg"] for item in error.errors()}
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR", "message": "Check the submitted fields.", "fields": fields,
        }})

    assets = Path(__file__).parent
    templates = Jinja2Templates(directory=assets / "templates")
    app.mount("/static", StaticFiles(directory=assets / "static"), name="static")

    @app.get("/")
    def home(request: Request):
        return templates.TemplateResponse(
            request=request, name="courses.html", context={"courses": coursework.list_courses(path)}
        )

    @app.post("/api/courses", status_code=201)
    def create_course(body: CourseCreate):
        return coursework.create_course(path, body.name, body.description)

    @app.get("/courses/{course_id}")
    def course_detail(request: Request, course_id: int):
        return templates.TemplateResponse(
            request=request, name="course.html", context={
                "course": coursework.get_course(path, course_id),
                "assignments": coursework.list_assignments(path, course_id),
            }
        )

    @app.get("/api/courses")
    def list_courses():
        return coursework.list_courses(path)

    @app.get("/api/courses/{course_id}")
    def get_course(course_id: int):
        return coursework.get_course(path, course_id)

    @app.patch("/api/courses/{course_id}")
    def edit_course(course_id: int, body: CoursePatch):
        return coursework.edit_course(path, course_id, body.model_dump(exclude_unset=True))

    @app.delete("/api/courses/{course_id}", status_code=204)
    def delete_course(course_id: int):
        coursework.delete_course(path, course_id)
        return Response(status_code=204)

    @app.post("/api/courses/{course_id}/assignments", status_code=201)
    def create_assignment(course_id: int, body: AssignmentCreate):
        repository = body.repository.model_dump() if body.repository is not None else None
        return coursework.create_assignment(path, course_id, body.title, body.description, body.due_date, repository)

    @app.get("/api/courses/{course_id}/assignments")
    def list_assignments(course_id: int):
        return coursework.list_assignments(path, course_id)

    @app.get("/api/assignments/{assignment_id}")
    def get_assignment(assignment_id: int):
        return coursework.get_assignment(path, assignment_id)

    @app.get("/api/assignments/{assignment_id}/repository-summary")
    async def repository_summary(assignment_id: int):
        summary = await coursework.load_repository_summary(path, assignment_id, summary_reader)
        return JSONResponse(content=summary, headers={"Cache-Control": "no-store"})

    @app.get("/assignments/{assignment_id}")
    def assignment_detail(request: Request, assignment_id: int):
        return templates.TemplateResponse(
            request=request, name="assignment.html", context={
                "assignment": coursework.get_assignment(path, assignment_id),
                "tasks": coursework.list_tasks(path, assignment_id),
            }
        )

    @app.patch("/api/assignments/{assignment_id}")
    def edit_assignment(assignment_id: int, body: AssignmentPatch):
        return coursework.edit_assignment(path, assignment_id, body.model_dump(exclude_unset=True))

    @app.delete("/api/assignments/{assignment_id}", status_code=204)
    def delete_assignment(assignment_id: int):
        coursework.delete_assignment(path, assignment_id)
        return Response(status_code=204)

    @app.post("/api/assignments/{assignment_id}/tasks", status_code=201)
    def create_task(assignment_id: int, body: TaskCreate):
        return coursework.create_task(path, assignment_id, body.title)

    @app.get("/api/assignments/{assignment_id}/tasks")
    def list_tasks(assignment_id: int):
        return coursework.list_tasks(path, assignment_id)

    @app.patch("/api/tasks/{task_id}")
    def edit_task(task_id: int, body: TaskPatch):
        return coursework.edit_task(path, task_id, body.model_dump(exclude_unset=True))

    @app.delete("/api/tasks/{task_id}", status_code=204)
    def delete_task(task_id: int):
        coursework.delete_task(path, task_id)
        return Response(status_code=204)

    return app
