"""
runtime/runtime_models.py
Data models for NexusBot V2 runtime layer.
"""
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class DeploymentProfile:
    """
    Represents a fully-validated, deployment-ready strategy configuration.
    Produced by the Deployment Candidate Engine.
    Persisted as JSON by profile_storage.py.
    """
    # Identity
    profile_id:       str
    symbol:           str
    strategy:         str

    # Scoring
    deployment_score: float
    grade:            str           # UNSAFE / EXPERIMENTAL / PROMISING / ROBUST / RARE

    # Parameters
    parameters:       dict = field(default_factory=dict)
    full_parameters:  dict = field(default_factory=dict)

    # Metrics
    validation_metrics: dict = field(default_factory=dict)
    train_metrics:      dict = field(default_factory=dict)
    stability_score:    float = 0.0

    # Warnings
    warnings:           list = field(default_factory=list)
    ready_for_deployment: bool = False

    # Timestamps
    generated_at:     str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z"
    )
    description:      Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeploymentProfile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_candidate(cls, candidate: dict, profile_id: str) -> "DeploymentProfile":
        """Converts a deployment candidate dict to a DeploymentProfile."""
        return cls(
            profile_id          = profile_id,
            symbol              = candidate.get("symbol",              "UNKNOWN"),
            strategy            = candidate.get("strategy",            "UNKNOWN"),
            deployment_score    = float(candidate.get("deployment_score", 0.0)),
            grade               = candidate.get("grade",               "UNKNOWN"),
            parameters          = candidate.get("parameters",          {}),
            full_parameters     = candidate.get("full_parameters",     {}),
            validation_metrics  = candidate.get("validation_metrics",  {}),
            train_metrics       = candidate.get("train_metrics",       {}),
            stability_score     = float(candidate.get("stability_score", 0.0)),
            warnings            = candidate.get("warnings",            []),
            ready_for_deployment= bool(candidate.get("ready_for_deployment", False)),
            generated_at        = candidate.get("generated_at",        datetime.datetime.utcnow().isoformat() + "Z"),
        )
