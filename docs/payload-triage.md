# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | accepted | - | - | - |
| EDGE-02 | accepted | - | - | - |
| EDGE-03 | accepted | - | - | - |
| EDGE-04 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | rejected | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | rejected | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | rejected | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | rejected | - | MALFORMED_REQUEST | 400 |
| EDGE-09 | rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | rejected | - | MALFORMED_REQUEST | 400 |
| EDGE-12 | rejected | - | MALFORMED_REQUEST | 400 |

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07 (policy number "mot-4471" in lowercase)

**The ambiguity.** Section 2.2 states that `policy_number` is an "Identifier as held in the policy master" but does not explicitly specify whether matching is case-sensitive. The policy master holds "MOT-4471" (uppercase), while the notification carries "mot-4471" (lowercase). Two readings were available: (1) exact match required including case, or (2) case-insensitive matching.

**Decision.** Policy number matching is case-sensitive. A notification with "mot-4471" is rejected with `POLICY_NOT_FOUND` when the master holds "MOT-4471".

**Authority.** Section 2.2 states the field is an "Identifier as held in the policy master." The phrase "as held" indicates the value must match exactly as it appears in the authoritative system, including case. Additionally, treating identifiers as case-insensitive without explicit specification introduces ambiguity into what constitutes a match.

**Rejected alternative.** Case-insensitive matching would accept a policy number the master does not recognize in that form. Identifiers are typically case-sensitive unless explicitly normalized, and the contract provides no normalization rule. Accepting a variant form risks mismatches with downstream systems that expect the canonical form.

**Contract amended.** Section 2.2, `policy_number` field notes: added "exactly" before "as held" to read "Identifier exactly as held in the policy master" for clarity.

### Decision 2

**Payload.** EDGE-11 (claim_type "flood")

**The ambiguity.** Section 2.3 defines the claim type vocabulary as `collision`, `theft`, `glass`, `liability`, `weather`. Section 4.2 rule V-5 checks whether `claim_type` is "permitted on the policy's product." The contract did not specify what happens when `claim_type` is a value not in the section 2.3 vocabulary at all, such as "flood." Two readings were available: (1) reject as malformed before reaching rule evaluation (400), or (2) allow through to V-5 which would fail because no policy permits a claim type outside the vocabulary (422).

**Decision.** A `claim_type` value not in the section 2.3 vocabulary is rejected with `MALFORMED_REQUEST` and status 400 before any rule is evaluated.

**Authority.** Section 2.2 specifies `claim_type` is "One of the values in 2.3." A value not in that set does not conform to the field definition. Section 2.4 establishes that a request whose field values do not conform to their definitions cannot be interpreted and receives status 400. The field type is defined as an enumeration, not as an arbitrary string.

**Rejected alternative.** Allowing a non-vocabulary value through to V-5 would mean evaluating a notification built from a field value the contract does not define. Section 2.1 states that "The service rejects a body carrying a field not listed" because accepting undefined content would record data the caller did not validly send. The same principle applies to field values: accepting an undefined value would record a claim type the contract does not recognize.

**Contract amended.** Section 6.1, `MALFORMED_REQUEST` description: already states "a field value is not in the defined vocabulary." No further change required; the existing text supports this decision.

### Decision 3

**Payload.** EDGE-12 (estimated_amount "3499.999" with three decimal places)

**The ambiguity.** Section 2.2 specifies `estimated_amount` as "United States dollars, two decimal places." The contract did not specify what happens when a value carries more than two decimal places, such as "3499.999." Two readings were available: (1) reject as malformed (400) because it does not conform to the specified format, or (2) accept and truncate or round to two decimal places.

**Decision.** An `estimated_amount` with more than two decimal places is rejected with `MALFORMED_REQUEST` and status 400 before any rule is evaluated.

**Authority.** Section 2.2 defines the field format precisely as "two decimal places." A value with a different precision does not conform to the field definition. Section 2.4 establishes that a field carrying a value "of the wrong type" is refused with status 400, and format violations are type violations. More fundamentally, section 2.1 states that accepting a payload with ignored or transformed content "would record a notification built from data the caller did not send." Truncating 3499.999 to 3499.99 or rounding it to 3500.00 would record an amount the caller did not submit.

**Rejected alternative.** Accepting and truncating would silently modify the caller's data, violating the principle that the recorded notification must reflect what was sent. The caller's code submitted a value in the wrong format, and the correct response is to refuse it and require the caller to fix their code, not to guess at the intended value.

**Contract amended.** Section 6.1, `MALFORMED_REQUEST` description: already states "a field has the wrong type or format." No further change required; the existing text supports this decision.

## Reconciliation: Day 2 Model and Repository Implementation

**Date.** Day 2 implementation complete.

**What was implemented.** 

- `NotificationRequest` model that parses incoming payloads and validates structure (contract section 2.2). Rejects unknown fields, missing required fields, wrong types, and invalid field values (claim type vocabulary, decimal places, positive amounts).
- `Policy` model representing policy master data (fields required by rules in section 4).
- `RuleFailure` and `ClaimRecord` models to represent decision outcomes and recorded notifications.
- `NotificationRepository` that stores recorded notifications, generates unique claim references in the pattern `CLM-YYYY-NNNNNN`, and detects duplicates by matching on `policy_number`, `loss_date`, and `claim_type`.
- Unit tests covering field constraints, `fnol_invalid.json` / `fnol_edge.json` model vs rule split, and repository behaviors documented in the contract.

**What the models refuse and when.**

1. **MALFORMED_REQUEST (400)** — Rejected at model layer before any rule evaluation:
   - Unknown fields in the payload (contract 2.2, 2.4)
   - Missing required fields: `policy_number`, `loss_date`, `claim_type`, `estimated_amount`
   - Wrong type: `policy_number` not a string, `loss_date` not a date, `claim_type` not a string, `estimated_amount` not numeric
   - Invalid field values:
     - `policy_number`: empty string
     - `loss_date`: format not `YYYY-MM-DD`, or invalid date (e.g., month 13)
     - `claim_type`: not in vocabulary {collision, theft, glass, liability, weather}
     - `estimated_amount`: not greater than zero, or more than 2 decimal places

2. **Policy-dependent validation (422)** — Handled by rules, not models:
   - `POLICY_NOT_FOUND` (V-1): policy number does not exist (delegated to `policy_client`)
   - `LOSS_BEFORE_INCEPTION` (V-2): loss date before policy effective date
   - `LOSS_AFTER_EXPIRY` (V-3): loss date after policy expiry date
   - `AMOUNT_EXCEEDS_LIMIT` (V-4): estimated amount exceeds policy limit
   - `TYPE_NOT_COVERED` (V-5): claim type not permitted on policy product
   - `POLICY_CANCELLED` (V-7): loss date on or after cancellation date

3. **Duplicate detection (409)** — `DUPLICATE_NOTIFICATION` (V-6):
   - Handled by repository's `find_matching()` method, which only searches recorded notifications (WI-0151 AC-3: rejected submissions are not stored).

**Contract reconciliation.**

The contract was complete and unambiguous for model-layer validation. All field constraints in section 2.2 are now enforced:
- `policy_number`: not empty, case-sensitive, required
- `loss_date`: YYYY-MM-DD format, required
- `claim_type`: one of five defined values, required
- `estimated_amount`: greater than zero, two decimal places, required
- `description`: optional, absent and null treated equivalently
- Unknown fields forbidden

The split between 400 (malformed) and 422 (unacceptable) is implemented as specified in section 2.4: shape errors that the service cannot interpret are 400; content errors that violate rules are 422.

**How the section 6 check was performed.**

Model-layer failures raise Pydantic `ValidationError`. They are not HTTP yet; Day 4 maps them to one contract code. Every validator and type constraint on `NotificationRequest` was listed and looked up in section 6.1:

| What the model refuses | Section 6.1 code | Status |
| --- | --- | --- |
| Extra / unknown field (`extra: forbid`) | `MALFORMED_REQUEST` (“undefined field is present”) | 400 |
| Missing required field | `MALFORMED_REQUEST` (“required field is absent”) | 400 |
| Wrong type (`policy_number` not str, `loss_date` not a date, amount not numeric) | `MALFORMED_REQUEST` (“wrong type or format”) | 400 |
| `loss_date` not `YYYY-MM-DD` / not a real calendar date | `MALFORMED_REQUEST` (“wrong type or format”) | 400 |
| `claim_type` not in the 2.3 vocabulary (`Literal`) | `MALFORMED_REQUEST` (“value is not in the defined vocabulary”) | 400 |
| Empty `policy_number` | `MALFORMED_REQUEST` (field does not meet 2.2) | 400 |
| `estimated_amount` ≤ 0 or more than two decimal places | `MALFORMED_REQUEST` (“wrong type or format”) | 400 |

**What was found.** No gap. All of the above already sit under `MALFORMED_REQUEST` in section 6.1. No new code or status was added.

**What was not a model code.** `POLICY_NOT_FOUND`, term/limit/product/cancellation failures, and `DUPLICATE_NOTIFICATION` are rule or repository outcomes. They already have rows in section 6. The models do not emit them.

**Tests.** Parametrized unit tests for models (including every `fnol_invalid.json` and `fnol_edge.json` id, classified as malformed vs survives-to-rules) and repository (`record`, `allocate_claim_reference`, `find_matching`). Ruff and mypy clean.


## Reconciliation addendum: repository feedback

**What changed.** `record()` now accepts a `NotificationRequest`, not a `ClaimRecord`. A `ClaimRecord` exists only after a successful `record()`. The claim-reference year is `date.today().year` (the year of recording), not `loss_date.year`, matching contract section 3. Duplicate “two of three fields” coverage is three named parametrized cases. WI-0151 AC-3 is demonstrated by allocating a reference for INVALID-06 without recording it, then recording that same triple; `find_matching` is empty until the resubmission is stored.

**Contract.** Section 3 already stated that `YYYY` is the year of recording. No contract amendment. The previous implementation contradicted the contract; the code was corrected.