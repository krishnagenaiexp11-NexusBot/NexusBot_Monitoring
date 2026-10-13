from dataclasses import dataclass, field
import json

@dataclass
class VariantResult:
    variant_name: str
    parameters: dict
    train_metrics: dict
    val_metrics: dict
    stability_score: float
    validation_stability_score: float
    deployment_score: float
    ranking: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "variant_name": self.variant_name,
            "parameters": self.parameters,
            "train_metrics": self.train_metrics,
            "val_metrics": self.val_metrics,
            "stability_score": self.stability_score,
            "validation_stability_score": self.validation_stability_score,
            "deployment_score": self.deployment_score,
            "ranking": self.ranking,
            "warnings": self.warnings
        }

@dataclass
class GenerationResult:
    generation_index: int
    variants: list[VariantResult] = field(default_factory=list)
    ai_diagnostics: str = ""

    def to_dict(self) -> dict:
        return {
            "generation_index": self.generation_index,
            "variants": [v.to_dict() for v in self.variants],
            "ai_diagnostics": self.ai_diagnostics
        }
