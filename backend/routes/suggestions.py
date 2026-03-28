from flask import Blueprint, jsonify, request
from extensions import db
from models import Suggestion

bp = Blueprint("suggestions", __name__)

REQUIRED = ["name", "city", "country"]


@bp.post("/api/suggestions")
def submit_suggestion():
    data = request.get_json() or {}
    missing = [f for f in REQUIRED if not str(data.get(f, "")).strip()]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    suggestion = Suggestion(
        name=data["name"],
        city=data["city"],
        country=data["country"],
        lat=data.get("lat"),
        lng=data.get("lng"),
        type=data.get("type"),
        description=data.get("description"),
        schedule_notes=data.get("schedule_notes"),
        website=data.get("website"),
        submitter_name=data.get("submitter_name"),
        submitter_email=data.get("submitter_email"),
    )
    db.session.add(suggestion)
    db.session.commit()
    return jsonify({"message": "Suggestion received — thank you!"}), 201
