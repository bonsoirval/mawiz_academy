"""SQLAlchemy data model for identity, learning, payments, and referral activity."""

from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from secrets import token_hex
from .extensions import db

ph = PasswordHasher()

ROLE_NAMES = ("learner", "instructor", "mentor", "admin")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    signup_coupon_code = db.Column(db.String(64), index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="learner", index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    password_changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = db.Column(db.DateTime)
    welcome_email_sent_at = db.Column(db.DateTime)
    welcome_email_eligible = db.Column(db.Boolean, nullable=False, default=True)
    profile = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")
    direct_permissions = db.relationship("UserPermission", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = ph.hash(password)
        self.password_changed_at = datetime.now(timezone.utc)

    def check_password(self, password):
        try:
            valid = ph.verify(self.password_hash, password)
            if valid and ph.check_needs_rehash(self.password_hash):
                self.set_password(password)
            return valid
        except (VerifyMismatchError, ValueError):
            return False


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(150))
    education = db.Column(db.String(200))
    employment = db.Column(db.String(200))
    career_goal = db.Column(db.String(150))
    career_path = db.Column(db.String(32), index=True)
    experience_level = db.Column(db.String(50))
    headline = db.Column(db.String(255))
    profile_picture = db.Column(db.String(255))
    onboarding_completed = db.Column(db.Boolean, default=False, nullable=False)
    onboarding_completed_at = db.Column(db.DateTime)


class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(120), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)


class RolePermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(32), nullable=False, index=True)
    permission_id = db.Column(db.Integer, db.ForeignKey("permission.id", ondelete="CASCADE"), nullable=False)
    permission = db.relationship("Permission")
    __table_args__ = (db.UniqueConstraint("role", "permission_id", name="uq_role_permission"),)


class UserPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey("permission.id", ondelete="CASCADE"), nullable=False)
    allowed = db.Column(db.Boolean, nullable=False, default=True)
    permission = db.relationship("Permission")
    __table_args__ = (db.UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),)


class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    category = db.Column(db.String(80), nullable=False, default="technical")
    description = db.Column(db.Text, default="")


class LearnerSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), nullable=False)
    level = db.Column(db.String(40), nullable=False, default="Not Assessed")
    evidence_count = db.Column(db.Integer, nullable=False, default=0)
    skill = db.relationship("Skill")
    __table_args__ = (db.UniqueConstraint("learner_id", "skill_id", name="uq_learner_skill"),)


module_skill = db.Table(
    "module_skill",
    db.Column("module_id", db.Integer, db.ForeignKey("module.id", ondelete="CASCADE"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), primary_key=True),
)

lesson_skill = db.Table(
    "lesson_skill",
    db.Column("lesson_id", db.Integer, db.ForeignKey("lesson.id", ondelete="CASCADE"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), primary_key=True),
)

simulation_track = db.Table(
    "simulation_track",
    db.Column("simulation_id", db.Integer, db.ForeignKey("simulation.id", ondelete="CASCADE"), primary_key=True),
    db.Column("track_id", db.Integer, db.ForeignKey("track.id", ondelete="CASCADE"), primary_key=True),
)
simulation_course = db.Table(
    "simulation_course",
    db.Column("simulation_id", db.Integer, db.ForeignKey("simulation.id", ondelete="CASCADE"), primary_key=True),
    db.Column("course_id", db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), primary_key=True),
)
simulation_module = db.Table(
    "simulation_module",
    db.Column("simulation_id", db.Integer, db.ForeignKey("simulation.id", ondelete="CASCADE"), primary_key=True),
    db.Column("module_id", db.Integer, db.ForeignKey("module.id", ondelete="CASCADE"), primary_key=True),
)
simulation_lesson = db.Table(
    "simulation_lesson",
    db.Column("simulation_id", db.Integer, db.ForeignKey("simulation.id", ondelete="CASCADE"), primary_key=True),
    db.Column("lesson_id", db.Integer, db.ForeignKey("lesson.id", ondelete="CASCADE"), primary_key=True),
)

course_skill = db.Table(
    "course_skill",
    db.Column("course_id", db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skill.id", ondelete="CASCADE"), primary_key=True),
)


class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    description = db.Column(db.Text, default="")
    published = db.Column(db.Boolean, default=False, nullable=False)
    courses = db.relationship("Course", secondary="track_course", back_populates="tracks", order_by="Course.title")


class TrackCourse(db.Model):
    __tablename__ = "track_course"
    track_id = db.Column(db.Integer, db.ForeignKey("track.id", ondelete="CASCADE"), primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), primary_key=True)


class CoursePrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), unique=True, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default="NGN")


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    career_goal = db.Column(db.String(150))
    # Ordered program stage: hard_skills -> soft_skills -> simulation -> career_path
    stage = db.Column(db.String(32), nullable=False, default="hard_skills", index=True)
    duration_value = db.Column(db.Integer, nullable=False, default=1)
    duration_unit = db.Column(db.String(16), nullable=False, default="weeks")
    published = db.Column(db.Boolean, default=False, nullable=False)
    tracks = db.relationship("Track", secondary="track_course", back_populates="courses")
    price = db.relationship("CoursePrice", backref="course", uselist=False, cascade="all, delete-orphan")
    modules = db.relationship("Module", backref="course", cascade="all, delete-orphan", order_by="Module.position")
    skills = db.relationship("Skill", secondary=course_skill, order_by="Skill.name")

    @property
    def duration_label(self):
        value = self.duration_value or 1
        unit = self.duration_unit or "weeks"
        return f"{value} {unit[:-1] if value == 1 and unit.endswith('s') else unit}"


class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    position = db.Column(db.Integer, default=0)
    lessons = db.relationship("Lesson", backref="module", cascade="all, delete-orphan", order_by="Lesson.position")
    skills = db.relationship("Skill", secondary=module_skill, order_by="Skill.name")
    assignments = db.relationship("Assignment", backref="module", foreign_keys="Assignment.module_id", cascade="all, delete-orphan", order_by="Assignment.position")
    quiz_links = db.relationship("ModuleQuiz", backref="module", cascade="all, delete-orphan")


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, default="")
    youtube_url = db.Column(db.String(255))
    position = db.Column(db.Integer, default=0)
    assignments = db.relationship("Assignment", backref="lesson", foreign_keys="Assignment.lesson_id", cascade="all, delete-orphan", order_by="Assignment.position")
    quizzes = db.relationship("Quiz", back_populates="lesson", foreign_keys="Quiz.lesson_id", cascade="all, delete-orphan", order_by="Quiz.id")
    skills = db.relationship("Skill", secondary=lesson_skill, order_by="Skill.name")


class ModuleProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id", ondelete="CASCADE"), nullable=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint("learner_id", "module_id", name="uq_module_progress"),)


class LessonProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id", ondelete="CASCADE"), nullable=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (db.UniqueConstraint("learner_id", "lesson_id", name="uq_lesson_progress"),)


class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    instructions = db.Column(db.Text, default="")
    passing_score = db.Column(db.Integer, nullable=False, default=70)
    published = db.Column(db.Boolean, default=False, nullable=False)
    lesson = db.relationship("Lesson", back_populates="quizzes", foreign_keys=[lesson_id])
    questions = db.relationship("QuizQuestion", backref="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.position")
    module_links = db.relationship("ModuleQuiz", backref="quiz", cascade="all, delete-orphan")


class ModuleQuiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id", ondelete="CASCADE"), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (db.UniqueConstraint("module_id", "quiz_id", name="uq_module_quiz"),)


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    instructions = db.Column(db.Text, default="")
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id", ondelete="CASCADE"), nullable=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id", ondelete="CASCADE"), nullable=True)
    required = db.Column(db.Boolean, nullable=False, default=True)
    published = db.Column(db.Boolean, nullable=False, default=False)
    position = db.Column(db.Integer, default=0)


class AssignmentSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    response = db.Column(db.Text, default="")
    evidence_url = db.Column(db.String(1000))
    status = db.Column(db.String(30), nullable=False, default="submitted")
    score = db.Column(db.Integer)
    max_score = db.Column(db.Integer)
    grade = db.Column(db.String(2))
    feedback = db.Column(db.Text, default="")
    marked_at = db.Column(db.DateTime)
    marked_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (db.UniqueConstraint("assignment_id", "learner_id", name="uq_assignment_submission"),)


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(255), nullable=False)
    explanation = db.Column(db.Text, default="")
    points = db.Column(db.Integer, nullable=False, default=1)
    position = db.Column(db.Integer, default=0)


class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id", ondelete="CASCADE"), nullable=False)
    score = db.Column(db.Integer, nullable=False, default=0)
    max_score = db.Column(db.Integer, nullable=False, default=0)
    passed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    quiz = db.relationship("Quiz", foreign_keys=[quiz_id])
    responses = db.relationship("QuizResponse", backref="attempt", cascade="all, delete-orphan")


class QuizResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("quiz_attempt.id", ondelete="CASCADE"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_question.id", ondelete="CASCADE"), nullable=False)
    selected_option = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)


class EmailAuthChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    code_hash = db.Column(db.String(128), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    # The learning catalog and course page templates access enrollment.course.
    course = db.relationship("Course", foreign_keys=[course_id])
    progress = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    deadline_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course"),)


class CoursePayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupon.id", ondelete="SET NULL"))
    reference = db.Column(db.String(80), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="NGN")
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    purpose = db.Column(db.String(32), nullable=False, default="course")
    extension_days = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    paystack_transaction_id = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    paid_at = db.Column(db.DateTime)
    user = db.relationship("User")
    course = db.relationship("Course")


class TrackRecommendationAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_hash = db.Column(db.String(128), nullable=False, index=True)
    recommended_track_id = db.Column(db.Integer, db.ForeignKey("track.id", ondelete="SET NULL"), nullable=True, index=True)
    scores_json = db.Column(db.Text, nullable=False, default="{}")
    answers_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    recommended_track = db.relationship("Track")


class AssessmentQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(40), nullable=False, default="beginner")
    options_json = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(255), nullable=False)
    explanation = db.Column(db.Text, default="")
    points = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, default=True, nullable=False)


class AssessmentAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    assessment_type = db.Column(db.String(40), nullable=False, default="initial")
    score = db.Column(db.Integer, nullable=False, default=0)
    max_score = db.Column(db.Integer, nullable=False, default=0)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    responses = db.relationship("AssessmentResponse", backref="attempt", cascade="all, delete-orphan")


class AssessmentResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("assessment_attempt.id", ondelete="CASCADE"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("assessment_question.id", ondelete="CASCADE"), nullable=False)
    selected_option = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    problem = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.DateTime)
    published = db.Column(db.Boolean, default=False, nullable=False)
    # Optional learning-context links. Module/lesson links also retain course context.
    track_id = db.Column(db.Integer, db.ForeignKey("track.id", ondelete="SET NULL"), index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="SET NULL"), index=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id", ondelete="SET NULL"), index=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id", ondelete="SET NULL"), index=True)
    track = db.relationship("Track", foreign_keys=[track_id])
    course = db.relationship("Course", foreign_keys=[course_id])
    module = db.relationship("Module", foreign_keys=[module_id])
    lesson = db.relationship("Lesson", foreign_keys=[lesson_id])
    # Module assignments are the in-course projects; this flag marks the capstone.
    is_final_program_project = db.Column(db.Boolean, default=False, nullable=False)


class ProjectSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    evidence_url = db.Column(db.String(1000))
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), default="pending")
    submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Competency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)


class Simulation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    scenario = db.Column(db.Text, nullable=False)
    task = db.Column(db.Text, nullable=False)
    published = db.Column(db.Boolean, default=False, nullable=False)
    tracks = db.relationship("Track", secondary=simulation_track, order_by="Track.title")
    courses = db.relationship("Course", secondary=simulation_course, order_by="Course.title")
    modules = db.relationship("Module", secondary=simulation_module, order_by="Module.title")
    lessons = db.relationship("Lesson", secondary=simulation_lesson, order_by="Lesson.title")


class CareerPathContent(db.Model):
    """Published learning resources for one of the learner's selected career paths."""
    id = db.Column(db.Integer, primary_key=True)
    path_name = db.Column(db.String(32), nullable=False, index=True)  # entrepreneurship or job
    title = db.Column(db.String(200), nullable=False)
    content_type = db.Column(db.String(24), nullable=False, default="text")  # text, video, flashcards
    body = db.Column(db.Text, default="")
    video_url = db.Column(db.String(1000))
    flashcards_json = db.Column(db.Text, default="[]")
    position = db.Column(db.Integer, nullable=False, default=0)
    published = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SimulationAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    simulation_id = db.Column(db.Integer, db.ForeignKey("simulation.id", ondelete="CASCADE"), nullable=False)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    response = db.Column(db.Text, nullable=False)
    score = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class PortfolioItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence_url = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Referral(db.Model):
    """Reusable referral code and link owned by a learner.

    Notes
    -----
    This table represents the shareable code, not an individual conversion.
    Registrations and purchases belong in :class:`ReferralEvent`, allowing one
    code to be used by multiple people. ``referred_user_id`` and
    ``completed_at`` are retained only to support databases created before the
    event model was introduced.
    """
    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    referred_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    link_token = db.Column(db.String(96), nullable=False, unique=True, index=True)
    clicks = db.Column(db.Integer, nullable=False, default=0)
    last_clicked_at = db.Column(db.DateTime)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    reward_value = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = db.Column(db.DateTime)


class ReferralEvent(db.Model):
    """An immutable registration or purchase credited to a referral code.

    Notes
    -----
    Keeping event records instead of counters makes referral reporting auditable.
    ``payment_id`` is unique so the Paystack callback and webhook cannot credit
    the same payment twice. Additional purchasable material types should create a
    purchase event with their own material reference before access is granted.
    """
    id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(db.Integer, db.ForeignKey("referral.id", ondelete="CASCADE"), nullable=False, index=True)
    referred_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="SET NULL"), nullable=True, index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("course_payment.id", ondelete="SET NULL"), nullable=True, unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(3), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    referral = db.relationship("Referral", backref=db.backref("events", cascade="all, delete-orphan"))
    referred_user = db.relationship("User", foreign_keys=[referred_user_id])
    course = db.relationship("Course", foreign_keys=[course_id])
    payment = db.relationship("CoursePayment", foreign_keys=[payment_id])
    __table_args__ = (
        db.UniqueConstraint("referred_user_id", "event_type", name="uq_referral_event_user_type"),
    )


class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), default="")
    discount_type = db.Column(db.String(20), nullable=False, default="percent")
    discount_value = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    minimum_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    max_redemptions = db.Column(db.Integer)
    per_user_limit = db.Column(db.Integer, nullable=False, default=1)
    starts_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    redemptions = db.relationship("CouponRedemption", backref="coupon", cascade="all, delete-orphan")


class CouponRedemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupon.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="SET NULL"), nullable=True)
    amount_before = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_after = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="applied")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ReferralClick(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(db.Integer, db.ForeignKey("referral.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_hash = db.Column(db.String(128))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    referral = db.relationship("Referral", backref=db.backref("click_events", cascade="all, delete-orphan"))


class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False, default="")
    description = db.Column(db.String(255), default="")
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
