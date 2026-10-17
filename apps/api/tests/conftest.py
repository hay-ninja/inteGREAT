from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from integreat.config import Settings
from integreat.main import create_app

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "fixtures"
GOOD_REPO = FIX / "esp32_servo_demo"
FAULT_A_REPO = FIX / "esp32_servo_demo_fault_a"
MANIFEST = FIX / "manifests" / "esp32_servo_demo.yaml"


@pytest.fixture
def client():
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0))
    with TestClient(app) as c:
        yield c


def import_and_confirm(client, repo=FAULT_A_REPO):
    p = client.post("/api/v1/projects/import", json={"repo_path": str(repo), "manifest_path": str(MANIFEST)}).json()
    exp = client.post(f"/api/v1/projects/{p['id']}/expectations/propose").json()
    exp = client.post(f"/api/v1/projects/{p['id']}/expectations/{exp['id']}/confirm", json={}).json()
    return p, exp


def run_test(client, pid, exp_id, scenario):
    run = client.post(f"/api/v1/projects/{pid}/tests",
                      json={"expectation_id": exp_id, "source": {"kind": "replay", "scenario": scenario}})
    assert run.status_code == 200, run.text
    return client.get(f"/api/v1/tests/{run.json()['id']}").json()["run"]
