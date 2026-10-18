import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 800 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) { await ws.first().click(); await page.waitForTimeout(600); }
await page.locator(".card-menu").first().locator("..").click({ position: { x: 60, y: 60 } });
const open = page.getByRole("button", { name: "Open project" });
if (await open.isVisible().catch(() => false)) await open.click();
await page.waitForSelector(".graph-canvas", { timeout: 15000 });
// expand all graph groups
const expand = page.getByRole("button", { name: /Expand (all|group)/i });
if (await expand.isVisible().catch(() => false)) { await expand.click(); await page.waitForTimeout(1500); }
// count edges whose stroke resolves to the error colour
const errColor = await page.evaluate(() => {
  const probe = document.createElement("span");
  probe.style.color = "var(--color-error)"; document.body.appendChild(probe);
  const c = getComputedStyle(probe).color; probe.remove(); return c;
});
const stats = await page.evaluate((err) => {
  const paths = [...document.querySelectorAll(".react-flow__edge path.react-flow__edge-path")];
  const red = paths.filter((p) => getComputedStyle(p).stroke === err);
  const animated = paths.filter((p) => p.closest(".react-flow__edge")?.classList.contains("animated"));
  return { edges: paths.length, red: red.length, animated: animated.length };
}, errColor);
console.log("error color:", errColor, "stats:", JSON.stringify(stats));
await page.screenshot({ path: "C:/Users/hayre/AppData/Local/Temp/integreat-shots/failure-trace.png" });
console.log("pageerrors:", errors.length ? errors : "none");
await browser.close();
