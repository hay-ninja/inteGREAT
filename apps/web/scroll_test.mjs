import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 800 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) { await ws.first().click(); await page.waitForTimeout(600); }
await page.locator(".card-menu").first().waitFor({ timeout: 8000 });
await page.locator(".card-menu").first().locator("..").click({ position: { x: 60, y: 60 } });
await page.getByRole("button", { name: "Open project" }).click();
await page.waitForSelector(".graph-canvas", { timeout: 15000 });
await page.getByRole("button", { name: "Activity", exact: true }).first().click();
await page.waitForTimeout(400);
// Pick the bottom-most scrollable region (drawer) and wheel over its centre.
const reg = await page.evaluate(() => {
  const els = [...document.querySelectorAll("div")].filter((d) => d.scrollHeight > d.clientHeight + 30);
  return els.map((d) => { const r = d.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, sh: d.scrollHeight }; });
});
console.log("regions:", JSON.stringify(reg.map((r) => ({ x: Math.round(r.x), y: Math.round(r.y), sh: r.sh, ch: Math.round(r.h) }))));
const drawer = reg.filter((r) => r.y > 400).sort((a, b) => b.y - a.y)[0];
if (drawer) {
  await page.mouse.move(drawer.x + drawer.w / 2, drawer.y + drawer.h / 2);
  const t0 = Date.now();
  for (let i = 0; i < 8; i++) await page.mouse.wheel(0, 300);
  await page.waitForTimeout(250);
  const res = await page.evaluate((y) => {
    const el = [...document.querySelectorAll("div")].find((d) => d.getBoundingClientRect().y === y && d.scrollTop > 0)
            ?? [...document.querySelectorAll("div")].find((d) => d.scrollTop > 0);
    return el ? el.scrollTop : 0;
  }, drawer.y);
  console.log("drawer scrollTop after 8 ticks:", res, `(${Date.now() - t0}ms)`);
}
console.log("pageerrors:", errors.length ? errors : "none");
await browser.close();
