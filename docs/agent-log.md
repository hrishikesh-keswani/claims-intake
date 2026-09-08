# Agent decision log

Engineering judgments made while building the Day 3 rule engine. Each entry names a change, the decision, and a reason that traces to the contract or an acceptance criterion.

## Accepted: `evaluate_notification(notification, policy)` instead of the starter signature

**What was produced.** The starter `evaluate_notification` took a `PolicyClient` and a `NotificationRepository` and returned `ValidationOutcome`. Day 3's interface contract (C3) specifies `evaluate_notification(notification, policy) -> RuleFailure | None`.

**Decision.** Accept C3. `evaluate_notification` loops `POLICY_RULES` (V-2, V-7, V-3, V-4, V-5) and returns the first `RuleFailure`, or `None`. It does not call the policy master or the repository.

**Reason.** The acceptance criterion is that `evaluate_notification` performs no I/O and takes only a notification and a policy. Contract section 4.1 says V-1 short-circuits: if the policy does not exist, no rule that reads a policy field is evaluated. That lookup is `PolicyClient.get_policy`, which is I/O. Keeping it out of `evaluate_notification` is what makes WI-0142 AC-4 hold: a missing policy is `POLICY_NOT_FOUND`, not `LOSS_BEFORE_INCEPTION`. The starter signature would have forced V-1 and V-6 into the same function as the pure policy comparisons, so a reader could not test the policy rules without a client and a store.

## Rejected: putting V-6 inside `POLICY_RULES`

**What was produced.** A draft that added `evaluate_not_duplicate` to `POLICY_RULES` so that contract 4.1 order lived in one table. That required `POLICY_RULES` entries to accept a repository, or `evaluate_notification` to close over one.

**Decision.** Reject. `POLICY_RULES` contains only `(notification, policy) -> ValidationOutcome` functions. V-6 runs in `submit_notification` after `evaluate_notification` returns `None`, via `repository.find_matching`. The order in 4.1 still holds: V-1 (client), then V-2 through V-5 (`POLICY_RULES`), then V-6 (repository), then `record`.

**Reason.** WI-0151 AC-3: a rejected notification is not a duplicate because nothing was recorded. Duplicate detection is a query against recorded rows, which is why Day 2 put `find_matching` on the repository. If V-6 lived in `POLICY_RULES`, `evaluate_notification` would have to take a repository, violating the no-I/O criterion, and a failed rule path could be confused with a stored row. Contract section 4.2 V-6 is "no recorded notification exists with matching `policy_number`, `loss_date`, and `claim_type`" — that is a repository fact, not a policy-field comparison.

## Gate observation (step 8)

Pushed a commit that made pytest fail (`tests/unit/test_gate_probe.py`, `assert False`). The `checks` workflow failed: "checks / checks (pull_request) Failing after 16s." There were no merge conflicts.
The Merge pull request button stayed enabled. A failing check did not block the merge. Required status checks are not configured on `main`. That is a repository-settings finding, not a defect in `checks.yaml`.
