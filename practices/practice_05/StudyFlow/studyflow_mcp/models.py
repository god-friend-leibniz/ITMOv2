from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from studyflow.domain import repository_name, repository_owner


def utc_timestamp(value):
    datetime.fromisoformat(value)
    return value


UtcTimestamp = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"), AfterValidator(utc_timestamp)]


class RepositoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner: Annotated[str, Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$"), AfterValidator(repository_owner)]
    repo: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$", json_schema_extra={"not": {"enum": [".", ".."]}}), AfterValidator(repository_name)]


class RepositorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: str
    description: str | None
    default_branch: Annotated[str, Field(min_length=1)] | None
    primary_languages: list[Annotated[str, Field(min_length=1)]] = Field(max_length=3, json_schema_extra={"uniqueItems": True})
    last_push_at: UtcTimestamp | None
    fetched_at: UtcTimestamp

    @field_validator("owner")
    @classmethod
    def valid_owner(cls, value):
        repository_owner(value)
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        repository_name(value)
        return value

    @model_validator(mode="after")
    def consistent_summary(self):
        if self.url != f"https://github.com/{self.owner}/{self.name}":
            raise ValueError("Repository URL must match its canonical GitHub identifiers.")
        if len(self.primary_languages) != len(set(self.primary_languages)):
            raise ValueError("Primary languages must be unique.")
        return self


class SummarySuccess(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ok: Literal[True]
    summary: RepositorySummary
    error: None


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    code: Literal["INVALID_INPUT", "REPOSITORY_NOT_FOUND", "REPOSITORY_MOVED", "RATE_LIMITED", "GITHUB_AUTH_ERROR", "GITHUB_UNAVAILABLE", "INTERNAL_ERROR"]
    message: str = Field(min_length=1)
    retry_after_seconds: Annotated[int, Field(ge=0)] | None


class SummaryFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ok: Literal[False]
    summary: None
    error: ToolError


SUMMARY_RESULT = TypeAdapter(Annotated[SummarySuccess | SummaryFailure, Field(discriminator="ok")])
