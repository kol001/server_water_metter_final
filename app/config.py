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
    UPLOAD_FOLDER = "uploads/articles"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
    
    # MongoDB
    MONGO_URI = "mongodb://localhost:27017"
    DB_NAME = "water_tank"
    
    # JSON Provider
    JSON_PROVIDER_CLASS = CustomJSONProvider