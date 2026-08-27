## Copyright and license checks

New source files in this fork use the `Ngo Quoc Huy` copyright header. Existing
Plane and third-party notices must be preserved. Package metadata uses the SPDX
identifier `AGPL-3.0-only`.

Check all rules:

```bash
pnpm check:copyright
```

Apply headers to source files added relative to `upstream/preview`:

```bash
pnpm --filter=@plane/codemods copyright-headers --write --added-from upstream/preview
```

Normalize package license metadata:

```bash
pnpm --filter=@plane/codemods copyright-headers --write-package-licenses
```

CI runs the same check through `.github/workflows/copyright-check.yml`.
