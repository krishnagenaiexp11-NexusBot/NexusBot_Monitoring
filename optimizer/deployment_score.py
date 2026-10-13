"""
optimizer/deployment_score.py
Thin re-export of research.deployment_score for use within the optimizer package.
"""
from research.deployment_score import (   # noqa: F401
    calculate_deployment_score,
    calculate_grade,
)

__all__ = ["calculate_deployment_score", "calculate_grade"]
