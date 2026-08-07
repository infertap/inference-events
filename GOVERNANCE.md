# Governance

Four rules, each load-bearing.

**1. A requirement enters with its fixture.** A normative requirement enters a specification
together with the conformance fixture (or, for producer-side behavior a fixture cannot
express, the named test) that would fail an implementation violating it. A requirement
without one enters the spec's "requirements with no covering fixture" table instead, and a
non-empty table gates any release claiming conformance. The table is empty today; keeping it
empty is the point.

**2. Fixtures change only here, with the text that motivates them.** A corpus change lands in
the same commit as the spec change it expresses, and `CONTRACT_HASH` is re-blessed in that
commit (`python3 tools/contract-hash.py --write`). Consumers vendor this repository at a
pinned commit and verify the hash offline. An implementation that fails conformance is fixed
by changing the implementation, or by landing a change here and bumping the pin. Editing
vendored fixtures is not a fix.

**3. Versioning follows the spec's own law.** Additive changes (new record kinds, new
optional fields) increment the minor version. Anything else, including any change in the
meaning of an existing field, increments the major version, and a meaning change is never
made without one. Producer version skew is steady state; readers follow the mixed-fleet law.

**4. Generators derive from the text, never from an implementation.** Every fixture's
expectation is computed by the generators in `tools/` from the specification's normative
semantics. A fixture that mirrors an implementation's bug is itself a defect, whatever the
implementation.

## Proposing a change

Open a pull request containing the spec text, the covering fixture, and the re-blessed hash,
in one commit. A proposal that cannot state its fixture is not ready; rule 1 says where it
waits.
