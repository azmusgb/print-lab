// Params Panel palette.html in headless Chromium with the Fusion palette bridge stubbed. Run by tests/test_params_panel_dom.py.
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const page_url = pathToFileURL(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../tools/fusion/ParamsPanel/palette.html")).href;

const param = (name, expression) => ({ name, expression, value: expression, comment: "", favorite: false, drives: ["Sketch1"], limits: [] });
const doc = (design, params) => ({ design, params, theme: "light", model: { bodies: 0 }, problems: { errors: [], warnings: [] }, projects: [] });

const failures = [];
const check = (name, ok, detail) => { console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : " :: " + detail}`); if (!ok) failures.push(name); };

const browser = await chromium.launch();
async function open(sets) {
  const page = await browser.newPage();
  // The bridge: "ready" answers the first document; "set" applies the expression to the current one and returns it.
  await page.addInitScript(() => {
    window.__docs = {}; window.__current = null; window.__sent = [];
    window.adsk = { fusionSendData: (action, json) => {
      const data = JSON.parse(json);
      window.__sent.push([action, data]);
      const d = window.__docs[window.__current];
      if (action === "set") d.params = d.params.map((p) => (p.name === data.name ? { ...p, expression: data.expression, value: data.expression } : p));
      return Promise.resolve(JSON.stringify(d));
    } };
  });
  await page.goto(page_url);
  await page.evaluate((s) => { window.__docs = s.docs; window.__current = s.current; }, sets);
  await page.evaluate((d) => window.fusionJavaScriptHandler.handle("state", JSON.stringify(d)), sets.docs[sets.current]);
  return page;
}
const push = (page, name) => page.evaluate((n) => { window.__current = n; window.fusionJavaScriptHandler.handle("state", JSON.stringify(window.__docs[n])); }, name);
const focused = (page) => page.evaluate(() => { const a = document.activeElement; return a ? `${a.tagName.toLowerCase()}.${a.className}|${a.dataset.name || ""}|${a.getAttribute("aria-label") || ""}` : ""; });

// G1: Enter on a step button keeps focus on that same button after the rows are rebuilt.
for (const [label, expected] of [["Increase width", "Increase width"], ["Decrease height", "Decrease height"]]) {
  const page = await open({ current: "A", docs: { A: doc("A", [param("width", "10 mm"), param("height", "5 mm")]) } });
  await page.focus(`button.step[aria-label="${label}"]`);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__sent.some((s) => s[0] === "set"));
  await page.waitForTimeout(100);
  const f = await focused(page);
  check(`G1 focus stays on "${label}" after Enter`, f.endsWith("|" + expected), f);
  await page.close();
}
{
  // A step button that is no longer usable hands focus to its row's field instead of dropping it to the body.
  const page = await open({ current: "A", docs: { A: doc("A", [param("width", "10 mm")]) } });
  await page.focus(`button.step[aria-label="Increase width"]`);
  await page.evaluate(() => { window.__docs.A.params[0].expression = "=height * 2"; });
  await page.evaluate(() => window.fusionJavaScriptHandler.handle("state", JSON.stringify(window.__docs.A)));
  const f = await focused(page);
  check("G1 disabled step button falls back to its field", f.startsWith("input.expr") && f.includes("|width|"), f);
  await page.close();
}

// G2: an unsent draft belongs to its document.
{
  const docs = { A: doc("A", [param("width", "10 mm")]), B: doc("B", [param("width", "20 mm")]) };
  const page = await open({ current: "A", docs });
  await page.fill("input.expr", "99 mm");
  await page.evaluate(() => window.fusionJavaScriptHandler.handle("state", JSON.stringify(window.__docs.A)));
  check("G2 draft survives a re-render of the same document", (await page.inputValue("input.expr")) === "99 mm", await page.inputValue("input.expr"));
  await page.evaluate(() => { window.__sent.length = 0; }); // fill() may have committed A's draft on blur; only what follows matters
  await push(page, "B");
  const v = await page.inputValue("input.expr");
  const dirty = await page.$eval("input.expr", (i) => i.classList.contains("dirty"));
  check("G2 draft is dropped when Fusion switches document", v === "20 mm" && !dirty, `value=${v} dirty=${dirty}`);
  await page.focus("input.expr");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(100);
  const sent = await page.evaluate(() => window.__sent.filter((s) => s[0] === "set"));
  check("G2 Enter on B's unchanged field sends nothing", sent.length === 0, JSON.stringify(sent));
  await page.close();
}

await browser.close();
if (failures.length) { console.log(`${failures.length} failed`); process.exit(1); }
console.log("all passed");
