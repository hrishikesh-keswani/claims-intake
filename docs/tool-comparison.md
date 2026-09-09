# Tool comparison: Cursor (used only cursor for this lab)

Day 4 asked for one bounded piece to be done in Cursor rather than handed to an
external agent. The only tool used on this lab was Cursor. The bounded piece
was the README platform note: why `docker buildx build --platform linux/amd64`
exists, written so a new joiner does not already have to know the answer.
`routes.py`, the integration tests, and the Dockerfile were also produced in
Cursor, against the same contract.

## What Cursor made easy

Writing the platform paragraph with the contract and the current `uname` output
open in the editor. The constraint was voice, not structure: restating the
command would fail the criterion, and the explanation had to start from this
machine being `Linux aarch64` and end at why CI would reject an ARM image.
Cursor is a good place for that kind of sentence-level work. You can read the
paragraph as a new joiner would, cut the parts that only make sense if you
already know what `buildx` is, and keep the one claim that matters: the flag
chooses the architecture the image must run on, not the architecture of the
laptop that built it.

It also made the mechanical contract work fast. Once the plan named the
endpoint, the envelope, and the fixtures, Cursor produced `POST /notifications`,
the 400 override for `RequestValidationError`, the lookup-reason map, and a
parametrized integration test per rule V-1 through V-7 plus the three
dependency reasons. That is the kind of task where "implement against this
table" is a complete instruction. The tests are what make the speed safe.

## What Cursor made awkward

Anything that is a closed mapping from a table to code, if you do it by hand in
the editor. Contract section 6 is twelve rows of code-to-status. FastAPI's
default validation status is 422 and the contract's parse failure is 400.
`PolicyLookupFailed` has three reasons and three 5xx codes. Keeping the table,
the exception types, and the TestClient overrides in your head at once is
awkward. One missed row is a silent contract break, and you find it only when a
test names the code.

Work that cannot be finished from the repository alone is awkward too. The
Dockerfile is correct on disk: it copies `src/` and `data/` so
`StubPolicyClient` still resolves `policies.json`, and the documented build
line pins `linux/amd64`. Cursor will treat "write the Dockerfile" as done when
the file exists. Proving the image is a different task. It depends on a Docker
daemon on the machine. This environment did not have one at first, so the
image had to be built and started later, on a host that actually ran Docker.
