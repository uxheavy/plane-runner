# M6 Evidence Contract: Composer Integration Kit

## Selected evidence

| Scenario     | Acceptance proof                                           | Prevention proof                                                |
| ------------ | ---------------------------------------------------------- | --------------------------------------------------------------- |
| Request      | Bundle becomes one bounded workspace hydration request     | Empty, oversized, and mixed-workspace bundles fail structurally |
| Response     | Ordered canonical and authorization-only results attach    | Count, order, reference, source, and shape mismatches fail      |
| Partial      | Authorized region items reach the composer with warnings   | Denied client observations are removed before the consumer      |
| Freshness    | Client observation and server canonical value coexist      | Neither value overwrites or impersonates the other              |
| Consumer     | Dummy consumer imports only the package's public Interface | No Plane UI or composer implementation dependency is required   |
| Cancellation | Abort before or during hydration returns `ABORTED`         | Cancelled context never reaches the consumer                    |

## Fixture families

Version 1 JSON fixtures cover entity, field, editor, region/partial, hydration,
and structured selection failure results. Tests load them through the same
public contracts used by the dummy consumer.
