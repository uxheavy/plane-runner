# Maya API Dogfood — Wave 2

## Retest boundary

| Item              | Value                                                                         |
| ----------------- | ----------------------------------------------------------------------------- |
| Change under test | Top-level serializer error normalization and unknown-key messages (`QUI-001`) |
| Route             | `POST /api/workspaces/{workspaceSlug}/chat-context/hydrate/`                  |
| Persona lane      | Active workspace and project administrator                                    |
| Scope             | Maya's complete wave-1 routed API test file                                   |

## Evidence

```text
docker compose -f docker-compose-test.yml run --rm api-tests \
  pytest plane/tests/contract/api/test_semantic_context_hydration_maya_dogfood.py -q
3 passed in 2.00s
```

| Retested behavior                                 | Result |
| ------------------------------------------------- | ------ |
| Six supported entities and 11 work-item fields    | Pass   |
| Mixed 17-item request and response ordering       | Pass   |
| Duplicate references and fresh canonical values   | Pass   |
| Absent, equal, older, and newer observed versions | Pass   |
| Maximum 50-item request                           | Pass   |

## Wave verdict

| Question                         | Answer                                                                           |
| -------------------------------- | -------------------------------------------------------------------------------- |
| Regression from `QUI-001`        | None found in Maya's lane                                                        |
| Verified product bugs            | None                                                                             |
| Blocked routes                   | None                                                                             |
| Would Maya use the API tomorrow? | Yes. Normal project-lead hydration remains reliable after the serializer change. |

The first Docker launch was not executed because the approval service timed out.
The permitted retry ran the complete test file successfully. No identifiers or
credentials were captured.
