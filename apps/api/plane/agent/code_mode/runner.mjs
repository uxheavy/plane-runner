import * as nodeModule from "node:module";
import * as readline from "node:readline";
import * as vm from "node:vm";

const require = nodeModule.createRequire(import.meta.url);
const TYPESCRIPT_MODULE = "/usr/share/node_modules/typescript/lib/typescript.js";

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

const PREPARED_CALL_PREFIX = "prepared-call:";
const MAX_PREPARED_CALL_REF_BYTES = 256;
const hasExactKeys = (value, expected) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
};

const isPreparedCallRef = (value) =>
  typeof value === "string" &&
  value.startsWith(PREPARED_CALL_PREFIX) &&
  Buffer.byteLength(value, "utf8") <= MAX_PREPARED_CALL_REF_BYTES;

const preparedCallRefFromWorkItemReadCall = (value) => {
  if (typeof value === "string") {
    if (!isPreparedCallRef(value)) throw new Error("prepared work-item read reference is invalid");
    return value;
  }
  if (hasExactKeys(value, ["preparedCallRef"])) {
    const nestedRef = value.preparedCallRef;
    if (isPreparedCallRef(nestedRef)) return nestedRef;
    if (
      hasExactKeys(nestedRef, ["preparedCallRef"]) &&
      isPreparedCallRef(nestedRef.preparedCallRef)
    ) {
      return nestedRef.preparedCallRef;
    }
    throw new Error("prepared work-item read reference is invalid");
  }
  if (!hasExactKeys(value, ["action", "input", "operationRef"])) {
    throw new Error("prepared work-item read call is invalid");
  }
  if (value.action !== "read" || value.operationRef !== "operation:work_item.read") {
    throw new Error("prepared work-item read call is invalid");
  }
  if (!hasExactKeys(value.input, ["preparedCallRef"])) {
    throw new Error("prepared work-item read call is invalid");
  }
  const preparedCallRef = value.input.preparedCallRef;
  if (!isPreparedCallRef(preparedCallRef)) {
    throw new Error("prepared work-item read reference is invalid");
  }
  return preparedCallRef;
};

const normalizeOperationInput = (operationId, input) => {
  if (operationId !== "work_item.read") return input;
  if (!hasExactKeys(input, ["preparedCallRef"])) {
    throw new Error("prepared work-item read input is invalid");
  }
  return { preparedCallRef: preparedCallRefFromWorkItemReadCall(input.preparedCallRef) };
};

host[callbackNames.operation] = (operationId, input, ...args) =>
  callback(
    "operation",
    callbackNames.operation,
    [operationId, normalizeOperationInput(operationId, input), ...args],
  );
host[callbackNames.spill] = (...args) => callback("spill", callbackNames.spill, args);
Object.freeze(host);

const stripTypes = (value) => {
  if (typeof nodeModule.stripTypeScriptTypes === "function") {
    return nodeModule.stripTypeScriptTypes(value, { mode: "strip" });
  }
  const typescript = require(TYPESCRIPT_MODULE);
  return typescript.transpileModule(value, {
    compilerOptions: {
      target: typescript.ScriptTarget.ES2022,
      module: typescript.ModuleKind.ESNext,
    },
  }).outputText;
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
