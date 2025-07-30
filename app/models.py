import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import joblib
import os

def generate_simulated_data(device_id="chateau_1", n=1000, start_level=80.0):
    data = []
    current_time = datetime(2025, 7, 14, 0, 0)
    level = start_level

    for i in range(n):
        pump_state = random.choices([0, 1], weights=[0.85, 0.15])[0]
        variation = random.uniform(0.01, 0.2)
        if pump_state == 1:
            level = min(100.0, level + variation)
        else:
            level = max(0.0, level - variation)

        timestamp = int(current_time.timestamp())
        received_at = current_time.isoformat() + "Z"
        hour = current_time.hour
        day = current_time.date()

        data.append({
            "device_id": device_id,
            "timestamp": timestamp,
            "received_at": received_at,
            "level": level,
            "pump_state": pump_state,
            "hour": hour,
            "day": str(day)
        })

        current_time += timedelta(minutes=1)

    df = pd.DataFrame(data)
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/simulated_data.csv", index=False)
    return df

class WaterLevelPredictor:
    def __init__(self):
        self.scaler = joblib.load("models/scaler.joblib")
        self.isoforest = joblib.load("models/isolation_forest.joblib")
        self.regressor = joblib.load("models/regression.joblib")
        self.kmeans = joblib.load("models/kmeans.joblib")

    def predict(self, data):
        df = pd.DataFrame([data])
        df["pump_state"] = df["pump_state"].astype(int)
        features = ["level", "hour", "pump_state"]
        X = df[features]
        X_scaled = self.scaler.transform(X)
        anomaly = self.isoforest.predict(X_scaled)[0]
        predicted_level = self.regressor.predict(df[["hour", "pump_state"]])[0]
        cluster = self.kmeans.predict(X_scaled)[0]
        return {
            "anomaly": anomaly == -1,
            "predicted_level": predicted_level,
            "cluster": int(cluster)
        }