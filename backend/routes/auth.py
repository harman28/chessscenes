from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from models import User
from auth import create_token

bp = Blueprint("auth", __name__)


@bp.post("/api/auth/login")
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_token(user.id, user.username)
    return jsonify({"token": token, "username": user.username})


@bp.post("/api/auth/create-admin")
def create_admin():
    """Bootstrap route — only works when no users exist yet."""
    if User.query.first():
        return jsonify({"error": "Admin already exists"}), 403
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": f"Admin '{username}' created"}), 201
