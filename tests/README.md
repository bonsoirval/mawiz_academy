# Mawiz Academy automated tests

Run the complete offline suite from the project root:

```bash
python -m pytest -q
# or
make test
```

Run a focused group:

```bash
python -m pytest -q tests/auth/
python -m pytest -q tests/payments/
python -m pytest -q tests/security/
python -m pytest -q tests/public/
```

The shared `conftest.py` fixture uses an in-memory SQLite database, seeded
demo data, a temporary mail sink, and disabled rate limits. Tests do not use
the production database or make external HTTP requests.

The `scripts/manual_paystack_*_check.py` files are opt-in manual smoke checks
for a real Paystack **test-mode** secret key. They are intentionally outside
pytest discovery because they contact the live Paystack API and require
credentials. Do not use a live secret key for those checks.

Registration validates email syntax without performing DNS deliverability
lookups. A successful syntax check does not prove that a mailbox exists;
email ownership is established by the verification link.
