#!/bin/bash
set -e
cd backend

# If DB has no places yet, run the migration from the bundled CSV
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

gunicorn "app:create_app()" --bind "0.0.0.0:${PORT:-8000}"
