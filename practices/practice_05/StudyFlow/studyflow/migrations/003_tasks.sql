CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1))
);

CREATE INDEX tasks_assignment_id ON tasks(assignment_id);
