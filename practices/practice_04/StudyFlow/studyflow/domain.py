def course_name(value: str) -> str:
    name = value.strip()
    if not 1 <= len(name) <= 200:
        raise ValueError("Course name must contain 1 to 200 characters.")
    return name
