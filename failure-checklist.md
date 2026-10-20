# Failure checklist

These are defects that actually got past the author and reached a reviewer, CI, the user, or production. They come from real sessions and PRs; the evidence and instances are in `evidence.md`, mined 2026-10-19.
- The **architect** maps applicable IDs to acceptance criteria in the plan's Risks section.
- **QA** sweeps every ID against the diff and records Applies? / Result / Evidence.
- To add a row, use the next free ID, and only add it when a real defect justifies it (QA's lesson candidates feed this).

## Deploy & data

**FC-01 Migration not applied where the code runs.**
- Applies when: the diff adds a migration, and the target deploys from the default branch without migrating (Vercel/Neon, many PaaS setups).
- Check:
  - The plan carries a human step: "apply to production before merge".
  - QA confirms the step is listed. QA never runs it.
  - Shopware: `bin/console database:migrate --all <Plugin>` must be in the verification commands.

**FC-02 Build/dependency manifest changes what ships.**
- Applies when: the diff touches `pyproject.toml`, `requirements*.txt`, `package.json` engines, `composer.json`, `vercel.json`, `.vercelignore`, a Dockerfile, or any bundler config.
- Check: name the deploy's dependency source of truth, and require a preview/build route check as an AC.

**FC-03 Destructive DDL without a guard.**
- Check: `grep -nE 'DROP|TRUNCATE|ALTER .* TYPE|CASCADE'` in new migrations. Each hit needs a row-count guard (`DO $$ … RAISE`) and a human read-only count first.

**FC-04 Boundary input returns 5xx instead of 4xx.** Covers:
- explicit `null` sent to a NOT NULL column via PATCH;
- `= NULL` compares in retry re-reads (use `IS NOT DISTINCT FROM`);
- derived decimals beyond the numeric scale or CHECK;
- unescaped `%`/`_` in LIKE;
- NUL bytes;
- payload size near the platform cap.

Check: post each relevant one at every new or changed endpoint. Run the repo's schema fuzzer (e.g. schemathesis) if it has one.

**FC-05 Client limits ≠ server/DB limits.**
- Check: for each new CHECK, Field validator or column length, find the matching client `maxLength`/validation. The values must be identical.

**FC-06 New HTTP verb or route not allowed by CORS or the router.**
- Check: grep the CORS `allow_methods` and route registration. Verify against the running web client, not only unit tests.

## Async state & idempotency

**FC-07 Optimistic update without a stale guard.**
- Check: every mutation that changes local state bumps the request/stale counter, restores state on failure, and re-issues any refresh it cancelled.
- Test: delayed refresh plus an action inside that window.

**FC-08 Retry id lost, so a duplicate write is possible.**
- Check: trace the client-generated id from the first POST through retry, edit, reopen and Retake. Saved-state flags must not be reset early.
- Test: "server committed, response lost, then retry" gives exactly one row.

**FC-09 Overlapping async side effects.**
- Applies when: there is a cancel-then-schedule or delete-then-create flow.
- Check: it is serialized (a queue or single-flight), with a test of two overlapping calls.

**FC-10 Cancel/close/back during async work loses input or leaves a blank state.**
- Test: typed input plus a late response, for every cancel path. Use one shared "untouched draft" predicate.

**FC-11 Derived value stale after a unit or mode toggle.**
- Test: "clear field, then toggle" and "change source, then toggle". Assert the saved payload.

**FC-12 One error state shared by load and action failures, or an error that survives close.**
- Check: separate load and action errors, and both are cleared on close.

**FC-13 External state never re-read.** Examples: OS permission, auth, feature flag.
- Check: re-check on app resume or focus.

## Spec conformance

**FC-14 Copy, numbers or limits not verbatim to the request or plan.**
- Check: `grep -F` every quoted string and number from the plan or request in the diff.

**FC-15 A shared function changed, breaking another caller.**
- Check: list the callers of every changed shared handler or service, and run those flows' tests or e2e in the same task.
- Shopware: check decorators and subscribers of the touched service.

**FC-16 Code that can't run as written.** Examples: temporal dead zone or declaration order, a platform API limit (e.g. Android Alert max 3 buttons), a value import breaking a node-run test.
- Check: run the type checker, and check platform limits for each new native API used.

**FC-17 Reused UI or logic shows wrong numbers for a new data shape.**
- Check: fixture-based assertion of the displayed totals, not just "renders".

## UI & accessibility

**FC-18 Nested interactive elements, or a hidden affordance.**
- Check: no pressable or button inside another, and every action has a visible control.
- At the web preview: `page.locator('button button, [role=button] [role=button]')` count is 0.

**FC-19 Colour outside tokens, or contrast below 4.5:1 (text) or 3:1 (controls).**
- Check: grep hex literals outside the theme file, and compute the ratios of new pairs.

**FC-20 Breaks at the smallest supported width.**
- Check: run at 320×568 (mobile) with long-string fixtures, and confirm there is no horizontal scroll.

**FC-21 States missing.**
- Check: loading, empty, error and disabled, plus keyboard/focus and accessibility labels for each new control.

## Environment & verification

**FC-22 A verification command can't run here.** Causes: dev tools not in the image, a service not started, migrations baked into an image, or a permission denial.
- The architect dry-runs every verification command once.
- If a command is denied, the engineer and QA report BLOCKED. They never commit untested work and never route around the denial.

**FC-23 Verification hit a real database.** Causes: wrong env var, default connection.
- Check: before any write-capable run, print the DB host and prove isolation.
- Shopware: confirm the container and `APP_ENV` before running `bin/console`.

**FC-24 Behaviour only verifiable on a device or in production.**
- Check: list it verbatim as "not verified" in the hand-off. Never mark it PASS.

## Tests

**FC-25 Test never seen failing.**
- Check: a RED run exists, e.g. `git stash` the implementation and run the new test.

**FC-26 Test doesn't exercise the path it names.**
- Check: race tests wait for the request to be in flight; each optimistic action has a forced-failure case; test files are committed, not left in /tmp.
- Check: each new regression test is proven by one mutation (remove the guard it protects, on a scratch copy or temporary image) and the failing assertion is quoted. A guard the base already has is worded as a mutation check, not "fails at base". A stale-response test holds the OLD response bytes, not just the request.

**FC-27 Flaky time or locale assumption.**
- Check: freeze the clock in e2e, and avoid asserting wall-clock-dependent text.

**FC-28 Mocks hiding constraint logic.**
- Check: constraint and transaction behaviour is tested against a real, freshly migrated database.

**FC-33 Serverless global resource never recovers.**
- Check: a module-global pool or client is installed only after it opens successfully, with warm-up and checkout timeouts of a few seconds. A test points it at an unreachable host, asserts a 503 and that nothing is installed, then restores the host and asserts a 200.

## Shopware specifics (from the human's CLAUDE.md standards)

**FC-29 DAL bypassed.**
- Check: no raw SQL in business logic outside migrations or justified hot paths. A custom entity has Definition, Entity, Collection and a service registration.

**FC-30 Post-change commands missing.** Check that the plan includes these where they apply:
- `cache:clear`, `plugin:refresh`, `database:migrate --all <Plugin>` and `dal:refresh:index`;
- `theme:compile` for storefront work, and the admin build for admin work.

**FC-31 Shipped migration edited.**
- Check: `git diff` shows no modification to a migration that already exists on the default branch.

**FC-32 Admin API endpoint without ACL.**
- Check: an `_acl` route default is present, and the required privileges are documented.
