# Plane MCP v0.2.11 Per-Tool Dispositions

## Status

Proposed compatibility dispositions. Derived from `plane-mcp-v0.2.11.json` at pinned commit `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`.

Source inventory SHA-256: `2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1`.

## Invariants

- Exactly 177 unique tool rows are present.
- Every row matches exactly one rule from `MCP-COMPATIBILITY.md`.
- MCP-D-001 maps each SDK HTTP intent independently through the shared gateway transport.
- MCP-D-002 remains local and makes no Plane call.
- MCP-D-003 wraps Plane SDK calls and external byte transfer in the hardened attachment adapter.
- No tool is omitted, renamed, or deprecated for v1.
- The final manifest separately pins the generated handler-call and SDK method/path-to-versioned-operation maps. This table does not claim that generic strategy labels prove exact routing.

## Dispositions

| Tool                                    | Rule      | Adapter                | Gateway mapping strategy |
| --------------------------------------- | --------- | ---------------------- | ------------------------ |
| `list_customers`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_customer`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_customer`                     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_customer`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_customer`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_customer_properties`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_customer_property`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_customer_property`            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_customer_property`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_customer_property`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_customer_property_values`          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `set_customer_property_values`          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_customer_requests`                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_customer_request`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_customer_request`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_customer_request`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_customer_request`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_customer_work_items`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_customer_work_items`            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_cycles`                           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_cycle`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_cycle`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_cycle`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_cycle`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_cycle_work_items`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_cycle_work_items`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `transfer_cycle_work_items`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_cycle_archive`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `complete_cycle`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_initiatives`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_initiative`                     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_initiative`                   | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_initiative`                     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_initiative`                     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_initiative_projects`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_initiative_projects`            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_intake_work_items`                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_intake_work_item`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_intake_work_item`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_intake_work_item`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_intake_work_item`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_labels`                           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_label`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_label`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_label`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_label`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_milestones`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_milestone`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_milestone`                    | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_milestone`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_milestone`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_milestone_work_items`           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_milestone_work_items`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_modules`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_module`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_module`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_module`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_module`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_module_work_items`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_module_work_items`                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_module_archive`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_pages`                            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `attach_page_to_work_item`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_pages`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `detach_page_from_work_item`            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_page`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_page`                           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_pql_reference`                     | MCP-D-002 | local static reference | `local_static_reference` |
| `list_projects`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_project`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_project`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_project`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_project`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_project_archive`                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_project_worklog_summary`           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_project_members`                   | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_project_features`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_project_estimate`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_project_estimate_points`          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_project_estimate`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_project_estimate`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_project_estimate`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `link_estimate_to_project`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_project_estimate_points`        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_project_estimate_point`         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_project_estimate_point`         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_releases`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_release`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_release`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_release`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_release`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_release_changelog`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_release_changelog`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_release_labels`                   | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_release_label`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_release_label`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_release_label`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_release_labels`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_release_tags`                     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_release_tag`                    | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_release_tag`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_release_tag`                    | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_release_tag`                    | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_release_work_items`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_release_work_items`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_roles`                            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_role`                         | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_states`                           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_state`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_state`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_state`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_state`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_me`                                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_activities`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_activity`           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_attachments`            | MCP-D-003 | hardened attachment    | `attachment_specialized` |
| `get_work_item_attachment_download_url` | MCP-D-003 | hardened attachment    | `attachment_specialized` |
| `upload_work_item_attachment_from_url`  | MCP-D-003 | hardened attachment    | `attachment_specialized` |
| `delete_work_item_attachment`           | MCP-D-003 | hardened attachment    | `attachment_specialized` |
| `read_work_item_attachment`             | MCP-D-003 | hardened attachment    | `attachment_specialized` |
| `list_work_item_comments`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_comment`            | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_comment`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item_comment`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_comment`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_links`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_link`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_link`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item_link`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_link`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_properties`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_property`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_property`           | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item_property`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_property`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_work_item_type_properties`      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_property_options`       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_property_option`    | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_property_option`      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item_property_option`      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_property_option`      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_work_item_property_value`          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `set_work_item_property_value`          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_property_value`       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_relation_definitions`   | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_relation_definition`  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item_relation_definition`  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_relation_definition`  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_relations`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_relation`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `remove_work_item_relation`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_item_types`                  | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item_type`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `import_work_item_types_to_project`     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `resolve_work_item_type`                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_type`               | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item_type`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item_type`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_items`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `count_work_items`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_item`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item`                    | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `retrieve_work_item_by_identifier`      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_item`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_item`                      | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_work_item_assignee`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_work_item_label`                | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_archived_work_items`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `manage_work_item_archive`              | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `search_work_items`                     | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `list_work_logs`                        | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `create_work_log`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_work_log`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `delete_work_log`                       | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_workspace_members`                 | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `get_features`                          | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
| `update_workspace_features`             | MCP-D-001 | shared SDK transport   | `sdk_http_intent`        |
