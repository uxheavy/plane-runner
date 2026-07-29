type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type ReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev021Fixture = Readonly<{ inline_input: ReadInput; spill_input: ReadInput }>;
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
type ArtifactRead = Readonly<{
  artifact_ref: string;
  offset: number;
  byte_length: number;
  bytes_base64: string;
  chunk_sha256: string;
  next_cursor: string | null;
  infrastructure_attempt_ref: string;
}>;
type PlaneCallback = Readonly<{
  call(operation: "plane.work_items.get@1", input: ReadInput): Promise<ReadSuccess>;
  readArtifact(artifactRef: string, cursor: string | undefined, limit: 23000): Promise<ArtifactRead>;
}>;
type Ev021Record = Readonly<{
  work_item_reference: WorkItemRef;
  output_kind: "inline" | "artifact";
  authoritative_byte_length: number;
  authoritative_sha256: string;
  artifact_ref: string | null;
  artifact_read_count: 0 | 2;
  reconstruction_match: boolean | null;
}>;

export default async function run(
  fixture: Ev021Fixture,
  plane: PlaneCallback
): Promise<readonly [Ev021Record, Ev021Record]> {
  const inline = await plane.call("plane.work_items.get@1", fixture.inline_input);
  const spill = await plane.call("plane.work_items.get@1", fixture.spill_input);
  if (inline.state !== "succeeded" || inline.output.kind !== "inline") {
    throw new Error("EV021_INLINE_BOUNDARY_FAILED");
  }
  if (spill.state !== "succeeded" || spill.output.kind !== "artifact") {
    throw new Error("EV021_SPILL_BOUNDARY_FAILED");
  }

  const inlineBytes = new TextEncoder().encode(canonicalize(inline.output.value));
  const inlineDigest = await sha256(inlineBytes);
  const first = await plane.readArtifact(spill.output.artifact_ref, undefined, 23000);
  if (first.next_cursor === null) throw new Error("EV021_FIRST_CURSOR_MISSING");
  const second = await plane.readArtifact(spill.output.artifact_ref, first.next_cursor, 23000);
  const firstBytes = decodeBase64(first.bytes_base64);
  const secondBytes = decodeBase64(second.bytes_base64);
  const reconstructed = new Uint8Array(firstBytes.byteLength + secondBytes.byteLength);
  reconstructed.set(firstBytes, 0);
  reconstructed.set(secondBytes, firstBytes.byteLength);
  const reconstructedDigest = await sha256(reconstructed);
  const reconstructionMatch =
    first.artifact_ref === spill.output.artifact_ref &&
    second.artifact_ref === spill.output.artifact_ref &&
    first.offset === 0 &&
    second.offset === first.byte_length &&
    first.byte_length === firstBytes.byteLength &&
    second.byte_length === secondBytes.byteLength &&
    second.next_cursor === null &&
    reconstructed.byteLength === spill.output.authoritative_byte_length &&
    reconstructedDigest === spill.output.authoritative_sha256;
  if (!reconstructionMatch) throw new Error("EV021_RECONSTRUCTION_MISMATCH");

  return [
    {
      work_item_reference: fixture.inline_input.work_item,
      output_kind: "inline",
      authoritative_byte_length: inlineBytes.byteLength,
      authoritative_sha256: inlineDigest,
      artifact_ref: null,
      artifact_read_count: 0,
      reconstruction_match: null,
    },
    {
      work_item_reference: fixture.spill_input.work_item,
      output_kind: "artifact",
      authoritative_byte_length: spill.output.authoritative_byte_length,
      authoritative_sha256: spill.output.authoritative_sha256,
      artifact_ref: spill.output.artifact_ref,
      artifact_read_count: 2,
      reconstruction_match: true,
    },
  ];
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("EV021_NON_JSON_NUMBER");
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
  throw new Error("EV021_NON_JSON_VALUE");
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}
async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
