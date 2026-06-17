from __future__ import annotations

from zer0factor.eval.domain import EvaluationRequest
from zer0factor.registry import FactorRegistry


class FactorSelector:
    def resolve(self, request: EvaluationRequest) -> tuple[str, ...]:
        if request.factor_source == "explicit":
            return self._resolve_explicit(request)
        if request.factor_source == "registry":
            return self._resolve_registry(request)
        raise ValueError(
            f"unknown factor_source '{request.factor_source}': "
            "must be 'explicit' or 'registry'"
        )

    def _resolve_explicit(self, request: EvaluationRequest) -> tuple[str, ...]:
        factor_names = tuple(request.factor_names)
        if not factor_names:
            raise ValueError("factor_names must not be empty")
        return factor_names

    def _resolve_registry(self, request: EvaluationRequest) -> tuple[str, ...]:
        registry = FactorRegistry(request.registry_path)
        candidates = registry.filter(enabled=True if request.enabled_only else None)
        if request.categories:
            categories = set(request.categories)
            candidates = [factor for factor in candidates if factor.category in categories]
        factor_names = tuple(factor.name for factor in candidates)
        if not factor_names:
            raise ValueError("no factors matched from registry with the given filters")
        return factor_names
