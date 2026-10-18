import { chromium } from "playwright-core";
const b = await chromium.launch({ channel: "chrome", headless: true });
const pg = await b.newPage({ viewport: { width: 1000, height: 420 } });
pg.on("pageerror", e => console.log("PAGE ERROR:", String(e).slice(0, 160)));
await pg.goto("http://localhost:5173", { waitUntil: "networkidle" });
await pg.waitForTimeout(2000);
const enter = pg.getByRole("button", { name: "Open the workspace" }).first();
if (await enter.isVisible().catch(() => false)) { await enter.click(); await pg.waitForTimeout(1200); }
await pg.locator("[class*=card]", { hasText: "wrong pin" }).first().click({ timeout: 10000 });
await pg.waitForTimeout(900);
const dlg = pg.locator("dialog[open]").first();
// inflate the content wrapper (first child) to force real overflow
await dlg.locator("> *").first().evaluate(el => {
  const d = document.createElement("div"); d.style.height = "900px"; el.appendChild(d);
});
await pg.waitForTimeout(200);
const info = await dlg.evaluate(el => ({
  dlgH: Math.round(el.getBoundingClientRect().height),
  kids: [...el.children].map(c => ({
    h: Math.round(c.getBoundingClientRect().height), scrollH: c.scrollHeight,
    clientH: c.clientHeight, oy: getComputedStyle(c).overflowY })),
}));
console.log(JSON.stringify(info));
const contentKid = dlg.locator("> *").first();
const canScroll = await contentKid.evaluate(el => el.scrollHeight > el.clientHeight);
await pg.mouse.move(500, 200); await pg.mouse.wheel(0, 600); await pg.waitForTimeout(300);
const st = await contentKid.evaluate(el => el.scrollTop);
console.log("content child scrollable:", canScroll, "| wheel scrollTop:", st);
await pg.screenshot({ path: "dlg_scroll.png" });
await b.close();
