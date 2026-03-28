from extensions import db
from datetime import datetime, timezone

class Suggestion(db.Model):
    __tablename__ = "suggestions"

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String, nullable=False)
    city             = db.Column(db.String, nullable=False)
    country          = db.Column(db.String, nullable=False)
    lat              = db.Column(db.Float)
    lng              = db.Column(db.Float)
    type             = db.Column(db.String)
    description      = db.Column(db.Text)
    schedule_notes   = db.Column(db.Text)
    website          = db.Column(db.String)
    submitter_name   = db.Column(db.String)
    submitter_email  = db.Column(db.String)
    status           = db.Column(db.String, nullable=False, default="pending")  # pending | approved | rejected
    admin_notes      = db.Column(db.Text)
    submitted_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id":              self.id,
            "name":            self.name,
            "city":            self.city,
            "country":         self.country,
            "lat":             self.lat,
            "lng":             self.lng,
            "type":            self.type,
            "description":     self.description,
            "schedule_notes":  self.schedule_notes,
            "website":         self.website,
            "submitter_name":  self.submitter_name,
            "submitter_email": self.submitter_email,
            "status":          self.status,
            "admin_notes":     self.admin_notes,
            "submitted_at":    self.submitted_at.isoformat() if self.submitted_at else None,
        }
