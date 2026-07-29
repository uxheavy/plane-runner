type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type AuthorizedReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev026Fixture = Readonly<{
  run_tag: string;
  persistence_nonce: string;
  pinned_launcher_path: string;
  authorized_read_input: AuthorizedReadInput;
}>;
type PlaneCallback = Readonly<{
  call(operation: "plane.work_items.get@1", input: AuthorizedReadInput): Promise<Readonly<{ state: string }>>;
}>;
type ProbeRecord = Readonly<{
  ordinal: number;
  probe_id: string;
  attempted: true;
  observed_error_code: string;
  controls: readonly [number, "succeeded", number, "succeeded"];
}>;

declare const process: Readonly<{
  getBuiltinModule(name: "module" | "worker_threads" | "vm"): unknown;
}>;

const PROFILE = [
  ["read_etc_passwd", "filesystem_denied"],
  ["read_pinned_launcher", "filesystem_denied"],
  ["write_tmp", "filesystem_denied"],
  ["subprocess", "subprocess_denied"],
  ["persistence_local_storage", "storage_surface_denied"],
  ["persistence_cache", "storage_surface_denied"],
  ["persistence_deno_kv", "storage_surface_denied"],
  ["worker_data_url", "worker_creation_denied"],
  ["worker_blob_url", "worker_creation_denied"],
  ["codegen_eval_import", "runtime_codegen_denied"],
  ["codegen_function_import", "runtime_codegen_denied"],
  ["codegen_async_function_import", "runtime_codegen_denied"],
  ["codegen_generator_function_import", "runtime_codegen_denied"],
  ["codegen_async_generator_function_import", "runtime_codegen_denied"],
  ["process_builtin_module", "runtime_surface_denied"],
  ["process_builtin_worker_threads", "runtime_surface_denied"],
  ["process_builtin_vm", "runtime_surface_denied"],
] as const;

const DATA_IMPORT_EXPRESSION = 'import("data:text/javascript,export default 1")';

export default async function run(fixture: Ev026Fixture, plane: PlaneCallback): Promise<readonly ProbeRecord[]> {
  const nonce = fixture.persistence_nonce;
  const hostile = {
    read_etc_passwd: () => Deno.readTextFile("/etc/passwd"),
    read_pinned_launcher: () => Deno.readTextFile(fixture.pinned_launcher_path),
    write_tmp: () => Deno.writeTextFile(`/tmp/ev026-${fixture.run_tag}`, "write-canary"),
    subprocess: () => new Deno.Command("/bin/echo", { args: ["ev026-process-canary"] }).output(),
    persistence_local_storage: () => {
      const key = `plane:ev026:${nonce}`;
      globalThis.localStorage.setItem(key, nonce);
      globalThis.localStorage.getItem(key);
    },
    persistence_cache: async () => {
      const cache = await caches.open(`plane-ev026-${nonce}`);
      const request = new Request(`https://ev026.invalid/${nonce}`);
      await cache.put(request, new Response(nonce, { headers: { "content-type": "text/plain" } }));
      await cache.match(request);
    },
    persistence_deno_kv: async () => {
      const kv = await Deno.openKv(`/tmp/plane-ev026-${nonce}.sqlite3`);
      try {
        await kv.set(["plane", "ev026", nonce], nonce);
        await kv.get(["plane", "ev026", nonce]);
      } finally {
        kv.close();
      }
    },
    worker_data_url: () => {
      const payload = workerPayload(nonce);
      const worker = new Worker(`data:application/javascript,${encodeURIComponent(payload)}`, { type: "module" });
      void worker;
    },
    worker_blob_url: () => {
      const payload = workerPayload(nonce);
      const blobUrl = URL.createObjectURL(new Blob([payload], { type: "application/javascript" }));
      try {
        const worker = new Worker(blobUrl, { type: "module" });
        void worker;
      } finally {
        URL.revokeObjectURL(blobUrl);
      }
    },
    codegen_eval_import: async () => {
      const indirectEval = eval;
      await indirectEval(DATA_IMPORT_EXPRESSION);
    },
    codegen_function_import: async () => {
      const FunctionConstructor = function () {}.constructor as FunctionConstructor;
      const load = FunctionConstructor(`return ${DATA_IMPORT_EXPRESSION}`) as () => Promise<unknown>;
      await load();
    },
    codegen_async_function_import: async () => {
      const AsyncFunctionConstructor = Object.getPrototypeOf(async function () {}).constructor as FunctionConstructor;
      const load = AsyncFunctionConstructor(`return ${DATA_IMPORT_EXPRESSION}`) as () => Promise<unknown>;
      await load();
    },
    codegen_generator_function_import: async () => {
      const GeneratorFunctionConstructor = Object.getPrototypeOf(function* () {}).constructor as FunctionConstructor;
      const load = GeneratorFunctionConstructor(`return ${DATA_IMPORT_EXPRESSION}`) as () => Generator<
        never,
        Promise<unknown>,
        unknown
      >;
      await load().next().value;
    },
    codegen_async_generator_function_import: async () => {
      const AsyncGeneratorFunctionConstructor = Object.getPrototypeOf(async function* () {})
        .constructor as FunctionConstructor;
      const load = AsyncGeneratorFunctionConstructor(`yield ${DATA_IMPORT_EXPRESSION}`) as () => AsyncGenerator<
        unknown,
        void,
        unknown
      >;
      await load().next();
    },
    process_builtin_module: () => process.getBuiltinModule("module"),
    process_builtin_worker_threads: () => process.getBuiltinModule("worker_threads"),
    process_builtin_vm: () => process.getBuiltinModule("vm"),
  } as const;

  const records: ProbeRecord[] = [];
  for (const [index, [probeId, expectedCode]] of PROFILE.entries()) {
    records.push(
      // Each hostile probe and its liveness brackets must complete before the next probe.
      // oxlint-disable-next-line no-await-in-loop
      await bracket(index + 1, probeId, expectedCode, hostile[probeId], fixture.authorized_read_input, plane)
    );
  }
  if (records.length !== PROFILE.length) throw new Error("EV026_RUNTIME_PROFILE_INCOMPLETE");
  return records;
}

async function bracket(
  ordinal: number,
  probeId: string,
  expectedCode: string,
  hostile: () => unknown | Promise<unknown>,
  input: AuthorizedReadInput,
  plane: PlaneCallback
): Promise<ProbeRecord> {
  const beforeCompute = compute(ordinal, 1);
  await authorizedRead(input, plane);
  const observedCode = await requirePolicyDenial(hostile, expectedCode);
  const afterCompute = compute(ordinal, 2);
  await authorizedRead(input, plane);
  return {
    ordinal,
    probe_id: probeId,
    attempted: true,
    observed_error_code: observedCode,
    controls: [beforeCompute, "succeeded", afterCompute, "succeeded"],
  };
}

function compute(ordinal: number, phase: 1 | 2): number {
  const value = ordinal * 109 + phase;
  if (!Number.isSafeInteger(value)) throw new Error("COMPUTE_CONTROL_FAILED");
  return value;
}
async function authorizedRead(input: AuthorizedReadInput, plane: PlaneCallback): Promise<void> {
  const result = await plane.call("plane.work_items.get@1", input);
  if (result.state !== "succeeded") throw new Error("AUTHORIZED_CALLBACK_CONTROL_FAILED");
}
async function requirePolicyDenial(hostile: () => unknown | Promise<unknown>, expectedCode: string): Promise<string> {
  let caught: unknown;
  try {
    await hostile();
  } catch (error) {
    caught = error;
  }
  if (caught === undefined) throw new Error("HOSTILE_PROBE_UNEXPECTEDLY_SUCCEEDED");
  const code = policyCode(caught, expectedCode);
  if (code !== expectedCode) throw new Error(`WRONG_POLICY_DENIAL:${code}`);
  return code;
}
function policyCode(error: unknown, expectedCode: string): string {
  if (typeof error !== "object" || error === null) return "missing";
  if (error instanceof Deno.errors.NotCapable) return expectedCode;
  if (error instanceof EvalError && expectedCode === "runtime_codegen_denied") return expectedCode;
  if ("code" in error && typeof error.code === "string") return error.code;
  if ("error" in error && typeof error.error === "object" && error.error !== null) {
    const nested = error.error;
    if ("code" in nested && typeof nested.code === "string") return nested.code;
  }
  return "missing";
}

function workerPayload(nonce: string): string {
  const literal = JSON.stringify(nonce);
  return `
    const nonce = ${literal};
    try {
      const key = \`plane:ev026:\${nonce}\`;
      globalThis.localStorage.setItem(key, nonce);
      globalThis.localStorage.getItem(key);
    } catch {}
    try {
      const cache = await caches.open(\`plane-ev026-\${nonce}\`);
      const request = new Request(\`https://ev026.invalid/\${nonce}\`);
      await cache.put(request, new Response(nonce, { headers: { "content-type": "text/plain" } }));
      await cache.match(request);
    } catch {}
    try {
      const kv = await Deno.openKv(\`/tmp/plane-ev026-\${nonce}.sqlite3\`);
      await kv.set(["plane", "ev026", nonce], nonce);
      await kv.get(["plane", "ev026", nonce]);
      kv.close();
    } catch {}
  `;
}
