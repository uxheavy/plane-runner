type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type AuthorizedReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev023Fixture = Readonly<{
  canary_name: string;
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

const PROFILE = [
  ["env_get", "environment_denied"],
  ["env_to_object", "environment_denied"],
  ["proc_self_environ", "filesystem_denied"],
  ["system_memory_info", "system_denied"],
  ["os_release", "system_denied"],
  ["load_average", "system_denied"],
  ["hostname", "system_denied"],
] as const;

export default async function run(fixture: Ev023Fixture, plane: PlaneCallback): Promise<readonly ProbeRecord[]> {
  const hostile = {
    env_get: () => Deno.env.get(fixture.canary_name),
    env_to_object: () => Deno.env.toObject(),
    proc_self_environ: () => Deno.readTextFile("/proc/self/environ"),
    system_memory_info: () => Deno.systemMemoryInfo(),
    os_release: () => Deno.osRelease(),
    load_average: () => Deno.loadavg(),
    hostname: () => Deno.hostname(),
  } as const;

  const records: ProbeRecord[] = [];
  for (const [index, [probeId, expectedCode]] of PROFILE.entries()) {
    records.push(
      // Each hostile probe and its liveness brackets must complete before the next probe.
      // oxlint-disable-next-line no-await-in-loop
      await bracket(index + 1, probeId, expectedCode, hostile[probeId], fixture.authorized_read_input, plane)
    );
  }
  if (records.length !== PROFILE.length) throw new Error("EV023_PROFILE_INCOMPLETE");
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
  const value = ordinal * 101 + phase;
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
