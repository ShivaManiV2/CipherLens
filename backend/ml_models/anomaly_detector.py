"""
CipherLens — Anomaly Detection Module
Uses Isolation Forest to detect suspicious user behavior based on audit logs.
"""

import numpy as np
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from sklearn.ensemble import IsolationForest

class AnomalyDetector:
    def __init__(self):
        # We use a global model for all users
        # contamination=0.05 means we expect ~5% of data to be anomalous
        self.model = IsolationForest(contamination=0.05, random_state=42)
        self.is_trained = False

    def extract_features(self, logs: List[Any]) -> Dict[int, List[float]]:
        """
        Extract features for each user based on their recent activity (last 24 hours from the latest log).
        Features:
        0: Number of LOGIN actions
        1: Number of SIGN actions
        2: Number of VERIFY actions
        3: Number of unique IP addresses used
        """
        if not logs:
            return {}

        user_features = defaultdict(lambda: {"login": 0, "sign": 0, "verify": 0, "ips": set()})
        
        # Consider the most recent log time as 'now' for the dataset
        latest_time = max(log.timestamp for log in logs)
        if not latest_time.tzinfo:
            latest_time = latest_time.replace(tzinfo=timezone.utc)

        for log in logs:
            log_time = log.timestamp
            if not log_time.tzinfo:
                log_time = log_time.replace(tzinfo=timezone.utc)
            
            # Only consider logs within the 24h window of the latest log for that batch
            if latest_time - log_time <= timedelta(days=1):
                uid = log.user_id
                action = log.action.upper()
                
                if action == "LOGIN":
                    user_features[uid]["login"] += 1
                elif action == "SIGN":
                    user_features[uid]["sign"] += 1
                elif action == "VERIFY":
                    user_features[uid]["verify"] += 1
                
                if log.ip_address:
                    user_features[uid]["ips"].add(log.ip_address)

        # Convert to feature vectors
        feature_dict = {}
        for uid, feats in user_features.items():
            feature_dict[uid] = [
                float(feats["login"]),
                float(feats["sign"]),
                float(feats["verify"]),
                float(len(feats["ips"]))
            ]
            
        return feature_dict

    def train(self, logs: List[Any]) -> bool:
        """
        Train the Isolation Forest model using historical audit logs.
        """
        feature_dict = self.extract_features(logs)
        if len(feature_dict) < 5:
            # Not enough data to train a meaningful anomaly detector
            return False
            
        X = list(feature_dict.values())
        self.model.fit(X)
        self.is_trained = True
        return True

    def predict(self, recent_logs: List[Any], target_user_id: int) -> Tuple[bool, float]:
        """
        Predict if a user's recent behavior is anomalous.
        Returns:
            (is_anomalous: bool, anomaly_score: float)
            Score is typically between -1 and 1. Lower (negative) means more anomalous.
        """
        if not self.is_trained:
            # If not trained, fallback to safe
            return False, 1.0

        feature_dict = self.extract_features(recent_logs)
        if target_user_id not in feature_dict:
            return False, 1.0

        x = np.array([feature_dict[target_user_id]])
        prediction = self.model.predict(x)[0]
        score = self.model.score_samples(x)[0]
        
        # prediction is -1 for outliers, 1 for inliers
        is_anomalous = bool(prediction == -1)
        return is_anomalous, float(score)

# Global instance
anomaly_detector = AnomalyDetector()
