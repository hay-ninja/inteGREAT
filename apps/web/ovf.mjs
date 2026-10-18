import { chromium } from "playwright";
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 800, height: 600 } });
await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
if (await page.getByText("Explore a demo").isVisible().catch(() => false)) {
  await page.getByText("Wrong pin in the code").click();
  await page.getByRole("button", { name: "Load demo" }).click();
}
await page.waitForSelector(".graph-canvas", { timeout: 20000 });
await page.waitForTimeout(800);
const wide = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll("*").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.right > 800 && r.width > 4) out.push(`${el.tagName}.${String(el.className).slice(0,60)} right=${Math.round(r.right)} w=${Math.round(r.width)}`);
  });
  return out.slice(0, 15);
});
console.log(wide.join("\n"));
await b.close();
