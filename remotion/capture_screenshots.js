/**
 * capture_screenshots.js
 *
 * Uses Puppeteer to screenshot app.makone-bi.com pages and save them
 * to remotion/public/ for use in AvatarShowcase composition.
 *
 * Usage:
 *   node capture_screenshots.js [base_url] [output_dir]
 *
 * Defaults:
 *   base_url   = https://app.makone-bi.com
 *   output_dir = ./public
 */

import puppeteer from "puppeteer";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const BASE_URL = process.argv[2] || "https://app.makone-bi.com";
const OUT_DIR  = process.argv[3] || path.join(__dirname, "public");

const PAGES = [
  { path: "/",       filename: "dashboard.png" },
  { path: "/create", filename: "create.png"    },
];

const VIEWPORT = { width: 1920, height: 1080 };

async function run() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await puppeteer.launch({
    headless: "new",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  });

  try {
    for (const page_cfg of PAGES) {
      const url = BASE_URL + page_cfg.path;
      const out = path.join(OUT_DIR, page_cfg.filename);

      console.log(`Screenshotting ${url} → ${out}`);

      const page = await browser.newPage();
      await page.setViewport(VIEWPORT);

      await page.goto(url, { waitUntil: "networkidle2", timeout: 30000 });

      // Wait an extra second for any animations to settle
      await new Promise(r => setTimeout(r, 1000));

      await page.screenshot({ path: out, fullPage: false });
      await page.close();

      console.log(`Saved: ${out}`);
    }
  } finally {
    await browser.close();
  }

  console.log("Screenshots complete.");
}

run().catch(err => {
  console.error("Screenshot capture failed:", err.message);
  process.exit(1);
});
