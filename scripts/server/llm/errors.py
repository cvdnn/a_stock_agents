from __future__ import annotations

from typing import Optional


class LLMReadinessError(RuntimeError):
    """Stable, user-safe failure raised before business tools may run."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider_id = provider_id
        self.model_id = model_id

