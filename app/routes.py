from flask import request, jsonify, render_template, send_from_directory
from bson import ObjectId
from datetime import datetime, timedelta
from calendar import monthrange
from .auth import require_auth
from .utils import allowed_file, MONTH_NAMES
from werkzeug.utils import secure_filename
import bcrypt  # Ajout de l'importation de bcrypt
import os  # Ajout pour send_from_directory

def init_routes(app):
    db = app.config["DB"]

    @app.route("/", methods=["GET", "POST"])
    def upload_page():
        if request.method == "POST":
            return "Fichier reçu"
        return render_template("upload.html")

    @app.route("/login", methods=["GET"])
    def login_page():
        return render_template("login.html")

    @app.route("/api/register", methods=["POST"])
    def register():
        from .auth import register
        return register(db)()

    @app.route("/api/login", methods=["POST"])
    def login():
        from .auth import login
        return login(db)()

    @app.route("/api/profile", methods=["PUT"])
    @require_auth
    def edit_profile():
        data = request.json or {}
        update = {}
        if "username" in data:
            update["username"] = data["username"]
        if "password" in data:
            update["password"] = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt())
        if not update:
            return jsonify({"error": "Rien à modifier"}), 400
        db.users.update_one({"_id": request.user_id}, {"$set": update})
        return jsonify({"status": "profil mis à jour"}), 200

    @app.route("/api/profile", methods=["GET"])
    @require_auth
    def get_profile():
        try:
            user_oid = ObjectId(request.user_id)
        except Exception:
            return jsonify({"error": "ID utilisateur invalide"}), 400
        user = db.users.find_one({"_id": user_oid}, {"password": 0})
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
        user["_id"] = str(user["_id"])
        user_devices = list(db.devices.find({"user_id": request.user_id}))
        for device in user_devices:
            device["_id"] = str(device["_id"])
            if "user_id" in device:
                device["user_id"] = str(device["user_id"])
        profile = {
            "username": user.get("username"),
            "role": user.get("role"),
            "created_at": user.get("created_at"),
            "devices": user_devices
        }
        return jsonify(profile), 200

    @app.route("/api/devices", methods=["POST"])
    @require_auth
    def add_device():
        d = request.json or {}
        if db.devices.find_one({"device_id": d.get("device_id")}):
            return jsonify({"error": "ID déjà existant"}), 400
        device = {
            "device_id": d.get("device_id"),
            "user_id": request.user_id,
            "name": d.get("name", "Appareil sans nom"),
            "location": d.get("location", ""),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "status": "active"
        }
        db.devices.insert_one(device)
        db.users.update_one({"_id": request.user_id}, {"$push": {"devices": d["device_id"]}})
        return jsonify({"status": "succès", "device_id": d["device_id"]}), 201

    @app.route("/api/devices", methods=["GET"])
    @require_auth
    def list_devices():
        device_list = list(db.devices.find({"user_id": request.user_id}, {"_id": 0}))
        for device in device_list:
            if "user_id" in device:
                device["user_id"] = str(device["user_id"])
            if "device_id" in device:
                device["device_id"] = str(device["device_id"])
            if "created_at" in device and isinstance(device["created_at"], str):
                device["created_at"] = device["created_at"]
            # Récupérer le dernier niveau d'eau pour cet appareil
            latest_level = db.water_levels.find_one(
                {"device_id": device["device_id"]},
                {"level": 1, "received_at": 1, "_id": 0},
                sort=[("received_at", -1)]
            )
            device["latest_level"] = latest_level["level"] if latest_level else None
            device["level_updated_at"] = latest_level["received_at"] if latest_level else None
        return jsonify(device_list), 200

    @app.route("/api/graph-data", methods=["POST"])
    @require_auth
    def graph_data():
        data = request.json or {}
        device_id = data.get("device_id")
        view = data.get("view", "month")
        year = data.get("year", datetime.utcnow().year)
        month_name = data.get("month")
        start_date = data.get("start_date")

        if not device_id:
            return jsonify({"error": "device_id requis"}), 400

        device = db.devices.find_one({"device_id": device_id, "user_id": request.user_id})
        if not device:
            return jsonify({"error": "Appareil non trouvé ou non autorisé"}), 403

        query = {"device_id": device_id}
        projection = {"_id": 0, "day": 1, "level": 1}

        if view == "day Jolting day" and start_date:
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
                query["day"] = start_date
            except ValueError:
                return jsonify({"error": "Format de date invalide (attendu: YYYY-MM-DD)"}), 400
        elif view == "month" and month_name and year:
            month = MONTH_NAMES.get(month_name.lower())
            if not month:
                return jsonify({"error": "Nom de mois invalide"}), 400
            try:
                start = datetime(year, month, 1).strftime("%Y-%m-%d")
                end = (datetime(year, month + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d") if month < 12 else datetime(year, 12, 31).strftime("%Y-%m-%d")
                today = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")
                end = min(end, today)
                query["day"] = {"$gte": start, "$lte": end}
            except ValueError:
                return jsonify({"error": "Mois ou année invalide"}), 400
        else:
            return jsonify({"error": "Paramètres manquants pour la vue demandée"}), 400

        recs = db.water_levels.find(query, projection).sort("day", 1)
        grouped = {}
        for r in recs:
            grouped.setdefault(r["day"], []).append(r["level"])
        
        days_in_month = monthrange(year, month)[1]
        out = []
        for day in range(1, days_in_month + 1):
            day_str = f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
            levels = grouped.get(day_str, [])
            avg = sum(levels) / len(levels) if levels else 0
            out.append({"day": day_str, "avg": avg})

        return jsonify(out), 200

    @app.route("/api/yearly-graph-data", methods=["POST"])
    @require_auth
    def yearly_graph_data():
        data = request.json or {}
        device_id = data.get("device_id")
        year = data.get("year", datetime.utcnow().year)

        if not device_id:
            return jsonify({"error": "device_id requis"}), 400

        device = db.devices.find_one({"device_id": device_id, "user_id": request.user_id})
        if not device:
            return jsonify({"error": "Appareil non trouvé ou non autorisé"}), 403

        today = datetime.utcnow() + timedelta(hours=3)
        last_day = today.strftime("%Y-%m-%d") if year == today.year else f"{year}-12-31"

        pipeline = [
            {
                "$match": {
                    "device_id": device_id,
                    "day": {"$gte": f"{year}-01-01", "$lte": last_day}
                }
            },
            {
                "$group": {
                    "_id": {"$substr": ["$day", 0, 7]},
                    "avg_level": {"$avg": "$level"}
                }
            },
            {
                "$sort": {"_id": 1}
            },
            {
                "$project": {
                    "_id": 0,
                    "month": "$_id",
                    "avg": "$avg_level"
                }
            }
        ]

        recs = list(db.water_levels.aggregate(pipeline))
        months = [f"{year}-{str(m).zfill(2)}" for m in range(1, 13 if year < today.year else today.month + 1)]
        out = []
        for month in months:
            found = next((r for r in recs if r["month"] == month), None)
            out.append({
                "month": month,
                "avg": found["avg"] if found else 0
            })

        return jsonify(out), 200

    @app.route("/api/notifications", methods=["GET"])
    @require_auth
    def get_notifications():
        recs = db.alerts.find({"user_id": request.user_id}, {"_id": 0}).sort("timestamp", -1).limit(50)
        # Convertir user_id en chaîne pour chaque document
        recs = [{**rec, "user_id": str(rec["user_id"])} for rec in recs]
        return jsonify(recs), 200

    @app.route("/api/articles", methods=["POST"])
    @require_auth
    def upload_article():
        titre = request.form.get("titre")
        desc = request.form.get("description")
        type_ = request.form.get("type", "info")
        if not titre or not desc:
            return jsonify({"error": "titre ou description manquant"}), 400
        imgs = request.files.getlist("images")
        urls = []
        for img in imgs:
            if img and allowed_file(img.filename):
                fn = secure_filename(img.filename)
                path = os.path.join(app.config["UPLOAD_FOLDER"], fn)
                img.save(path)
                urls.append(f"/uploads/articles/{fn}")
        doc = {
            "titre": titre,
            "description": desc,
            "type": type_,
            "image_urls": urls,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        db.articles.insert_one(doc)
        return jsonify({"status": "succès", "article": doc}), 201

    @app.route("/api/articles", methods=["GET"])
    def list_articles():
        recs = list(db.articles.find({}, {"_id": 0}))
        return jsonify(recs), 200

    @app.route("/api/article-of-the-week", methods=["GET"])
    def article_of_week():
        art = db.articles.find_one({"type": "semaine"}, {"_id": 0})
        return jsonify(art or {}), 200

    @app.route("/api/pump_action", methods=["POST"])
    @require_auth
    def pump_action():
        data = request.json or {}
        device_id = data.get("device_id")
        action = data.get("action")
        if not device_id or action not in ["on", "off"]:
            return jsonify({"error": "device_id ou action invalide (on/off)"}), 400
        device = db.devices.find_one({"device_id": device_id, "user_id": request.user_id})
        if not device:
            return jsonify({"error": "Appareil non trouvé ou non autorisé"}), 403
        db.devices.update_one(
            {"device_id": device_id},
            {"$set": {"pump_state": action == "on", "updated_at": (datetime.utcnow() + timedelta(hours=3)).isoformat() + "Z"}}
        )
        return jsonify({"status": f"Pompe {action} pour {device_id}"}), 200

    @app.route("/api/pump_command/<device_id>", methods=["GET"])
    def get_pump_command(device_id):
        try:
            device = db.devices.find_one({"device_id": device_id})
            if not device:
                return jsonify({"error": "Appareil non trouvé"}), 404
            pump_state = device.get("pump_state", False)
            return jsonify({"device_id": device_id, "action": "on" if pump_state else "off"}), 200
        except Exception as e:
            print(f"Erreur dans get_pump_command: {str(e)}")  # Log l'erreur
            return jsonify({"error": f"Erreur serveur: {str(e)}"}), 500    

    @app.route("/api/weather", methods=["GET"])
    def get_weather():
        return jsonify({"weather": "donnée météo factice"}), 200

    @app.route("/uploads/articles/<filename>")
    def serve_img(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)