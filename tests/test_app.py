"""Tests unitaires pour l'application serveur de niveaux d'eau.

Ce fichier utilise pytest et mongomock pour simuler la base de données MongoDB.
Chaque test démarre l'application avec une base vierge afin de garantir
que les cas sont isolés les uns des autres. Nous patchons également le
worker de minuterie et le prédicteur IA afin d'éviter de lancer des
threads en arrière‑plan ou de charger des modèles lourds lors des tests.
"""

import os
import sys
import json
from datetime import datetime, timedelta

import pytest
import mongomock

# Importations différées pour pouvoir patcher avant que l'application ne soit créée.
import importlib


class DummyPredictor:
    """Prédicteur factice renvoyant toujours les mêmes valeurs.

    Cela permet de tester la route `/api/water-level` sans dépendre des
    modèles `joblib`. Les valeurs choisies ici permettent de tester
    facilement les alertes et les champs retournés.
    """

    def predict(self, data):
        # Retourne une anomalie si le niveau est < 10 afin de tester les alertes.
        anomaly = data.get("level", 0) < 10
        return {
            "anomaly": anomaly,
            "predicted_level": data.get("level", 0) + 1.0,
            "cluster": 0,
        }


@pytest.fixture
def app(monkeypatch):
    """Construit et retourne une instance de l'application configurée pour les tests.

    - Utilise `mongomock` comme backend MongoDB.
    - Patch le worker de minuterie pour éviter de démarrer un thread infini.
    - Remplace `WaterLevelPredictor` par `DummyPredictor`.
    """
    # Ajouter le répertoire parent au chemin pour pouvoir importer le paquet app
    # `test_app.py` se trouve dans repo/tests, le dossier `app` est dans repo
    test_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(test_dir, os.pardir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Importer les modules à patcher
    timer = importlib.import_module("app.timer")
    water_level = importlib.import_module("app.water_level")

    # Patcher la fonction start_timer_worker pour qu'elle ne fasse rien
    monkeypatch.setattr(timer, "start_timer_worker", lambda app, socketio: None)
    # Patcher la classe WaterLevelPredictor par notre DummyPredictor
    monkeypatch.setattr(water_level, "WaterLevelPredictor", DummyPredictor)

    # Créer l'application
    from app import create_app
    flask_app = create_app()

    # Utiliser une base mongomock au lieu de MongoDB réelle
    flask_app.config["DB"] = mongomock.MongoClient().db
    # Définir un dossier d'uploads temporaire pour les tests
    uploads_dir = os.path.join(os.getcwd(), "uploads_test")
    flask_app.config["UPLOAD_FOLDER"] = uploads_dir
    os.makedirs(uploads_dir, exist_ok=True)

    yield flask_app

    # Nettoyer le dossier des fichiers uploadés après les tests
    for root, dirs, files in os.walk(uploads_dir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    if os.path.exists(uploads_dir):
        os.rmdir(uploads_dir)


@pytest.fixture
def client(app):
    """Retourne un client de test Flask pour l'application."""
    return app.test_client()


def register_user(client, username="user1", password="pass123"):
    return client.post("/api/register", json={"username": username, "password": password})


def login_user(client, username="user1", password="pass123"):
    return client.post("/api/login", json={"username": username, "password": password})


@pytest.fixture
def auth_token(client):
    """Crée un utilisateur de test et renvoie un token JWT pour l'authentification."""
    register_user(client)
    res = login_user(client)
    data = res.get_json()
    return data["token"]


def test_registration_and_login(client):
    """Teste l'inscription et la connexion d'un utilisateur."""
    # Inscription
    res = register_user(client, username="alice", password="secret")
    assert res.status_code == 201
    data = res.get_json()
    assert "user_id" in data
    # Tentative d'inscription avec le même nom
    res_dup = register_user(client, username="alice", password="secret")
    assert res_dup.status_code == 400
    # Connexion correcte
    res_login = login_user(client, username="alice", password="secret")
    assert res_login.status_code == 200
    token = res_login.get_json().get("token")
    assert token is not None
    # Connexion incorrecte
    res_bad = login_user(client, username="alice", password="wrong")
    assert res_bad.status_code == 401


def test_require_auth_protection(client):
    """Vérifie qu'une route protégée renvoie 401 sans token ou avec un token invalide."""
    # Sans token
    res_no_auth = client.get("/api/profile")
    assert res_no_auth.status_code == 401
    # Avec token invalide
    res_bad = client.get("/api/profile", headers={"Authorization": "Bearer invalide"})
    assert res_bad.status_code == 401


def test_profile_get_and_update(client, auth_token):
    """Teste la récupération et la mise à jour du profil utilisateur."""
    # Récupération du profil
    res_profile = client.get("/api/profile", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_profile.status_code == 200
    data = res_profile.get_json()
    assert data["username"] == "user1"
    # Mise à jour du nom d'utilisateur
    res_update = client.put(
        "/api/profile",
        json={"username": "newname"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_update.status_code == 200
    # Vérifier que le nouveau nom est pris en compte
    res_profile_after = client.get("/api/profile", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_profile_after.get_json()["username"] == "newname"


def test_device_add_and_list(client, auth_token):
    """Teste l'ajout d'un device et la récupération de la liste des devices."""
    # Ajout d'un device
    res_add = client.post(
        "/api/devices",
        json={"device_id": "dev123", "name": "Mon Château", "location": "Jardin"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_add.status_code == 201
    # Ajout d'un device dupliqué
    res_dup = client.post(
        "/api/devices",
        json={"device_id": "dev123"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_dup.status_code == 400
    # Liste des devices
    res_list = client.get("/api/devices", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_list.status_code == 200
    devices = res_list.get_json()
    assert isinstance(devices, list)
    assert len(devices) == 1
    dev = devices[0]
    assert dev["device_id"] == "dev123"
    # Le niveau le plus récent n'a pas encore été envoyé, donc latest_level est None
    assert dev.get("latest_level") is None


def test_graph_data_invalid_month(client, auth_token):
    """Teste la réponse de l'API quand un mois invalide est fourni."""
    # Création d'un device
    client.post(
        "/api/devices",
        json={"device_id": "devG", "name": "Test", "location": "Test"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    # Appel avec un mois invalide
    res = client.post(
        "/api/graph-data",
        json={"device_id": "devG", "view": "month", "month": "invalid", "year": 2025},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res.status_code == 400


def test_pump_action_and_command(client, auth_token):
    """Teste l'activation et la désactivation de la pompe."""
    # Créer un device
    client.post(
        "/api/devices",
        json={"device_id": "pump1"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    # Activer la pompe
    res_on = client.post(
        "/api/pump_action",
        json={"device_id": "pump1", "action": "on"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_on.status_code == 200
    assert "Pompe on" in res_on.get_json()["status"]
    # Vérifier l'état de la pompe
    res_cmd_on = client.get("/api/pump_command/pump1")
    assert res_cmd_on.status_code == 200
    assert res_cmd_on.get_json()["action"] == "on"
    # Désactiver la pompe
    res_off = client.post(
        "/api/pump_action",
        json={"device_id": "pump1", "action": "off"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_off.status_code == 200
    # Vérifier l'état de la pompe après
    res_cmd_off = client.get("/api/pump_command/pump1")
    assert res_cmd_off.get_json()["action"] == "off"


def test_water_level_unknown_device(client, auth_token):
    """Envoie un niveau d'eau pour un device inexistant et vérifie l'erreur."""
    res = client.post(
        "/api/water-level",
        json={"device_id": "inconnu", "level": 50, "pump_state": 0, "timestamp": int(datetime.utcnow().timestamp())},
    )
    assert res.status_code == 400


def test_water_level_valid(client, auth_token):
    """Teste l'envoi d'un niveau d'eau et la création d'une entrée en base."""
    # Ajouter un device
    client.post(
        "/api/devices",
        json={"device_id": "wl1"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    # Envoyer un niveau d'eau normal
    res = client.post(
        "/api/water-level",
        json={"device_id": "wl1", "level": 80, "pump_state": 0, "timestamp": int(datetime.utcnow().timestamp())},
    )
    assert res.status_code == 200
    body = res.get_json()
    # Vérifier la structure de la réponse
    assert body["status"] == "succès"
    preds = body["predictions"]
    assert set(preds.keys()) == {"anomaly", "predicted_level", "cluster"}
    # Le prédicteur factice ajouté 1.0
    assert preds["predicted_level"] == 81.0


def test_add_timer_flow(client, auth_token):
    """Teste l'ajout, la récupération et la suppression d'un timer."""
    # Ajouter un device
    client.post(
        "/api/devices",
        json={"device_id": "timer1"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    # Format ISO‑8601 correct
    start_time = (datetime.utcnow() + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res_add = client.post(
        "/api/timer",
        json={"device_id": "timer1", "start_time": start_time, "duration": 5},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_add.status_code == 201
    timer_id = res_add.get_json()["timer_id"]
    # Récupération des timers
    res_list = client.get("/api/timers", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_list.status_code == 200
    timers = res_list.get_json()
    assert len(timers) == 1
    assert timers[0]["timer_id"] == timer_id
    # Suppression du timer
    res_del = client.delete(f"/api/timer/{timer_id}", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_del.status_code == 200
    # Vérifier qu'il n'est plus présent
    res_list_after = client.get("/api/timers", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_list_after.status_code == 200
    assert len(res_list_after.get_json()) == 0


def test_validate_iso8601_and_allowed_file():
    """Teste les fonctions utilitaires validate_iso8601 et allowed_file."""
    from app.utils import validate_iso8601, allowed_file
    # Chaîne valide
    assert validate_iso8601("2025-07-14T12:34:56Z") is True
    # Chaînes invalides
    assert validate_iso8601("2025-07-14 12:34:56") is False
    assert validate_iso8601("invalid") is False
    # Extensions autorisées
    assert allowed_file("photo.JPG") is True
    assert allowed_file("doc.pdf") is False