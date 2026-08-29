import assert from "node:assert/strict";
import test from "node:test";


import { evaluatePolicy, parseNameStatus, readIndexFile } from "./check.mjs";

function evaluate(changes, files = {}, existing = new Set()) {
  return evaluatePolicy({
    changes,
    baseHasPath: (path) => existing.has(path),
    baseBlob: () => "a".repeat(40),
    readFile: (path) => files[path] ?? null,
    now: new Date("2026-08-29T00:00:00Z"),
  });
}

test("parses added and renamed paths", () => {
  assert.deepEqual(parseNameStatus("A\0apps/web/new.ts\0R100\0old.ts\0new.ts\0"), [
    { status: "A", path: "apps/web/new.ts" },
    { status: "R", oldPath: "old.ts", path: "new.ts" },
  ]);
});

test("rejects only newly introduced generic buckets", () => {
  const change = [{ status: "A", path: "apps/web/helpers/new-helper.ts" }];
  assert.deepEqual(evaluate(change).map((error) => error.rule), ["RP001"]);
  assert.deepEqual(evaluate(change, {}, new Set(["apps/web/helpers"])), []);
});

test("rejects tracked outputs and rewritten migration history", () => {
  const errors = evaluate([
    { status: "A", path: "packages/ui/dist/index.js" },
    { status: "M", path: "apps/api/plane/db/migrations/0001_initial.py" },
    { status: "T", path: "apps/api/plane/db/migrations/0002_existing.py" },
  ]);
  assert.deepEqual(errors.map((error) => error.rule), ["RP002", "RP003", "RP003"]);
});

test("accepts an exact unexpired migration exception", () => {
  const path = "apps/api/plane/db/migrations/0001_initial.py";
  const files = {
    ".github/repository-policy-exceptions.json": JSON.stringify([
      {
        rule: "RP003",
        path,
        baseBlob: "a".repeat(40),
        reason: "Repair an invalid historical migration",
        approvedBy: "@api-owner",
        expires: "2026-08-30",
      },
    ]),
  };
  assert.deepEqual(evaluate([{ status: "M", path }], files), []);
});

test("rejects malformed migration exception dates", () => {
  const path = "apps/api/plane/db/migrations/0001_initial.py";
  const files = {
    ".github/repository-policy-exceptions.json": JSON.stringify([
      {
        rule: "RP003",
        path,
        baseBlob: "a".repeat(40),
        reason: "Repair an invalid historical migration",
        approvedBy: "@api-owner",
        expires: "not-a-date",
      },
    ]),
  };
  assert.deepEqual(evaluate([{ status: "M", path }], files).map((error) => error.rule), ["RP003"]);
});

test("enforces internal dependency protocol and ownership for new workspaces", () => {
  const path = "packages/example/package.json";
  const files = {
    [path]: JSON.stringify({ dependencies: { "@plane/types": "1.0.0" } }),
    CODEOWNERS: "packages/example/ @owner\n",
  };
  assert.deepEqual(evaluate([{ status: "A", path }], files).map((error) => error.rule), ["RP004"]);

  files[path] = JSON.stringify({ dependencies: { "@plane/types": "workspace:*" } });
  assert.deepEqual(evaluate([{ status: "A", path }], files), []);
});

test("requires an owner for a new workspace", () => {
  const path = "packages/example/package.json";
  const files = { [path]: "{}", CODEOWNERS: "packages/ui/ @owner\n" };
  assert.deepEqual(evaluate([{ status: "A", path }], files).map((error) => error.rule), ["RP005"]);

  files.CODEOWNERS = "packages/example/src/ @owner\n";
  assert.deepEqual(evaluate([{ status: "A", path }], files).map((error) => error.rule), ["RP005"]);

  files.CODEOWNERS = "packages/example/\n";
  assert.deepEqual(evaluate([{ status: "A", path }], files).map((error) => error.rule), ["RP005"]);

  files.CODEOWNERS = "packages/example/ @owner\n";
  assert.deepEqual(
    evaluate([{ status: "R", oldPath: "package.json", path }], files),
    [],
  );

  files.CODEOWNERS = "packages/ui/ @owner\n";
  assert.deepEqual(
    evaluate([{ status: "R", oldPath: "package.json", path }], files).map((error) => error.rule),
    ["RP005"],
  );
});

test("reads staged policy inputs from the index", () => {
  const calls = [];
  const content = readIndexFile("CODEOWNERS", (...args) => {
    calls.push(args);
    return "staged owner\n";
  });
  assert.equal(content, "staged owner\n");
  assert.deepEqual(calls[0].slice(0, 2), ["git", ["show", ":CODEOWNERS"]]);
});
