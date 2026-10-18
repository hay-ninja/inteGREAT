// Focused check: SourcePicker -> Live rig -> persistent top-bar badge.
import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const sleep = (ms) => page.waitForTimeout(ms);
const shot = (n) => page.screenshot({ path: `../tmp_shots/${n}.png` });
page.on("pageerror", (e) => console.log("PAGEERROR", e));

await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) { await ws.first().click(); await sleep(600); }

// Open the first project card (skip the ⋯ menu overlay by clicking card body text)
await page.locator(".card-menu").first().waitFor({ timeout: 8000 });
await page.locator(".card-menu").first().locator("xpath=..").locator("xpath=.//*[not(self::div[@class='card-menu'])]").first();
await page.locator(".card-menu").first().locator("..").click({ position: { x: 60, y: 60 } });
await sleep(1000);
const openBtn = page.getByRole("button", { name: "Open project" });
if (await openBtn.isVisible().catch(() => false)) { await openBtn.click(); await sleep(2000); }
console.log("opened project; topbar texts:",
  await page.locator("text=Simulated").count(), "sim |", await page.locator("text=Replay").count(), "replay");

// Navigate the chapter rail to Run (02) — click the "Run" chapter chip
const runChip = page.getByText(/^Run$/).or(page.getByText("02 Run")).first();
// If at Verify state, click "Start a new test" then propose+confirm
if (await page.getByRole("button", { name: "Start a new test" }).isVisible().catch(() => false)) {
  await page.getByRole("button", { name: "Start a new test" }).click(); await sleep(800);
}
const suggest = page.getByRole("button", { name: "Suggest a test from the code" });
if (await suggest.isVisible().catch(() => false)) {
  await suggest.click(); await sleep(2000);
  const confirm = page.getByRole("button", { name: /Confirm|Use this|Confirm this test/ }).first();
  if (await confirm.isVisible().catch(() => false)) { await confirm.click(); await sleep(1000); }
} else if (await runChip.isVisible().catch(() => false)) {
  await runChip.click(); await sleep(800);
}
await shot("l01-run");

// SourcePicker in the Run chapter — three segments: Simulated / Replay / Live rig
const picker = page.locator("button").filter({ hasText: "Live rig" }).first();
if (await picker.isVisible().catch(() => false)) { await picker.click(); await sleep(600); }
await shot("l02-live");
// Count occurrences: 1 = only the badge (picker is a segmented control, "Live rig" is its option too)
console.log("Live rig count:", await page.getByText("Live rig").count());
console.log("badge visible:", await page.locator("header").getByText("Live rig").or(page.locator(".topbar-divider").locator("..").getByText("Live rig")).isVisible().catch(() => false));
console.log("setup btn:", await page.getByRole("button", { name: "Set up the live rig" }).first().isVisible().catch(() => false));
await browser.close();
