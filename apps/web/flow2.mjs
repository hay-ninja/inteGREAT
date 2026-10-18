import { chromium } from "playwright";
const S = "C:/Users/hayre/AppData/Local/Temp/integreat-shots";
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
if (await page.getByText("Explore a demo").isVisible().catch(() => false)) {
  await page.getByText("Wrong pin in the code").click();
  await page.getByRole("button", { name: "Load demo" }).click();
}
await page.waitForSelector(".graph-canvas", { timeout: 20000 });
// run a sim test to populate the flow
const sug = page.locator("button").filter({ hasText: "Suggest a test from the code" }).first();
if (await sug.isVisible().catch(() => false)) { await sug.click(); await page.locator("button").filter({ hasText: "Confirm test" }).first().click(); await page.waitForTimeout(600); }
const run = page.locator("button").filter({ hasText: /Run test|Run again/ }).first();
if (await run.isVisible().catch(() => false)) { await run.click(); await page.waitForTimeout(6000); }
await page.getByText("Event flow", { exact: true }).first().click();
await page.waitForTimeout(1400);
await page.screenshot({ path: `${S}/p-06-flowdata.png` });
await page.getByText("Dependencies", { exact: true }).first().click();
await page.waitForTimeout(1200);
await page.screenshot({ path: `${S}/p-07-graph.png` });
console.log("done");
await b.close();
