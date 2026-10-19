"""Development seed data for permissions, identities, and sample learning content."""

import json
from datetime import datetime, timedelta, timezone
from app.extensions import db
from app.models import (AssessmentQuestion, Competency, Course, Lesson, Module, Permission, Profile,
                        Project, RolePermission, Simulation, Skill, User, Quiz, QuizQuestion, Enrollment, Track, Assignment, Referral)

PERMISSIONS = {
    "learner.dashboard.view": "View learner dashboard",
    "learner.onboarding.manage": "Complete and update learner onboarding",
    "profile.manage": "View and update personal profile",
    "learner.assessment.take": "Take initial learner assessment",
    "learner.assessment.view": "View assessment results",
    "learning.catalog.view": "View learning catalog",
    "learning.course.view": "View course details",
    "learning.lesson.view": "View lessons",
    "projects.view": "View published projects",
    "projects.submit": "Submit project evidence",
    "simulations.view": "View workplace simulations",
    "simulations.attempt": "Attempt workplace simulations",
    "portfolio.manage": "Manage personal portfolio evidence",
    "admin.dashboard.view": "View administrator dashboard",
    "admin.courses.manage": "Create and manage courses, modules and lessons",
    "admin.courses.publish": "Publish or unpublish courses",
    "admin.quizzes.manage": "Create and manage quizzes and questions",
    "admin.quizzes.publish": "Publish or unpublish quizzes",
    "learning.enrollment.create": "Enroll in a published course",
    "learning.quiz.take": "Take published quizzes",
}

ROLE_GRANTS = {
    "learner": [k for k in PERMISSIONS if not k.startswith("admin.")],
    "instructor": ["profile.manage", "learner.dashboard.view", "learning.catalog.view", "learning.course.view", "learning.lesson.view", "learning.enrollment.create", "learning.quiz.take", "projects.view", "simulations.view", "admin.courses.manage", "admin.courses.publish", "admin.quizzes.manage", "admin.quizzes.publish"],
    "mentor": ["profile.manage", "learner.dashboard.view", "learning.catalog.view", "learning.course.view", "learning.lesson.view", "projects.view", "simulations.view"],
    "admin": list(PERMISSIONS),
}


def seed():
    for code, description in PERMISSIONS.items():
        permission = Permission.query.filter_by(code=code).first()
        if not permission:
            permission = Permission(code=code, description=description)
            db.session.add(permission)
            db.session.flush()
    # Keep role grants in sync with the declared role policy (including removals).
    for role, codes in ROLE_GRANTS.items():
        RolePermission.query.filter_by(role=role).delete(synchronize_session=False)
        for code in codes:
            permission = Permission.query.filter_by(code=code).first()
            if permission:
                db.session.add(RolePermission(role=role, permission_id=permission.id))

    skills_data = [
        ("JavaScript", "technical"), ("Python", "technical"), ("SQL", "technical"), ("API Development", "technical"),
        ("Data Analysis", "technical"), ("Professional Communication", "professional"), ("Problem Solving", "professional"),
        ("Accountability", "professional"), ("Time Management", "professional")]
    for name, category in skills_data:
        if not Skill.query.filter_by(name=name).first():
            db.session.add(Skill(name=name, category=category, description=f"Mawiz {category} capability: {name}."))

    admin = User.query.filter_by(email="admin@mawiz.local").first()
    if not admin:
        admin=User(email="admin@mawiz.local", username="admin", role="admin", email_verified=True)
        admin.set_password("ChangeMe!Admin123"); admin.profile=Profile(first_name="Mawiz",last_name="Admin",onboarding_completed=True)
        db.session.add(admin)
    learner = User.query.filter_by(email="learner@mawiz.local").first()
    if not learner:
        learner=User(email="learner@mawiz.local", username="demo-learner", role="learner", email_verified=True)
        learner.set_password("ChangeMe!Learner123"); learner.profile=Profile(first_name="Demo",last_name="Learner",career_goal="Backend Developer",experience_level="Beginner",onboarding_completed=True)
        db.session.add(learner)

    # Dedicated seeded identities for the teaching and learner-support workspaces.
    demo_staff = [
        ("instructor@mawiz.local", "demo-instructor", "instructor", "ChangeMe!Instructor123", "Demo", "Instructor", "Course facilitator · Backend Development"),
        ("mentor@mawiz.local", "demo-mentor", "mentor", "ChangeMe!Mentor123", "Demo", "Mentor", "Learner mentor · Career readiness"),
    ]
    for email, username, role, password, first_name, last_name, headline in demo_staff:
        staff = User.query.filter_by(email=email).first()
        if not staff:
            staff = User(email=email, username=username, role=role, email_verified=True, is_active=True)
            staff.set_password(password)
            staff.profile = Profile(first_name=first_name, last_name=last_name, headline=headline, onboarding_completed=True)
            db.session.add(staff)
        else:
            staff.role = role
            staff.is_active = True
            staff.email_verified = True
            if not staff.profile:
                staff.profile = Profile(first_name=first_name, last_name=last_name, headline=headline, onboarding_completed=True)
            else:
                staff.profile.headline = staff.profile.headline or headline

    import secrets
    for existing_learner in User.query.filter_by(role="learner").all():
        if not existing_learner.username:
            existing_learner.username = f"learner-{existing_learner.id}"
        existing = Referral.query.filter_by(referrer_id=existing_learner.id).first()
        if not existing:
            code = f"MAWIZ-{existing_learner.username.upper()}"[:80]
            if Referral.query.filter_by(code=code).first():
                code = f"MAWIZ-{existing_learner.username.upper()}-{secrets.token_hex(2).upper()}"[:80]
            db.session.add(Referral(referrer_id=existing_learner.id, code=code, link_token=secrets.token_urlsafe(18), status="active"))

    track = Track.query.filter_by(slug="backend-development").first()
    if not track:
        track = Track(title="Backend Development", slug="backend-development", description="A structured path from backend foundations to workplace-ready delivery.", published=True)
        db.session.add(track)
        db.session.flush()

    course=Course.query.filter_by(slug="backend-development-foundations").first()
    if not course:
        course=Course(title="Backend Development Foundations",slug="backend-development-foundations",career_goal="Backend Developer",description="A practical pathway from backend fundamentals to deployable API projects.",published=True)
        m1=Module(title="JavaScript Foundations",position=1); m1.lessons=[Lesson(title="Programming foundations",body="Understand variables, functions, control flow and practical problem solving.",position=1),Lesson(title="Working with APIs",body="Learn request/response concepts and API fundamentals.",position=2)]
        m2=Module(title="Node.js and Express",position=2); m2.lessons=[Lesson(title="Build your first API",body="Create routes, validate input and return structured responses.",position=1)]
        course.modules=[m1,m2]; db.session.add(course)
    if course and track and track not in course.tracks:
        track.courses.append(course)
    if course:
        course.skills = Skill.query.filter(Skill.name.in_([
            "JavaScript", "API Development", "Problem Solving",
        ])).order_by(Skill.name).all()
    if course and learner and not Enrollment.query.filter_by(user_id=learner.id, course_id=course.id).first():
        db.session.add(Enrollment(user_id=learner.id, course_id=course.id, progress=0))
    first_lesson = Lesson.query.order_by(Lesson.id).first()
    if first_lesson and not Quiz.query.filter_by(lesson_id=first_lesson.id).first():
        quiz = Quiz(lesson_id=first_lesson.id, title="Programming Foundations Checkpoint", instructions="Choose the best answer for each question.", passing_score=70, published=True)
        quiz.questions = [
            QuizQuestion(prompt="Which approach is best when requirements are unclear?", options_json=json.dumps(["Guess silently", "Clarify the expected outcome and constraints", "Ignore the requirement", "Start coding without context"]), correct_option="Clarify the expected outcome and constraints", explanation="Clarification reduces rework and demonstrates professional problem solving.", position=1),
            QuizQuestion(prompt="Which practice best supports maintainable backend code?", options_json=json.dumps(["Clear structure and validation", "No validation", "Hard-coded secrets", "Duplicated logic everywhere"]), correct_option="Clear structure and validation", explanation="Validation and clear structure improve reliability and maintainability.", position=2),
        ]
        db.session.add(quiz)
    if first_lesson and not Assignment.query.filter_by(lesson_id=first_lesson.id).first():
        db.session.add(Assignment(lesson_id=first_lesson.id, title="Foundations reflection", instructions="Explain how you would clarify an ambiguous backend requirement before implementation.", required=True, published=True, position=1))
    if not Project.query.first():
        db.session.add(Project(title="Customer Management API",problem="A small business needs a secure customer management service.",requirements="Build an API with authentication, validation, persistence, documentation and deployment evidence.",deadline=datetime.now(timezone.utc)+timedelta(days=14),published=True))
    if not Simulation.query.first():
        db.session.add(Simulation(title="Client Requirement Clarification",scenario="A client sends an unclear request and expects a quick implementation.",task="Write the response you would send before beginning development. Clarify requirements, scope, risks and next steps.",published=True))
    for name, description in [("Professional Communication","Clarity, tone, structure and appropriate escalation."),("Accountability","Ownership, progress updates, deadline handling and transparency."),("Problem Solving","Clarifying ambiguity, reasoning through constraints and proposing practical solutions.")]:
        if not Competency.query.filter_by(name=name).first(): db.session.add(Competency(name=name,description=description))

    if AssessmentQuestion.query.count() == 0:
        questions = [
            ("Which response best handles an unclear client requirement?", ["Start coding immediately", "Ask focused clarifying questions and confirm scope", "Ignore the ambiguity", "Wait until the deadline"], "Ask focused clarifying questions and confirm scope", "Professional Communication"),
            ("A deadline is at risk. What should you do first?", ["Hide the problem", "Stop communicating", "Share a concise progress update, impact and recovery plan", "Delete the task"], "Share a concise progress update, impact and recovery plan", "Accountability"),
            ("Which HTTP method is normally used to create a resource?", ["GET", "POST", "DELETE", "HEAD"], "POST", "API Development"),
            ("What is the best first step when a technical task is ambiguous?", ["Guess silently", "Clarify assumptions and expected outcome", "Skip it", "Copy another solution"], "Clarify assumptions and expected outcome", "Problem Solving"),
            ("Which practice best protects a password in a database?", ["Plain text", "Reversible encryption only", "A strong password hash such as Argon2", "A browser cookie"], "A strong password hash such as Argon2", "Security"),
        ]
        for prompt, options, correct, category in questions:
            db.session.add(AssessmentQuestion(prompt=prompt, category=category, options_json=json.dumps(options), correct_option=correct, explanation="Choose the option that best reflects practical, secure and professional work.", points=1))
    db.session.commit()
