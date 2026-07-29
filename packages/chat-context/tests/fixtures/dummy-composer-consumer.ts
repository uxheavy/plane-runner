/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComposerContextAttachmentV1, ComposerContextConsumerPort } from "../../src";

export class DummyComposerConsumer implements ComposerContextConsumerPort {
  readonly attachments: ComposerContextAttachmentV1[] = [];

  async attachContext(attachment: ComposerContextAttachmentV1): Promise<void> {
    this.attachments.push(structuredClone(attachment));
  }
}
