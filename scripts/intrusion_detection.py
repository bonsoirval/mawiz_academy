"""Review recent audit events for repeated authentication failures.

Notes
-----
This is an operational signal, not a replacement for centralized security monitoring.
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from app import create_app
from app.models import AuditEvent
parser = argparse.ArgumentParser(description='Review recent Mawiz audit events for suspicious authentication activity.')
parser.add_argument('--minutes', type=int, default=15)
parser.add_argument('--threshold', type=int, default=10)
args = parser.parse_args()
app = create_app()
with app.app_context():
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=args.minutes)
    events = AuditEvent.query.filter(AuditEvent.created_at >= cutoff, AuditEvent.action.in_(['auth.login_failed','auth.2fa_failed'])).all()
    by_ip = Counter(e.ip_address or 'unknown' for e in events)
    suspicious = {ip: count for ip, count in by_ip.items() if count >= args.threshold}
    if suspicious:
        print('Intrusion detection ALERT')
        for ip, count in suspicious.items(): print(f'  {ip}: {count} failed authentication events in the last {args.minutes} minutes')
        raise SystemExit(2)
    print(f'Intrusion detection clear: {len(events)} failed authentication events in the last {args.minutes} minutes.')
