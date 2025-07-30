from flask import request, jsonify
from bson import ObjectId
from datetime import datetime, timedelta
from threading import Thread
import time
from .auth import require_auth
from .utils import validate_iso8601

def start_timer_worker(app, socketio):
    def timer_worker():
        db = app.config["DB"]
        while True:
            now = datetime.utcnow()
            timers_to_process = db.timers.find({"status": "pending"})
            for timer in timers_to_process:
                start_time = datetime.strptime(timer["start_time"], "%Y-%m-%dT%H:%M:%SZ")
                if now >= start_time:
                    db.devices.update_one(
                        {"device_id": timer["device_id"]},
                        {"$set": {"pump_state": True, "updated_at": (now + timedelta(hours=3)).isoformat() + "Z"}}
                    )
                    socketio.emit("pump_action", {"device_id": timer["device_id"], "action": "on"}, namespace="/ws/pump_action")
                    db.timers.update_one(
                        {"_id": timer["_id"]},
                        {"$set": {"status": "active", "activated_at": now.isoformat() + "Z"}}
                    )
                    Thread(target=stop_pump_after_duration, args=(timer, socketio, db)).start()
            time.sleep(60)

    def stop_pump_after_duration(timer, socketio, db):
        time.sleep(timer["duration"])
        now = datetime.utcnow()
        db.devices.update_one(
            {"device_id": timer["device_id"]},
            {"$set": {"pump_state": False, "updated_at": (now + timedelta(hours=3)).isoformat() + "Z"}}
        )
        socketio.emit("pump_action", {"device_id": timer["device_id"], "action": "off"}, namespace="/ws/pump_action")
        db.timers.update_one(
            {"_id": timer["_id"]},
            {"$set": {"status": "completed", "completed_at": now.isoformat() + "Z"}}
        )

    Thread(target=timer_worker, daemon=True).start()

def init_timer_routes(app):
    db = app.config["DB"]

    @app.route("/api/timer", methods=["POST"])
    @require_auth
    def add_timer():
        d = request.json or {}
        if not d.get("device_id") or not d.get("start_time") or not isinstance(d.get("duration"), (int, float)) or d.get("duration") <= 0:
            return jsonify({"error": "device_id, start_time ou duration invalide"}), 400
        if not validate_iso8601(d.get("start_time")):
            return jsonify({"error": "Format de start_time invalide (attendu: YYYY-MM-DDThh:mm:ssZ)"}), 400
        timer = {
            "user_id": request.user_id,
            "device_id": d.get("device_id"),
            "start_time": d.get("start_time"),
            "duration": d.get("duration"),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        db.timers.insert_one(timer)
        app.socketio.emit("timer", {"type": "timer", "data": timer}, namespace="/ws/timer")
        return jsonify({"status": "timer ajouté", "timer_id": str(timer["_id"])}), 201

    @app.route("/api/timers", methods=["GET"])
    @require_auth
    def get_timers():
        timers_list = list(db.timers.find({"user_id": request.user_id}).sort("created_at", -1).limit(50))
        for timer in timers_list:
            timer["timer_id"] = str(timer.pop("_id"))
            timer["user_id"] = str(timer["user_id"])  # Convertir user_id en chaîne
        return jsonify(timers_list), 200

    @app.route("/api/timer/<timer_id>", methods=["DELETE"])
    @require_auth
    def delete_timer(timer_id):
        result = db.timers.delete_one({"_id": ObjectId(timer_id), "user_id": request.user_id})
        if result.deleted_count == 0:
            return jsonify({"error": "Timer non trouvé ou non autorisé"}), 404
        return jsonify({"status": "timer supprimé"}), 200   