import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", String(process.pid) + "-" + String(Date.now()));
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } }, { waitUntil() {}, passThroughOnException() {} });
}

test("server renders the production application shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /海外销售情报工作台/);
  assert.match(html, /登录工作台/);
  assert.doesNotMatch(html, /正在连接安全工作台/);
  assert.match(html, /前端版本：连接保护 v2/);
  assert.doesNotMatch(html, /Codex is working|Your site is taking shape/);
});

test("frontend uses authenticated API data and no static article fallback", async () => {
  const [page, client, layout] = await Promise.all([readFile(new URL("app/page.tsx", root), "utf8"), readFile(new URL("app/api-client.ts", root), "utf8"), readFile(new URL("app/layout.tsx", root), "utf8")]);
  assert.match(page, /api<\{items:Article\[\]\}>/);
  assert.match(page, /api<Source\[\]>/);
  assert.doesNotMatch(page, /ARTICLES|COUNTRY_STATS|sources\.yaml/);
  assert.match(client, /\/api\/auth\/refresh/);
  assert.match(client, /refreshInFlight/);
  assert.match(client, /AUTH_EXPIRED_EVENT/);
  assert.match(client, /API_TIMEOUT_MS/);
  assert.match(client, /API_BASE_VALID/);
  assert.doesNotMatch(page, /正在连接安全工作台/);
  assert.match(page, /连接保护 v2/);
  assert.match(layout, /海外销售情报工作台/);
});

test("country chart is horizontal, clickable, and routes to the merged opportunity page", async () => {
  const [page, css, countryRedirect, regionRedirect] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("app/globals.css", root), "utf8"),
    readFile(new URL("app/country/page.tsx", root), "utf8"),
    readFile(new URL("app/region/page.tsx", root), "utf8"),
  ]);
  assert.match(page, /className="horizontal-chart"/);
  assert.match(page, /onClick=\{\(\)=>onCountry\(x\.name\)\}/);
  assert.match(page, /国家与区域机会/);
  assert.match(css, /\.horizontal-chart button\{[^}]*grid-template-columns/);
  assert.match(countryRedirect, /view=opportunities&dimension=country/);
  assert.match(regionRedirect, /view=opportunities&dimension=region/);
});

test("source management uses one admin batch action and no row-level crawl button", async () => {
  const page = await readFile(new URL("app/page.tsx", root), "utf8");
  assert.match(page, /一键抓取全部可运行来源/);
  assert.match(page, /\/api\/admin\/crawl-batches/);
  assert.match(page, /同一时间只允许一个全量批次/);
  assert.doesNotMatch(page, /\/api\/sources\/\$\{s\.id\}\/run/);
  assert.doesNotMatch(page, />立即抓取</);
});

test("cscec page hides page diffs and opens detail without review controls", async () => {
  const page = await readFile(new URL("app/page.tsx", root), "utf8");
  assert.doesNotMatch(page, /\/api\/ka\/cscec\/page-diffs/);
  assert.doesNotMatch(page, /\["diffs","页面差异"\]/);
  assert.match(page, /showReview\?:boolean/);
  assert.match(page, /<Detail article=\{detail\} user=\{user\} onClose=.*showReview=\{view!=="cscec"\}/s);
});
