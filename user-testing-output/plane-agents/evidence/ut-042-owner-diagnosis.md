# UT-042 pre-provider diagnosis

This is a redacted, provider-free extract. It contains no runtime secret,
provider credential, or credential-derived value.

- Candidate: `138e528237e8646c4de7a39caaf4b349a0f65702`
- Raw result SHA-256: `13d2394b78f3e5306ca2ac4d0f5e8c1b747a131abc579a5ae3f524829cc94dd3`
- Result: `api-invocation` / `ImproperlyConfigured`; exit code `1`
- Provider attempts: `0`; run and invocation references: absent; effects: none
- Compared API images: `plane-agent-api:g4-v6-138e5282` and
  `plane-agent-api:g4-v6-7e5f05e8`

The shared launcher passed migration-only `POSTGRES_*` variables and
`DATABASE_MIGRATION_URL` into the normal production API process. Production
settings correctly reject those variables, so the fix removes those bindings
from the normal API invocation while retaining the runtime database URLs.

The runner writes `secrets.token_urlsafe(48)` with no trailing newline. The
runtime validator accepts exactly that one-line file and rejects embedded or
trailing newline characters; the focused runtime regression already covers
that contract. No secret-validation relaxation or alternate credential path is
part of this fix.
