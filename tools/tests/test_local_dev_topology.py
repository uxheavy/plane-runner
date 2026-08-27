# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "check-local-dev-topology.py"
SPEC = importlib.util.spec_from_file_location("check_local_dev_topology", MODULE_PATH)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

EXPECTED = checker.runtime_manifest()


def _image_metadata(**overrides: object) -> dict[str, object]:
    labels = {
        "org.uxheavy.plane.hermes.commit": EXPECTED["hermesCommit"],
        "org.uxheavy.plane.runtime.revision": EXPECTED["runtimeImageRevision"],
        "org.uxheavy.plane.runtime.contract": EXPECTED["runtimeContract"],
    }
    labels.update(overrides.pop("labels", {}))
    metadata: dict[str, object] = {
        "Id": EXPECTED["runtimeImageDigest"],
        "Config": {"Labels": labels},
    }
    metadata.update(overrides)
    return metadata


class LocalRuntimeImageBindingTests(unittest.TestCase):
    def test_manifest_tag_is_exactly_accepted(self) -> None:
        checker.assert_runtime_image_tag(EXPECTED["runtimeImageTag"], EXPECTED)

    def test_alternate_or_floating_tag_is_rejected(self) -> None:
        for alternate in (
            "uxheavy/plane-agent-runtime:hermes-e573a466-g4-ff8cd9c5",
            "plane-agent-runtime:hermes-other-g4",
            "plane-agent-runtime:latest",
        ):
            with self.subTest(alternate=alternate), self.assertRaisesRegex(AssertionError, "must equal manifest tag"):
                checker.assert_runtime_image_tag(alternate, EXPECTED)

    def test_missing_exact_image_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(AssertionError, "image metadata must be an object"):
            checker.assert_runtime_image_metadata(None, EXPECTED)

    def test_image_id_must_match_manifest_digest(self) -> None:
        with self.assertRaisesRegex(AssertionError, "image ID must equal the manifest digest"):
            checker.assert_runtime_image_metadata(_image_metadata(Id="sha256:not-the-manifest"), EXPECTED)

    def test_image_labels_must_match_manifest(self) -> None:
        for label in (
            "org.uxheavy.plane.hermes.commit",
            "org.uxheavy.plane.runtime.revision",
            "org.uxheavy.plane.runtime.contract",
        ):
            with self.subTest(label=label), self.assertRaisesRegex(AssertionError, "must match the manifest"):
                checker.assert_runtime_image_metadata(_image_metadata(labels={label: "wrong"}), EXPECTED)

    def test_verified_image_metadata_is_accepted(self) -> None:
        checker.assert_runtime_image_metadata(_image_metadata(), EXPECTED)


if __name__ == "__main__":
    unittest.main()
