# app/water_level.py
from flask import request, jsonify
from bson import ObjectId
from datetime import datetime, timedelta

from .models import WaterLevelPredictor  # <- ML predictor

def init_water_level_routes(app):
    db = app.config["DB"]
    predictor = WaterLevelPredictor()  # <- make it once, in closure

    @app.route("/api/water-level", methods=["POST"])
    def receive_water_level():
        d = request.json or {}

        device = db.devices.find_one({"device_id": d.get("device_id")})
        if not device:
            return jsonify({"error": "appareil inconnu"}), 400

        # ---- JSON‑safe record for EMIT (no ObjectId) ----
        rec_emit = {
            "device_id": device["device_id"],                  # str
            "user_id": str(device["user_id"]),                 # JSON safe
            "level": d.get("level"),
            "pump_state": d.get("pump_state"),
            "timestamp": d.get("timestamp"),
            "received_at": datetime.utcnow().isoformat() + "Z",
            "hour": datetime.utcnow().hour,
            "day": datetime.utcnow().strftime("%Y-%m-%d"),
        }

        # Predict (uses only JSON‑safe data)
        preds = predictor.predict(rec_emit)
        rec_emit.update({
            "anomaly": bool(preds["anomaly"]),
            "predicted_level": float(preds["predicted_level"]),
            "cluster": int(preds["cluster"]),
        })

        # ---- DB doc: copy & restore ObjectId for user_id ----
        rec_db = rec_emit.copy()
        rec_db["user_id"] = device["user_id"]  # ObjectId for Mongo

        # (Optional) want real datetime in DB?
        # rec_db["received_at"] = datetime.utcnow()

        res = db.water_levels.insert_one(rec_db)
        rec_emit["id"] = str(res.inserted_id)  # handy for clients

        # Emit JSON‑safe payload
        app.socketio.emit(
            "water_level",
            {"type": "water_level", "data": rec_emit},
            namespace="/ws/water-level"
        )

        # ---- Alerts (always keep emits JSON‑safe) ----
        if rec_emit["anomaly"]:
            recent = list(
                db.water_levels
                .find({"device_id": rec_emit["device_id"]})
                .sort("timestamp", -1)
                .limit(60)
            )
            if len(recent) >= 2:
                # Beware: if "timestamp" is ISO string, sort still ok (ISO is lex‑sortable).
                # If it's a Unix int elsewhere, that's fine too.
                diff = recent[0]["level"] - recent[1]["level"]

                if diff <= -10:
                    alert_emit = {
                        "device_id": rec_emit["device_id"],
                        "user_id": rec_emit["user_id"],  # str
                        "message": f"Fuite détectée sur {rec_emit['device_id']}",
                        "timestamp": rec_emit["received_at"],
                        "triggered_by": "system",
                    }
                    alert_db = alert_emit.copy()
                    alert_db["user_id"] = device["user_id"]  # ObjectId
                    db.alerts.insert_one(alert_db)
                    app.socketio.emit(
                        "alert", {"type": "alert", "data": alert_emit},
                        namespace="/ws/alerts"
                    )

                elif rec_emit["pump_state"] and diff == 0:
                    alert_emit = {
                        "device_id": rec_emit["device_id"],
                        "user_id": rec_emit["user_id"],  # str
                        "message": (
                            f"Panne possible : pompe activée mais niveau stagnant "
                            f"sur {rec_emit['device_id']}"
                        ),
                        "timestamp": rec_emit["received_at"],
                        "triggered_by": "system",
                    }
                    alert_db = alert_emit.copy()
                    alert_db["user_id"] = device["user_id"]  # ObjectId
                    db.alerts.insert_one(alert_db)
                    app.socketio.emit(
                        "alert", {"type": "alert", "data": alert_emit},
                        namespace="/ws/alerts"
                    )

        return jsonify({
            "status": "succès",
            "predictions": {
                "anomaly": rec_emit["anomaly"],
                "predicted_level": rec_emit["predicted_level"],
                "cluster": rec_emit["cluster"],
            }
        }), 200
