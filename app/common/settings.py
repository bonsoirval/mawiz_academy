"""Database-backed application settings with documented fallback defaults."""

from app.extensions import db
from app.models import SystemSetting

DEFAULTS = {
    'site_name': 'Mawiz Academy',
    'site_tagline': 'Learn the skill. Experience the work. Become work-ready.',
    'maintenance_mode': '0',
    'registration_enabled': '1',
    'email_verification_required': '1',
    'seo_title': 'Mawiz Academy — Become work-ready',
    'seo_description': 'Mawiz Academy helps learners learn skills, experience realistic work, and become work-ready.',
    'seo_keywords': 'Mawiz Academy, skills, learning, workplace simulation, work-ready',
    'seo_robots': 'index,follow',
    'canonical_base_url': '',
    'deadline_penalty_amount': '5000',
    'deadline_penalty_extension_days': '0',
}

def get_setting(key, default=None):
    row = SystemSetting.query.filter_by(key=key).first()
    return row.value if row else (DEFAULTS.get(key, default))

def get_bool(key, default=False):
    return get_setting(key, '1' if default else '0') in {'1','true','yes','on'}

def set_setting(key, value, description=''):
    row = SystemSetting.query.filter_by(key=key).first()
    if not row:
        row = SystemSetting(key=key, value=str(value), description=description)
        db.session.add(row)
    else:
        row.value = str(value)
        if description:
            row.description = description
    return row
