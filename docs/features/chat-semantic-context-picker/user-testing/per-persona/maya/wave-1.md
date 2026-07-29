# Maya API Dogfood — Wave 1

## Assigned surface

| Surface        | Cases                                                                |
| -------------- | -------------------------------------------------------------------- |
| Route          | `POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/`         |
| Identity       | Active workspace and project administrator                           |
| Entities       | Work item, project, cycle, module, page, view                        |
| Fields         | All 11 allowlisted work-item fields                                  |
| Batch behavior | Mixed 17-item request, duplicates, stable ordering, maximum 50 items |
| Freshness      | Absent, equal, older, and newer observed versions                    |

## Evidence

| Case                                              | Executable evidence                                            | Result |
| ------------------------------------------------- | -------------------------------------------------------------- | ------ |
| Six entities and 11 fields                        | `test_realistic_mixed_request_returns_all_entities_and_fields` | Pass   |
| Duplicate correlation, ordering, and fresh values | `test_duplicates_keep_input_order_and_each_result_is_fresh`    | Pass   |
| Maximum allowed batch                             | `test_maximum_batch_of_50_preserves_every_duplicate_result`    | Pass   |

Evidence file:
`apps/api/plane/tests/contract/api/test_semantic_context_hydration_maya_dogfood.py`

## Wave decision

| Question                         | Answer                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------- |
| Verified product bugs            | None                                                                                  |
| Blocked routes                   | None                                                                                  |
| Would Maya use the API tomorrow? | Yes. Every requested reference resolved in input order with current canonical values. |

Verification:

```text
docker compose -f docker-compose-test.yml run --rm api-tests \
  pytest plane/tests/contract/api/test_semantic_context_hydration_maya_dogfood.py -q
3 passed in 2.00s
```

The first run exposed a fixture error: `QuerySet.update()` did not change the
model-managed version timestamp. The fixture now uses `save()`. This was not a
product finding.
