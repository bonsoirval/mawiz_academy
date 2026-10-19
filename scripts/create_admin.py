"""Create an administrator account without storing credentials in source control.

Notes
-----
Run from the project root with the same environment configuration as the app.
"""

import argparse
from getpass import getpass

from email_validator import validate_email, EmailNotValidError

from app import create_app
from app.extensions import db
from app.models import User, Profile


def prompt_email() -> str:
    while True:
        value = input("Admin email: ").strip()
        try:
            return validate_email(value.lower()).normalized
        except EmailNotValidError as exc:
            print(f"Invalid email: {exc}")


def prompt_password() -> str:
    while True:
        password = getpass("Admin password (12+ chars, uppercase + number): ")
        confirmation = getpass("Confirm admin password: ")
        if password != confirmation:
            print("Passwords do not match. Try again.")
            continue
        if len(password) < 12 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
            print("Password must be at least 12 characters and contain an uppercase letter and number.")
            continue
        return password


parser = argparse.ArgumentParser(description="Create a Mawiz administrator account securely.")
parser.add_argument("--email", help="Administrator email; if omitted, prompt interactively")
parser.add_argument("--first-name", default="Mawiz")
parser.add_argument("--last-name", default="Administrator")
args = parser.parse_args()

email = args.email.strip().lower() if args.email else prompt_email()
try:
    email = validate_email(email).normalized
except EmailNotValidError as exc:
    raise SystemExit(f"Invalid email: {exc}")

password = prompt_password()
app = create_app()
with app.app_context():
    if User.query.filter_by(email=email).first():
        raise SystemExit("A user with that email already exists.")
    base = "".join(c.lower() for c in (args.first_name + "-" + args.last_name) if c.isalnum() or c in "-_")[:60] or "admin"
    username = base
    suffix = 2
    while User.query.filter_by(username=username).first():
        username = f"{base[:55]}-{suffix}"
        suffix += 1
    user = User(email=email, username=username, role="admin", email_verified=True)
    user.set_password(password)
    user.profile = Profile(
        first_name=args.first_name[:100],
        last_name=args.last_name[:100],
        onboarding_completed=True,
    )
    db.session.add(user)
    db.session.commit()
    print(f"Created administrator: {email}")
