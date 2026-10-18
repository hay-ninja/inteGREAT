// Verify the Test/Debug/Analyze view switcher on a project with an open incident.
import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 800 } });
const sleep = (ms) => page.waitForTimeout(ms);
const shot = (n) => page.screenshot({ path: `C:/Users/hayre/AppData/Local/Temp/integreat-shots/${n}.png` });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) { await ws.first().click(); await sleep(600); }

// Open the project card named "fault_a" (has an open incident)
await page.locator(".card-menu").first().waitFor({ timeout: 8000 });
const card = page.locator("div").filter({ hasText: /^fault_a/ }).last();
await page.getByText("fault_a", { exact: true }).first().click();
await sleep(800);
const openBtn = page.getByRole("button", { name: "Open project" });
if (await openBtn.isVisible().catch(() => false)) { await openBtn.click(); await sleep(2000); }

await page.waitForSelector(".chapter", { timeout: 10000 });
await shot("v00-workspace");
// Debug should auto-select (open incident); check the rail
console.log("views:", await page.locator(".chapter .cname").allTextContents());

// Navigate freely — Test view must be reachable even with an open incident
await page.locator(".chapter").nth(0).click(); await sleep(600);
await shot("v01-test-again");
console.log("test view run-again:", await page.getByRole("button", { name: /Run the test again|Run test|Run again/ }).isVisible().catch(() => false));

// Back to Debug
await page.locator(".chapter").nth(1).click(); await sleep(600);
await shot("v02-debug");
console.log("debug content:", await page.getByText(/Debug — the incident|Overview/).first().isVisible().catch(() => false));
console.log("origin tags:", (await page.getByText("Rules").count()) + "x Rules,", await page.getByText("AI", { exact: true }).count(), "x AI");

// Analyze view
await page.locator(".chapter").nth(2).click(); await sleep(600);
await shot("v03-analyze");
console.log("analyze explainer:", await page.getByText("where AI helps").first().isVisible().catch(() => false)
  || await page.getByText("Everything else on this screen is deterministic").isVisible().catch(() => false));
console.log("ai review section:", await page.getByText("AI evidence review").isVisible().catch(() => false));

// Panel resize to ~half screen
const handle = page.locator("[class*='resize'], [role='separator']").first();
if (await handle.isVisible().catch(() => false)) {
  const box = await handle.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(700, box.y + box.height / 2, { steps: 10 });
    await page.mouse.up();
    await sleep(400);
  }
}
await shot("v04-wide");
console.log("console errors:", errors.length ? errors.slice(0, 5) : "none");
await browser.close();
