from flask import request, jsonify
from functools import wraps
from bson import ObjectId
import jwt
import bcrypt
from datetime import datetime, timedelta  # Added import
from .config import Config

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Token manquant"}), 401
        try:
            token = token.replace("Bearer ", "")
            data = jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
            request.user_id = ObjectId(data["user_id"])
            request.role = data["role"]
        except (jwt.InvalidTokenError, Exception):
            return jsonify({"error": "Token invalide ou ID utilisateur invalide"}), 401
        return f(*args, **kwargs)
    return decorated

def register(db):
    def _register():
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")
        role = data.get("role", "user")
        if not username or not password:
            return jsonify({"error": "Nom ou mot de passe requis"}), 400
        if db.users.find_one({"username": username}):
            return jsonify({"error": "Nom déjà pris"}), 400
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        uid = db.users.insert_one({
            "username": username,
            "password": hashed,
            "role": role,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "devices": []
        }).inserted_id
        return jsonify({"status": "succès", "user_id": str(uid)}), 201
    return _register

def login(db):
    def _login():
        data = request.json or {}
        user = db.users.find_one({"username": data.get("username")})
        if not user or not bcrypt.checkpw(data.get("password", "").encode(), user["password"]):
            return jsonify({"error": "Identifiants invalides"}), 401
        token = jwt.encode({
            "user_id": str(user["_id"]),
            "role": user["role"],
            "exp": datetime.utcnow() + timedelta(hours=24)
        }, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)
        return jsonify({"token": token}), 200
    return _login