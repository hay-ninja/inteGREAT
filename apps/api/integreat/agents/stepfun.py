"""StepFun provider: OpenAI-compatible chat completions with strict JSON-schema output (D-023).

Used for triage and synthesis (the orchestration roles) while Gemini supplies specialists.
The model only returns JSON that matches the declared schema; our side still re-validates every
evidence/action/agent id it emits — schema-valid is necessary, not sufficient.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .provider import LLMInvalidOutput, LLMUnavailable

T = TypeVar("T", bound=BaseModel)

_DROP = {"title", "default", "$defs", "examples"}


def strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Convert a pydantic model to an OpenAI-style strict JSON schema:
    $defs inlined, every object gets required=[all properties] and additionalProperties=false.
    Nested objects become self-contained so the provider needs no $ref resolution."""
    raw = schema.model_json_schema()
    defs = raw.get("$defs", {})

    def resolve(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs.get(str(node["$ref"]).rsplit("/", 1)[-1], {})
            return resolve(dict(target))
        out = {}
        for k, v in node.items():
            if k in _DROP:
                continue
            if isinstance(v, dict):
                v = resolve(v)
            elif isinstance(v, list):
                v = [resolve(i) for i in v]
            out[k] = v
        if out.get("type") == "object" or "properties" in out:
            out.setdefault("type", "object")
            props = out.setdefault("properties", {})
            out["required"] = sorted(props)
            out["additionalProperties"] = False
        return out

    return resolve(raw)


class StepFunProvider:
    """Global StepFun endpoint (api.stepfun.ai). Model default: step-5-preview."""

    name = "stepfun"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.stepfun.ai/v1",
                 temperature: float = 0.2, max_output_tokens: int = 2048):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @property
    def available(self) -> bool:
        return True

    async def _call(self, system: str, prompt: str, schema: type[T], timeout_s: float) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": schema.__name__.lower(), "strict": True, "schema": strict_schema(schema)}},
        }
        try:
            resp = await asyncio.wait_for(
                self._client.post("/chat/completions", json=payload), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"StepFun request failed: {type(e).__name__}: {e}"[:400]) from e
        if resp.status_code != 200:
            detail = resp.text[:200].replace("\n", " ")
            raise LLMUnavailable(f"StepFun HTTP {resp.status_code}: {detail}"[:400])
        try:
            return resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            raise LLMInvalidOutput(f"StepFun malformed response: {resp.text[:200]}") from e

    async def generate_structured(self, *, system: str, prompt: str, schema: type[T], timeout_s: float) -> T:
        text = await self._call(system, prompt, schema, timeout_s)
        try:
            return schema.model_validate_json(text)
        except ValidationError as e:
            repair = (f"{prompt}\n\nYour previous output did not match the required JSON schema:\n"
                      f"{str(e)[:1500]}\nReturn ONLY corrected JSON.")
            text = await self._call(system, repair, schema, timeout_s)
            try:
                return schema.model_validate_json(text)
            except ValidationError as e2:
                raise LLMInvalidOutput(str(e2)[:500]) from e2

    async def analyze_image_optional(self, **_: Any) -> str | None:
        return None  # vision analysis stays with the Gemini runtime-vision path for now
