type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type AuthorizedReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev027Fixture = Readonly<{
  authorized_read_input: AuthorizedReadInput;
}>;
type PlaneCallback = Readonly<{
  call(
    operation: "plane.work_items.get@1",
    input: AuthorizedReadInput
  ): Promise<
    Readonly<{
      state: "succeeded";
      output: Readonly<{ kind: "inline"; value: Readonly<{ work_item: Readonly<{ id: string }> }> }>;
    }>
  >;
}>;
type Ev027Record = Readonly<{ ordinal: number; work_item_id: string }>;

export default async function run(fixture: Ev027Fixture, plane: PlaneCallback): Promise<readonly Ev027Record[]> {
  const records: Ev027Record[] = [];
  for (let ordinal = 1; ordinal <= 8; ordinal += 1) {
    // The harness injects one attack between each ordered pair of fresh controls.
    // oxlint-disable-next-line no-await-in-loop
    const result = await plane.call("plane.work_items.get@1", fixture.authorized_read_input);
    if (
      result.state !== "succeeded" ||
      result.output.kind !== "inline" ||
      typeof result.output.value.work_item.id !== "string"
    ) {
      throw new Error("EV027_CALLBACK_CONTROL_FAILED");
    }
    if (records[0] !== undefined && result.output.value.work_item.id !== records[0].work_item_id) {
      throw new Error("EV027_WORK_ITEM_IDENTITY_MISMATCH");
    }
    records.push({ ordinal, work_item_id: result.output.value.work_item.id });
  }
  if (records.length !== 8) throw new Error("EV027_CALLBACK_PROFILE_INCOMPLETE");
  return records;
}
