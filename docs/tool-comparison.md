# Tool comparison: Cursor vs the coding agent

Day 4 asked for one bounded piece to be done in Cursor rather than handed to the
agent. That piece was the README platform note: why `docker buildx build
--platform linux/amd64` exists, written so a new joiner does not already have to
know the answer. The agent wrote `routes.py`, the integration tests, and the
Dockerfile against the same contract.

## What Cursor made easy

Writing the platform paragraph with the contract and the current `uname` output
open in the editor. The constraint was voice, not structure: restating the
command would fail the criterion, and the explanation had to start from this
machine being `Linux aarch64` and end at why CI would reject an ARM image. Cursor
is a good place for that kind of sentence-level work. You can read the paragraph
as a new joiner would, cut the parts that only make sense if you already know
what `buildx` is, and keep the one claim that matters: the flag chooses the
architecture the image must run on, not the architecture of the laptop that
built it.

## What Cursor made awkward

Anything that is a closed mapping from a table to code. Contract section 6 is
twelve rows of code-to-status. FastAPI's default validation status is 422 and
the contract's parse failure is 400. `PolicyLookupFailed` has three reasons and
three 5xx codes. Doing that by hand in the editor means keeping the table, the
exception types, and the TestClient overrides in your head at once. Cursor does
not stop you, but it does not hold the mapping either. One missed row is a
silent contract break, and you find it only when a test names the code.

## What the agent made easy

The mechanical contract work. Once the plan named the endpoint, the envelope,
and the fixtures, the agent produced `POST /notifications`, the 400 override for
`RequestValidationError`, the lookup-reason map, and a parametrized integration
test per rule V-1 through V-7 plus the three dependency reasons. That is the
kind of task where "implement against this table" is a complete instruction.
The agent is faster than typing it, and the tests are what make the speed safe.

## What the agent made awkward

Work that cannot be finished from the repository alone. The Dockerfile is
correct on disk: it copies `src/` and `data/` so `StubPolicyClient` still
resolves `policies.json`, and the documented build line pins `linux/amd64`. This
environment has no Docker daemon, so the agent could not run
`docker buildx build --platform linux/amd64` or start the image. It smoke-tested
the process with uvicorn instead. An agent will treat "write the Dockerfile" as
done when the file exists. Proving the image is a different task, and it
depends on a daemon the agent cannot invent.

## Preference

Use Cursor for explanatory writing that is graded on whether a reader who does
not already know the answer can follow it — README run instructions, a platform
note, a review comment that has to cite a contract section rather than a
preference. Use the agent for translating a finished contract table into
handlers and HTTP tests, then read the diff against the table before you trust
it.
