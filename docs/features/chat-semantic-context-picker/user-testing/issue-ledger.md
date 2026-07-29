# API Dogfood Issue Ledger

| ID      | Severity | Persona | Evidence                                                                                                                             | Owner           | Status |
| ------- | -------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------- | ------ |
| QUI-001 | High     | Quinn   | Wave 1: 6 routed cases returned 500. Wave 2: all 31 Quinn cases passed and malformed top-level payloads returned safe 400 responses. | Debug/fix agent | Closed |

Severity uses blocker, high, medium, and low. A failed expectation is not closed
until the routed API is retested.
