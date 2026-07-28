import { chromium, devices } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const BASE = process.env.DASHBOARD_URL ?? "http://localhost:3000";
const EMAIL = process.env.REVIEWER_EMAIL ?? "";
const PASSWORD = process.env.REVIEWER_PASSWORD ?? "";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "build/dashboard-screenshots");
mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: "desktop", viewport: { width: 1440, height: 900 } },
  { name: "laptop", viewport: { width: 1024, height: 768 } },
  { name: "mobile", ...devices["iPhone 13"] },
];

async function collectIssues(page) {
  // The topbar is sticky, so content legitimately passes beneath it while
  // scrolled. Measure from the top so only true layout collisions are reported.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  return page.evaluate(() => {
    const problems = [];
    const visible = (node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        box.width > 0 &&
        box.height > 0
      );
    };

    document.querySelectorAll("*").forEach((node) => {
      if (!visible(node)) return;
      if (node.scrollWidth > node.clientWidth + 2 && node.clientWidth > 0) {
        const style = getComputedStyle(node);
        if (style.overflowX === "visible") {
          problems.push({
            kind: "horizontal-overflow",
            selector: node.tagName.toLowerCase() + (node.id ? `#${node.id}` : ""),
            scrollWidth: node.scrollWidth,
            clientWidth: node.clientWidth,
          });
        }
      }
    });

    if (document.documentElement.scrollWidth > window.innerWidth + 2) {
      problems.push({
        kind: "page-horizontal-scroll",
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      });
    }

    const boxes = [...document.querySelectorAll(".panel, .card, .tab, button, input, select")]
      .filter(visible)
      .map((node) => ({
        selector:
          node.tagName.toLowerCase() +
          (node.id ? `#${node.id}` : node.className ? `.${String(node.className).split(" ")[0]}` : ""),
        box: node.getBoundingClientRect(),
        node,
      }));

    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i];
        const b = boxes[j];
        if (a.node.contains(b.node) || b.node.contains(a.node)) continue;
        const overlapWidth =
          Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left);
        const overlapHeight =
          Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
        if (overlapWidth > 2 && overlapHeight > 2) {
          problems.push({
            kind: "overlap",
            a: a.selector,
            b: b.selector,
            overlapWidth: Math.round(overlapWidth),
            overlapHeight: Math.round(overlapHeight),
          });
        }
      }
    }
    return problems;
  });
}

async function run() {
  const browser = await chromium.launch();
  const report = [];
  const consoleErrors = [];

  for (const profile of VIEWPORTS) {
    const context = await browser.newContext(profile);
    const page = await context.newPage();
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(`${profile.name}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) =>
      consoleErrors.push(`${profile.name}: pageerror ${error.message}`),
    );

    // networkidle never settles reliably here; explicit waits below are the gate.
    await page.goto(BASE, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () => !document.getElementById("deployment-line").textContent.includes("loading"),
      { timeout: 15000 },
    );

    // Personal Memory — the session list loads after the actor list, so wait for
    // a real session option before pressing Load.
    await page.waitForFunction(
      () => {
        const select = document.getElementById("session-select");
        return select.options.length > 0 && Boolean(select.value);
      },
      { timeout: 20000 },
    );
    await page.click("#personal-refresh");
    await page.waitForSelector("#stm-list .card", { timeout: 60000 });
    await page.screenshot({
      path: `${OUT}/${profile.name}-personal.png`,
      fullPage: true,
    });
    report.push({
      viewport: profile.name,
      view: "personal",
      stmEvents: await page.textContent("#stm-count"),
      preferences: await page.textContent("#pref-count"),
      summaries: await page.textContent("#summary-count"),
      issues: await collectIssues(page),
    });

    // Shared Memory
    await page.click('.tab[data-view="shared"]');
    await page.click("#inventory-refresh");
    await page.waitForSelector("#inventory-list .card", { timeout: 60000 });
    await page.click("#search-run");
    await page.waitForSelector("#search-list .card", { timeout: 60000 });
    await page.screenshot({
      path: `${OUT}/${profile.name}-shared.png`,
      fullPage: true,
    });
    report.push({
      viewport: profile.name,
      view: "shared",
      inventory: await page.textContent("#inventory-count"),
      search: await page.textContent("#search-count"),
      firstScore: await page.textContent("#search-list .card .score"),
      issues: await collectIssues(page),
    });

    // Review Queue
    await page.click('.tab[data-view="review"]');
    if (EMAIL && PASSWORD) {
      await page.fill("#reviewer-email", EMAIL);
      await page.fill("#reviewer-password", PASSWORD);
      await page.click("#reviewer-signin");
      await page.waitForSelector("#review-list .card", { timeout: 60000 });
    }
    await page.screenshot({
      path: `${OUT}/${profile.name}-review.png`,
      fullPage: true,
    });
    const statuses = await page.$$eval("#review-list .tag", (nodes) =>
      nodes.map((node) => node.textContent),
    );
    report.push({
      viewport: profile.name,
      view: "review",
      candidates: await page.textContent("#review-count"),
      reviewerStatus: await page.textContent("#reviewer-status"),
      statuses: [...new Set(statuses)],
      issues: await collectIssues(page),
    });

    await context.close();
  }

  await browser.close();
  const totalIssues = report.reduce((sum, entry) => sum + entry.issues.length, 0);
  console.log(JSON.stringify({ report, consoleErrors, totalIssues }, null, 2));
  if (totalIssues || consoleErrors.length) process.exit(1);
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
