// UI walkthrough: drives the real app in headless Chromium at several viewports.
// Verifies the graph layers, event flow, selection, and repair dialog actually render.
// Run: node scripts/ui_walkthrough.mjs   (requires API on :8000 and web on :5173)
import { chromium } from "playwright";
import { mkdirSync } from "fs";

const SHOTS = "C:/Users/hayre/AppData/Local/Temp/integreat-shots";
mkdirSync(SHOTS, { recursive: true });

const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));

const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: false });
const log = (...a) => console.log("•", ...a);

await page.goto("http://localhost:5173", { waitUntil: "networkidle" });

// ---- import: pick the Fault A demo -------------------------------------------------
// App restores the last project from localStorage; clear it so the import screen shows.
await page.evaluate(() => localStorage.clear());
await page.reload({ waitUntil: "networkidle" });
await shot("00-import");
const onImport = await page.getByText("Explore a demo").isVisible().catch(() => false);
if (onImport) {
  await page.getByText("Wrong pin in the code").click();
  await shot("00b-demo-modal");
  await page.locator("dialog").getByText("Load demo").click().catch(async () => {
    await page.getByRole("button", { name: "Load demo" }).click();
  });
  await page.waitForSelector(".graph-canvas", { timeout: 15000 });
}
await page.waitForSelector(".graph-canvas", { timeout: 20000 });
log("graph canvas rendered");
await shot("01-combined-1280");

// ---- layer selector ---------------------------------------------------------------
const seg = (label) => page.getByRole("radio", { name: label }).or(page.getByText(label, { exact: true }));
await page.getByText("Hardware", { exact: true }).first().click();
await page.waitForTimeout(700);
const hwNodes = await page.locator(".gn.hw").count();
const codeNodesHW = await page.locator(".gn:not(.hw)").count();
log(`hardware layer: ${hwNodes} hw nodes, ${codeNodesHW} code nodes`);
await shot("02-hardware-layer");

await page.getByText("Software", { exact: true }).first().click();
await page.waitForTimeout(700);
const swNodes = await page.locator(".gn:not(.hw)").count();
const boundary = await page.locator(".gn.boundary").count();
log(`software layer: ${swNodes} code nodes, ${boundary} boundary refs`);
await shot("03-software-layer");

await page.getByText("Combined", { exact: true }).first().click();
await page.waitForTimeout(700);
const regions = await page.locator(".graph-region").count();
const edgeLabels = await page.locator(".react-flow__edge-text").allTextContents();
log(`combined: ${regions} regions; edge labels: ${edgeLabels.filter(Boolean).slice(0, 8).join(" | ")}`);
await shot("04-combined-regions");

// ---- run a test through the real flow ----------------------------------------------
const suggest = page.locator("button").filter({ hasText: "Suggest a test from the code" }).first();
if (await suggest.isVisible().catch(() => false)) {
  await suggest.click();
  const confirm = page.locator("button").filter({ hasText: "Confirm test" }).first();
  await confirm.waitFor({ state: "visible", timeout: 10000 });
  await confirm.click();
  await page.waitForTimeout(800);
}
const runBtn = page.locator("button").filter({ hasText: /Run test|Run again/ }).first();
log("run button visible:", await runBtn.isVisible().catch(() => false));
if (await runBtn.isVisible().catch(() => false)) {
  await runBtn.click();
  await page.waitForSelector("text=Collecting measurements, text=Leading hypothesis, text=Possible causes, text=passed", { timeout: 20000 }).catch(() => log("run did not reach a result state in 20s"));
  await page.waitForTimeout(1500);
}
await shot("05-after-run");

const closeAnyDialog = async () => {
  const x = page.locator("dialog[open]").first();
  if (await x.isVisible().catch(() => false)) {
    const btn = x.locator("button").first();
    if (await btn.isVisible().catch(() => false)) { await btn.click(); await page.waitForTimeout(400); }
  }
};

// ---- event flow view ---------------------------------------------------------------
await page.getByText("Event flow", { exact: true }).first().click();
await page.waitForTimeout(1200);
const fevCount = await page.locator(".fev").count();
const lanes = await page.locator(".lane-row").count();
log(`event flow: ${lanes} lanes, ${fevCount} events`);
await shot("06-event-flow");

// step through events
const nextBtn = page.getByRole("button", { name: "Next event" });
if (await nextBtn.isVisible().catch(() => false)) {
  await nextBtn.click(); await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Next event" }).click();
}
await shot("07-event-step");

// drawer: Activity (merged timeline + tool audit) and Devices (summary → rig setup dialog)
await page.getByRole("tab", { name: "Activity" }).or(page.getByText("Activity", { exact: true })).first().click();
await page.waitForTimeout(600);
const auditVisible = await page.evaluate(() => document.body.innerText.toUpperCase().includes("TOOL AUDIT"));
log(`activity tab renders merged audit: ${auditVisible}`);
await shot("07b-activity");
await page.getByText("Devices", { exact: true }).first().click();
await page.waitForTimeout(500);
const openSetup = page.locator("button").filter({ hasText: /Open rig setup|Set up live rig/ }).first();
if (await openSetup.isVisible().catch(() => false)) {
  await openSetup.click();
  await page.waitForTimeout(700);
  const rigDlg = await page.locator("dialog[open]").count();
  log(`devices tab routes to rig setup dialog: ${rigDlg > 0}`);
  await shot("07c-devices-summary");
  await closeAnyDialog();
} else {
  log("devices summary has no rig-setup route!");
}

// click a graph-related element from the selected event card
const graphLink = page.getByRole("button", { name: /servo|gpio|MOVE|module|fn/i }).last();
if (await graphLink.isVisible().catch(() => false)) {
  await graphLink.click();
  await page.waitForTimeout(800);
  log("cross-link returned to dependencies view");
  await shot("08-cross-link");
}

await closeAnyDialog();

// ---- repair dialog -----------------------------------------------------------------
const fixBtn = page.locator("button").filter({ hasText: "Prepare software fix" }).first();
if (await fixBtn.isVisible().catch(() => false)) {
  await fixBtn.click();
  await page.waitForTimeout(1500);
  const dlg = await page.getByText(/Devin|repair/i).count();
  log(`repair dialog visible, matches: ${dlg}`);
  await shot("09-repair-dialog");
} else {
  log("repair button not visible — Devin action unreachable!");
}
await closeAnyDialog();

// ---- narrow viewport ---------------------------------------------------------------
await page.setViewportSize({ width: 1024, height: 768 });
await page.waitForTimeout(900);
await shot("10-1024x768");
await page.setViewportSize({ width: 800, height: 600 });
await page.waitForTimeout(900);
const overflowX = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
log(`800px viewport: horizontal overflow = ${overflowX}`);
await shot("11-800x600");

console.log("\nconsole errors:", errors.length ? errors.slice(0, 8) : "none");
await browser.close();
console.log("screenshots in", SHOTS);
