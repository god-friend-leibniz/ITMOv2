from studyflow import db, domain


class CourseNotFound(Exception):
    pass


class AssignmentNotFound(Exception):
    pass


class TaskNotFound(Exception):
    pass


class RepositoryNotLinked(Exception):
    pass


def create_course(db_path, name, description):
    return db.insert_course(db_path, name, description)


def list_courses(db_path):
    return db.list_courses(db_path)


def get_course(db_path, course_id):
    course = db.get_course(db_path, course_id)
    if course is None:
        raise CourseNotFound
    return course


def edit_course(db_path, course_id, changes):
    course = db.update_course(db_path, course_id, changes)
    if course is None:
        raise CourseNotFound
    return course


def delete_course(db_path, course_id):
    if not db.delete_course(db_path, course_id):
        raise CourseNotFound


def assignment_result(record):
    result = dict(record)
    completed = result.pop("completed_tasks", 0)
    total = result.pop("total_tasks", 0)
    owner = result.pop("github_owner", None)
    repo = result.pop("github_repo", None)
    repository = {"owner": owner, "repo": repo} if owner is not None else None
    return {**result, "repository": repository, "progress": domain.assignment_progress(completed, total)}


def create_assignment(db_path, course_id, title, description, due_date, repository):
    record = db.insert_assignment(db_path, course_id, title, description, due_date, repository)
    if record is None:
        raise CourseNotFound
    return assignment_result(record)


def list_assignments(db_path, course_id):
    get_course(db_path, course_id)
    return [assignment_result(record) for record in db.list_assignments(db_path, course_id)]


def get_assignment(db_path, assignment_id):
    record = db.get_assignment(db_path, assignment_id)
    if record is None:
        raise AssignmentNotFound
    return assignment_result(record)


async def load_repository_summary(db_path, assignment_id, reader):
    reference = get_assignment(db_path, assignment_id)["repository"]
    if reference is None:
        raise RepositoryNotLinked
    return await reader(reference["owner"], reference["repo"])


def edit_assignment(db_path, assignment_id, changes):
    record = db.update_assignment(db_path, assignment_id, changes)
    if record is None:
        raise AssignmentNotFound
    return assignment_result(record)


def delete_assignment(db_path, assignment_id):
    if not db.delete_assignment(db_path, assignment_id):
        raise AssignmentNotFound


def task_result(record):
    return {**record, "is_completed": bool(record["is_completed"])}


def create_task(db_path, assignment_id, title):
    record = db.insert_task(db_path, assignment_id, title)
    if record is None:
        raise AssignmentNotFound
    return task_result(record)


def list_tasks(db_path, assignment_id):
    get_assignment(db_path, assignment_id)
    return [task_result(record) for record in db.list_tasks(db_path, assignment_id)]


def edit_task(db_path, task_id, changes):
    record = db.update_task(db_path, task_id, changes)
    if record is None:
        raise TaskNotFound
    return task_result(record)


def delete_task(db_path, task_id):
    if not db.delete_task(db_path, task_id):
        raise TaskNotFound
