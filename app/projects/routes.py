"""Published project catalogue and learner project-submission routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from app.common.security import permission_required, current_user
from app.extensions import db
from app.models import Project, ProjectSubmission, Enrollment, Course

projects_bp=Blueprint("projects", __name__, url_prefix="/projects")


def _learner_can_access_project(user, project):
    """Learners can access a scoped project only through an enrolled course/program."""
    if not user or user.role != "learner":
        return True
    enrolled_ids = {row.course_id for row in Enrollment.query.filter_by(user_id=user.id).all()}
    # Keep legacy, unlinked projects available as general projects.
    if not any((project.track_id, project.course_id, project.module_id, project.lesson_id)):
        return True
    course_id = project.course_id
    if not course_id and project.lesson:
        course_id = project.lesson.module.course_id
    if not course_id and project.module:
        course_id = project.module.course_id
    if course_id:
        return course_id in enrolled_ids
    if project.track_id:
        track = project.track
        return bool(track and any(course.id in enrolled_ids for course in track.courses))
    return False


@projects_bp.route("/")
@permission_required("projects.view", "learner", "instructor", "mentor", "admin")
def index():
    user = current_user()
    projects = Project.query.filter_by(published=True).order_by(Project.id.desc()).all()
    if user and user.role == "learner":
        from app.learning.routes import _stage_is_unlocked
        allowed = _stage_is_unlocked(user, "career_path")
        projects = [p for p in projects if _learner_can_access_project(user, p)
                    and (allowed or not p.is_final_program_project)]
    return render_template("projects/index.html", projects=projects)


@projects_bp.route("/<int:project_id>", methods=["GET", "POST"])
@permission_required("projects.submit", "learner")
def detail(project_id):
    project=Project.query.filter_by(id=project_id,published=True).first_or_404()
    user = current_user()
    if user and user.role == "learner" and not _learner_can_access_project(user, project):
        abort(404)
    if user and user.role == "learner" and project.is_final_program_project:
        from app.learning.routes import _stage_is_unlocked
        if not _stage_is_unlocked(user, "career_path"):
            flash("Complete Hard Skills, Soft Skills and Simulation before the final program project.", "warning")
            return redirect(url_for("projects.index"))
    if request.method=="POST":
        evidence_url=request.form.get("evidence_url", "").strip()[:1000]
        notes=request.form.get("notes", "").strip()
        submission=ProjectSubmission(project_id=project.id, learner_id=user.id, evidence_url=evidence_url, notes=notes)
        db.session.add(submission); db.session.commit(); flash("Project submission received for review.","success"); return redirect(url_for("projects.detail", project_id=project.id))
    return render_template("projects/detail.html", project=project)
