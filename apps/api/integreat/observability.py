"""Default Sentry observer. Explicit metadata only, no automatic integrations.

Never pass function arguments, exception messages, paths, prompts or observations here.
Telemetry failure must not change application results or exception propagation.
"""
from __future__ import annotations

import inspect
import logging
import time
from contextlib import ExitStack, contextmanager
from functools import wraps

from .config import Settings

OPERATIONS = frozenset({"http.request", "project.import", "project.build", "test.run",
                        "test.collect", "diagnosis.run", "visual.observe", "ai.structured",
                        "ai.image", "history.event"})
HISTORY_EVENTS = frozenset({"project.imported", "graph.updated", "test.started", "test.completed",
    "expectation.failed", "incident.created", "incident.resolved", "agent.started", "agent.stage",
    "agent.reported", "action.completed", "action.denied", "visual.started", "visual.completed", "error"})
PROVIDERS = frozenset({"gemini", "stepfun", "fake", "none", "other"})
ENDPOINTS = frozenset({"import_project", "rescan", "update_project", "delete_project", "get_graph",
                       "get_investigation", "start_test", "verify_test", "execute_action", "diagnose",
                       "request_repair", "refresh_repair", "serial_connect", "serial_release",
                       "capture", "configure", "start", "other"})
OUTCOMES = frozenset({"ok", "error", "cancelled", "passed", "failed", "unknown",
                      "pass", "fail", "inconclusive", "completed", "running", "created"})
LOG_BODY = "integreat.operation.completed"


def _attributes(values):
    """Closed attribute vocabulary, used on both spans and log envelopes."""
    safe = {}
    for key, value in values.items():
        if key == "operation" and isinstance(value, str) and value in OPERATIONS:
            safe[key] = value
        elif key == "provider" and isinstance(value, str) and value in PROVIDERS:
            safe[key] = value
        elif key == "endpoint" and isinstance(value, str) and value in ENDPOINTS:
            safe[key] = value
        elif key == "event_type" and isinstance(value, str) and value in HISTORY_EVENTS:
            safe[key] = value
        elif key == "source_kind" and value in ("live", "replay", "sim", "unknown"):
            safe[key] = value
        elif key == "outcome" and isinstance(value, str) and value in OUTCOMES:
            safe[key] = value
        elif key == "duration_ms" and type(value) in (int, float) and 0 <= value < 86_400_000:
            safe[key] = value
        elif key == "status_code" and type(value) is int and 100 <= value <= 599:
            safe[key] = value
    return safe


def scrub_log(log, _hint):
    if log.get("body") != LOG_BODY:
        return None
    values = {k: v.get("value") if isinstance(v, dict) else v
              for k, v in log.get("attributes", {}).items()}
    safe = _attributes(values)
    if "operation" not in safe:
        return None
    return {**{k: log[k] for k in ("body", "time_unix_nano", "trace_id", "span_id",
                                   "severity_text", "severity_number") if k in log},
            "attributes": safe}


def scrub_transaction(event, _hint):
    """Rebuild the envelope to discard any inherited scope/request metadata."""
    name = event.get("transaction")
    if name not in OPERATIONS:
        return None
    trace = event.get("contexts", {}).get("trace", {})
    def clean_span(span):
        return {**{k: span[k] for k in ("trace_id", "span_id", "parent_span_id", "start_timestamp",
                                       "timestamp", "status", "op") if k in span},
                "description": span.get("description") if span.get("description") in OPERATIONS else "operation",
                "data": _attributes(span.get("data", {}))}
    return {**{k: event[k] for k in ("type", "event_id", "transaction", "start_timestamp", "timestamp",
                                    "platform", "release", "environment") if k in event},
            "contexts": {"trace": {k: trace[k] for k in ("trace_id", "span_id", "parent_span_id", "op", "status") if k in trace}},
            "spans": [clean_span(s) for s in event.get("spans", [])],
            "tags": _attributes(event.get("tags", {}))}


class Telemetry:
    def __init__(self, settings: Settings, *, transport=None):
        self.client = None
        self.sdk = None
        self.status = "disabled" if not settings.sentry_enabled else "not_configured"
        if not settings.sentry_enabled:
            return
        if not settings.sentry_dsn:
            return  # No SDK import, threads, global initialization, or network.
        try:
            import sentry_sdk
            from sentry_sdk import logger
            self.sdk, self.logger = sentry_sdk, logger
            self.client = sentry_sdk.Client(
                dsn=settings.sentry_dsn, environment=settings.sentry_environment,
                release=settings.sentry_release, server_name="integreat-api",
                default_integrations=False, auto_enabling_integrations=False,
                data_collection={"user_info": False, "cookies": {"mode": "off"},
                    "http_headers": {"request": {"mode": "off"}}, "http_bodies": [],
                    "url_query_params": {"mode": "off"}, "gen_ai": {"inputs": False, "outputs": False},
                    "database_query_data": False, "queues": False,
                    "graphql": {"document": False, "variables": False},
                    "stack_frame_variables": False, "frame_context_lines": 0},
                include_local_variables=False, include_source_context=False,
                max_request_body_size="never", max_breadcrumbs=0, sample_rate=0,
                before_send=lambda event, hint: None, before_send_transaction=scrub_transaction,
                enable_logs=True, before_send_log=scrub_log, enable_metrics=False,
                trace_propagation_targets=[], traces_sample_rate=settings.sentry_traces_sample_rate,
                transport_queue_size=100, shutdown_timeout=1, transport=transport,
            )
            self.status = "active"
        except Exception:
            logging.getLogger(__name__).warning("Sentry unavailable; continuing with telemetry disabled")
            self.client = None  # Never print the DSN or SDK exception text.
            self.status = "unavailable"

    def history_event(self, event_type, payload):
        """Mirror only lifecycle metadata after history is saved. Return value is ignored.

        No Store, service, device manager or tool registry is passed to this observer.
        High-volume serial/frame events and arbitrary event text are never exported.
        """
        if self.client is None or event_type not in HISTORY_EVENTS:
            return
        try:
            source = payload.get("source", {})
            kind = source.get("kind", "unknown") if isinstance(source, dict) else "unknown"
            with self.operation("history.event", event_type=event_type, source_kind=kind) as state:
                outcome = payload.get("outcome")
                if outcome is None and isinstance(payload.get("result"), dict):
                    outcome = payload["result"].get("outcome")
                state.update(_attributes({"outcome": outcome}))
        except Exception:
            pass

    @contextmanager
    def operation(self, name, **attributes):
        state = _attributes({"operation": name, **attributes})
        stack, span = ExitStack(), None
        started = time.perf_counter()
        if self.client is not None and name in OPERATIONS:
            try:
                scope = stack.enter_context(self.sdk.new_scope())
                scope.set_client(self.client)
                if self.sdk.get_current_span() is None:
                    span = stack.enter_context(self.sdk.start_transaction(name=name, op=name))
                else:
                    span = stack.enter_context(self.sdk.start_span(op=name, name=name))
            except Exception:
                pass
        try:
            yield state
        except BaseException as exc:
            state["outcome"] = "error" if isinstance(exc, Exception) else "cancelled"
            raise
        finally:
            if self.client is not None and span is not None:
                try:
                    safe = _attributes({**state, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
                    safe.setdefault("outcome", "ok")
                    for key, value in safe.items():
                        span.set_data(key, value)
                        if key != "duration_ms":
                            scope.set_tag(key, value)
                    span.set_status("internal_error" if safe["outcome"] == "error" else "ok")
                    emit = self.logger.warning if safe["outcome"] in {"error", "failed", "fail", "inconclusive"} else self.logger.info
                    emit(LOG_BODY, attributes=safe)
                except Exception:
                    pass
            try:
                # Pass no exception into SDK exit hooks: exceptions are never collected.
                stack.close()
            except Exception:
                pass

    def close(self):
        if self.client is not None:
            try:
                self.client.close(timeout=1)
            except Exception:
                pass


def observed(name):
    """Instrument fixed workflow boundaries without inspecting arguments or result content."""
    def decorate(fn):
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_call(owner, *args, **kwargs):
                with owner.telemetry.operation(name) as state:
                    result = await fn(owner, *args, **kwargs)
                    if name == "test.run":
                        state["outcome"] = result.result.outcome.value if result.result else result.state.value
                    return result
            return async_call
        @wraps(fn)
        def sync_call(owner, *args, **kwargs):
            with owner.telemetry.operation(name):
                return fn(owner, *args, **kwargs)
        return sync_call
    return decorate


class ObservedProvider:
    def __init__(self, provider, telemetry):
        self.provider, self.telemetry = provider, telemetry

    def __getattr__(self, name):
        return getattr(self.provider, name)

    async def generate_structured(self, **kwargs):
        provider = self.name if self.name in PROVIDERS else "other"
        with self.telemetry.operation("ai.structured", provider=provider):
            return await self.provider.generate_structured(**kwargs)

    async def analyze_image_optional(self, **kwargs):
        provider = self.name if self.name in PROVIDERS else "other"
        with self.telemetry.operation("ai.image", provider=provider):
            return await self.provider.analyze_image_optional(**kwargs)


class TelemetryMiddleware:
    """Pure ASGI: no request/body reads, streaming wrapping, headers, or URL capture."""
    def __init__(self, app, telemetry):
        self.app, self.telemetry = app, telemetry

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (scope["type"] != "http" or path == "/api/v1/health"
                or path.startswith("/api/v1/devices/camera")):
            return await self.app(scope, receive, send)
        with self.telemetry.operation("http.request") as state:
            async def measured_send(message):
                if message["type"] == "http.response.start":
                    status = message["status"]
                    state.update(status_code=status, outcome="error" if status >= 500 else "ok")
                await send(message)
            try:
                await self.app(scope, receive, measured_send)
            finally:
                route = scope.get("route")
                endpoint = getattr(route, "name", "other")
                state["endpoint"] = endpoint if endpoint in ENDPOINTS else "other"
