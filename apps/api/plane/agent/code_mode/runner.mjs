import * as nodeModule from "node:module";
import * as readline from "node:readline";
import * as vm from "node:vm";

const write = (frame) => {
  process.stdout.write(`${JSON.stringify(frame)}\n`);
};

const fail = (code, message) => {
  write({ type: "error", code, message });
  process.exitCode = 1;
};

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
let start;
try {
  const first = await new Promise((resolve, reject) => {
    lines.once("line", (line) => resolve(line));
    lines.once("error", reject);
  });
  start = JSON.parse(first);
  if (start?.type !== "run" || typeof start.source !== "string" || !start.input || !start.callbacks) {
    throw new Error("invalid Code Mode start frame");
  }
} catch {
  fail("PROTOCOL_ERROR", "invalid Code Mode start frame");
  process.exit(1);
}

let callbackSequence = 0;
const callback = (kind, name, args) => {
  const id = `callback:${++callbackSequence}`;
  write({ type: "callback", id, kind, name, args });
  return new Promise((resolve, reject) => {
    const onLine = (line) => {
      try {
        const frame = JSON.parse(line);
        if (frame?.type !== "callback_result" || frame.id !== id) {
          reject(new Error("callback response is not bound to the request"));
          return;
        }
        lines.removeListener("line", onLine);
        resolve(frame.receipt);
      } catch {
        reject(new Error("callback response is not valid JSON"));
      }
    };
    lines.on("line", onLine);
  });
};

const callbackNames = start.callbacks;
const host = Object.create(null);
host[callbackNames.search] = (...args) => callback("search", callbackNames.search, args);
host[callbackNames.describe] = (...args) => callback("describe", callbackNames.describe, args);
host[callbackNames.operation] = (...args) => callback("operation", callbackNames.operation, args);
host[callbackNames.spill] = (...args) => callback("spill", callbackNames.spill, args);
Object.freeze(host);

const stripTypes = (value) => {
  if (typeof nodeModule.stripTypeScriptTypes === "function") {
    return nodeModule.stripTypeScriptTypes(value, { mode: "strip" });
  }
  // The review image ships Node 21 without the built-in eraser.  This
  // deliberately supports only the generated callback form: primitive
  // parameter/return annotations are removed, while object literal colons are
  // untouched.  Unsupported TypeScript still fails closed at module parse.
  return value
    .replace(/}\s*:\s*\{[^{}]*\}/g, "}")
    .replace(/(\b(?:host|input|operationId|idempotencyKey|correlationId|query|limit))\s*:\s*(?:any|unknown|string|number|boolean)(?=\s*[,)=;])/g, "$1")
    .replace(/\)\s*:\s*(?:any|unknown|string|number|boolean)(?=\s*\{)/g, ")");
};

try {
  const context = vm.createContext(Object.create(null), {
    codeGeneration: { strings: false, wasm: false },
  });
  const source = stripTypes(start.source);
  const module = new vm.SourceTextModule(source, {
    context,
    identifier: "plane-code-mode.ts",
  });
  await module.link(() => {
    throw new Error("Code Mode imports are not permitted");
  });
  await module.evaluate();
  const entry = module.namespace.default;
  if (typeof entry !== "function") {
    throw new Error("Code Mode source must export a default function");
  }
  const value = await entry(Object.freeze({ host, input: Object.freeze(start.input) }));
  write({ type: "result", value });
} catch (error) {
  fail("CODE_MODE_FAILED", error instanceof Error ? error.message : "Code Mode failed");
}
