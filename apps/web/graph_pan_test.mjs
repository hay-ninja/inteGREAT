import { chromium } from "playwright-core";
const b = await chromium.launch({ channel: "chrome", headless: true });
const pg = await b.newPage({ viewport: { width: 1440, height: 800 } });
pg.on("pageerror", e => console.log("PAGE ERROR:", String(e).slice(0, 160)));
await pg.goto("http://localhost:5173", { waitUntil: "networkidle" });
await pg.waitForTimeout(2000);
const enter = pg.getByRole("button", { name: "Open the workspace" }).first();
if (await enter.isVisible().catch(() => false)) { await enter.click(); await pg.waitForTimeout(1500); }
await pg.locator("[class*=card]", { hasText: "wrong pin" }).first().click({ timeout: 10000 });
await pg.waitForTimeout(800);
const load = pg.getByRole("button", { name: "Load demo" });
if (await load.isVisible().catch(() => false)) await load.click();
await pg.locator(".graph-canvas").waitFor({ timeout: 25000 });
await pg.waitForTimeout(1500);
const t = () => pg.locator(".react-flow__viewport").evaluate(el => getComputedStyle(el).transform);
const before = await t();
await pg.mouse.move(720, 380);
for (let i = 0; i < 6; i++) { await pg.mouse.wheel(0, 120); await pg.waitForTimeout(60); }
await pg.waitForTimeout(400);
const after = await t();
await pg.keyboard.down("Control");
for (let i = 0; i < 4; i++) { await pg.mouse.wheel(0, -240); await pg.waitForTimeout(60); }
await pg.keyboard.up("Control");
await pg.waitForTimeout(400);
const zoomed = await t();
console.log("wheel panned:", before !== after, "| ctrl+wheel zoomed:", after !== zoomed);
console.log("before:", before, "| after pan:", after, "| after ctrl:", zoomed);
await b.close();
