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
        from models import Place
        if db.session.query(Place).count() == 0:
            db.session.add(Place(
                name="Cafe de Laurierboom",
                slug="cafe-de-laurierboom",
                city="Amsterdam",
                country="Netherlands",
                lat=52.372347065141824,
                lng=4.880934681011202,
                type="chess_bar",
                description="Chess mecca of Amsterdam. Tournaments on barblitz.co. Casual chess always.",
                maps_url="https://maps.app.goo.gl/PizEC9TRQ4kt8QyK6",
                image_url="https://i.imgur.com/9NRex3f.jpeg",
                verified=True,
                active=True,
            ))
            db.session.commit()

    # Serve frontend static files
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)
