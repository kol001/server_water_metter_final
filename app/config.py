import os
from flask.json.provider import DefaultJSONProvider
from bson import ObjectId
from datetime import datetime

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat() + "Z"
        return super().default(obj)

class Config:
    SECRET_KEY = os.urandom(24).hex()
    JWT_SECRET = os.urandom(24).hex()
    JWT_ALGORITHM = "HS256"

    # ⚠️ on laisse une valeur par défaut, mais on la remplace par un ABSOLU dans create_app()
    UPLOAD_FOLDER = "uploads/articles"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

    MONGO_URI = "mongodb://localhost:27017"
    DB_NAME = "water_tank"

    JSON_PROVIDER_CLASS = CustomJSONProvider
