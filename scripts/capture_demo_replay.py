#!/usr/bin/env python3
"""Capture the hosted-demo replay bundle (D-034, extended for the Halloween seed D-046).

Drives a running local API through the demo stories — import → graph →
expectation → run → incident → inspect/manual actions → repair → repeat/verify —
and writes every response the frontend could request into
`apps/web/public/replay/demo.json`. The built site serves these responses when
no backend is reachable, so judges can click the whole demo story on a static
deploy while the full app keeps working locally.

The Halloween project records TWO incidents on one rig: the ghost LED's
inverted drive (arc A) and the pumpkin candle's dead flicker (arc B), including
a real Devin repair session for arc B when DEVIN_API_KEY is configured.

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
# iid -> request-body hashes of verify_fix executes that resolve it (captured). The
# open-state view is served under `GET /investigations/{iid}`; the resolved view
# under `GET /investigations/{iid}#resolved`, gated on these hashes.
resolves: dict[str, list[str]] = {}


def _norm(v):
    """Canonicalize numbers so Python 90.0 hashes identically to JS 90 — both sides
    must agree on the body hash or a recorded response is never matched."""
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def key_for(method: str, path: str, body: object | None) -> str:
    if body is None:
        return f"{method} {path}"
    canon = json.dumps(_norm(body), sort_keys=True, separators=(",", ":"))
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


def _end_ordered(choices: list, a: dict, end_status: str | None) -> list:
    """Record every choice a judge could pick, but call the story's ending choice
    LAST — the final manual-result call decides the persisted hypothesis state
    (e.g. 'Connected' leaves a power/signal hypothesis weakened, which is what
    unlocks the software-repair offer)."""
    sor = (a.get("arguments") or {}).get("status_on_result", {})
    end = [c for c in choices if sor.get(c) == end_status]
    return [c for c in choices if c not in end] + end


def capture_incident(iid: str, run_sources: list, end_status: str | None = None,
                     repair: bool = False) -> None:
    """Record the click-path through one incident: open view, permissions, tool /
    inspect / manual-check actions, repair surfaces, then run actions (repeat
    first, verify last — a passing verify resolves the incident)."""
    view = call("GET", f"/investigations/{enc(iid)}")
    collect_evidence(view)
    actions = view.get("actions", [])

    # Permissions: record grant + revoke responses for every category the actions need.
    cats = {a.get("permission_category") for a in actions} - {None}
    for cat in sorted(cats):
        for granted in (True, False):
            call("POST", f"/investigations/{enc(iid)}/permissions",
                 {"category": cat, "granted": granted})

    ordered = ([a for a in actions if a.get("kind") in ("inspect_source", "run_readonly_tool",
                                                       "expand_scope", "request_manual_check")]
               + [a for a in actions if a.get("kind") == "repeat_test"]
               + [a for a in actions if a.get("kind") == "verify_fix"])

    for a in ordered:
        aid, kind = a["id"], a.get("kind")
        try:
            if kind in ("inspect_source", "run_readonly_tool", "expand_scope"):
                res = call("POST", f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute",
                           {"approve_once": True})
                # The app may also send approve_once=false after a standing grant.
                routes[key_for("POST", f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute",
                               {"approve_once": False})] = res
                collect_evidence(res)
            elif kind == "request_manual_check":
                for choice in _end_ordered(a.get("result_choices", []), a, end_status):
                    call("POST", f"/investigations/{enc(iid)}/manual-results",
                         {"action_id": aid, "result": choice})
        except urllib.error.HTTPError as e:
            print(f"  {kind} ({aid}) -> HTTP {e.code} — skipped")

    # Repair surfaces sit between the bench checks and verification — the order the
    # story takes (checks clear the physical path → Devin prepares a fix → verify).
    call("GET", f"/investigations/{enc(iid)}/repairs")
    pre = call("GET", f"/investigations/{enc(iid)}/repairs/preflight")
    if repair and pre.get("ready"):
        job = call("POST", f"/investigations/{enc(iid)}/repairs", {"acknowledge_uncommitted": True})
        print(f"  devin repair {job['id']} -> {job.get('session_url')}")
        for _ in range(30):  # ~4 min; a still-running job is still honest to replay
            job = call("POST", f"/repairs/{enc(job['id'])}/refresh")
            if job.get("state") in ("ready_for_review", "failed"):
                break
            time.sleep(8)
        print(f"  repair ended at state={job.get('state')}")
        call("GET", f"/investigations/{enc(iid)}/repairs")
        call("GET", f"/investigations/{enc(iid)}/repairs/preflight")
    elif repair:
        print(f"  repair preflight not ready — recorded as-is: {pre.get('issues')}")

    for a in ordered:
        aid, kind = a["id"], a.get("kind")
        if kind not in ("repeat_test", "verify_fix"):
            continue
        for src in run_sources:
            body = {"source": src, "approve_once": False}
            try:
                res = call("POST", f"/investigations/{enc(iid)}/actions/{enc(aid)}/execute", body)
            except urllib.error.HTTPError as e:
                print(f"  {kind} ({aid}) -> HTTP {e.code} — skipped")
                continue
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

    # Final incident state. The open view (captured at the top) stays under the
    # plain key; the resolved view rides under #resolved.
    final_view = call("GET", f"/investigations/{enc(iid)}", record=False)
    collect_evidence(final_view)
    if iid in resolves:
        routes[f"GET /investigations/{enc(iid)}#resolved"] = final_view
    else:
        routes[f"GET /investigations/{enc(iid)}"] = final_view


def import_project(fx: dict):
    proj = call("POST", "/projects/import",
                {"repo_path": fx["repo_path"], "manifest_path": fx["manifest_path"]})
    pid = proj["id"]
    print(f"  imported {proj['name']} -> {pid}")
    call("GET", f"/projects/{enc(pid)}")
    graph = call("GET", f"/projects/{enc(pid)}/graph")
    subs = call("GET", f"/projects/{enc(pid)}/subsystems")
    # The frontend loads a scoped graph for its preferred subsystem (first component's
    # subsystem, else the first subsystem) and for any subsystem chip the judge clicks.
    preferred = next((n["subsystem_id"] for n in graph.get("nodes", [])
                      if n.get("kind") == "component" and n.get("subsystem_id")), None)
    if preferred is None and subs:
        preferred = subs[0]["id"]
    for sid in {s["id"] for s in subs} | ({preferred} if preferred else set()):
        call("GET", f"/projects/{enc(pid)}/graph?scope_node_id={enc(sid)}")
    return proj


def capture_fixture(fx: dict, scenario: str) -> dict:
    proj = import_project(fx)
    pid = proj["id"]

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
    call("GET", f"/projects/{enc(pid)}/tests")
    if not incidents:
        print(f"  no incident for {pid} (run may have passed) — done")
        return proj
    # Judges can verify with whatever source the picker holds — record the fault
    # replay, the 'good' replay, and the default simulated condition.
    capture_incident(incidents[-1]["id"],
                     [source, {"kind": "replay", "scenario": "good"},
                      {"kind": "sim", "scenario": "connected"}])
    return proj


def capture_halloween(fx: dict) -> dict:
    """Two-arc story on one two-LED rig (D-046): the ghost LED is wired active-low
    but driven active-high (arc A — INVERTED_LOGIC), and the pumpkin candle never
    lights on FLICKER (arc B — power/signal cleared by bench checks → Devin)."""
    proj = import_project(fx)
    pid = proj["id"]

    # --- Arc A: ghost LED, GHOST ON — command ACKed, LED responds, ends wrong ---
    ghost = call("POST", f"/projects/{enc(pid)}/expectations/propose",
                 {"component_id": "component:ghost_led"})
    call("POST", f"/projects/{enc(pid)}/expectations/{enc(ghost['id'])}/confirm",
         {"target": ghost["target"], "tolerance": ghost["tolerance"],
          "deadline_ms": ghost["deadline_ms"], "trigger_value": ghost["trigger"]["value"]})
    run = call("POST", f"/projects/{enc(pid)}/tests",
               {"expectation_id": ghost["id"],
                "source": {"kind": "replay", "scenario": "halloween_inverted"}})
    detail = wait_run(run["id"])
    collect_evidence(detail)
    call("GET", f"/tests/{enc(run['id'])}/flow")

    # Recorded now, while only the ghost incident exists — the workspace then opens
    # on arc A; arc B is reached via its run in History.
    incidents = call("GET", f"/projects/{enc(pid)}/incidents")
    iid1 = incidents[-1]["id"]
    capture_incident(iid1,
                     [{"kind": "replay", "scenario": "halloween_inverted"},
                      {"kind": "replay", "scenario": "halloween_ghost_good"},
                      {"kind": "sim", "scenario": "connected"}],
                     end_status="supported")

    # --- Arc B: pumpkin candle, FLICKER — ACKed but dark. Bench checks clear the
    # physical path, then Devin prepares a firmware fix on an isolated branch ---
    pumpkin = call("POST", f"/projects/{enc(pid)}/expectations/propose",
                   {"component_id": "component:pumpkin_led"})
    # The proposal prefers the ON literal; the engineer retypes the flicker command
    # in the confirm card — the backend re-resolves the ACK pattern. Record the
    # unedited confirm too, in case a judge confirms the proposal as-suggested.
    base = {"target": pumpkin["target"], "tolerance": pumpkin["tolerance"],
            "deadline_ms": pumpkin["deadline_ms"]}
    call("POST", f"/projects/{enc(pid)}/expectations/{enc(pumpkin['id'])}/confirm",
         {**base, "trigger_value": pumpkin["trigger"]["value"]})
    call("POST", f"/projects/{enc(pid)}/expectations/{enc(pumpkin['id'])}/confirm",
         {**base, "trigger_value": "FLICKER"})
    run = call("POST", f"/projects/{enc(pid)}/tests",
               {"expectation_id": pumpkin["id"],
                "source": {"kind": "replay", "scenario": "halloween_flicker_dark"}})
    detail = wait_run(run["id"])
    collect_evidence(detail)
    call("GET", f"/tests/{enc(run['id'])}/flow")

    incidents = call("GET", f"/projects/{enc(pid)}/incidents", record=False)
    iid2 = incidents[-1]["id"]
    capture_incident(iid2,
                     [{"kind": "replay", "scenario": "halloween_flicker_dark"},
                      {"kind": "replay", "scenario": "halloween_flicker_good"},
                      {"kind": "sim", "scenario": "connected"}],
                     end_status="weakened", repair=True)

    call("GET", f"/projects/{enc(pid)}/expectations")
    call("GET", f"/projects/{enc(pid)}/tests")
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
    halloween = next(fx for fx in fixtures if fx["repo_path"].endswith("esp32_halloween"))
    led_fault = next(fx for fx in fixtures if fx["repo_path"].endswith("esp32_led_demo_fault_a"))
    led_good = next(fx for fx in fixtures if fx["label"].startswith("LED demo — correct firmware"))

    projects = [capture_halloween(halloween),
                capture_fixture(led_fault, "connected"),
                capture_fixture(led_good, "signal_disconnected")]

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
