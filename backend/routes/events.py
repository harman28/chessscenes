from flask import Blueprint, jsonify, request
from extensions import db
from models import Event

bp = Blueprint("events", __name__)


@bp.get("/api/events")
def list_events():
    q = Event.query

    city = request.args.get("city", "").strip().lower()
    date = request.args.get("date", "").strip()  # exact ISO date: 2025-04-12
    from_date = request.args.get("from", "").strip()
    to_date = request.args.get("to", "").strip()

    if city:
        q = q.filter(db.func.lower(Event.city) == city)
    if date:
        q = q.filter_by(event_date=date)
    if from_date:
        q = q.filter(Event.event_date >= from_date)
    if to_date:
        q = q.filter(Event.event_date <= to_date)

    events = q.order_by(Event.event_date.asc(), Event.event_time.asc()).all()
    return jsonify([e.to_dict() for e in events])
