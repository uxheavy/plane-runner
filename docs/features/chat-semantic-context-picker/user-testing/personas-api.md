# API Dogfood Personas

These personas were created for the semantic-context hydration API because no
existing Plane persona file was found. They test the product contract through
isolated API clients; they do not represent UI research.

## Maya — project lead

Maya manages active projects and expects an agent to receive fresh, useful
context without extra explanation. She exercises normal member and admin flows,
all supported entities and fields, ordering, freshness, and realistic batches.

## Ravi — restricted collaborator

Ravi is a guest or limited member. He expects useful context inside his scope and
safe, unsurprising failures outside it. He exercises private pages, revoked
membership, missing project access, cross-workspace references, and deleted data.

## Quinn — skeptical integrator

Quinn will not trust an API that is ambiguous or fragile. They exercise
authentication, HTTP methods, content types, malformed and oversized payloads,
unsupported references, duplicate items, response correlation, and error shape.
