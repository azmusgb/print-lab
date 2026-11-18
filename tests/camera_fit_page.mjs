// Browser check of the camera-fit page: server.py on 127.0.0.1 against a loopback FAKE bridge (never Fusion).
// Run by tests/test_camera_fit_page.py, or: NODE_PATH=<dir with playwright> node tests/camera_fit_page.mjs
import { createRequire } from "node:module";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

const fake = { value: 20, sets: [], delay: 0, failNext: false };
const bridge = http.createServer((req, res) => {
  const send = (code, body, type = "application/json") => { res.writeHead(code, { "Content-Type": type }); res.end(body); };
  if (req.method === "GET") {
    if (req.url === "/params") return send(200, JSON.stringify([{ name: "knob_d", expression: `${fake.value} mm`, value_mm: null, unit: "mm", comment: "knob diameter (placeholder)" }]));
    if (req.url === "/status") return send(200, JSON.stringify({ document: "fake", unsaved: false, failed: [], volume_mm3: 1000, busy: false }));
    if (req.url === "/components") return send(200, JSON.stringify([
      { name: "carrier:1", visible: true, volume_mm3: 1, size_mm: [1, 1, 1] },
      { name: "tilt_knob:1", visible: true, volume_mm3: 1, size_mm: [1, 1, 1] }]));
    if (req.url.startsWith("/shot")) return send(200, PNG, "image/png");
    return send(404, "{}");
  }
  let raw = "";
  req.on("data", (d) => { raw += d; });
  req.on("end", () => {
    const body = JSON.parse(raw);
    setTimeout(() => {
      if (fake.failNext) { fake.failNext = false; return send(500, JSON.stringify({ error: "Fusion said no." })); }
      fake.sets.push(body.expression);
      fake.value = parseFloat(body.expression);
      send(200, JSON.stringify({ name: body.name, before: "", after: body.expression, failed: [] }));
    }, fake.delay);
  });
});
await new Promise((r) => bridge.listen(0, "127.0.0.1", r));

const work = fs.mkdtempSync(path.join(os.tmpdir(), "camera-fit-page-"));
fs.cpSync(path.join(ROOT, "tools", "camera_fit"), path.join(work, "camera_fit"), { recursive: true, filter: (s) => !s.includes(`${path.sep}data`) });
fs.cpSync(path.join(ROOT, "tools", "ui"), path.join(work, "ui"), { recursive: true });
const port = 20000 + Math.floor(Math.random() * 20000);
const server = spawn("python3", ["-u", path.join(work, "camera_fit", "server.py"), "--host", "127.0.0.1", "--port", String(port),
  "--bridge", `http://127.0.0.1:${bridge.address().port}`], { stdio: ["ignore", "pipe", "inherit"] });
const url = await new Promise((resolve, reject) => {
  const t = setTimeout(() => reject(new Error("server did not start")), 10000);
  server.stdout.on("data", (d) => { const m = /(http:\/\/\S+)/.exec(String(d)); if (m) { clearTimeout(t); resolve(m[1]); } });
});

const results = [];
const check = (name, ok, detail) => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : ` -> ${detail}`}`); };
const browser = await chromium.launch();
try {
  const open = async () => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.addInitScript(() => {  // count live "pb-value" listeners on the document
      window.__pb = 0;
      const add = document.addEventListener.bind(document), rm = document.removeEventListener.bind(document);
      document.addEventListener = (t, fn, o) => {
        if (t === "pb-value") { window.__pb++; o?.signal?.addEventListener("abort", () => { window.__pb--; }); }
        return add(t, fn, o);
      };
      document.removeEventListener = (t, ...a) => { if (t === "pb-value") window.__pb--; return rm(t, ...a); };
    });
    await page.goto(url);
    await page.locator("#all summary").click();  // the full list sits in a closed <details>
    await page.waitForSelector("#params .card[data-name=knob_d]");
    return page;
  };
  const card = (page) => page.locator("#params .card[data-name=knob_d]");
  const shown = (page) => card(page).locator(".val input").inputValue();
  const type = async (page, v) => { const b = card(page).locator(".val input"); await b.fill(String(v)); await b.dispatchEvent("change"); };
  const idle = (page) => page.waitForFunction(() => !document.querySelector(".card[aria-busy=true]"));

  // F1: a failed change reverts to the last confirmed value, not the load-time one
  fake.value = 20; fake.sets = []; fake.delay = 0;
  let page = await open();
  await type(page, 30); await idle(page);
  fake.failNext = true;
  await type(page, 31); await idle(page);
  const f1 = await shown(page), f1r = await card(page).locator("input[type=range]").inputValue();
  check("F1 failed change reverts to the last confirmed value (30)", f1 === "30" && f1r === "30" && fake.value === 30, `box=${f1} slider=${f1r} fusion=${fake.value}`);
  await page.context().close();

  // F2: two quick + clicks are two steps, not one
  fake.value = 20; fake.sets = []; fake.delay = 300;
  page = await open();
  await card(page).locator(".inc").click(); await card(page).locator(".inc").click();
  await page.waitForTimeout(1200); await idle(page);
  check("F2 two quick + clicks make two steps", fake.value === 20.2 && (await shown(page)) === "20.2", `fusion=${fake.value} box=${await shown(page)} sets=${fake.sets}`);
  await page.context().close();

  // F2b: while steps are queued the card shows its pending target, not the step that just finished
  fake.value = 20; fake.sets = []; fake.delay = 300;
  page = await open();
  await card(page).locator(".inc").click(); await card(page).locator(".inc").click();
  await page.waitForTimeout(450);  // first step done (~300 ms), second still in flight
  const mid = await shown(page);
  await page.waitForTimeout(800);
  check("F2b the card keeps showing the pending target between queued steps", mid === "20.2", `box=${mid}`);
  await page.context().close();

  // F2c: a card rebuilt while steps are queued joins the same queue instead of racing it
  fake.value = 20; fake.sets = []; fake.delay = 400;
  page = await open();
  await card(page).locator(".inc").click(); await card(page).locator(".inc").click();
  await page.locator("#next").click(); await page.locator("#next").click();
  const sc = page.locator("#stepparams .card[data-name=knob_d]");
  const startVal = await sc.locator(".val input").inputValue();
  await sc.locator(".inc").click();
  await page.waitForTimeout(2000); await idle(page);
  check("F2c a rebuilt card starts from the pending target and queues behind it",
    startVal === "20.2" && fake.sets.join() === "20.1 mm,20.2 mm,20.3 mm", `start=${startVal} sets=${fake.sets}`);
  await page.context().close();

  // F4: queued steps dropped by a failure are said to be dropped
  fake.value = 20; fake.sets = []; fake.delay = 200; fake.failNext = true;
  page = await open();
  await card(page).locator(".inc").click(); await card(page).locator(".inc").click();
  await page.waitForTimeout(900); await idle(page);
  const msg = await card(page).locator(".err").textContent();
  check("F4 a failure says later steps were not sent and reverts", /not sent/.test(msg) && (await shown(page)) === "20" && fake.sets.length === 0, `msg=${msg} box=${await shown(page)} sets=${fake.sets}`);
  await page.context().close();

  // R1: a value the owner typed and committed (Enter, box still focused) is shown the way Fusion has it
  fake.value = 20; fake.sets = []; fake.delay = 0;
  page = await open();
  const box = card(page).locator(".val input");
  await box.focus(); await box.fill("20,55"); await box.press("Enter"); await idle(page);
  const r1a = [await shown(page), await card(page).locator("input[type=range]").inputValue(), await card(page).getAttribute("data-changed")];
  await box.fill("20.123"); await box.press("Enter"); await idle(page);
  const r1b = await shown(page);
  check("R1 a committed typed value is normalised and the card updated while the box has focus",
    r1a[0] === "20.55" && Math.abs(Number(r1a[1]) - 20.55) <= 0.05 + 1e-9 && r1a[2] === "true" && r1b === "20.12", `a=${r1a} b=${r1b}`);
  // R3: text typed but not committed survives a queued step finishing, and a failure puts the box back
  fake.delay = 300;
  await card(page).locator(".inc").click(); await box.focus(); await box.fill("25");
  await page.waitForTimeout(600); await idle(page);
  const r3a = await shown(page);
  fake.failNext = true; await card(page).locator(".inc").click(); await box.focus(); await box.fill("26");
  await page.waitForTimeout(600); await idle(page);
  const r3b = await shown(page);
  check("R3 an uncommitted edit survives a finished step; a failure restores the confirmed value", r3a === "25" && r3b === "20.22", `a=${r3a} b=${r3b} fusion=${fake.value}`);
  await page.context().close();

  // R2: the failure message reaches whichever card is visible, even if it was rebuilt while the step was in flight
  fake.value = 20; fake.sets = []; fake.delay = 500; fake.failNext = true;
  page = await open();
  await card(page).locator(".inc").click(); await card(page).locator(".inc").click();
  await page.locator("#next").click(); await page.locator("#next").click();
  await page.waitForTimeout(900); await idle(page);
  const r2 = await page.locator("#stepparams .card[data-name=knob_d] .err").textContent();
  check("R2 the visible card shows the failure and the dropped steps", /Fusion said no\..*1 later step not sent/.test(r2), `msg=${r2}`);
  await page.context().close();

  // F6: rebuilding the walkthrough's cards does not leave their listeners on the document
  fake.value = 20; fake.sets = []; fake.delay = 0;
  page = await open();
  for (let i = 0; i < 4; i++) {  // step 2 (tilt knob) builds a knob_d card each visit
    await page.locator("#next").click(); await page.locator("#next").click();
    await page.locator("#prev").click(); await page.locator("#prev").click();
  }
  await page.locator("#next").click(); await page.locator("#next").click();
  const live = await page.evaluate(() => window.__pb), cards = await page.locator(".card").count();
  check("F6 no listener outlives its card", live <= cards, `listeners=${live} cards=${cards}`);
  await page.context().close();
} finally {
  await browser.close(); server.kill("SIGKILL"); await new Promise((r) => server.once("exit", r)); bridge.close(); fs.rmSync(work, { recursive: true, force: true });
}
process.exit(results.every(Boolean) ? 0 : 1);
