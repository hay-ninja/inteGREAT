"""Devin Cloud v3 client — remote, reviewable software-fix proposals only (D-025).

Endpoints (verified 2026-10-17, docs.devin.ai):
  POST {base}/v3/organizations/{org}/sessions  → create (non-idempotent — never auto-retried)
  GET  {base}/v3/organizations/{org}/sessions/{devin_id} → status
  GET  {base}/v3/self                        → credentials check (creates nothing)

Auth: Bearer service-user key (cog_...) or PAT, org id from Settings > Devin API.
Devin works in its own cloud sandbox; nothing it returns is applied to the local checkout,
merged, or flashed — and a remote "finished" is not a hardware verification.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import Settings
from ..models import RepairState


class DevinUnavailable(RuntimeError):
    pass


@dataclass
class DevinSessionInfo:
    session_id: str
    url: str
    status: str
    status_detail: str | None = None
    pull_requests: list[str] = field(default_factory=list)
    structured_output: dict[str, Any] | None = None
    acus_consumed: float | None = None


def map_remote_state(status: str, detail: str | None) -> RepairState:
    """Map documented Devin lifecycle values to our understandable job states."""
    if status in ("new", "claimed"):
        return RepairState.queued
    if status in ("running", "resuming"):
        if detail in ("waiting_for_user", "waiting_for_approval"):
            return RepairState.needs_input
        return RepairState.working
    if status == "suspended":
        return RepairState.needs_input
    if status == "exit":
        return RepairState.ready_for_review if detail == "finished" else RepairState.failed
    return RepairState.failed  # "error" or anything unexpected


class DevinClientProtocol:
    """Shared surface so UnavailableDevin/FakeDevin drop in for the real client."""

    available: bool = False
    reason: str = "not configured"

    async def whoami(self) -> dict[str, Any]:
        raise DevinUnavailable(self.reason)

    async def create_session(self, *, prompt: str, repos: list[str], title: str, tags: list[str],
                             max_acu_limit: float, structured_output_schema: dict[str, Any],
                             timeout_s: float) -> DevinSessionInfo:
        raise DevinUnavailable(self.reason)

    async def get_session(self, devin_id: str, timeout_s: float = 30.0) -> DevinSessionInfo:
        raise DevinUnavailable(self.reason)


class UnavailableDevin(DevinClientProtocol):
    def __init__(self, reason: str):
        self.reason = reason


class DevinHTTPClient(DevinClientProtocol):
    available = True
    reason = None

    def __init__(self, api_key: str, org_id: str, base_url: str = "https://api.devin.ai"):
        self.org_id = org_id
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    async def _request(self, method: str, path: str, timeout_s: float, **kw) -> dict[str, Any]:
        try:
            resp = await asyncio.wait_for(getattr(self._client, method)(path, **kw), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise
        except httpx.HTTPError as e:
            raise DevinUnavailable(f"Devin request failed: {type(e).__name__}: {e}"[:300]) from e
        if resp.status_code == 401:
            raise DevinUnavailable("Devin authentication failed (401) — check DEVIN_API_KEY")
        if resp.status_code == 403:
            raise DevinUnavailable("Devin rejected the request (403) — check org permissions")
        if resp.status_code == 404:
            raise DevinUnavailable("Devin session not found (404)")
        if resp.status_code == 429:
            raise DevinUnavailable("Devin rate limit (429) — try again later")
        if resp.status_code >= 400:
            raise DevinUnavailable(f"Devin HTTP {resp.status_code}: {resp.text[:160]}")
        try:
            return resp.json()
        except ValueError as e:
            raise DevinUnavailable("Devin returned malformed JSON") from e

    async def whoami(self) -> dict[str, Any]:
        return await self._request("get", "/v3/self", 15.0)

    def _session(self, data: dict[str, Any]) -> DevinSessionInfo:
        prs = data.get("pull_requests") or []
        return DevinSessionInfo(
            session_id=str(data.get("session_id") or data.get("devin_id") or ""),
            url=str(data.get("url") or ""),
            status=str(data.get("status") or ""),
            status_detail=data.get("status_detail"),
            pull_requests=[str(p.get("pr_url")) for p in prs if isinstance(p, dict) and p.get("pr_url")],
            structured_output=data.get("structured_output") if isinstance(data.get("structured_output"), dict) else None,
            acus_consumed=data.get("acus_consumed"))

    async def create_session(self, *, prompt: str, repos: list[str], title: str, tags: list[str],
                             max_acu_limit: float, structured_output_schema: dict[str, Any],
                             timeout_s: float) -> DevinSessionInfo:
        body: dict[str, Any] = {"prompt": prompt, "title": title[:255], "tags": tags[:8],
                                "max_acu_limit": max_acu_limit, "resumable": False,
                                "structured_output_required": True,
                                "structured_output_schema": structured_output_schema}
        if repos:
            body["repos"] = repos
        data = await self._request("post", f"/v3/organizations/{self.org_id}/sessions", timeout_s, json=body)
        return self._session(data)

    async def get_session(self, devin_id: str, timeout_s: float = 30.0) -> DevinSessionInfo:
        data = await self._request("get", f"/v3/organizations/{self.org_id}/sessions/{devin_id}", timeout_s)
        return self._session(data)


class FakeDevin(DevinClientProtocol):
    """Scripted client for tests. `script`: list of (status, detail, prs?, structured?) dicts served
    in order for get_session; create_error raises on create_session (e.g. asyncio.TimeoutError)."""

    def __init__(self, script: list[dict[str, Any]] | None = None, create_error: Exception | None = None):
        self.available = True
        self.reason = None
        self.script = list(script or [{"status": "running", "status_detail": "working"}])
        self.create_error = create_error
        self.calls: list[str] = []
        self.prompts: list[str] = []
        self._counter = 0

    async def whoami(self) -> dict[str, Any]:
        return {"principal_type": "service_user", "service_user_name": "fake"}

    async def create_session(self, *, prompt: str, timeout_s: float, **kw) -> DevinSessionInfo:
        self.calls.append("create")
        self.prompts.append(prompt)
        if self.create_error is not None:
            raise self.create_error
        self._counter += 1
        sid = f"devin-fake{self._counter}"
        first = self.script[0]
        return DevinSessionInfo(session_id=sid, url=f"https://app.devin.ai/sessions/{sid}",
                                status=first["status"], status_detail=first.get("status_detail"))

    async def get_session(self, devin_id: str, timeout_s: float = 30.0) -> DevinSessionInfo:
        self.calls.append("get")
        s = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        prs = s.get("pull_requests", [])
        prs = [str(p.get("pr_url")) if isinstance(p, dict) else str(p) for p in prs]
        return DevinSessionInfo(session_id=devin_id, url=f"https://app.devin.ai/sessions/{devin_id}",
                                status=s["status"], status_detail=s.get("status_detail"),
                                pull_requests=prs,
                                structured_output=s.get("structured_output"),
                                acus_consumed=s.get("acus_consumed"))


def make_devin(settings: Settings) -> DevinClientProtocol:
    if not settings.devin_api_key:
        return UnavailableDevin("DEVIN_API_KEY not set")
    if not settings.devin_org_id:
        return UnavailableDevin("INTEGREAT_DEVIN_ORG_ID not set (Settings → Devin API)")
    try:
        return DevinHTTPClient(settings.devin_api_key, settings.devin_org_id, settings.devin_api_base)
    except Exception as e:  # noqa: BLE001
        return UnavailableDevin(f"Devin client failed to start: {e}")
