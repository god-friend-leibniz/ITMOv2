from studyflow import db


def create_course(db_path, name, description):
    return db.insert_course(db_path, name, description)


def list_courses(db_path):
    return db.list_courses(db_path)
