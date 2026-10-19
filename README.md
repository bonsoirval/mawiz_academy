# Mawiz Academy — Secure Flask MVP Foundation + Phase 2

Mawiz Academy is being built around **Assess → Learn → Practice → Build → Simulate → Prove**. This repository now contains the secure application foundation plus the Phase 2 learner identity/onboarding flow.

## Completed in this build

### Foundation
- Flask application factory and modular blueprints
- PostgreSQL/SQLite SQLAlchemy persistence
- Argon2 password hashing
- CSRF protection
- Rate limiting
- Secure session configuration
- Security headers and CSP
- Audit events
- Server-side RBAC
- Permission-based access control (PBAC) with role grants and direct user overrides
- Admin Makefile for common operational tasks

### Phase 2 — Identity + Learner Setup
- Registration with strong password rules
- Email verification token flow
- Development mail sink (links are written to `instance/dev-mail.log`; tokens are never rendered into the page)
- Login with session rotation
- Password reset request + expiring reset token
- Learner profile/onboarding
- Career-goal selection
- Experience-level selection
- Existing-skill selection
- Initial skills assessment
- Assessment scoring and baseline capability level
- Career-goal-aware course recommendations

## The login-page hash issue

The string you reported was a signed Flask-WTF CSRF token. The previous templates used:

```jinja2
{{ csrf_token() }}
```

as visible form content. That was incorrect presentation. It has been changed to:

```jinja2
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

The CSRF token is therefore still generated and validated, but it is no longer displayed as text on the login page. All POST forms were corrected consistently.

## Permission model

A request can now be protected by both:

1. **RBAC** — the user's role (`learner`, `instructor`, `mentor`, `admin`)
2. **PBAC** — an explicit permission such as `projects.submit` or `admin.dashboard.view`

Direct user permission records can grant or deny a specific permission. A direct deny overrides a role grant. Admin retains platform-wide access by default, while explicit role/permission decorators can still constrain an endpoint.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set a strong `SECRET_KEY` in `.env`, then:

```bash
make init-db
make seed
make run
```

### Deployment copy without comments

Keep commented source in version control. When a deployment process requires a
comment-free Python copy, create it outside the repository and deploy that copy:

```bash
make strip-comments OUTPUT=/tmp/mawiz-deploy
```

The command preserves strings and docstrings, copies non-Python assets unchanged,
and never modifies the working tree. Run the normal test suite against the output
directory before deploying it.

Open `http://127.0.0.1:5000`.

### Demo accounts

- Admin: `admin@mawiz.local` / `ChangeMe!Admin123`
- Learner: `learner@mawiz.local` / `ChangeMe!Learner123`

Change demo credentials before any real deployment.

### Development verification/reset links

Because this foundation does not yet connect to a real transactional email provider, verification and password-reset links are written to the development mail sink:

```bash
make show-dev-mail
```

A production email provider should replace this sink before pilot launch.

## Paystack payments

Paid-course checkout uses Paystack's hosted checkout and server-side transaction verification. Create your local environment file from `.env.example` (or run `make dev`), then add a Paystack **test secret key** from your Paystack dashboard:

```text
PAYSTACK_SECRET_KEY=sk_test_your_actual_test_secret_key
PAYSTACK_API_BASE_URL=https://api.paystack.co
PAYSTACK_TIMEOUT_SECONDS=15
```

The learner opens a course and selects **Pay securely with Paystack**. Mawiz calculates the amount from the stored course price, creates a pending payment record, and redirects to Paystack's hosted checkout. The callback verifies transaction status, reference, amount, currency, and customer email before enrollment. A signed webhook independently confirms the transaction and safely handles repeated delivery. The learner can see their own records under **Payment History**; administrators can review recent records under **Admin → Payments**.

Use the same API base URL in test and live modes; the key controls the mode. Test with the Paystack test key and test payment details before launch. When moving to production, replace the test key with a live key in your deployment secret manager. Do not expose or commit either key. Ensure the deployed site uses HTTPS and the public callback URL resolves to the correct deployment.

In the Paystack dashboard, set the webhook URL to:

```text
https://your-domain.example/learning/payments/paystack/webhook
```

The callback verifies the transaction before granting enrollment. The webhook independently verifies Paystack's SHA-512 signature and re-verifies the transaction, so access is not granted from a browser redirect or webhook payload alone.

## Makefile administration

```text
make install       Install dependencies
make dev           Prepare .env
make init-db       Create database tables
make seed          Seed demo data and permissions
make reset-db      Recreate local SQLite DB
make run           Start Flask
make test          Run tests
make coverage      Run coverage
make compile       Compile-check Python
make security      Compile + auth/security tests
a make docker-up   Start Docker services
make docker-down   Stop Docker services
make show-dev-mail Show development email links
```

## Security notes

Production should use PostgreSQL, Redis-backed rate limiting, HTTPS, a secret manager, private object storage, real transactional email, centralized logs/monitoring, backups, dependency scanning, and a reverse proxy with a tightly controlled trusted-proxy configuration.

This repository is still an MVP implementation, not a claim of production certification or a substitute for a formal security review.

## Phase 3: LMS + authentication hardening

Phase 3 adds the core learning engine:

- Published course catalog and learner enrollment
- Lesson completion and course progress tracking
- Quizzes, questions, attempts, scoring and pass thresholds
- Instructor/admin course, module and lesson authoring
- Quiz authoring and publishing
- Permission checks for enrollment, quizzes and content management
- Secure email verification toggle
- Secure email 2FA toggle with expiring, single-use, attempt-limited codes
- Console development mail sink or SMTP production mail backend
- Administrative `make create-admin` command
- Static `make security-audit` command
- Audit-backed `make intrusion-detection` command

### Authentication toggles

Set these in `.env`:

```text
REQUIRE_EMAIL_VERIFICATION=true
REQUIRE_EMAIL_2FA=false
```

For production email delivery, use:

```text
MAIL_BACKEND=smtp
MAIL_FROM=no-reply@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_USE_TLS=true
```

### Administration

Create an administrator without putting the password in shell history:

```bash
make create-admin EMAIL=admin@example.com FIRST_NAME=Mawiz LAST_NAME=Admin
```

The command securely prompts for the password.

### Security operations

```bash
make security-audit
make intrusion-detection
make security
```

The intrusion detector is intentionally a lightweight application-level detector for repeated failed authentication activity. For a production deployment it should complement, not replace, a network/WAF/Fail2ban/SIEM layer.

## Course delivery and progression

- Lessons support written text, an approved YouTube URL, or both. YouTube videos are embedded through the privacy-enhanced `youtube-nocookie.com` host.
- Course duration is configured as a number of days, weeks, months, or years. When a learner enrolls, the application calculates a target completion deadline from the enrollment start date.
- Learners may actively progress through one course at a time. Other published courses remain visible in the catalog, but are marked as locked until the active course is completed. Server-side enrollment and checkout routes enforce the rule; the catalog state is only the visual explanation.
- Completing a course unlocks another course. Completed courses remain available for review.

## Release archive hygiene

Create a fresh local `.env` from `.env.example` before running this release. Runtime secrets, local SQLite data, Git history, Python virtual environments, and cache files are intentionally excluded from distributable archives.

## Seeded staff workspaces (development only)

The seed creates dedicated instructor/facilitator and mentor identities so the role-specific workspaces can be explored locally:

- Instructor / facilitator: `instructor@mawiz.local` / `ChangeMe!Instructor123`
- Mentor: `mentor@mawiz.local` / `ChangeMe!Mentor123`

These are development demo credentials, not production credentials. Change or disable them before deploying any environment reachable by other people. Run the existing seed command after upgrading so the staff accounts and role permissions are synchronized.

### Role responsibilities

- **Instructor / facilitator:** owns the course-delivery workspace and can create and manage tracks, courses, modules, lessons, course duration/pricing, quizzes, assignments and publishing. Instructor course management is shared across the platform; course ownership/assignment is not yet modeled.
- **Administrator:** retains platform-wide administration and the same full course-management capabilities.
- **Mentor:** gets a dedicated learner-support dashboard with learner participation and recent project-submission visibility. Mentors do not get course authoring or publishing permissions. The learner roster is platform-wide because mentor-to-learner assignments are not yet modeled.


## Application and Paystack system logs

Mawiz writes rotating application logs to `instance/logs/mawiz.log` by default. Configure `LOG_LEVEL`, `LOG_FILE`, `LOG_MAX_BYTES`, and `LOG_BACKUP_COUNT` in the environment. The file is created automatically. The admin sidebar includes **System Logs** at `/admin/system-logs`; access is restricted to administrators with the admin dashboard permission.

For checkout diagnostics, each request receives an `X-Request-ID` response header. Logs record the Paystack endpoint, HTTP status, test/live key mode, request field names, provider error message, and checkout/payment IDs. They do **not** record the secret key, Authorization header, checkout payload, or customer email. Match a failed checkout to its `request_id` in System Logs. Keep `instance/logs/` out of public web roots and backups that are shared externally.

## Learner learning-path selection

Learner registration now creates the account without requiring a career direction. After the learner signs in, Mawiz prompts them to choose **Entrepreneurship** or **Job & Freelance**, then sends them to the published course catalog to choose their first course. Learners can revisit their direction from **Learning direction** in the learner sidebar. Existing learners who already have a saved direction keep it; learners whose direction is blank are prompted to choose one at their next sign-in.

## Learning-stage management workspace

The administrator/instructor learning-management workspace uses four horizontal tabs:

1. **Hard Skills** — course authoring and management filtered to the `hard_skills` stage.
2. **Soft Skills** — the same course-management tools filtered to the `soft_skills` stage.
3. **Work Simulation** — existing workplace-simulation authoring and publishing tools.
4. **Career Path** — existing project authoring and publishing tools used to create practical career evidence.

Each tab opens its management workspace in the full page content area. The tabs adapt to two columns on medium screens and one column on narrow screens. Existing permission checks and management actions remain in place.

For security, the packaged source excludes local `.env` secrets, the local SQLite database, runtime logs, the Python virtual environment, and generated caches. Configure the application using `.env.example` and initialize the database using the documented setup steps.
