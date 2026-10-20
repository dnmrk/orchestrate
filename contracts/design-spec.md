# Contract: the design spec

The designer writes it to `.orchestrate/<slug>/design-spec.md` after the architect's first draft, and only when the plan's **UI** call-out isn't `none`. The architect then folds it into the plan: every spec item becomes an acceptance criterion on the task that builds that screen. The human approves the plan and the spec together.

Every item must be checkable by QA from the diff, a test, or a screenshot. If it can't be checked, it doesn't belong here. Every section is required; write `none` and say why in one clause if one doesn't apply.

```markdown
# <Feature> — design spec

**Plan:** tasks/todo.md   **Mode:** Operate | Read | Persuade | Experience (impeccable's surface mode)
**Design authority:** <DESIGN.md / PRODUCT.md / existing component library actually read, with paths; or "none found">

## Brief
3–5 bullets from impeccable `shape`: job and audience, primary task, success, what stays untouched, anti-goals.

## Screens
### S1: <screen or component>  — built in Task <N>
- **Mockup:** `.orchestrate/<slug>/mockups/S1.html`. One self-contained static HTML file (inline CSS, no build). It shows the default state, plus the empty, error and loading states side by side, at desktop width and at the smallest supported width. It uses the verbatim copy and the project's real token values. It's a picture for the human's approval, not the build's source of truth: the spec items are.
- **Flow:** entry point → steps → exit, one line each.
- **Layout & hierarchy:** what the user sees first, second, third; intent, not CSS.
- **Components:** each element → the existing component or token it uses, with the precedent file. No new tokens or colours unless named here as new.
- **Copy (verbatim):** every label, button, empty/error message, in quotes. (FC-14)
- **States:** loading, empty, error (load vs action, separately), success, disabled, partial/overflow, cancelled mid-async. One line each on what renders. (FC-10, FC-12, FC-21)
- **Responsive:** behaviour at the smallest supported width (320 px for web unless the project says otherwise) and at each breakpoint that changes layout. (FC-20)
- **Accessibility:** focus order, role and accessible name per control, no nested interactives, contrast via tokens. (FC-18, FC-19)
- **Spec items:** the checkable list the architect turns into ACs.
  - `D-1.1` <observable behaviour> — **Check:** <test / grep / screenshot at width / axe>
  - `D-1.2` …

## Plan gaps
Screens, states or copy the request needs but no task builds. The architect resolves each one.

## Assumptions
What the designer decided without a human answer. Each one starts with "Designer's call: …".

## Open questions for the human
Only questions whose answer changes what gets built. Recommended answer first.
```
