from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.2.0"


class ContradictionWeights(BaseModel):
    conclusion: float = 0.35
    constraint: float = 0.25
    evidence: float = 0.15
    assumption: float = 0.15
    premise: float = 0.10

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> ContradictionWeights:
        total = (
            self.conclusion
            + self.constraint
            + self.evidence
            + self.assumption
            + self.premise
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"contradiction weights must sum to 1.0, got {total}")
        return self


class ClassifierFeatureConfig(BaseModel):
    numeric_empirical: float = 0.35
    numeric_pragmatic: float = 0.10
    graph_empirical: float = 0.25
    graph_pragmatic: float = 0.15
    objective_pragmatic: float = 0.40
    policy_rules: float = 0.45
    policy_domain: float = 0.25
    lexeme_empirical: float = 0.20
    lexeme_policy: float = 0.20
    lexeme_pragmatic: float = 0.20
    open_multi_present: float = 0.30
    open_long_query: float = 0.20
    score_floor: float = 0.35
    score_margin: float = 0.10
    long_query_chars: int = 240


def _default_regime_required() -> Dict[str, List[str]]:
    return {
        "closed_formal": ["formal"],
        "empirical": ["empirical", "causal"],
        "policy_normative": ["policy", "formal"],
        "pragmatic_systems": ["utility", "causal", "empirical"],
        "open_dialectic": ["formal", "policy", "empirical", "causal", "utility"],
    }


def _default_regime_optional() -> Dict[str, List[str]]:
    return {
        "closed_formal": ["empirical"],
        "empirical": ["formal"],
        "policy_normative": ["utility", "empirical"],
        "pragmatic_systems": ["policy", "formal"],
        "open_dialectic": [],
    }


def _default_domain_overlays() -> Dict[str, List[str]]:
    return {
        "legal": ["policy"],
        "security": ["policy"],
        "privacy": ["policy"],
        "healthcare": ["policy"],
        "finance": ["policy"],
        "sre": ["utility", "empirical"],
        "infra": ["utility", "empirical"],
        "performance": ["utility", "empirical"],
        "science": ["empirical", "causal"],
        "telemetry": ["empirical", "causal"],
    }


class SelectorTableConfig(BaseModel):
    fill_order: List[str] = Field(
        default_factory=lambda: ["formal", "policy", "empirical", "causal", "utility"]
    )
    regime_required: Dict[str, List[str]] = Field(default_factory=_default_regime_required)
    regime_optional: Dict[str, List[str]] = Field(default_factory=_default_regime_optional)
    domain_overlays: Dict[str, List[str]] = Field(default_factory=_default_domain_overlays)


class LLMConfig(BaseModel):
    enabled: bool = False
    model_id: str = ""
    temperature: float = 0.0
    seed: int = 0
    cache: bool = True


class EngineConfig(BaseModel):
    """v1.1 engineering priors. Not claimed to be empirically calibrated."""

    schema_version: Literal["1.1.0", "1.2.0"] = SCHEMA_VERSION
    tau_base: float = 0.40
    qualified_tau: float = 0.20
    u_insufficient: float = 0.60
    uncited_penalty: float = 0.50
    contradiction: ContradictionWeights = ContradictionWeights()
    classifier: ClassifierFeatureConfig = ClassifierFeatureConfig()
    selector: SelectorTableConfig = SelectorTableConfig()
    llm: LLMConfig = LLMConfig()
    min_heads: int = 3
    stale_hours: float = 168.0
    head_timeout_ms: int = 250
    pool_budget_ms: int = 400
    counterfactual_timeout_ms: int = 200
    max_probes: int = 12
    max_probe_params: int = 4
    n_unresolved_cap: int = 10
    isolate_heads: bool = True
    dynamic_tau: bool = True
    stop_on_first_resolving: bool = False

    @property
    def llm_enabled(self) -> bool:
        return self.llm.enabled


def config_hash(config: EngineConfig) -> str:
    payload = config.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


DEFAULT_CONFIG = EngineConfig()
DEFAULT_CONFIG_HASH = config_hash(DEFAULT_CONFIG)
