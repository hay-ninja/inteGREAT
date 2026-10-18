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
// click a real node (not a region)
const node = pg.locator(".react-flow__node-trace").nth(3);
await node.scrollIntoViewIfNeeded().catch(() => {});
const nb = await node.boundingBox();
console.log("node at x:", nb && Math.round(nb.x + nb.width / 2));
await node.click({ timeout: 8000 });
await pg.waitForTimeout(900); // pan anim ~280ms + settle
const insp = pg.locator(".graph-inspector");
const ib = await insp.boundingBox();
console.log("inspector on left:", !!ib && ib.x < 20, "| bounds:", ib && `${Math.round(ib.x)},${Math.round(ib.width)}`);
const nb2 = await node.boundingBox();
const mid = nb2 && Math.round(nb2.x + nb2.width / 2);
console.log("node now at x:", mid, "| right of panel:", mid > (ib?.width ?? 0) + 30);
await pg.screenshot({ path: "inspector_left.png" });
await b.close();
