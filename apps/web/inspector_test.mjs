import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 800 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) { await ws.first().click(); await page.waitForTimeout(600); }
await page.locator(".card-menu").first().waitFor({ timeout: 8000 });
// open each project until one shows failed edges; click a node to test inspector
for (let i = 0; i < 4; i++) {
  const cards = page.locator(".card-menu");
  if (i >= await cards.count()) break;
  await cards.nth(i).locator("..").click({ position: { x: 60, y: 60 } });
  const open = page.getByRole("button", { name: "Open project" });
  if (await open.isVisible().catch(() => false)) await open.click();
  await page.waitForSelector(".graph-canvas", { timeout: 15000 }).catch(() => null);
  await page.waitForTimeout(1200);
  const failedEdges = await page.locator(".react-flow__edge path").evaluateAll(
    (ps) => ps.filter((p) => getComputedStyle(p).stroke === "rgb(224, 90, 90)" || p.style.stroke.includes("error")).length);
  const marks = await page.evaluate(() => document.querySelectorAll(".hl-failed_expectation").length);
  console.log(`project ${i}: failed-hl nodes=${marks}, red-ish edges=${failedEdges}`);
  // click a graph node → inspector side panel
  await page.locator(".gn").first().click().catch(() => null);
  await page.waitForTimeout(500);
  const insp = page.locator(".graph-inspector");
  if (await insp.isVisible().catch(() => false)) {
    const box = await insp.boundingBox();
    console.log("inspector:", JSON.stringify({ right: Math.round(box.x + box.width), w: Math.round(box.width), screen: 1440 }));
    const scrollable = await page.evaluate(() => {
      const b = document.querySelector(".graph-inspector-body");
      return b ? b.scrollHeight >= b.clientHeight : false;
    });
    console.log("inspector scrollable region ok:", scrollable);
    await page.screenshot({ path: "C:/Users/hayre/AppData/Local/Temp/integreat-shots/inspector-side.png" });
    // Escape closes
    await page.keyboard.press("Escape");
    console.log("escape closes:", !(await insp.isVisible().catch(() => false)));
    break;
  }
  // try next project
  await page.goBack().catch(() => page.goto("http://localhost:5173"));
}
console.log("pageerrors:", errors.length ? errors : "none");
await browser.close();
