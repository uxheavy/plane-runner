type ReadInput = Readonly<{ work_item: Readonly<{ id: string }>; include_relations: false }>;
type Ev022Fixture = Readonly<{
  inputs: readonly [ReadInput, ReadInput, ReadInput, ReadInput, ReadInput];
}>;
type ArtifactDescriptor = Readonly<{
  kind: "artifact";
  artifact_ref: string;
  authoritative_byte_length: number;
  authoritative_sha256: string;
}>;
type ReadSuccess = Readonly<{
  state: "succeeded";
  output: Readonly<{ kind: "inline"; value: unknown }> | ArtifactDescriptor;
}>;
type PlaneCallback = Readonly<{
  call(operation: "plane.work_items.get@1", input: ReadInput): Promise<ReadSuccess>;
}>;
type Ev022Record = Readonly<{
  ordinal: number;
  work_item_id: string;
  authoritative_sha256: string;
  authoritative_byte_length: number;
  output_kind: "inline" | "artifact";
  artifact_ref: string | null;
}>;

export default async function run(fixture: Ev022Fixture, plane: PlaneCallback): Promise<readonly Ev022Record[]> {
  const records: Ev022Record[] = [];
  for (let index = 0; index < 5; index += 1) {
    const input = fixture.inputs[index];
    if (input === undefined) throw new Error(`EV022_INPUT_MISSING:${index + 1}`);
    // The cumulative-budget oracle requires these reads to execute in submitted order.
    // oxlint-disable-next-line no-await-in-loop
    const result = await plane.call("plane.work_items.get@1", input);
    if (result.state !== "succeeded") throw new Error(`EV022_READ_FAILED:${index + 1}`);
    if (index < 4) {
      if (result.output.kind !== "inline") throw new Error(`EV022_EARLY_SPILL:${index + 1}`);
      const bytes = new TextEncoder().encode(canonicalize(result.output.value));
      records.push({
        ordinal: index + 1,
        work_item_id: input.work_item.id,
        // Hashing must complete before the next read mutates cumulative-result state.
        // oxlint-disable-next-line no-await-in-loop
        authoritative_sha256: await sha256(bytes),
        authoritative_byte_length: bytes.byteLength,
        output_kind: "inline",
        artifact_ref: null,
      });
    } else {
      if (result.output.kind !== "artifact") throw new Error("EV022_FIFTH_RESULT_DID_NOT_SPILL");
      records.push({
        ordinal: 5,
        work_item_id: input.work_item.id,
        authoritative_sha256: result.output.authoritative_sha256,
        authoritative_byte_length: result.output.authoritative_byte_length,
        output_kind: "artifact",
        artifact_ref: result.output.artifact_ref,
      });
    }
  }
  if (records.length !== 5) throw new Error("EV022_PROFILE_INCOMPLETE");
  return records;
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("EV022_NON_JSON_NUMBER");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .toSorted()
      .map((key) => `${JSON.stringify(key)}:${canonicalize(record[key])}`)
      .join(",")}}`;
  }
  throw new Error("EV022_NON_JSON_VALUE");
}
async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
