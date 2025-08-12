import os
from flask import Flask
from .config import Config
from .routes import init_routes
from .websocket import init_websocket
from .timer import start_timer_worker, init_timer_routes
from .water_level import init_water_level_routes
from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    app.config.from_object(Config)

    # ✅ UPLOAD_FOLDER ABSOLU = app/static/uploads/articles
    app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads", "articles")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # (optionnel mais utile pour vérifier)
    print("UPLOAD_FOLDER ->", app.config["UPLOAD_FOLDER"])

    # DB / websockets / routes
    from pymongo import MongoClient
    client = MongoClient(Config.MONGO_URI)
    app.config["DB"] = client[Config.DB_NAME]

    socketio.init_app(app)
    init_routes(app)
    init_websocket(socketio)
    init_water_level_routes(app)
    init_timer_routes(app)
    start_timer_worker(app, socketio)
    app.socketio = socketio
    return app
