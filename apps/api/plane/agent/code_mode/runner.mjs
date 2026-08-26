import * as nodeModule from "node:module";
import * as readline from "node:readline";
import * as vm from "node:vm";

const require = nodeModule.createRequire(import.meta.url);
const TYPESCRIPT_MODULE = process.env.PLANE_CODE_MODE_TYPESCRIPT || "/usr/share/node_modules/typescript/lib/typescript.js";
const CODE_MODE_ERROR_CLASSES = new Set([
  "module_parse_or_load",
  "default_export_missing",
  "callback_or_protocol",
  "execution_runtime",
  "child_exit_no_result",
]);

const write = (frame) => {
  process.stdout.write(`${JSON.stringify(frame)}\n`);
};

const fail = (code, errorClass, toolError) => {
  const errorMessage = {
    module_parse_or_load: "Code Mode imports are not permitted",
    default_export_missing: "Code Mode source must export a default function",
    execution_runtime: "Code Mode execution failed in the restricted isolate",
    callback_or_protocol: "Code Mode callback or protocol failed closed",
    child_exit_no_result: "Code Mode child exited without a result",
  }[errorClass] || (code === "TYPE_CHECK_FAILED" ? "Code Mode source does not match the current Plane declarations" : undefined);
  write({
    type: "error",
    code,
    ...(CODE_MODE_ERROR_CLASSES.has(errorClass) ? { errorClass } : {}),
    ...(errorMessage ? { errorMessage } : {}),
    ...(toolError && typeof toolError === "object" ? { toolError } : {}),
  });
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
          const error = new Error("callback response is not bound to the request");
          error.codeModeErrorClass = "callback_or_protocol";
          reject(error);
          return;
        }
        lines.removeListener("line", onLine);
        resolve(frame.receipt);
      } catch {
        const error = new Error("callback response is not valid JSON");
        error.codeModeErrorClass = "callback_or_protocol";
        reject(error);
      }
    };
    lines.on("line", onLine);
  });
};

const callbackNames = start.callbacks;
const host = Object.create(null);
if (start.mode === "plane") {
  host[callbackNames.resource] = (...args) => callback("resource", callbackNames.resource, args);
  host[callbackNames.finish] = (...args) => callback("finish", callbackNames.finish, args);
} else {
  host[callbackNames.search] = (...args) => callback("search", callbackNames.search, args);
  host[callbackNames.describe] = (...args) => callback("describe", callbackNames.describe, args);
}

if (start.mode !== "plane") {
const PREPARED_CALL_PREFIX = "prepared-call:";
const MAX_PREPARED_CALL_REF_BYTES = 256;
const hasExactKeys = (value, expected) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value).toSorted();
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
  if (operationId !== "work_item.read" || !hasExactKeys(input, ["preparedCallRef"])) return input;
  return { preparedCallRef: preparedCallRefFromWorkItemReadCall(input.preparedCallRef) };
};

host[callbackNames.operation] = (operationId, input, ...args) => {
  try {
    return callback(
      "operation",
      callbackNames.operation,
      [operationId, normalizeOperationInput(operationId, input), ...args],
    );
  } catch (error) {
    if (error && typeof error === "object") error.codeModeErrorClass = "callback_or_protocol";
    throw error;
  }
};
host[callbackNames.spill] = (...args) => callback("spill", callbackNames.spill, args);
}
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

const checkTypes = (source, declarations) => {
  const typescript = require(TYPESCRIPT_MODULE);
  const fileName = "plane-code-mode.ts";
  const typeSource = `${declarations}\nconst __plane_body = async () => {\n${source}\n};`;
  const options = {
    target: typescript.ScriptTarget.ES2022,
    module: typescript.ModuleKind.ESNext,
    strict: true,
    noEmit: true,
    skipLibCheck: true,
  };
  const compilerHost = typescript.createCompilerHost(options);
  const originalGetSourceFile = compilerHost.getSourceFile.bind(compilerHost);
  compilerHost.getSourceFile = (name, languageVersion, onError, shouldCreateNewSourceFile) =>
    name === fileName
      ? typescript.createSourceFile(name, typeSource, languageVersion, true)
      : originalGetSourceFile(name, languageVersion, onError, shouldCreateNewSourceFile);
  const program = typescript.createProgram([fileName], options, compilerHost);
  const diagnostics = [
    ...program.getSyntacticDiagnostics(),
    ...program.getSemanticDiagnostics(),
  ];
  if (diagnostics.length) {
    const message = typescript.flattenDiagnosticMessageText(diagnostics[0].messageText, " ").slice(0, 512);
    const error = new Error(message);
    error.code = "TYPE_CHECK_FAILED";
    error.toolError = {
      code: "TYPE_CHECK_FAILED",
      message: `TypeScript declarations rejected the code: ${message}`,
      resolution: "Use the current Plane declaration slice and correct the TypeScript body.",
      retryable: false,
      recovery: "fix_code",
    };
    throw error;
  }
};

const makePlaneRuntime = async (context, input) => {
  const bridgeSource = `
    const freeze = (value) => {
      if (value && typeof value === "object" && !Object.isFrozen(value)) {
        Object.values(value).forEach(freeze);
        Object.freeze(value);
      }
      return value;
    };
    export default (serialized, call, finish) => {
      const input = JSON.parse(serialized);
      const task = freeze(input.task);
      const plane = {};
      for (const method of input.methods) {
        const [namespace, name] = method.path.split(".");
        plane[namespace] ??= {};
        plane[namespace][name] = (...args) => call(method.path, args).then((result) => {
          if (result?.__plane_error__) {
            const error = new Error(result.__plane_error__.message || "Plane operation failed");
            error.code = result.__plane_error__.code || "PLANE_OPERATION_FAILED";
            error.toolError = result.__plane_error__;
            throw error;
          }
          if (result?.status === "error") {
            const error = new Error(result.error?.message || "Plane operation failed");
            error.code = "PLANE_OPERATION_FAILED";
            error.toolError = result.error;
            throw error;
          }
          return result.value;
        });
      }
      plane.finish = (value) => finish(value).then((result) => {
        if (result?.__plane_error__) {
          const error = new Error(result.__plane_error__.message || "Plane finish failed");
          error.code = result.__plane_error__.code || "FINISH_REJECTED";
          error.toolError = result.__plane_error__;
          throw error;
        }
        return result;
      });
      return { task, plane: freeze(plane) };
    };
  `;
  const bridge = new vm.SourceTextModule(bridgeSource, { context, identifier: "plane-facade.ts" });
  await bridge.link(() => { throw new Error("Code Mode imports are not permitted"); });
  await bridge.evaluate();
  return bridge.namespace.default(
    JSON.stringify({ task: input.task, methods: input.methods }),
    (...args) => host[callbackNames.resource](...args),
    (value) => host[callbackNames.finish](value),
  );
};

let phase = "module_parse_or_load";
try {
  const context = vm.createContext(Object.create(null), {
    codeGeneration: { strings: false, wasm: false },
  });
  const planeRuntime = start.mode === "plane" ? await makePlaneRuntime(context, start.input) : null;
  if (start.mode === "plane" && typeof start.input.declarations === "string") {
    checkTypes(start.source, start.input.declarations);
  }
  const source = stripTypes(
    start.mode === "plane"
      ? `export default async (task, plane) => {\n${start.source}\n}`
      : start.source,
  );
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
    const error = new Error("Code Mode source must export a default function");
    error.codeModeErrorClass = "default_export_missing";
    throw error;
  }
  phase = "execution_runtime";
  const value = start.mode === "plane"
    ? await entry(planeRuntime.task, planeRuntime.plane)
    : await entry(Object.freeze({ host, input: Object.freeze(start.input) }));
  if (start.mode === "plane" && value === undefined) {
    const error = new Error("Plane:execute completed without a JSON return or plane.finish");
    error.codeModeErrorClass = "execution_runtime";
    error.code = "MISSING_TERMINAL_PUBLICATION";
    throw error;
  }
  write({ type: "result", value });
} catch (error) {
  const errorClass = CODE_MODE_ERROR_CLASSES.has(error?.codeModeErrorClass)
    ? error.codeModeErrorClass
    : phase;
  fail(
    start.mode === "plane" && typeof error?.code === "string" ? error.code : "CODE_MODE_FAILED",
    errorClass,
    start.mode === "plane" ? error?.toolError : undefined,
  );
}
