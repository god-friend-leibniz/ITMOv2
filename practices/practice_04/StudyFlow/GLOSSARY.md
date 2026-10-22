# StudyFlow

StudyFlow helps a student organize university coursework and see how much of each assignment's checklist is complete.

## Language

**Course**:
A university subject that groups a student's assignments.
_Avoid_: Project, workspace

**Assignment**:
A piece of coursework belonging to exactly one course, optionally with a due date and a GitHub repository reference.
_Avoid_: Task, issue

**Task**:
A single checklist item belonging to exactly one assignment, either complete or incomplete.
_Avoid_: Sub-assignment, GitHub issue

**Checklist**:
The collection of tasks belonging to an assignment; an assignment may have an empty checklist.
_Avoid_: Separate task list, workflow

**Assignment progress**:
The proportion of an assignment's tasks that are complete; an empty checklist has zero progress. It measures checklist completion, not submission, grading, or GitHub activity.
_Avoid_: Grade, submission status

**Repository reference**:
The GitHub owner and repository name identifying an assignment's optional supporting repository. An assignment has at most one reference, and the same repository may support several assignments.
_Avoid_: Owned repository, coursework entity

**Repository summary**:
A current view of a referenced GitHub repository's description, default branch, languages, and last push time.
_Avoid_: Assignment progress, synchronization
