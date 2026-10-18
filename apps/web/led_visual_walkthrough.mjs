// Real UI/API walkthrough with synthetic LED images, never physical hardware evidence.
import { chromium } from "playwright";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { mkdirSync } from "node:fs";
import assert from "node:assert/strict";

const web = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(web, "../..");
const python = path.join(root, "apps/api/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const fixture = `
import time
import uvicorn
from pathlib import Path
from integreat.main import create_app
from integreat.config import Settings
from tests.test_led_visual import Camera
app = create_app(Settings(db_path=':memory:', fixtures_dir=Path('../../fixtures').resolve(), replay_speed=0))
camera = Camera()
app.state.service.devices.camera.source = camera
@app.post('/test-level/{value}')
def level(value: int):
    camera.mode, camera.level = 'reference', value
@app.post('/test-mode/{mode}')
def mode(mode: str):
    camera.mode, camera.started = mode, time.monotonic()
uvicorn.run(app, host='127.0.0.1', port=18766, log_level='error')
`;
const apiBase = "http://127.0.0.1:18766";
const backend = spawn(python, ["-c", fixture], { cwd: path.join(root, "apps/api"), windowsHide: true, stdio: "ignore" });
let vite, browser;
const post = async (url, body) => {
  const res = await fetch(apiBase + url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
  assert(res.ok, await res.clone().text());
  return res.json();
};
try {
  let ready = false;
  for (let i = 0; i < 60; i++) {
    try { ready = (await fetch(apiBase + "/api/v1/health")).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert(ready, "API fixture failed to start");
  vite = await createServer({ configFile: false, root: web, plugins: [react()], server: {
    host: "127.0.0.1", port: 18767, strictPort: true, proxy: { "/api": { target: apiBase, ws: true } } } });
  await vite.listen();
  const project = await post("/api/v1/projects/import", { repo_path: path.join(root, "fixtures/esp32_led_fade"), manifest_path: path.join(root, "fixtures/manifests/esp32_led_fade.yaml") });
  const base = `/api/v1/projects/${project.id}/visual`;
  const ids = [];
  for (const [component_id, pos] of [["component:led_1", .1], ["component:led_2", .6]]) {
    for (const [state, level] of [["off", 0], ["on", 1]]) {
      await post(`/test-level/${level}`);
      ids.push((await post(base + "/references", { component_id, state, region: { x: pos, y: pos, width: .1, height: .1 } })).id);
    }
  }
  await post(base + "/configs", { reference_ids: ids, confirmed: true, duration_ms: 8000 });
  browser = await chromium.launch({ channel: process.env.PHONE_TEST_BROWSER || "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.addInitScript(id => localStorage.setItem("integreat.lastProject", id), project.id);
  await page.goto("http://127.0.0.1:18767");
  await page.getByRole("heading", { name: "LED visual check", exact: true }).waitFor();
  await page.getByText("Edit calibrated LED regions", { exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll(".led-region-picker rect").length === 2);
  assert.equal(await page.locator(".led-region-picker rect").count(), 2);
  await page.getByRole("button", { name: "Connect or change camera" }).click();
  await page.getByText("No markers are needed.", { exact: false }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Calibrate", exact: true }).count(), 0);
  await page.getByRole("button", { name: "Rig ready — continue", exact: true }).click();
  await page.getByText("Edit calibrated LED regions", { exact: true }).click();
  await post("/test-mode/fault");
  await page.getByRole("button", { name: "Observe LED fades", exact: true }).click();
  await page.getByRole("heading", { name: "FAIL", exact: true }).waitFor({ timeout: 16000 });
  await post("/test-mode/good");
  await page.getByRole("button", { name: "I fixed it — verify with the same check" }).click();
  await page.getByRole("heading", { name: "PASS", exact: true }).waitFor({ timeout: 16000 });
  await page.getByText("Visual failure resolved by this passing verification.", { exact: true }).waitFor();
  await page.reload();
  await page.getByRole("heading", { name: "PASS", exact: true }).waitFor();
  const shotDir = path.join(root, ".phone-camera");
  mkdirSync(shotDir, { recursive: true });
  await page.screenshot({ path: path.join(shotDir, "led-panel.png"), fullPage: true });
  assert.deepEqual(errors, []);
  console.log("Synthetic LED UI/API: saved calibration, marker-free setup, failed observation, passing verification, graph state, reload passed.");
} finally {
  await browser?.close();
  await vite?.close();
  backend.kill();
}
