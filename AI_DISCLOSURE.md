# AI use and review notes

## Prompt history

The prompts that shaped this change, in order, were:

1. `why it is showing site cant be reached`
2. `MAKE IT RUN` — followed by requirements to submit executable software and
   clear install/configure/run/verification steps; use a public GitHub
   repository with meaningful commits; disclose prompt history and AI use;
   explain assumptions, design decisions, trade-offs, tests, limitations, and
   evidence that the solution works; and be ready to walk through it.

## Where AI was used

An AI coding assistant inspected the Python project and its generated result
schema, then drafted the local HTTP server, browser dashboard, tests, and
documentation. AI accelerated the setup by identifying that the existing VS
Code launch target opened `localhost:8080` without starting any server, and by
implementing a dependency-free route from the existing result exports to a
usable dashboard. The implementation relied substantially on AI for the first
draft of the server, dashboard UI, and endpoint tests. It did not ask AI to
change or reinterpret the experiment's statistical calculations.

## Human review and verification

The dashboard deliberately uses the existing generated experiment results; it
does not claim to run a new statistical analysis. Its primary result is selected
from each experiment's predeclared metric plan, and it does not load or expose
the evaluation-only ground-truth export. The app binds to loopback by default
and uses only the Python standard library.

Automated checks run during implementation: all 8 unit tests passed, the live
health/data endpoints returned successfully, and the dashboard was opened in a
browser and its search/selection interaction was exercised. The project owner
should review the code, output, assumptions, and limitations before submitting
it. No independent human review is claimed here.

## Limitations

- Data is synthetic, fixed-seed demonstration data, not evidence about real
  users or a production experiment.
- This local dashboard is read-only and has no authentication; do not expose it
  on a public network.
- Creating/publishing a public GitHub repository and claiming personal review
  require actions by the repository owner.
