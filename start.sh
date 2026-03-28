#!/bin/bash
set -e
cd "$(dirname "$0")/backend"

# Find python3
PYTHON=$(which python3 || which python || find /app -name python3 -type f 2>/dev/null | head -1 || find / -name python3 -type f 2>/dev/null | head -1)
echo "Using python: $PYTHON"

# Auto-migrate if DB is empty
$PYTHON - <<'EOF'
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

exec $(dirname $PYTHON)/gunicorn "app:create_app()" --bind "0.0.0.0:${PORT:-8000}"
