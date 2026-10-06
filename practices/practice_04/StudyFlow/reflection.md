# StudyFlow reflection

## First vertical slice, 2026-10-06

The domain-modeling design kept this slice focused: a Course has identity, a name, and a description. The implementation uses ordinary functions, concrete SQLite queries, and the existing FastAPI/template boundary. Assignment, task, and GitHub behavior remains for later slices.

TDD exposed real observable gaps: absent API/page routes, invalid coursework accepted or reported incorrectly, a browser form that did not save, and missing request-failure feedback. Each behavior was exercised through HTTP, the browser, or the hook command before its implementation. [The observed sequence](docs/evidence/first-slice.md) records red and green outcomes.

The automatic hook required more care than creating a configuration file. Its trust state was still untrusted after the initial UI step, and the running editing session did not adopt the new hook. Persisting the user's exact approval and testing fresh runtimes established actual synchronous execution, including a deliberate HTTP-status regression and repair. [Hook evidence](docs/evidence/hook.md) distinguishes these runtime events from manual handler calls. This is the main lesson from the environment work: registration, trust, and actual invocation must each be checked.

SQL migrations were placed inside the Python package so wheel installation includes them alongside templates and static assets. An installed-wheel smoke check outside the source directory verified these resources. This changes a file location, without changing the architecture or domain decisions.

Current limitations: only course creation/listing is implemented; automatic hook activation must be reviewed in each new workspace; browser tests run explicitly rather than on every edit. MCP success/error demonstrations and the remaining CRUD/progress features belong to later steps, and this reflection should be extended with their actual outcomes.
