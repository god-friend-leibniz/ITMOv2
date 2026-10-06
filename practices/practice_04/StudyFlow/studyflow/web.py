from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

from studyflow import coursework, db, domain


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    description: str = Field(default="", max_length=5000)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        return domain.course_name(value)


def create_app(*, db_path=None):
    path = db_path if db_path is not None else db.database_path()

    @asynccontextmanager
    async def lifespan(app):
        db.migrate(path)
        yield

    app = FastAPI(title="StudyFlow", lifespan=lifespan)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, error):
        if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
            return JSONResponse(status_code=503, content={"error": {
                "code": "DATABASE_BUSY", "message": "The database is busy. Please try again.", "fields": {},
            }})
        return JSONResponse(status_code=500, content={"error": {
            "code": "INTERNAL_ERROR", "message": "The request could not be completed.", "fields": {},
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

    @app.get("/api/courses")
    def list_courses():
        return coursework.list_courses(path)

    return app
