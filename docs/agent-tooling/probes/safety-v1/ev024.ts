type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type AuthorizedReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev024Fixture = Readonly<{
  dns_name: string;
  public_https_url: string;
  plane_direct_https_url: string;
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

const PROFILE = ["dns", "public_https", "plane_direct_https"] as const;

export default async function run(fixture: Ev024Fixture, plane: PlaneCallback): Promise<readonly ProbeRecord[]> {
  const hostile = {
    dns: () => Deno.resolveDns(fixture.dns_name, "A"),
    public_https: () => fetch(fixture.public_https_url),
    plane_direct_https: () => fetch(fixture.plane_direct_https_url),
  } as const;
  const records: ProbeRecord[] = [];
  for (const [index, probeId] of PROFILE.entries()) {
    // Listener and callback evidence is bracketed independently for each ordered probe.
    // oxlint-disable-next-line no-await-in-loop
    records.push(await bracket(index + 1, probeId, hostile[probeId], fixture.authorized_read_input, plane));
  }
  if (records.length !== PROFILE.length) throw new Error("EV024_PROFILE_INCOMPLETE");
  return records;
}

async function bracket(
  ordinal: number,
  probeId: string,
  hostile: () => unknown | Promise<unknown>,
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
  const value = ordinal * 103 + phase;
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
