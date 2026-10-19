"""Generated learner portfolio and manually added evidence routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.common.security import permission_required, current_user
from app.extensions import db
from app.models import Course, Enrollment, LearnerSkill, PortfolioItem, Skill, ModuleProgress, LessonProgress
portfolio_bp=Blueprint("portfolio", __name__, url_prefix="/portfolio")


def _legacy_course_skills(course, all_skills):
    """Provide useful generated skills for older courses that have not been tagged yet."""
    if course.skills:
        return list(course.skills)
    curriculum = " ".join(
        [course.title, course.description or ""]
        + [module.title for module in course.modules]
        + [lesson.title + " " + (lesson.body or "") for module in course.modules for lesson in module.lessons]
    ).lower()
    return [skill for skill in all_skills if skill.name.lower() in curriculum]


@portfolio_bp.route("/", methods=["GET","POST"])
@permission_required("portfolio.manage", "learner")
def index():
    user = current_user()
    if request.method=="POST":
        if request.form.get("action") == "generate":
            flash("Your portfolio has been updated from your completed learning and verified skills.", "success")
        else:
            title=request.form.get("title","").strip()[:200]; description=request.form.get("description","").strip(); evidence=request.form.get("evidence_url","").strip()[:1000]
            if title and description:
                db.session.add(PortfolioItem(learner_id=user.id,title=title,description=description,evidence_url=evidence)); db.session.commit(); flash("Portfolio evidence added.","success")
        return redirect(url_for("portfolio.index"))
    completed_courses = Enrollment.query.filter(
        Enrollment.user_id == user.id, Enrollment.progress >= 100
    ).order_by(Enrollment.completed_at.desc(), Enrollment.started_at.desc()).all()
    all_skills = Skill.query.order_by(Skill.name).all()
    skill_sources = {}
    for enrollment in completed_courses:
        for skill in _legacy_course_skills(enrollment.course, all_skills):
            skill_sources.setdefault(skill.id, {"skill": skill, "courses": []})["courses"].append(enrollment.course.title)
    # Skills configured on individual modules/lessons are earned only after the
    # corresponding completion record exists. This is additive to course-level skills.
    completed_module_ids = {row.module_id for row in ModuleProgress.query.filter_by(learner_id=user.id, completed=True).all()}
    if completed_module_ids:
        from app.models import Module
        for module in Module.query.filter(Module.id.in_(completed_module_ids)).all():
            for skill in module.skills:
                entry = skill_sources.setdefault(skill.id, {"skill": skill, "courses": []})
                entry.setdefault("modules", []).append(module.title)
    completed_lesson_ids = {row.lesson_id for row in LessonProgress.query.filter_by(learner_id=user.id, completed=True).all()}
    if completed_lesson_ids:
        from app.models import Lesson
        for lesson in Lesson.query.filter(Lesson.id.in_(completed_lesson_ids)).all():
            for skill in lesson.skills:
                entry = skill_sources.setdefault(skill.id, {"skill": skill, "courses": []})
                entry.setdefault("lessons", []).append(lesson.title)
    for learner_skill in LearnerSkill.query.filter_by(learner_id=user.id).all():
        if learner_skill.level != "Not Assessed" or learner_skill.evidence_count:
            entry = skill_sources.setdefault(learner_skill.skill_id, {"skill": learner_skill.skill, "courses": []})
            entry["level"] = learner_skill.level
            entry["evidence_count"] = learner_skill.evidence_count
    acquired_skills = sorted(skill_sources.values(), key=lambda entry: entry["skill"].name.lower())
    profile = user.profile
    name = " ".join(part for part in [getattr(profile, "first_name", ""), getattr(profile, "last_name", "")] if part).strip() or user.username
    return render_template(
        "portfolio/index.html", items=PortfolioItem.query.filter_by(learner_id=user.id).order_by(PortfolioItem.created_at.desc()).all(),
        completed_courses=completed_courses, acquired_skills=acquired_skills, portfolio_name=name,
    )
