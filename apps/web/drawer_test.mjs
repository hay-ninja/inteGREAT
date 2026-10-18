// Drawer checks: camera tab, draggable height, split panes, env-setup rename.
import { chromium } from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 800 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
const shots = "C:/Users/hayre/AppData/Local/Temp/integreat-shots";
const log = (...a) => console.log("•", ...a);

await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
const ws = page.getByRole("button", { name: "Open the workspace" });
if (await ws.first().isVisible().catch(() => false)) { await ws.first().click(); await page.waitForTimeout(600); }
await page.locator(".card-menu").first().waitFor({ timeout: 8000 });
await page.locator(".card-menu").first().locator("..").click({ position: { x: 60, y: 60 } });
await page.waitForTimeout(800);
const ob = page.getByRole("button", { name: "Open project" });
if (await ob.isVisible().catch(() => false)) { await ob.click(); await page.waitForTimeout(2500); }

// rename check
log("env setup btn:", await page.getByRole("button", { name: "Environment setup" }).first().isVisible().catch(() => false));

// open the drawer on the camera tab
await page.getByRole("button", { name: "Camera", exact: true }).first().click();
await page.waitForTimeout(600);
log("camera tab empty state:", await page.getByText("No camera connected").isVisible().catch(() => false));
await page.screenshot({ path: `${shots}/d01-camera-tab.png` });

// drag the top edge up → drawer grows
const handle = page.locator('[role="separator"][aria-label="Resize logs panel"]');
const drawerBox = async () => (await handle.boundingBox()).y;
const before = await drawerBox();
const hb = await handle.boundingBox();
await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
await page.mouse.down();
await page.mouse.move(hb.x + hb.width / 2, hb.y - 160, { steps: 10 });
await page.mouse.up();
await page.waitForTimeout(400);
const after = await drawerBox();
log("drawer grew on drag up:", before - after, "px (expect >100)");

// split: button → second pane with own tabs
await page.getByLabel("Split into two panes").click();
await page.waitForTimeout(500);
const divider = page.locator('[role="separator"][aria-label="Resize split pane"]');
log("split divider:", await divider.isVisible().catch(() => false));
log("right pane tabs:", await page.getByRole("button", { name: "Activity", exact: true }).count() >= 1
                    && await page.getByRole("button", { name: "Board messages", exact: true }).count() >= 1);
await page.screenshot({ path: `${shots}/d02-split.png` });

// drag divider left → right pane grows
const db = await divider.boundingBox();
await page.mouse.move(db.x + db.width / 2, db.y + db.height / 2);
await page.mouse.down();
await page.mouse.move(db.x - 200, db.y + db.height / 2, { steps: 10 });
await page.mouse.up();
await page.waitForTimeout(400);
const db2 = await divider.boundingBox();
log("divider moved left:", Math.round(db.x - db2.x), "px (expect ~200)");

// drag divider hard right → split closes
await page.mouse.move(db2.x + db2.width / 2, db2.y + db2.height / 2);
await page.mouse.down();
await page.mouse.move(db2.x + 1200, db2.y + db2.height / 2, { steps: 12 });
await page.mouse.up();
await page.waitForTimeout(500);
log("split closed by drag:", !(await divider.isVisible().catch(() => false)));

// drag drawer top edge hard down → drawer collapses
const hb2 = await handle.boundingBox();
await page.mouse.move(hb2.x + hb2.width / 2, hb2.y + hb2.height / 2);
await page.mouse.down();
await page.mouse.move(hb2.x + hb2.width / 2, hb2.y + 800, { steps: 12 });
await page.mouse.up();
await page.waitForTimeout(500);
const collapsedY = await drawerBox();
log("drawer collapsed by drag:", collapsedY > 700);

// reopen via tab click
await page.getByRole("button", { name: "Activity", exact: true }).first().click();
await page.waitForTimeout(500);
log("drawer reopened:", (await drawerBox()) < 700);

console.log("\nconsole errors:", errors.length ? errors.slice(0, 6) : "none");
await browser.close();
