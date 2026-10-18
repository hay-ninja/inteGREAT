// Browser integration test with Chromium's synthetic camera, never hardware evidence.
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const python = path.join(root, "apps/api/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const fixture = `
import uvicorn
from integreat.observations.camera_adapter import CameraManager
from integreat.observations.browser_camera import BrowserCamera
from integreat.api.phone import create_phone_app
manager = CameraManager()
manager.source = BrowserCamera()
manager.source.token = 'synthetic-browser-test'
app = create_phone_app(manager)
@app.get('/test-status')
def status():
    return {'connected': manager.connected, 'paired': manager.source.authorized('synthetic-browser-test')}
@app.post('/test-pair')
def pair():
    manager.release()
    manager.source = BrowserCamera()
    manager.source.token = 'synthetic-browser-test'
uvicorn.run(app, host='127.0.0.1', port=18765, log_level='error')
`;
const server = spawn(python, ["-c", fixture], { cwd: path.join(root, "apps/api"), windowsHide: true, stdio: "ignore" });
let browser;
try {
  let ready = false;
  for (let i = 0; i < 50; i++) {
    try { ready = (await fetch("http://127.0.0.1:18765/phone")).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert(ready, "Fixture server failed to start");
  browser = await chromium.launch({ channel: process.env.PHONE_TEST_BROWSER || "chrome", headless: true, args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("http://127.0.0.1:18765/phone#synthetic-browser-test");
  assert(!page.url().includes("#"), "Token should be removed from browser history");
  await page.getByRole("button", { name: "Start camera", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "Streaming to your laptop" }).waitFor();
  assert((await (await fetch("http://127.0.0.1:18765/test-status")).json()).connected);
  await page.getByRole("button", { name: "Stop camera", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "Camera stopped" }).waitFor();
  assert.deepEqual(await (await fetch("http://127.0.0.1:18765/test-status")).json(), { connected: false, paired: false });
  assert.equal(await page.locator("video").evaluate(v => v.srcObject), null);
  await page.goto("about:blank");
  await fetch("http://127.0.0.1:18765/test-pair", { method: "POST" });
  await page.goto("http://127.0.0.1:18765/phone#synthetic-browser-test");
  await page.getByRole("button", { name: "Start camera", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "Streaming to your laptop" }).waitFor();
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.getByRole("status").filter({ hasText: "Safari was hidden" }).waitFor();
  assert.equal(await page.locator("video").evaluate(v => v.srcObject), null);
  const denied = await browser.newPage();
  await denied.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException("Denied", "NotAllowedError"); };
  });
  await denied.goto("http://127.0.0.1:18765/phone#synthetic-browser-test");
  await denied.getByRole("button", { name: "Start camera", exact: true }).click();
  await denied.getByRole("status").filter({ hasText: "Camera permission denied" }).waitFor();
  assert.deepEqual(errors, []);
  console.log("Synthetic browser camera: capture, JPEG upload, token removal, stop/revocation, hidden-page shutdown, permission denial passed.");
} finally {
  await browser?.close();
  server.kill();
}
