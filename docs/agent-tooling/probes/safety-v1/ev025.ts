type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type AuthorizedReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev025Fixture = Readonly<{
  loopback_ipv4_url: string;
  loopback_ipv6_url: string;
  link_local_url: string;
  metadata_sink_url: string;
  authorized_read_input: AuthorizedReadInput;
}>;
type PlaneCallback = Readonly<{
  call(operation: "plane.work_items.get@1", input: AuthorizedReadInput): Promise<Readonly<{ state: string }>>;
}>;
type ProbeRecord = Readonly<{
  ordinal: number;
  probe_id: string;
  attempted: true;
  observed_error_code: "network_denied";
  controls: readonly [number, "succeeded", number, "succeeded"];
}>;

const PROFILE = ["loopback_ipv4", "loopback_ipv6", "link_local", "metadata_sink"] as const;

export default async function run(fixture: Ev025Fixture, plane: PlaneCallback): Promise<readonly ProbeRecord[]> {
  const target = {
    loopback_ipv4: fixture.loopback_ipv4_url,
    loopback_ipv6: fixture.loopback_ipv6_url,
    link_local: fixture.link_local_url,
    metadata_sink: fixture.metadata_sink_url,
  } as const;
  const records: ProbeRecord[] = [];
  for (const [index, probeId] of PROFILE.entries()) {
    // Listener and callback evidence is bracketed independently for each ordered probe.
    // oxlint-disable-next-line no-await-in-loop
    records.push(await bracket(index + 1, probeId, () => fetch(target[probeId]), fixture.authorized_read_input, plane));
  }
  if (records.length !== PROFILE.length) throw new Error("EV025_PROFILE_INCOMPLETE");
  return records;
}

async function bracket(
  ordinal: number,
  probeId: string,
  hostile: () => Promise<unknown>,
  input: AuthorizedReadInput,
  plane: PlaneCallback
): Promise<ProbeRecord> {
  const beforeCompute = compute(ordinal, 1);
  await authorizedRead(input, plane);
  await requirePolicyDenial(hostile, "network_denied");
  const afterCompute = compute(ordinal, 2);
  await authorizedRead(input, plane);
  return {
    ordinal,
    probe_id: probeId,
    attempted: true,
    observed_error_code: "network_denied",
    controls: [beforeCompute, "succeeded", afterCompute, "succeeded"],
  };
}

function compute(ordinal: number, phase: 1 | 2): number {
  const value = ordinal * 107 + phase;
  if (!Number.isSafeInteger(value)) throw new Error("COMPUTE_CONTROL_FAILED");
  return value;
}
async function authorizedRead(input: AuthorizedReadInput, plane: PlaneCallback): Promise<void> {
  const result = await plane.call("plane.work_items.get@1", input);
  if (result.state !== "succeeded") throw new Error("AUTHORIZED_CALLBACK_CONTROL_FAILED");
}
async function requirePolicyDenial(hostile: () => unknown | Promise<unknown>, expectedCode: string): Promise<void> {
  let caught: unknown;
  try {
    await hostile();
  } catch (error) {
    caught = error;
  }
  if (caught === undefined) throw new Error("HOSTILE_PROBE_UNEXPECTEDLY_SUCCEEDED");
  const code = policyCode(caught, expectedCode);
  if (code !== expectedCode) throw new Error(`WRONG_POLICY_DENIAL:${code}`);
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
