"""One-time schema migration for Learning Path stages.

Notes
-----
Run from the project root with the application environment loaded. This script is
kept for historical installations; review it before using it against production.
"""
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    if "course" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("course")}
        if "stage" not in columns:
            db.session.execute(text("ALTER TABLE course ADD COLUMN stage VARCHAR(32) NOT NULL DEFAULT 'hard_skills'"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_course_stage ON course (stage)"))
    if "project" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("project")}
        if "is_final_program_project" not in columns:
            db.session.execute(text("ALTER TABLE project ADD COLUMN is_final_program_project BOOLEAN NOT NULL DEFAULT 0"))
    db.session.commit()
    print("Learning Path schema migration complete.")
