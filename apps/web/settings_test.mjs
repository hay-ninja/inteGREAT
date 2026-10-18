// Headless check: project edit/delete, live-mode separation.
// Run: node settings_test.mjs  (needs Vite :5173 + API :8000)
import { chromium } from "playwright";

const shots = "C:/Users/hayre/dev/projects/side/inteGREAT/tmp_shots";
const errors = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));
const sleep = (ms) => page.waitForTimeout(ms);

await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
if (await page.getByRole("button", { name: "Open the workspace" }).first().isVisible().catch(() => false)) {
  await page.getByRole("button", { name: "Open the workspace" }).first().click();
  await sleep(600);
}

// --- 1. card menu -> Edit details
const card = page.locator(".card-menu").first();
await card.waitFor({ timeout: 8000 });
await page.screenshot({ path: `${shots}/s01-hub.png` });
await card.click();
await sleep(400);
await page.getByText("Edit details…").first().click();
await sleep(600);
await page.screenshot({ path: `${shots}/s02-settings.png` });
const settingsVisible = await page.getByText("Project settings").first().isVisible();
console.log("settings dialog:", settingsVisible);
console.log("has name field:", await page.getByLabel("Name").isVisible());
console.log("has context field:", await page.getByText("Context for debugging").isVisible());
console.log("has file fields:", await page.getByText("Code folder (Software)", { exact: true }).isVisible());
console.log("has danger zone:", await page.getByText("Danger zone").first().isVisible());

// --- 2. rename + context -> save -> PATCH
const patchP = page.waitForResponse((r) => r.request().method() === "PATCH" && r.url().includes("/projects/"));
await page.getByLabel("Name").fill("Renamed via test");
await page.getByLabel("Context for debugging").fill("Arm stalls above 60 degrees.");
await page.getByRole("button", { name: "Save", exact: true }).click();
const patchRes = await patchP;
console.log("PATCH status:", patchRes.status());
await sleep(500);

// --- 3. delete flow (cancel then real delete on a disposable project)
await page.locator(".card-menu").first().click();
await sleep(400);
await page.getByText("Delete…").first().click();
await sleep(500);
await page.screenshot({ path: `${shots}/s03-delete-confirm.png` });
console.log("delete confirm:", await page.getByText("can't be undone").isVisible());
await page.getByRole("button", { name: "Delete project" }).click();
await sleep(800);
console.log("card count after delete:", await page.locator(".card-menu").count());

// --- 4. open a project -> mode chip + settings + live separation
await page.locator(".card-menu").first().locator("..").locator("[class*='card'], [data-slot]").first().click().catch(async () => {
  // ClickableCard may not match that selector — click the card's text instead
  await page.locator(".card-menu").first().locator("xpath=..").click();
});
await sleep(1500);
// if the pending modal appeared, confirm it
const openBtn = page.getByRole("button", { name: "Open project" });
if (await openBtn.isVisible().catch(() => false)) { await openBtn.click(); await sleep(2000); }
await page.screenshot({ path: `${shots}/s04-workspace.png` });
console.log("mode chip:", await page.getByText("Simulated").first().isVisible().catch(() => false));

// More menu -> Project settings
await page.getByRole("button", { name: "More" }).click();
await sleep(400);
await page.getByText("Project settings…").first().click();
await sleep(600);
console.log("workspace settings dialog:", await page.getByText("Project settings").first().isVisible());
console.log("subsystems section:", await page.getByText("Subsystems").first().isVisible());
await page.screenshot({ path: `${shots}/s05-ws-settings.png` });
await page.getByRole("button", { name: "Cancel" }).click();
await sleep(300);

// --- 5. open the verify dialog (mounts SourcePicker) and switch source to Live
const causes = page.getByText("Potential causes").first();
if (await causes.isVisible().catch(() => false)) { await causes.click(); await sleep(400); }
const verifyBtn = page.getByRole("button", { name: /Verify|verify/ }).first();
if (await verifyBtn.isVisible().catch(() => false)) { await verifyBtn.click(); await sleep(600); }
const srcPick = page.locator("[role='dialog'] button, dialog button").filter({ hasText: /Simulated|Replay|Live/ }).first();
if (await srcPick.isVisible().catch(() => false)) {
  await srcPick.click();
  await sleep(500);
  const liveOpt = page.getByText(/^Live/).last();
  if (await liveOpt.isVisible().catch(() => false)) { await liveOpt.click(); await sleep(600); }
}
// Close the dialog — only the persistent top-bar badge should carry "Live environment" now.
await page.getByRole("button", { name: "Cancel" }).first().click().catch(() => page.keyboard.press("Escape"));
await sleep(500);
await page.screenshot({ path: `${shots}/s07-live.png` });
console.log("live chip:", await page.getByText("Live environment").first().isVisible().catch(() => false));
console.log("live notice or setup button:",
  await page.getByText("Live hardware debugging").isVisible().catch(() => false),
  await page.getByRole("button", { name: "Set up the live environment" }).first().isVisible().catch(() => false));

console.log("console errors:", errors.length ? errors.slice(0, 5) : "none");
await browser.close();
