#!/usr/bin/env python3
"""Capture the hosted-demo replay bundle (D-034).

Drives a running local API through both demo stories — import → graph →
expectation → sim run → incident → inspect/manual actions → repeat/verify —
and writes every response the frontend could request into
`apps/web/public/replay/demo.json`. The built site serves these responses when
no backend is reachable, so judges can click the whole demo story on a static
deploy while the full app keeps working locally.

Run: `apps/api/.venv/Scripts/python scripts/capture_demo_replay.py`
(requires the API on :8000).
"""
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
OUT = "apps/web/public/replay/demo.json"

routes: dict[str, object] = {}
evidence_by_id: dict[str, object] = {}
# iid -> request-body hashes that resolve the incident (verify_fix passes). The
# open-state view is served under `GET /investigations/{iid}`; the resolved view
# under `GET /investigations/{iid}#resolved`, gated on these hashes.
resolves: dict[str, list[str]] = {}


def key_for(method: str, path: str, body: object | None) -> str:
    if body is None:
        return f"{method} {path}"
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return f"{method} {path}::{hashlib.sha1(canon.encode()).hexdigest()[:12]}"


def call(method: str, path: str, body: object | None = None, record: bool = True):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        print(f"HTTP {e.code} {method} {path}: {detail}", file=sys.stderr)
        raise
    if record:
        routes[key_for(method, path, body)] = resp
    return resp


def enc(v: str) -> str:
    return urllib.parse.quote(v, safe="")


def collect_evidence(payload) -> None:
    """Pull every evidence dict out of a nested response into the id map."""
    if isinstance(payload, dict):
        if isinstance(payload.get("id"), str) and payload["id"].startswith("evidence:"):
            evidence_by_id[payload["id"]] = payload
        for v in payload.values():
            collect_evidence(v)
    elif isinstance(payload, list):
        for v in payload:
            collect_evidence(v)


def wait_run(run_id: str):
    for _ in range(120):
        detail = call("GET", f"/tests/{enc(run_id)}")
        if detail.get("run", {}).get("state") in ("completed", "failed", "error"):
            return detail
        time.sleep(1)
    raise SystemExit(f"run {run_id} never finished")


def capture_fixture(fx: dict, scenario: str) -> dict:
    proj = call("POST", "/projects/import",
                {"repo_path": fx["repo_path"], "manifest_path": fx["manifest_path"]})
    pid = proj["id"]
    print(f"  imported {proj['name']} -> {pid}")

    for path in (f"/projects/{enc(pid)}", f"/projects/{enc(pid)}/graph",
                 f"/projects/{enc(pid)}/graph?scope_node_id=subsystem%3Amotor_control",
                 f"/projects/{enc(pid)}/subsystems"):
        call("GET", path)

    exp = call("POST", f"/projects/{enc(pid)}/expectations/propose")
    confirm = {"target": exp["target"], "tolerance": exp["tolerance"],
               "deadline_ms": exp["deadline_ms"], "trigger_value": exp["trigger"]["value"]}
    call("POST", f"/projects/{enc(pid)}/expectations/{enc(exp['id'])}/confirm", confirm)

    source = {"kind": "sim", "scenario": scenario}
    run = call("POST", f"/projects/{enc(pid)}/tests",
               {"expectation_id": exp["id"], "source": source})
    detail = wait_run(run["id"])
    collect_evidence(detail)
    call("GET", f"/tests/{enc(run['id'])}/flow")

    incidents = call("GET", f"/projects/{enc(pid)}/incidents")
    call("GET", f"/projects/{enc(pid)}/expectations")
    if not incidents:
        print(f"  no incident for {pid} (run may have passed) — done")
        return proj
    iid = incidents[-1]["id"]
    view = call("GET", f"/investigations/{enc(iid)}")
    collect_evidence(view)

    # Permissions: record grant + revoke responses for every category the actions need.
    cats = {a.get("permission_category") for a in view.get("actions", [])} - {None}
    for cat in sorted(cats):
        for granted in (True, False):
            call("POST", f"/investigations/{enc(iid)}/permissions",
                 {"category": cat, "granted": granted})

    # Order matters: verify_fix can resolve the incident, after which everything
    # 409s — record non-run actions first, repeats next, verify last.
    actions = view.get("actions", [])
    ordered = ([a for a in actions if a.get("kind") in ("inspect_source", "run_readonly_tool", "expand_scope", "request_manual_check")]
               + [a for a in actions if a.get("kind") == "repeat_test"]
               + [a for a in actions if a.get("kind") == "verify_fix"])
    for a in ordered:
        aid = a["id"]
        kind = a.get("kind")
        try:
            if kind in ("inspect_source", "run_readonly_tool", "expand_scope"):
                res = call("POST", f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute",
                           {"approve_once": True})
                # The app may also send approve_once=false after a standing grant.
                routes[key_for("POST", f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute",
                               {"approve_once": False})] = res
                collect_evidence(res)
            elif kind in ("repeat_test", "verify_fix"):
                for src in (source, {"kind": "replay", "scenario": "good"}):
                    body = {"source": src, "approve_once": False}
                    res = call("POST", f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute", body)
                    collect_evidence(res)
                    tid = (res.get("result") or res).get("test_run_id")
                    if tid:
                        d = wait_run(tid)
                        collect_evidence(d)
                        call("GET", f"/tests/{enc(tid)}/flow")
                    if kind == "verify_fix":
                        after = call("GET", f"/investigations/{enc(iid)}", record=False)
                        if after.get("incident", {}).get("state") == "resolved":
                            resolves.setdefault(iid, []).append(key_for("POST",
                                f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute", body).split("::")[-1])
                            routes[f"GET /investigations/{enc(iid)}#resolved"] = after
            elif kind == "request_manual_check":
                for choice in a.get("result_choices", []):
                    call("POST", f"/investigations/{enc(iid)}/manual-results",
                         {"action_id": aid, "result": choice})
        except urllib.error.HTTPError as e:
            print(f"  {kind} ({aid}) -> HTTP {e.code} — skipped")

    # Final incident state + repair surfaces. The open view (captured right after
    # the run) stays under the plain key; the resolved view rides under #resolved.
    final_view = call("GET", f"/investigations/{enc(iid)}", record=False)
    collect_evidence(final_view)
    if iid in resolves:
        routes[f"GET /investigations/{enc(iid)}#resolved"] = final_view
    else:
        routes[f"GET /investigations/{enc(iid)}"] = final_view
    call("GET", f"/investigations/{enc(iid)}/repairs")
    call("GET", f"/investigations/{enc(iid)}/repairs/preflight")
    return proj


def main() -> None:
    demo = call("GET", "/demo")
    call("GET", "/sources")
    call("GET", "/replays")
    call("GET", "/devices")

    # Honest AI status for the hosted build — the demo runs without a backend.
    agents = call("GET", "/agents/status")
    agents["available"] = False
    agents["reason"] = "Hosted demo — AI review runs in the full local app"
    routes["GET /agents/status"] = agents

    fixtures = demo["fixtures"]
    plan = [(fixtures[0], "connected"), (fixtures[1], "signal_disconnected")]
    projects = [capture_fixture(fx, sc) for fx, sc in plan]

    routes["GET /projects"] = projects

    bundle = {"captured_for": "hosted-demo", "routes": routes, "evidence": evidence_by_id,
              "resolves": resolves}
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(bundle, f)
    kb = len(json.dumps(bundle)) // 1024
    print(f"wrote {OUT}: {len(routes)} routes, {len(evidence_by_id)} evidence records, {kb} kB")


if __name__ == "__main__":
    main()
