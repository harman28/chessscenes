from flask import Flask, request, Response
from config import Config
from extensions import db
from models import Setting


def create_app():
    app = Flask(__name__)
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

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)