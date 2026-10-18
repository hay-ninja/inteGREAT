"""LLM provider interface (PRD §11.4). Gemini first; a scripted fake for tests; an explicit 'unavailable'.

Model id, temperature, token budget, retries and the API key come from configuration. The key is never
sent to the frontend or into model context.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    pass


class LLMInvalidOutput(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str | None

    @property
    def available(self) -> bool: ...

    async def generate_structured(self, *, system: str, prompt: str, schema: type[T], timeout_s: float) -> T: ...

    async def analyze_image_optional(self, *, prompt: str, jpeg: bytes, timeout_s: float) -> str | None: ...


class UnavailableProvider:
    name = "none"
    model = None

    def __init__(self, reason: str):
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    async def generate_structured(self, **_: Any):
        raise LLMUnavailable(self.reason)

    async def analyze_image_optional(self, **_: Any) -> str | None:
        return None


class GeminiProvider:
    """google-genai structured output. One bounded repair attempt on invalid JSON (PRD §11.3)."""

    name = "gemini"

    def __init__(self, api_key: str, model: str, temperature: float = 0.2, max_output_tokens: int = 2048):
        from google import genai  # imported lazily so tests/offline use don't need network setup

        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @property
    def available(self) -> bool:
        return True

    async def _call(self, system: str, prompt: str, schema: type[T], timeout_s: float) -> str:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system, temperature=self.temperature, max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json", response_schema=schema)
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(model=self.model, contents=prompt, config=cfg),
                timeout=timeout_s)
        except asyncio.TimeoutError:
            raise
        except Exception as e:  # noqa: BLE001 — quota, auth, network: all mean "model unavailable"
            raise LLMUnavailable(f"Gemini call failed: {type(e).__name__}: {e}"[:400]) from e
        return resp.text or ""

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

    async def analyze_image_optional(self, *, prompt: str, jpeg: bytes, timeout_s: float) -> str | None:
        from google.genai import types

        try:
            resp = await asyncio.wait_for(self._client.aio.models.generate_content(
                model=self.model, contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), prompt]),
                timeout=timeout_s)
        except Exception:  # noqa: BLE001 — optional by definition
            return None
        return resp.text


class FakeProvider:
    """Deterministic provider for tests: `script(schema_name, prompt) -> dict | Exception`."""

    name = "fake"
    model = "fake-model"

    def __init__(self, script: Callable[[str, str], Any]):
        self.script = script
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return True

    async def generate_structured(self, *, system: str, prompt: str, schema: type[T], timeout_s: float) -> T:
        self.calls.append((schema.__name__, system + "\n" + prompt))
        out = self.script(schema.__name__, prompt)
        if isinstance(out, BaseException):
            raise out
        if isinstance(out, (int, float)):  # a delay in seconds → simulate a slow model
            await asyncio.wait_for(asyncio.sleep(out), timeout=timeout_s)
            raise LLMUnavailable("unreachable")
        try:
            return schema.model_validate(out)
        except ValidationError as e:
            raise LLMInvalidOutput(str(e)[:500]) from e

    async def analyze_image_optional(self, **_: Any) -> str | None:
        return None
