import os
from flask import Flask, request, Response, send_from_directory
from config import Config
from extensions import db
from models import Setting

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)

    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    @app.before_request
    def handle_options():
        if request.method == "OPTIONS":
            r = Response()
            r.headers["Access-Control-Allow-Origin"] = "*"
            r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            return r

    db.init_app(app)

    from routes import auth, places, events, suggestions, admin
    app.register_blueprint(auth.bp)
    app.register_blueprint(places.bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(suggestions.bp)
    app.register_blueprint(admin.bp)

    with app.app_context():
        db.create_all()
        if not db.session.get(Setting, "show_unverified"):
            db.session.add(Setting(key="show_unverified", value="true"))
            db.session.commit()
    _auto_migrate(app)

    # Serve frontend static files
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


def _auto_migrate(app):
    csv_path = os.path.join(os.path.dirname(__file__), "chessscenesdatapublic.csv")
    if not os.path.exists(csv_path):
        return
    import csv as csvlib, re
    from models import Place
    with app.app_context():
        if db.session.query(Place).count() > 0:
            return
        print("Auto-migrating from CSV...")
        COLUMN_MAP = {
            "name": "name", "city": "city", "country": "country",
            "lat": "lat", "latitude": "lat", "lng": "lng", "lon": "lng", "longitude": "lng",
            "type": "type", "description": "description", "desc": "description",
            "schedule_notes": "schedule_notes", "notes": "schedule_notes", "schedule": "schedule_notes",
            "schedule_days": "schedule_days", "days": "schedule_days",
            "website": "website", "url": "website", "link": "website",
            "image_url": "image_url", "image": "image_url", "photo": "image_url",
            "maps_url": "maps_url", "gmap": "maps_url", "gmaps": "maps_url",
            "verified": "verified",
        }
        def slugify(text):
            text = text.lower().strip()
            text = re.sub(r"[^\w\s-]", "", text)
            return re.sub(r"[\s_-]+", "-", text)
        inserted = 0
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csvlib.DictReader(f):
                norm = {COLUMN_MAP[k.strip().lower()]: v.strip() for k, v in row.items() if k.strip().lower() in COLUMN_MAP}
                name = norm.get("name")
                if not name:
                    continue
                base = slugify(name)
                slug, i = base, 2
                while db.session.query(Place).filter_by(slug=slug).first():
                    slug = f"{base}-{i}"; i += 1
                try:
                    db.session.add(Place(
                        name=name, slug=slug,
                        city=norm.get("city", ""), country=norm.get("country", ""),
                        lat=float(norm["lat"]) if norm.get("lat") else None,
                        lng=float(norm["lng"]) if norm.get("lng") else None,
                        type=norm.get("type", ""), description=norm.get("description", ""),
                        schedule_notes=norm.get("schedule_notes", ""),
                        schedule_days=norm.get("schedule_days", ""),
                        website=norm.get("website", ""),
                        maps_url=norm.get("maps_url") or None,
                        image_url=norm.get("image_url", ""),
                        verified=norm.get("verified", "1").lower() in ("1", "true", "yes"),
                        active=True,
                    ))
                    db.session.flush()
                    inserted += 1
                except Exception as e:
                    db.session.rollback()
        db.session.commit()
        print(f"Auto-migration done. Inserted {inserted} places.")


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)