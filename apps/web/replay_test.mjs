import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
const log = (...a) => console.log("•", ...a);
const shots = "C:/Users/hayre/AppData/Local/Temp/integreat-shots";

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
await page.getByText("Wrong pin in the code").click();
await page.locator("dialog").getByText("Load demo").click();
await page.waitForSelector(".graph-canvas", { timeout: 15000 });
log("graph rendered from replay");
await page.screenshot({ path: `${shots}/r02-graph.png` });

// layer switching via the rail
for (const layer of ["Hardware", "Software", "All"]) {
  await page.getByRole("button", { name: layer, exact: true }).first().click();
  await page.waitForTimeout(400);
}
log("layer switching ok");

// suggest + confirm the test (skipped if the project already has one confirmed)
const suggest = page.locator("button").filter({ hasText: "Suggest a test" }).first();
if (await suggest.isVisible().catch(() => false)) {
  await suggest.click();
  await page.locator("button").filter({ hasText: "Confirm test" }).first().waitFor({ timeout: 8000 });
  await page.locator("button").filter({ hasText: "Confirm test" }).first().click();
  await page.waitForTimeout(600);
}
// run the test — replay must synthesize the completed lifecycle
const runBtn = page.locator("button").filter({ hasText: /Run test|Run again/ }).first();
await runBtn.click();
await page.waitForSelector("text=In short", { timeout: 15000 }).catch(() => log("NO incident result"));
log("incident open:", await page.getByText("Incorrect GPIO mapping").isVisible().catch(() => false));
await page.screenshot({ path: `${shots}/r03-incident.png` });

// inspect action
const inspect = page.locator("button").filter({ hasText: "Inspect GPIO mapping" }).first();
if (await inspect.isVisible().catch(() => false)) {
  await inspect.click();
  await page.waitForTimeout(800);
  const dlg = await page.locator("dialog[open]").count();
  log("inspect result dialog:", dlg > 0);
  await page.screenshot({ path: `${shots}/r04-inspect.png` });
  if (dlg) await page.keyboard.press("Escape");
}

// verify the repair — replay:good resolves the incident
await page.locator("button").filter({ hasText: /verify it|verify this/i }).first().click();
await page.waitForTimeout(500);
await page.locator("dialog").getByText("Replay", { exact: true }).click();
await page.waitForTimeout(300);
const scenario = page.locator("dialog").locator("button, [role=combobox]").filter({ hasText: /wrong gpio|disconnected|good|marker|no ack/i }).first();
if (await scenario.isVisible().catch(() => false)) {
  await scenario.click();
  await page.getByRole("option", { name: "good" }).or(page.getByText("good", { exact: true })).last().click();
}
await page.locator("dialog").getByRole("button", { name: "Run verification" }).click();
await page.waitForSelector("text=Was:", { timeout: 15000 }).catch(() => log("NO resolved state"));
log("resolved view:", await page.getByText("Verified").first().isVisible().catch(() => false));
await page.screenshot({ path: `${shots}/r05-resolved.png` });

// event flow via rail
await page.getByText("Timeline", { exact: true }).first().click();
await page.waitForTimeout(900);
log("event flow lanes:", await page.locator(".lane-row").count(), "events:", await page.locator(".fev").count());
await page.screenshot({ path: `${shots}/r06-flow.png` });

// --- second demo: tied hypotheses + manual check (fault B) ---
await page.locator(".brand").click();
await page.waitForTimeout(900);
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) await ws.first().click();
await page.waitForTimeout(800);
await page.getByText("Disconnected servo signal", { exact: false }).first().click();
await page.locator("dialog").getByText("Load demo").click();
await page.waitForTimeout(1500);
// view mode persists — return to the map
await page.getByRole("button", { name: "Map", exact: true }).first().click().catch(() => undefined);
await page.waitForSelector(".graph-canvas", { timeout: 15000 }).catch(() => page.screenshot({ path: `${shots}/r08b-stuck.png` }));
log("fault B canvas:", await page.locator(".graph-canvas").isVisible().catch(() => false));
// pick the disconnected-signal simulated condition, then run
const runBtn2 = page.locator("button").filter({ hasText: /Run test|Run again/ }).first();
if (await runBtn2.isVisible().catch(() => false)) {
  await runBtn2.click();
  await page.waitForSelector("text=In short", { timeout: 15000 }).catch(() => log("no fault-B incident"));
  log("fault B tied hypotheses:", await page.getByText("Signal or power connection").first().isVisible().catch(() => false));
  await page.screenshot({ path: `${shots}/r08-faultb.png` });
  // submit a manual check result — a Selector dropdown, then "Record check result"
  const check = page.locator("button").filter({ hasText: /Check signal|Check servo/i }).first();
  if (await check.isVisible().catch(() => false)) {
    await check.click();
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${shots}/r08c-dialog.png` });
    const pick = page.locator("dialog").getByText("Choose the result").first();
    if (await pick.isVisible().catch(() => false)) {
      await pick.click();
      await page.waitForTimeout(400);
      await page.getByRole("option", { name: /disconnected/i }).or(page.locator("dialog").getByText("Disconnected", { exact: true })).first().click();
      await page.waitForTimeout(400);
      await page.getByText("Record check result").click();
      await page.waitForTimeout(1200);
      await page.screenshot({ path: `${shots}/r09-manual.png` });
      log("manual check submitted:", await page.getByText("Disconnected").first().isVisible().catch(() => false));
    } else log("manual dialog picker not found");
  }
}

// 800px overflow check
await page.setViewportSize({ width: 800, height: 600 });
await page.waitForTimeout(600);
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > 800);
log("800px horizontal overflow:", overflow);
await page.screenshot({ path: `${shots}/r07-800.png` });

console.log("\nconsole errors:", errors.length ? errors.slice(0, 8) : "none");
await browser.close();
