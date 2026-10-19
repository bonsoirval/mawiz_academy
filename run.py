"""Development server and command-line entry point.

Notes
-----
The operational commands here are intentionally limited to local setup and seed
data. Production deployments should use a WSGI server and managed configuration.
"""

import sys
from pathlib import Path
from app import create_app
from app.extensions import db

app = create_app()

if __name__ == "__main__":
    if "--init-db" in sys.argv:
        with app.app_context(): db.create_all()
        print("Database initialized.")
        sys.exit(0)
    if "--seed" in sys.argv:
        with app.app_context():
            from app.seed import seed
            seed()
        print("Seed data loaded.")
        sys.exit(0)
    if "--show-dev-mail" in sys.argv:
        path = Path(app.config["MAIL_SINK_PATH"])
        if path.exists(): print(path.read_text(encoding="utf-8"))
        else: print("No development mail has been generated yet.")
        sys.exit(0)
    app.run(host="127.0.0.1", port=5000, debug=app.config.get("DEBUG", False))
