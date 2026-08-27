/**
 * Copyright (c) 2026-present Ngo Quoc Huy
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";

import {
  FORK_COPYRIGHT,
  SPDX_LICENSE,
  UPSTREAM_COPYRIGHT,
  hasValidHeader,
  preservesLegalNotices,
  transformCopyrightHeader,
} from "../copyright-headers.mjs";

describe("copyright headers", () => {
  it("replaces the upstream owner on a newly added Python file", () => {
    const source = `# ${UPSTREAM_COPYRIGHT}\n# ${SPDX_LICENSE}\n\nprint("hello")\n`;
    const result = transformCopyrightHeader(source, "example.py");

    expect(result).toContain(FORK_COPYRIGHT);
    expect(result).not.toContain(UPSTREAM_COPYRIGHT);
    expect(result).toContain('print("hello")');
    expect(transformCopyrightHeader(result, "example.py")).toBe(result);
  });

  it("adds the fork header after a Python shebang", () => {
    const result = transformCopyrightHeader(
      "#!/usr/bin/env python3\nprint('hello')\n",
      "example.py"
    );

    expect(result).toMatch(
      `#!/usr/bin/env python3\n# ${FORK_COPYRIGHT}\n# ${SPDX_LICENSE}\n`
    );
  });

  it("adds the fork header to a TypeScript file", () => {
    const result = transformCopyrightHeader(
      "export const value = 1;\n",
      "example.ts"
    );

    expect(result).toMatch(`/**\n * ${FORK_COPYRIGHT}\n * ${SPDX_LICENSE}\n`);
  });

  it("accepts fork and preserved upstream headers", () => {
    expect(hasValidHeader(`// ${FORK_COPYRIGHT}\n// ${SPDX_LICENSE}\n`)).toBe(
      true
    );
    expect(
      hasValidHeader(`// ${UPSTREAM_COPYRIGHT}\n// ${SPDX_LICENSE}\n`)
    ).toBe(true);
    expect(hasValidHeader("export const value = 1;\n")).toBe(false);
  });

  it("preserves inherited legal notices on modified files", () => {
    const commercial =
      "# Copyright (c) Plane Software, Inc.\n# SPDX-License-Identifier: LicenseRef-Plane-Commercial\n";

    expect(
      preservesLegalNotices(commercial, `${commercial}\nprint('changed')\n`)
    ).toBe(true);
    expect(preservesLegalNotices(commercial, "print('changed')\n")).toBe(false);
    expect(
      preservesLegalNotices(
        "export const old = true;\n",
        `// ${FORK_COPYRIGHT}\n// ${SPDX_LICENSE}\n`
      )
    ).toBe(true);
  });
});
