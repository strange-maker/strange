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
  assert.match(html, /正在连接安全工作台/);
  assert.doesNotMatch(html, /Codex is working|Your site is taking shape/);
});

test("frontend uses authenticated API data and no static article fallback", async () => {
  const [page, client, layout] = await Promise.all([readFile(new URL("app/page.tsx", root), "utf8"), readFile(new URL("app/api-client.ts", root), "utf8"), readFile(new URL("app/layout.tsx", root), "utf8")]);
  assert.match(page, /api<\{items:Article\[\]\}>/);
  assert.match(page, /api<Source\[\]>/);
  assert.doesNotMatch(page, /ARTICLES|COUNTRY_STATS|sources\.yaml/);
  assert.match(client, /\/api\/auth\/refresh/);
  assert.match(layout, /海外销售情报工作台/);
});
