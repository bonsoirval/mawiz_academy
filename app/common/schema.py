"""Idempotent schema compatibility checks run when the application starts.

Notes
-----
This module supports existing installations that predate the current model. New
tables are created by SQLAlchemy; additive column/index repairs are explicit here.
"""

from sqlalchemy import inspect, text
from app.extensions import db

def ensure_schema():
    """Bring supported existing databases forward to the current application schema.

    Notes
    -----
    This project uses additive, idempotent SQLite/PostgreSQL-compatible schema
    repairs instead of a migration framework. New tables are created by
    ``db.create_all()``, while pre-existing tables receive required columns here.
    The referral block converts the old single-conversion fields to the newer,
    auditable event history without deleting legacy data.
    """
    from app.models import User, Referral, ReferralEvent
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'user' in tables:
        columns = {c['name'] for c in inspector.get_columns('user')}
        if 'username' not in columns:
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN username VARCHAR(80)'))
        if 'signup_coupon_code' not in columns:
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN signup_coupon_code VARCHAR(64)'))
        if 'welcome_email_sent_at' not in columns:
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN welcome_email_sent_at TIMESTAMP'))
        if 'welcome_email_eligible' not in columns:
            # Existing accounts should not receive a retroactive first-login email.
            # New accounts get True from the ORM model default.
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN welcome_email_eligible BOOLEAN NOT NULL DEFAULT FALSE'))
        db.session.commit()
    if 'profile' in tables:
        columns = {c['name'] for c in inspector.get_columns('profile')}
        if 'career_path' not in columns:
            db.session.execute(text('ALTER TABLE profile ADD COLUMN career_path VARCHAR(32)'))
        if 'profile_picture' not in columns:
            db.session.execute(text('ALTER TABLE profile ADD COLUMN profile_picture VARCHAR(255)'))
        db.session.commit()
    if 'course' in tables:
        columns = {c['name'] for c in inspector.get_columns('course')}
        # Older installations predate staged learning management. The admin
        # courses page filters on this field, so add it before ORM queries run.
        if 'stage' not in columns:
            db.session.execute(text("ALTER TABLE course ADD COLUMN stage VARCHAR(32) NOT NULL DEFAULT 'hard_skills'"))
        if 'duration_value' not in columns:
            db.session.execute(text('ALTER TABLE course ADD COLUMN duration_value INTEGER NOT NULL DEFAULT 1'))
        if 'duration_unit' not in columns:
            db.session.execute(text("ALTER TABLE course ADD COLUMN duration_unit VARCHAR(16) NOT NULL DEFAULT 'weeks'"))
        db.session.commit()
    if 'track' in tables:
        columns = {c['name'] for c in inspector.get_columns('track')}
        # Tracks created by earlier versions did not store publication state.
        if 'published' not in columns:
            db.session.execute(text('ALTER TABLE track ADD COLUMN published BOOLEAN NOT NULL DEFAULT FALSE'))
        db.session.commit()
    if 'lesson' in tables:
        columns = {c['name'] for c in inspector.get_columns('lesson')}
        if 'youtube_url' not in columns:
            db.session.execute(text('ALTER TABLE lesson ADD COLUMN youtube_url VARCHAR(255)'))
        db.session.commit()
    # Lesson pages query assignment checkpoint metadata during both GET and POST.
    # Older databases may predate these columns; db.create_all() does not alter tables.
    if 'assignment' in tables:
        columns = {c['name'] for c in inspector.get_columns('assignment')}
        if 'required' not in columns:
            db.session.execute(text('ALTER TABLE assignment ADD COLUMN required BOOLEAN NOT NULL DEFAULT TRUE'))
        if 'published' not in columns:
            db.session.execute(text('ALTER TABLE assignment ADD COLUMN published BOOLEAN NOT NULL DEFAULT FALSE'))
        if 'position' not in columns:
            db.session.execute(text('ALTER TABLE assignment ADD COLUMN position INTEGER NOT NULL DEFAULT 0'))
        db.session.commit()
    if 'quiz' in tables:
        columns = {c['name'] for c in inspector.get_columns('quiz')}
        if 'published' not in columns:
            db.session.execute(text('ALTER TABLE quiz ADD COLUMN published BOOLEAN NOT NULL DEFAULT FALSE'))
        db.session.commit()
    if 'project' in tables:
        columns = {c['name'] for c in inspector.get_columns('project')}
        # Project learning-context links are additive; existing project records remain intact.
        if 'track_id' not in columns:
            db.session.execute(text('ALTER TABLE project ADD COLUMN track_id INTEGER REFERENCES track(id) ON DELETE SET NULL'))
        if 'course_id' not in columns:
            db.session.execute(text('ALTER TABLE project ADD COLUMN course_id INTEGER REFERENCES course(id) ON DELETE SET NULL'))
        if 'module_id' not in columns:
            db.session.execute(text('ALTER TABLE project ADD COLUMN module_id INTEGER REFERENCES "module"(id) ON DELETE SET NULL'))
        if 'lesson_id' not in columns:
            db.session.execute(text('ALTER TABLE project ADD COLUMN lesson_id INTEGER REFERENCES lesson(id) ON DELETE SET NULL'))
        db.session.commit()
    if 'enrollment' in tables:
        columns = {c['name'] for c in inspector.get_columns('enrollment')}
        if 'started_at' not in columns:
            db.session.execute(text('ALTER TABLE enrollment ADD COLUMN started_at TIMESTAMP'))
        if 'deadline_at' not in columns:
            db.session.execute(text('ALTER TABLE enrollment ADD COLUMN deadline_at TIMESTAMP'))
        if 'completed_at' not in columns:
            db.session.execute(text('ALTER TABLE enrollment ADD COLUMN completed_at TIMESTAMP'))
        db.session.commit()
    if 'course_payment' in tables:
        columns = {c['name'] for c in inspector.get_columns('course_payment')}
        if 'purpose' not in columns:
            db.session.execute(text("ALTER TABLE course_payment ADD COLUMN purpose VARCHAR(32) NOT NULL DEFAULT 'course'"))
        if 'extension_days' not in columns:
            db.session.execute(text('ALTER TABLE course_payment ADD COLUMN extension_days INTEGER NOT NULL DEFAULT 0'))
        db.session.commit()
    if 'assignment_submission' in tables:
        columns = {c['name'] for c in inspector.get_columns('assignment_submission')}
        if 'score' not in columns:
            db.session.execute(text('ALTER TABLE assignment_submission ADD COLUMN score INTEGER'))
        if 'max_score' not in columns:
            db.session.execute(text('ALTER TABLE assignment_submission ADD COLUMN max_score INTEGER'))
        if 'grade' not in columns:
            db.session.execute(text('ALTER TABLE assignment_submission ADD COLUMN grade VARCHAR(2)'))
        if 'feedback' not in columns:
            db.session.execute(text("ALTER TABLE assignment_submission ADD COLUMN feedback TEXT DEFAULT ''"))
        if 'marked_at' not in columns:
            db.session.execute(text('ALTER TABLE assignment_submission ADD COLUMN marked_at TIMESTAMP'))
        if 'marked_by_id' not in columns:
            db.session.execute(text('ALTER TABLE assignment_submission ADD COLUMN marked_by_id INTEGER REFERENCES "user"(id) ON DELETE SET NULL'))
        db.session.commit()
    if 'referral' in tables:
        columns = {c['name'] for c in inspector.get_columns('referral')}
        if 'link_token' not in columns:
            db.session.execute(text('ALTER TABLE referral ADD COLUMN link_token VARCHAR(96)'))
        if 'clicks' not in columns:
            db.session.execute(text('ALTER TABLE referral ADD COLUMN clicks INTEGER DEFAULT 0'))
        if 'last_clicked_at' not in columns:
            db.session.execute(text('ALTER TABLE referral ADD COLUMN last_clicked_at TIMESTAMP'))
        db.session.commit()
    db.create_all()
    # Preserve the old one-learner referral attribution as a registration event.
    for referral in Referral.query.filter(Referral.referred_user_id.isnot(None)).all():
        exists = ReferralEvent.query.filter_by(
            referred_user_id=referral.referred_user_id, event_type="registration"
        ).first()
        if not exists:
            db.session.add(ReferralEvent(
                referral_id=referral.id,
                referred_user_id=referral.referred_user_id,
                event_type="registration",
                created_at=referral.completed_at or referral.created_at,
            ))
    for user in User.query.filter((User.username.is_(None)) | (User.username == '')).all():
        base = ''.join(ch.lower() for ch in user.email.split('@')[0] if ch.isalnum() or ch in '._-')[:60] or f'user{user.id}'
        candidate = base
        n = 2
        while User.query.filter(User.username == candidate, User.id != user.id).first():
            candidate = f'{base[:55]}-{n}'
            n += 1
        user.username = candidate
    for referral in Referral.query.all():
        owner = db.session.get(User, referral.referrer_id)
        if owner and (not referral.code or referral.code.startswith("MAWIZ") and referral.code[5:].isdigit()):
            candidate = f"MAWIZ-{owner.username.upper()}"[:80]
            if Referral.query.filter(Referral.code == candidate, Referral.id != referral.id).first():
                import secrets
                candidate = f"MAWIZ-{owner.username.upper()}-{secrets.token_hex(2).upper()}"[:80]
            referral.code = candidate
    for referral in Referral.query.filter((Referral.link_token.is_(None)) | (Referral.link_token == '')).all():
        import secrets
        referral.link_token = secrets.token_urlsafe(18)
        referral.clicks = referral.clicks or 0
    db.session.commit()
    db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_user_username ON "user" (username)'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_profile_career_path ON profile (career_path)'))
    db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_referral_code ON referral (code)'))
    db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_referral_link_token ON referral (link_token)'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_project_track_id ON project (track_id)'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_project_course_id ON project (course_id)'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_project_module_id ON project (module_id)'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_project_lesson_id ON project (lesson_id)'))
    db.session.commit()
