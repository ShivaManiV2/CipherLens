"""
CipherLens — Security & Anomaly Detection Endpoints

POST /api/security/train-anomaly-model — Train the Isolation Forest model on historical audit logs.
GET  /api/security/anomalies           — Get recent anomalous user behaviors.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_user
from backend.models.models import AuditLog, User
from backend.ml_models.anomaly_detector import anomaly_detector

router = APIRouter(prefix="/api/security", tags=["Security"])


class TrainResponse(BaseModel):
    message: str
    is_trained: bool


class AnomalyResult(BaseModel):
    user_id: int
    username: str
    is_anomalous: bool
    anomaly_score: float
    features: Dict[str, float]


@router.post(
    "/train-anomaly-model",
    response_model=TrainResponse,
    summary="Train Anomaly Detection Model",
)
async def train_model(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Train the global Isolation Forest model on historical audit logs.
    Requires at least 5 active users/sessions to train effectively.
    """
    # Fetch all audit logs
    logs = db.query(AuditLog).all()
    
    # Train the model
    success = anomaly_detector.train(logs)
    
    if not success:
        return TrainResponse(
            message="Not enough audit log data to train the model. Perform more actions first.",
            is_trained=False,
        )
        
    return TrainResponse(
        message="Anomaly detection model successfully trained on historical data.",
        is_trained=True,
    )


@router.get(
    "/anomalies",
    response_model=List[AnomalyResult],
    summary="Fetch Recent Anomalies",
)
async def get_anomalies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch recent anomalous behaviors for all users over the last 24 hours.
    Requires the model to be trained first via POST /train-anomaly-model.
    """
    if not anomaly_detector.is_trained:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model is not trained. Call /train-anomaly-model first."
        )

    # Get logs from the last 24 hours
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    recent_logs = db.query(AuditLog).filter(AuditLog.timestamp >= one_day_ago).all()
    
    if not recent_logs:
        return []

    # Get features for all users in the recent window
    feature_dict = anomaly_detector.extract_features(recent_logs)
    
    results = []
    # Predict for each user
    for uid, feats in feature_dict.items():
        is_anomalous, score = anomaly_detector.predict(recent_logs, uid)
        
        # Look up username
        user = db.query(User).filter(User.id == uid).first()
        username = user.username if user else f"Unknown (ID: {uid})"
        
        results.append(
            AnomalyResult(
                user_id=uid,
                username=username,
                is_anomalous=is_anomalous,
                anomaly_score=score,
                features={
                    "login": feats[0],
                    "sign": feats[1],
                    "verify": feats[2],
                    "unique_ips": feats[3]
                }
            )
        )
        
    # Return only anomalous results
    return [r for r in results if r.is_anomalous]
