from extensions import db
from datetime import datetime, timezone

class Event(db.Model):
    __tablename__ = "events"

    id          = db.Column(db.Integer, primary_key=True)
    place_id    = db.Column(db.Integer, db.ForeignKey("places.id", ondelete="SET NULL"), nullable=True)
    name        = db.Column(db.String, nullable=False)
    city        = db.Column(db.String, nullable=False)
    country     = db.Column(db.String, nullable=False)
    lat         = db.Column(db.Float)
    lng         = db.Column(db.Float)
    event_date  = db.Column(db.String, nullable=False)  # ISO: 2025-04-12
    event_time  = db.Column(db.String)                  # HH:MM
    description = db.Column(db.Text)
    url         = db.Column(db.String)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    place = db.relationship("Place", back_populates="events")

    def to_dict(self):
        return {
            "id":          self.id,
            "place_id":    self.place_id,
            "place_name":  self.place.name if self.place else None,
            "place_slug":  self.place.slug if self.place else None,
            "name":        self.name,
            "city":        self.city,
            "country":     self.country,
            "lat":         self.lat or (self.place.lat if self.place else None),
            "lng":         self.lng or (self.place.lng if self.place else None),
            "event_date":  self.event_date,
            "event_time":  self.event_time,
            "description": self.description,
            "url":         self.url,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }
