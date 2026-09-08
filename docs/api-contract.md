# Claims Intake Service: API Contract

Version 0.4. Owned by the claims intake team. Consumed by the claims portal team.

This document is the authority on what the service accepts, what it returns, and under what conditions it refuses. Where the code and this document disagree, the document is correct and the code is a defect.

Sections 1 through 3 are fixed. Do not edit them.

## 1. Purpose and scope

The claims intake service accepts a first notice of loss from the claims portal, validates it against the policy master and a table of business rules, and either records a notification and issues a claim reference or refuses the submission with a specific reason.

**In scope.** Accepting a notification, validating it, and recording it. Issuing a claim reference. Reporting the reason a notification was refused.

**Out of scope.** Adjusting, reserving, payment, and any decision about coverage beyond the rules in section 4. The service decides whether a notification is well formed and admissible. It does not decide whether the claim will be paid.

**The policy master is a dependency, not part of this service.** The service reads policy records from it and does not write to it. A policy that cannot be read is a condition this contract specifies, and it is specified separately from a policy that does not exist, because the two require different action from the caller.

**Compatibility.** Adding a field to a response is a compatible change and callers must ignore fields they do not recognize. Adding a new error code is a compatible change and callers must fall through to default handling for a code they do not recognize. Changing the meaning of an existing code, removing a field, or changing a status code for an existing condition is not compatible and does not happen without a version increment agreed with the portal team.

## 2. Request

### 2.1 Endpoint

```
POST /notifications
Content-Type: application/json
```

### 2.2 Body

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `policy_number` | string | yes | Identifier exactly as held in the policy master. Not empty. Case-sensitive. |
| `loss_date` | string | yes | Calendar date, `YYYY-MM-DD`. |
| `claim_type` | string | yes | One of the values in 2.3. Not empty. |
| `estimated_amount` | decimal | yes | United States dollars, two decimal places. Greater than zero. |
| `description` | string | no | Free text. Absent and `null` are equivalent. |

The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

Which of these are admissible on a given notification depends on the product the policy is written on. The vocabulary is fixed by this contract. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, or a field was present that this contract does not define. The caller's code is wrong.

A request that was interpreted and whose content is not admissible is refused with status `422`. The caller's data is wrong, and a person needs to see the reason.

This split is stated here once and holds without exception everywhere else in this document.

## 3. Success response

A notification that passes every rule in section 4 is recorded and the service responds:

```
201 Created
Content-Type: application/json

{
  "claim_reference": "CLM-2026-000317",
  "status": "recorded"
}
```

**`claim_reference`** matches the pattern `CLM-YYYY-NNNNNN`, where `YYYY` is the calendar year in which the notification was recorded and `NNNNNN` is a zero padded sequence. A claim reference is unique across all recorded notifications and is never reissued. It is the value the claims handler quotes and the value every downstream system keys on.

**`status`** is `recorded` on every success response this contract defines. It exists because the portal displays it and because a future state that is not `recorded` is foreseeable. Callers must not treat it as constant.

A refused notification is never recorded and no claim reference is issued. There is no partial outcome: either a notification exists with a reference, or nothing was written.

## 4. Validation

### 4.1 Evaluation order

Rules are evaluated in the sequence they appear in section 4.2, from top
to bottom, not by identifier number. Evaluation stops at the first
failure and that rule's code is returned.

V-1 short circuits: if it fails, no rule that reads a policy field is
evaluated.

Where multiple rules are violated, only the first failure in the
sequence is reported. The caller receives one error code and one status.
A notification that fails V-2 and V-4 returns `LOSS_BEFORE_INCEPTION`
because V-2 appears first in the table.

### 4.2 Rule table

| ID  | Condition                                                                        | Code                    | Status |
| --- | -------------------------------------------------------------------------------- | ----------------------- | ------ |
| V-1 | `policy_number` exists in the policy master                                      | `POLICY_NOT_FOUND`      | 422    |
| V-2 | `loss_date` >= policy `effective_date`                                           | `LOSS_BEFORE_INCEPTION` | 422    |
| V-7 | policy `cancellation_date` is null OR `loss_date` < policy `cancellation_date`   | `POLICY_CANCELLED`      | 422    |
| V-3 | `loss_date` <= policy `expiry_date`                                              | `LOSS_AFTER_EXPIRY`     | 422    |
| V-4 | `estimated_amount` <= policy `limit`                                             | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| V-5 | `claim_type` permitted on the policy's product                                   | `TYPE_NOT_COVERED`      | 422    |
| V-6 | No recorded notification exists with matching `policy_number`, `loss_date`, and `claim_type` | `DUPLICATE_NOTIFICATION` | 409    |

Boundaries are inclusive as written. A loss on the inception date is
covered (WI-0142, AC-3). An amount equal to the limit is within cover.
A loss on the cancellation date is not covered: cancellation takes
effect at the start of that date (WI-0158, AC-2).

## 5. Error envelope

Every failure response carries three fields: `code`, `message`, and `detail`.

### 5.1 Envelope structure

```json
{
  "code": "ERROR_CODE_NAME",
  "message": "Human readable description",
  "detail": {}
}
```

**`code`** is a stable contract. It identifies the condition that caused
the failure and does not change across versions unless the meaning of the
condition itself changes. Callers must switch on this value to decide
what to do next. Adding a new code is a compatible change; removing or
changing the meaning of an existing code is not.

**`message`** is not stable. It is written for a person reading the error
and may be rephrased, expanded, or corrected without a version increment.
Callers must not parse it, match substrings within it, or depend on its
content in any way. Display it or log it, but do not interpret it.

**`detail`** carries additional structured context specific to the code.
Its shape is defined per code, not globally. A caller handling
`DUPLICATE_NOTIFICATION` may rely on `detail.existing_claim_reference`
being present, but a caller handling `POLICY_NOT_FOUND` must not assume
that key exists. Where a code provides no additional context, `detail`
is an empty object, never null or absent.

Callers must ignore keys in `detail` they do not recognize. Adding a key
is a compatible change. Removing a documented key or changing the type of
a documented value is not.

### 5.2 Example: rule failure with detail

A duplicate notification returns structured detail identifying the
existing record.

```
409 Conflict
Content-Type: application/json

{
  "code": "DUPLICATE_NOTIFICATION",
  "message": "A notification for this policy, loss date, and claim type has already been recorded.",
  "detail": {
    "existing_claim_reference": "CLM-2026-000215"
  }
}
```

The caller uses `existing_claim_reference` to direct the handler to the
recorded claim rather than allowing a retry.

### 5.3 Example: uninterpretable request

A request whose body cannot be parsed as valid JSON, or whose structure
does not conform to section 2, is refused before any rule is evaluated.

```
400 Bad Request
Content-Type: application/json

{
  "code": "MALFORMED_REQUEST",
  "message": "Required field 'estimated_amount' is absent.",
  "detail": {
    "field": "estimated_amount",
    "reason": "required_field_missing"
  }
}
```

The service could not interpret what the caller sent. The caller's code
is wrong. `detail.field` and `detail.reason` are provided where the
service can identify the specific problem, but are absent where the body
is not valid JSON or is so malformed that no field can be identified.
Callers must not assume these keys are always present for
`MALFORMED_REQUEST`.

### 5.4 Example: dependency failure

Where the policy master cannot be reached, times out, or returns a
response the service cannot parse, the notification cannot be validated.
This is not the caller's fault.

```
503 Service Unavailable
Content-Type: application/json

{
  "code": "POLICY_MASTER_UNAVAILABLE",
  "message": "The policy master did not respond within the allowed time.",
  "detail": {}
}
```

The caller should retry. The detail object is empty because there is no
additional context the service can provide that would help the caller
decide what to do differently.

## 6. Status code mapping

Every error code maps to exactly one HTTP status.

### 6.1 Client errors (4xx)

These failures are the caller's responsibility. Retrying without changing
the request will produce the same result.

| Code                    | Status | Meaning |
| ----------------------- | ------ | ------- |
| `MALFORMED_REQUEST`     | 400    | The request body is not valid JSON, a required field is absent, a field has the wrong type or format, an undefined field is present, or a field value is not in the defined vocabulary. |
| `DUPLICATE_NOTIFICATION` | 409   | A notification with this `policy_number`, `loss_date`, and `claim_type` has already been recorded. |
| `POLICY_NOT_FOUND`      | 422    | The `policy_number` does not exist in the policy master. |
| `LOSS_BEFORE_INCEPTION` | 422    | The `loss_date` is before the policy `effective_date`. |
| `POLICY_CANCELLED`      | 422    | The policy has a `cancellation_date` and the `loss_date` falls on or after it. |
| `LOSS_AFTER_EXPIRY`     | 422    | The `loss_date` is after the policy `expiry_date`. |
| `AMOUNT_EXCEEDS_LIMIT`  | 422    | The `estimated_amount` exceeds the policy `limit`. |
| `TYPE_NOT_COVERED`      | 422    | The `claim_type` is not permitted on the policy's product. |

**422 Unprocessable Content** means the request was well formed but the
content is not admissible. The notification violates a business rule or
references a policy that does not exist.

**409 Conflict** means the request conflicts with a resource that already
exists. The notification has already been recorded and retrying would
create a duplicate.

**400 Bad Request** means the service could not interpret the request.
The caller's code is wrong.

### 6.2 Server errors (5xx)

These failures are not the caller's responsibility. The request may have
been valid, but the service could not process it because a dependency
failed or the service itself encountered an internal error. Retrying may
succeed if the condition is transient.

| Code                           | Status | Meaning |
| ------------------------------ | ------ | ------- |
| `POLICY_MASTER_UNAVAILABLE`    | 503    | The policy master could not be reached or did not respond. |
| `POLICY_MASTER_TIMEOUT`        | 504    | The policy master did not respond within the allowed time. |
| `POLICY_MASTER_INVALID_RESPONSE` | 502  | The policy master returned a response the service cannot parse. |
| `INTERNAL_ERROR`               | 500    | The service encountered an unexpected internal failure. |

A policy master that responds with no matching policy returns
`POLICY_NOT_FOUND` (422), not a 5xx code. The dependency answered
correctly; the policy does not exist.
