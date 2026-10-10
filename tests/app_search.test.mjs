import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../public/static/app.js", import.meta.url), "utf8");
const searchCode = source.slice(source.indexOf("function scheduleSearch("), source.indexOf("function renderIndexing("));
function harness(fetch) {
  let timer = null;
  const state = { searchRequest: 0, searchPollTimer: null };
  const elements = {
    query: { value: "fixture" }, searchCount: {},
    gamesOnlyToggle: { checked: true }, formatFilter: { value: "" },
  };
  const rendered = [];
  const errors = [];
  const context = vm.createContext({
    state, elements, AbortController, URLSearchParams,
    apiFetch: fetch,
    setResultsBusy() {},
    showEmptyResults: (...args) => errors.push(args),
    renderIndexing() {}, renderResults: (...args) => rendered.push(args),
    setTimeout(callback) { timer = callback; return 1; },
    clearTimeout() { timer = null; },
  });
  vm.runInContext(searchCode, context);
  return { context, state, rendered, errors, getTimer: () => timer };
}
const response = (payload, status = 200) => ({ status, ok: status < 400, json: async () => payload });

test("catalog errors stop polling and show the cause", async () => {
  const h = harness(async () => response({ indexing: { ready: false, error: "disk full" } }, 202));
  await h.context.search("fixture");
  assert.equal(h.getTimer(), null);
  assert.equal(h.errors.at(-1)[1], "disk full");
});

test("typing a new query invalidates old responses during debounce", async () => {
  let finish;
  const h = harness(() => new Promise((resolve) => { finish = resolve; }));
  const pending = h.context.search("older");
  h.context.scheduleSearch();
  finish(response({ results: [{ fileName: "old" }], total: 1 }));
  await pending;
  assert.equal(h.rendered.length, 0);
});

test("clearing a query cancels catalog polling and rejects old results", async () => {
  let finish;
  const h = harness(() => new Promise((resolve) => { finish = resolve; }));
  const pending = h.context.search("older");
  await h.context.search("");
  finish(response({ indexing: { ready: false } }, 202));
  await pending;
  assert.equal(h.getTimer(), null);
  assert.equal(h.rendered.length, 0);
});
