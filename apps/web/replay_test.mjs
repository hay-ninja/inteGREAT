import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
const log = (...a) => console.log("•", ...a);
const shots = "C:/Users/hayre/AppData/Local/Temp/integreat-shots";

/** Pick a scenario in a SourcePicker inside `scope`: segment → Selector → option. */
async function pickScenario(scope, segment, optionName) {
  await scope.getByText(segment, { exact: true }).click();
  await page.waitForTimeout(300);
  const combo = scope.locator("button, [role=combobox]").filter({ hasText: /wired as declared|condition|Recording|replay|sim|halloween|good|disconnected|connected|marker/i }).last();
  await combo.click().catch(() => undefined);
  await page.waitForTimeout(300);
  await page.getByRole("option", { name: new RegExp(optionName, "i") }).or(page.getByText(optionName, { exact: false })).last().click();
  await page.waitForTimeout(200);
}

await page.goto("http://localhost:8080", { waitUntil: "networkidle" });
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle" });
await page.waitForTimeout(1200);
const banner = await page.getByText("Hosted demo").isVisible().catch(() => false);
log("landing + hosted-demo banner:", banner);
await page.screenshot({ path: `${shots}/r00-landing.png` });

await page.getByRole("button", { name: "Open the workspace" }).first().click();
await page.waitForTimeout(800);
await page.screenshot({ path: `${shots}/r01-import.png` });

// ---- Segment 1: Halloween rig — arc A, the inverted ghost LED ----
// First demo card = esp32_halloween; the workspace opens on the ghost incident.
await page.getByText("Simulated · ~5 minutes").first().click();
await page.locator("dialog").getByText("Load demo").click();
await page.waitForSelector(".graph-canvas", { timeout: 15000 });
log("graph rendered from replay");
await page.screenshot({ path: `${shots}/r02-graph.png` });

for (const layer of ["Hardware", "Software", "All"]) {
  await page.getByRole("button", { name: layer, exact: true }).first().click();
  await page.waitForTimeout(400);
}
log("layer switching ok");

// Ghost incident is open on load; the recorded repeat runs under any source pick.
const runBtn = page.locator("button").filter({ hasText: /Run the test again|Run test|Run again/ }).first();
if (await runBtn.isVisible().catch(() => false)) {
  await runBtn.click();
  await page.waitForSelector("text=In short", { timeout: 15000 }).catch(() => log("NO run result"));
}
await page.locator(".chapter").nth(1).click(); // Debug
await page.waitForTimeout(600);
log("inverted hypothesis:", await page.getByText("Inverted drive logic").first().isVisible().catch(() => false));
await page.screenshot({ path: `${shots}/r03-inverted.png` });

// Verify with the recorded good replay.
await page.getByText("Potential causes").first().click().catch(() => undefined);
await page.waitForTimeout(400);
await page.locator("button").filter({ hasText: /verify it|verify this/i }).first().click();
await page.waitForTimeout(500);
await pickScenario(page.locator("dialog"), "Replay", "halloween ghost good");
await page.locator("dialog").getByRole("button", { name: "Run verification" }).click();
await page.waitForSelector("text=Was:", { timeout: 15000 }).catch(() => log("NO resolved state"));
log("ghost resolved:", await page.getByText("Verified").first().isVisible().catch(() => false));
await page.screenshot({ path: `${shots}/r04-verified.png` });

// ---- Arc B: the pumpkin flicker incident, reached via History ----
await page.locator(".chapter").nth(3).click(); // History
await page.waitForTimeout(900);
const flickerRow = page.getByText("FLICKER", { exact: true }).first();
if (await flickerRow.isVisible().catch(() => false)) {
  await flickerRow.click();
  await page.waitForTimeout(900);
  await page.locator(".chapter").nth(1).click();
  await page.waitForTimeout(600);
  log("pumpkin incident:", await page.getByText(/signal lead disconnected|Power or ground/).first().isVisible().catch(() => false));
  await page.screenshot({ path: `${shots}/r05-pumpkin.png` });
} else log("NO flicker run in history");

// ---- Segment 2: LED fault A — GPIO mismatch + inspect ----
await page.locator(".brand").click();
await page.waitForTimeout(900);
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) await ws.first().click();
await page.waitForTimeout(800);
await page.getByText("Simulated · ~5 minutes").nth(1).click();
await page.locator("dialog").getByText("Load demo").click();
await page.waitForSelector(".graph-canvas", { timeout: 15000 }).catch(() => page.screenshot({ path: `${shots}/r06b-stuck.png` }));
log("fault A canvas:", await page.locator(".graph-canvas").isVisible().catch(() => false));
const runBtn2 = page.locator("button").filter({ hasText: /Run the test again|Run test|Run again/ }).first();
if (await runBtn2.isVisible().catch(() => false)) {
  await runBtn2.click();
  await page.waitForSelector("text=In short", { timeout: 15000 }).catch(() => log("no fault-A result"));
}
log("gpio mismatch:", await page.getByText("Incorrect GPIO mapping").isVisible().catch(() => false));
await page.screenshot({ path: `${shots}/r06-faulta.png` });
const inspect = page.locator("button").filter({ hasText: "Inspect GPIO mapping" }).first();
if (await inspect.isVisible().catch(() => false)) {
  await inspect.click();
  await page.waitForTimeout(800);
  const dlg = await page.locator("dialog[open]").count();
  log("inspect result dialog:", dlg > 0);
  if (dlg) await page.keyboard.press("Escape");
}

// ---- Segment 3: LED good firmware — tied signal/power hypotheses + manual check ----
await page.locator(".brand").click();
await page.waitForTimeout(900);
const ws2 = page.getByRole("button", { name: "Open the workspace" });
if (await ws2.first().isVisible().catch(() => false)) await ws2.first().click();
await page.waitForTimeout(800);
await page.getByText("Simulated · ~5 minutes").nth(2).click();
await page.locator("dialog").getByText("Load demo").click();
await page.waitForTimeout(1500);
await page.getByRole("button", { name: "Map", exact: true }).first().click().catch(() => undefined);
await page.waitForSelector(".graph-canvas", { timeout: 15000 }).catch(() => page.screenshot({ path: `${shots}/r08b-stuck.png` }));
log("fault B canvas:", await page.locator(".graph-canvas").isVisible().catch(() => false));
const runBtn3 = page.locator("button").filter({ hasText: /Run the test again|Run test|Run again/ }).first();
if (await runBtn3.isVisible().catch(() => false)) {
  await runBtn3.click();
  await page.waitForSelector("text=In short", { timeout: 15000 }).catch(() => log("no fault-B incident"));
  log("fault B tied hypotheses:", await page.getByText(/signal lead disconnected|Power or ground/).first().isVisible().catch(() => false));
  await page.screenshot({ path: `${shots}/r08-faultb.png` });
  await page.locator(".chapter").nth(1).click();
  await page.waitForTimeout(300);
  await page.getByText("Potential causes").first().click().catch(() => undefined);
  await page.waitForTimeout(300);
  const check = page.locator("button").filter({ hasText: /Check signal|Check servo/i }).first();
  if (await check.isVisible().catch(() => false)) {
    await check.click();
    await page.waitForTimeout(600);
    const choice = page.locator("dialog").getByText("Disconnected", { exact: true }).first();
    if (await choice.isVisible().catch(() => false)) {
      await choice.click();
      await page.waitForTimeout(300);
      await page.getByText("Record check result").click();
      await page.waitForTimeout(1200);
      log("manual check submitted:", await page.getByText("supported").first().isVisible().catch(() => false));
    } else log("manual dialog choice buttons not found");
  }
}

// event flow via rail
await page.getByText("Timeline", { exact: true }).first().click().catch(() => undefined);
await page.waitForTimeout(900);
log("event flow lanes:", await page.locator(".lane-row").count(), "events:", await page.locator(".fev").count());
await page.screenshot({ path: `${shots}/r09-flow.png` });

// 800px overflow check
await page.setViewportSize({ width: 800, height: 600 });
await page.waitForTimeout(600);
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > 800);
log("800px horizontal overflow:", overflow);
await page.screenshot({ path: `${shots}/r10-800.png` });

console.log("\nconsole errors:", errors.length ? errors.slice(0, 8) : "none");
await browser.close();
