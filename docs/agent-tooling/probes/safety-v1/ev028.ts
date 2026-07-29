type ProjectRef = Readonly<{ id: string; identifier?: never }> | Readonly<{ id?: never; identifier: string }>;
type WorkItemRef =
  | Readonly<{ id: string; project?: never; sequence?: never }>
  | Readonly<{ id?: never; project: ProjectRef; sequence: number }>;
type ReadInput = Readonly<{ work_item: WorkItemRef; include_relations: false }>;

type Ev028Fixture = Readonly<{
  inputs: readonly [ReadInput, ReadInput, ReadInput, ReadInput, ReadInput, ReadInput, ReadInput, ReadInput];
}>;
type ReadSuccess = Readonly<{
  state: "succeeded";
  attempt_id: string;
  audit_ref: string;
  output: Readonly<{ kind: "inline"; value: Readonly<{ work_item: Readonly<{ id: string }> }> }>;
}>;
type PlaneCallback = Readonly<{
  call(operation: "plane.work_items.get@1", input: ReadInput): Promise<ReadSuccess>;
}>;
type Ev028Record = Readonly<{
  ordinal: number;
  work_item_id: string;
  attempt_id: string;
  audit_ref: string;
}>;

export default async function run(fixture: Ev028Fixture, plane: PlaneCallback): Promise<readonly Ev028Record[]> {
  const calls = [
    plane.call("plane.work_items.get@1", fixture.inputs[0]),
    plane.call("plane.work_items.get@1", fixture.inputs[1]),
    plane.call("plane.work_items.get@1", fixture.inputs[2]),
    plane.call("plane.work_items.get@1", fixture.inputs[3]),
    plane.call("plane.work_items.get@1", fixture.inputs[4]),
    plane.call("plane.work_items.get@1", fixture.inputs[5]),
    plane.call("plane.work_items.get@1", fixture.inputs[6]),
    plane.call("plane.work_items.get@1", fixture.inputs[7]),
  ] as const;
  const results = await Promise.all(calls);
  return results.map((result, index) => {
    if (result.state !== "succeeded" || result.output.kind !== "inline") {
      throw new Error(`EV028_READ_FAILED:${index + 1}`);
    }
    return {
      ordinal: index + 1,
      work_item_id: result.output.value.work_item.id,
      attempt_id: result.attempt_id,
      audit_ref: result.audit_ref,
    };
  });
}
