#!/bin/bash
set -e
export PATH="/app/.venv/bin:$PATH"
cd "$(dirname "$0")/backend"

# Auto-migrate if DB is empty
python3 - <<'EOF'
import os, sys
sys.path.insert(0, ".")
from app import create_app
from extensions import db
from models import Place

app = create_app()
with app.app_context():
    count = db.session.query(Place).count()
    print(f"DB has {count} places")
    if count == 0 and os.path.exists("chessscenesdatapublic.csv"):
        print("Running migration...")
        import subprocess
        subprocess.run(["python3", "migrate.py", "--csv", "chessscenesdatapublic.csv"], check=True)
        print("Migration done")
EOF

exec gunicorn "app:create_app()" --bind "0.0.0.0:${PORT:-8000}"
