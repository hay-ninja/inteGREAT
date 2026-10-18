"""End-to-end LED demo coverage: proposal, evaluation, and the three demo faults.

The inverted-logic run (active-low wiring + active-high code) is the discriminating
case: the light *changes* state, so signal/power hypotheses don't apply — only
INVERTED_LOGIC explains a response that ends wrong.
"""

from .conftest import LED_FAULT_A_REPO, LED_MANIFEST, LED_MANIFEST_LOW, LED_REPO, import_and_confirm, run_test
from .test_api_flow import assert_evidence_resolves, investigation

API = "/api/v1"


def test_led_proposal_is_binary_and_resolves_on_level(client):
    p = client.post(f"{API}/projects/import",
                    json={"repo_path": str(LED_REPO), "manifest_path": str(LED_MANIFEST)}).json()
    exp = client.post(f"{API}/projects/{p['id']}/expectations/propose").json()
    assert exp["metric"] == "led_state" and exp["unit"] == "state"
    assert exp["target"] == 1 and exp["tolerance"] == 0
    assert exp["trigger"]["value"] == "LED ON" and exp["ack_pattern"] == "ACK LED ON"
    assert exp["on_level"] == "HIGH"  # resolved: handleCommand → ledOn → digitalWrite HIGH
    assert exp["component_id"] == "component:status_led"


def test_led_good_run_passes(client):
    p, exp = import_and_confirm(client, LED_REPO, LED_MANIFEST)
    run = run_test(client, p["id"], exp["id"], "led_good")
    assert run["result"]["outcome"] == "pass" and run["incident_id"] is None


def test_led_fault_a_flags_gpio_mismatch(client):
    p, exp = import_and_confirm(client, LED_FAULT_A_REPO, LED_MANIFEST)
    run = run_test(client, p["id"], exp["id"], "led_fault_a_wrong_gpio")
    assert run["result"]["outcome"] == "fail"
    view = investigation(client, run["incident_id"])
    assert_evidence_resolves(view)
    top = view["hypotheses"][0]
    assert top["fault_code"] == "GPIO_CONFIG_MISMATCH" and top["rank"] == 1


def test_led_disconnected_offers_signal_and_power(client):
    p, exp = import_and_confirm(client, LED_REPO, LED_MANIFEST)
    run = run_test(client, p["id"], exp["id"], "led_disconnected")
    assert run["result"]["outcome"] == "fail"
    view = investigation(client, run["incident_id"])
    assert_evidence_resolves(view)
    assert {h["fault_code"] for h in view["hypotheses"]} == {"POSSIBLE_POWER_OR_SIGNAL_FAULT"}
    assert "INVERTED_LOGIC" not in {h["fault_code"] for h in view["hypotheses"]}


def test_led_inverted_logic_is_diagnosed(client):
    """Active-low wiring + code driving HIGH for 'on': lit-at-boot LED turns OFF on ON."""
    p, exp = import_and_confirm(client, LED_REPO, LED_MANIFEST_LOW)
    run = run_test(client, p["id"], exp["id"], "led_inverted")
    assert run["result"]["outcome"] == "fail"
    facts = {f["key"]: f["value"] for f in run["result"]["facts"]}
    assert facts["physical_motion"] == "yes" and facts["physical_state"] == "no"
    view = investigation(client, run["incident_id"])
    assert_evidence_resolves(view)
    inv = next(h for h in view["hypotheses"] if h["fault_code"] == "INVERTED_LOGIC")
    assert inv["status"] == "plausible" and inv["rank"] == 1
    # The shadow reproduces the signature under the declared (mismatched) system,
    # and the counterfactual `do(code drives the active level)` is cited.
    assert "Counterfactual" in inv["explanation"]
    assert not any(h["fault_code"] == "POSSIBLE_POWER_OR_SIGNAL_FAULT" for h in view["hypotheses"])


def test_led_marker_lost_is_measurement_unavailable(client):
    p, exp = import_and_confirm(client, LED_REPO, LED_MANIFEST)
    run = run_test(client, p["id"], exp["id"], "led_marker_lost")
    assert run["result"]["outcome"] == "inconclusive"
    view = investigation(client, run["incident_id"])
    assert {h["fault_code"] for h in view["hypotheses"]} == {"CAMERA_MEASUREMENT_UNAVAILABLE"}


def test_led_sim_run_uses_real_pipeline(client):
    """Simulated rig + rendered frames + LedStateEstimator — no fabricated data."""
    p, exp = import_and_confirm(client, LED_REPO, LED_MANIFEST)
    run = run_test(client, p["id"], exp["id"], "connected", kind="sim")
    assert run["state"] == "completed" and run["result"]["outcome"] == "pass"
    assert run["incident_id"] is None and run["synthetic"] is True
