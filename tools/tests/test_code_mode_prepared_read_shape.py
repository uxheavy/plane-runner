# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import json
import subprocess
from pathlib import Path


RUNNER = (
    Path(__file__).parents[2]
    / "apps"
    / "api"
    / "plane"
    / "agent"
    / "code_mode"
    / "runner.mjs"
)


def _run(source: str, work_item_read_call=None):
    help_result = subprocess.run(["node", "--help"], check=True, capture_output=True, text=True)
    permission_flag = "--permission" if "--permission" in help_result.stdout else "--experimental-permission"
    process = subprocess.Popen(
        [
            "node",
            permission_flag,
            "--no-addons",
            "--no-global-search-paths",
            "--allow-fs-read=" + str(RUNNER),
            "--allow-fs-read=/usr/share/node_modules/typescript",
            "--experimental-vm-modules",
            "--no-warnings",
            str(RUNNER),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(
        json.dumps(
            {
                "type": "run",
                "source": source,
                "input": {},
                "callbacks": {
                    "search": "search_plane_operations",
                    "describe": "describe_plane_operation",
                    "operation": "call_plane_operation",
                    "spill": "spill_plane_result",
                },
            }
        )
        + "\n"
    )
    process.stdin.flush()
    frames = []
    for line in process.stdout:
        frame = json.loads(line)
        frames.append(frame)
        if frame["type"] != "callback":
            break
        process.stdin.write(
            json.dumps(
                {
                    "type": "callback_result",
                    "id": frame["id"],
                    "receipt": {
                        "ok": True,
                        "result": {
                            "results": [
                                {
                                    "workItemReadCall": work_item_read_call
                                    or {
                                        "action": "read",
                                        "operationRef": "operation:work_item.read",
                                        "input": {"preparedCallRef": "prepared-call:opaque"},
                                    },
                                }
                            ]
                        },
                    },
                }
            )
            + "\n"
        )
        process.stdin.flush()
    process.terminate()
    process.wait(timeout=5)
    return frames


def test_code_mode_extracts_exact_work_item_read_call_before_callback():
    frames = _run(
        """
        export default async function ({host}) {
          const search = await host.call_plane_operation("search_workspace", {}, "i", "c");
          return await host.call_plane_operation(
            "work_item.read",
            {preparedCallRef: search.result.results[0].workItemReadCall},
            "i2",
            "c2"
          );
        }
        """
    )
    assert [frame["type"] for frame in frames] == ["callback", "callback", "result"]
    assert frames[1]["args"] == [
        "work_item.read",
        {"preparedCallRef": "prepared-call:opaque"},
        "i2",
        "c2",
    ]


def test_code_mode_extracts_shallow_prepared_ref_wrapper_before_callback():
    frames = _run(
        """
        export default async function ({host}) {
          const search = await host.call_plane_operation("search_workspace", {}, "i", "c");
          return await host.call_plane_operation(
            "work_item.read",
            {preparedCallRef: search.result.results[0].workItemReadCall},
            "i2",
            "c2"
          );
        }
        """,
        {"preparedCallRef": "prepared-call:opaque"},
    )
    assert [frame["type"] for frame in frames] == ["callback", "callback", "result"]
    assert frames[1]["args"] == [
        "work_item.read",
        {"preparedCallRef": "prepared-call:opaque"},
        "i2",
        "c2",
    ]


def test_code_mode_rejects_raw_ids_before_read_callback():
    frames = _run(
        """
        export default async function ({host}) {
          return await host.call_plane_operation(
            "work_item.read",
            {project_id: "raw", issue_id: "raw"},
            "i",
            "c"
          );
        }
        """
    )
    assert frames[-1]["type"] == "error"
    assert frames[-1]["code"] == "CODE_MODE_FAILED"
    assert [frame for frame in frames if frame["type"] == "callback"] == []


def test_code_mode_rejects_extra_prepared_read_keys_before_callback():
    frames = _run(
        """
        export default async function ({host}) {
          return await host.call_plane_operation(
            "work_item.read",
            {preparedCallRef: "prepared-call:opaque", issue_id: "raw"},
            "i",
            "c"
          );
        }
        """
    )
    assert frames[-1]["type"] == "error"
    assert frames[-1]["code"] == "CODE_MODE_FAILED"
    assert [frame for frame in frames if frame["type"] == "callback"] == []


def test_code_mode_rejects_deep_or_oversized_prepared_ref_wrappers():
    source = """
    export default async function ({host}) {
      const search = await host.call_plane_operation("search_workspace", {}, "i", "c");
      return await host.call_plane_operation(
        "work_item.read",
        {preparedCallRef: search.result.results[0].workItemReadCall},
        "i2",
        "c2"
      );
    }
    """
    for work_item_read_call in (
        {"preparedCallRef": {"preparedCallRef": {"preparedCallRef": "prepared-call:opaque"}}},
        {"preparedCallRef": "prepared-call:" + ("x" * 256)},
    ):
        frames = _run(source, work_item_read_call)
        assert frames[-1]["type"] == "error"
        assert frames[-1]["code"] == "CODE_MODE_FAILED"
        assert [frame for frame in frames if frame["type"] == "callback"] == [frames[0]]
