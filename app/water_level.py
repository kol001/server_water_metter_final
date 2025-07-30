from flask import request, jsonify
from bson import ObjectId
from datetime import datetime, timedelta
from .models import WaterLevelPredictor

def init_water_level_routes(app):
    db = app.config["DB"]
    predictor = WaterLevelPredictor()

    @app.route("/api/water-level", methods=["POST"])
    def receive_water_level():
        d = request.json or {}
        device = db.devices.find_one({"device_id": d.get("device_id")})
        if not device:
            return jsonify({"error": "appareil inconnu"}), 400
        rec = {
            "device_id": device["device_id"],
            "user_id": device["user_id"],
            "level": d.get("level"),
            "pump_state": d.get("pump_state"),
            "timestamp": d.get("timestamp"),
            "received_at": datetime.utcnow().isoformat() + "Z",
            "hour": datetime.utcnow().hour,
            "day": datetime.utcnow().strftime("%Y-%m-%d")
        }
        # Prédictions IA
        predictions = predictor.predict(rec)
        # Convertir les types NumPy en types Python
        rec.update({
            "anomaly": bool(predictions["anomaly"]),  # Convertir numpy.bool_ en bool
            "predicted_level": float(predictions["predicted_level"]),  # Convertir numpy.float64 en float
            "cluster": int(predictions["cluster"])  # Convertir numpy.int32 en int
        })
        db.water_levels.insert_one(rec)
        app.socketio.emit("water_level", {"type": "water_level", "data": rec}, namespace="/ws/water-level")
        
        if predictions["anomaly"]:
            recent = list(db.water_levels.find({"device_id": rec["device_id"]}).sort("timestamp", -1).limit(60))
            if len(recent) >= 2:
                diff = recent[0]["level"] - recent[1]["level"]
                if diff <= -10:
                    alert = {
                        "device_id": rec["device_id"],
                        "user_id": rec["user_id"],
                        "message": f"Fuite détectée sur {rec['device_id']}",
                        "timestamp": rec["received_at"],
                        "triggered_by": "system"
                    }
                    db.alerts.insert_one(alert)
                    app.socketio.emit("alert", {"type": "alert", "data": alert}, namespace="/ws/alerts")
                elif rec["pump_state"] and diff == 0:
                    alert = {
                        "device_id": rec["device_id"],
                        "user_id": rec["user_id"],
                        "message": f"Panne possible : pompe activée mais niveau stagnant sur {rec['device_id']}",
                        "timestamp": rec["received_at"],
                        "triggered_by": "system"
                    }
                    db.alerts.insert_one(alert)
                    app.socketio.emit("alert", {"type": "alert", "data": alert}, namespace="/ws/alerts")
        return jsonify({"status": "succès", "predictions": {
            "anomaly": bool(predictions["anomaly"]),  # Convertir pour la réponse
            "predicted_level": float(predictions["predicted_level"]),
            "cluster": int(predictions["cluster"])
        }}), 200