from flask import Flask
from flask_socketio import SocketIO
from .config import Config
from .routes import init_routes
from .websocket import init_websocket
from .timer import start_timer_worker, init_timer_routes  # Ajout de init_timer_routes
from .water_level import init_water_level_routes
from pymongo import MongoClient

# Initialiser socketio au niveau du module
socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Connexion MongoDB
    client = MongoClient(Config.MONGO_URI)
    app.config["DB"] = client[Config.DB_NAME]
    
    # Initialiser socketio avec l'application
    socketio.init_app(app)
    
    # Initialiser les routes et WebSocket
    init_routes(app)
    init_websocket(socketio)
    init_water_level_routes(app)
    init_timer_routes(app)  # Ajout pour enregistrer les routes de timer.py
    
    # Lancer le worker des timers
    start_timer_worker(app, socketio)
    
    # Stocker socketio dans app pour les routes
    app.socketio = socketio
    
    return app