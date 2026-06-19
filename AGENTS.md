# AGENTS.md

## Purpose

This file defines how Codex must work in this repository. Treat these rules as repository-level engineering policy.

## Engineering priorities

Optimize in this order:

1. Runable, Correctness and reproducibility.
4. Maintainability and architectural consistency.
5. Performance, scalability, and latency.
6. Developer ergonomics.

When trade-offs exist, state the trade-off explicitly before making changes.

## Repository orientation

Before editing files, inspect the repository structure and identify:

- Application entry points.
- Core domain modules.
- Test directories.
- Build/lint/type-check commands.
- Existing conventions for logging, errors, configuration, dependency injection, and data models.

Prefer existing abstractions over introducing new patterns.

## Default task behavior

For non-trivial tasks:

1. Restate the goal in precise engineering terms.
2. Identify the files likely to change.
3. Identify invariants that must be preserved.
4. Propose a short implementation plan.
5. Implement the smallest safe diff.
6. Add or update tests when behavior changes.
7. Run the narrowest relevant validation first.
8. Run broader validation if the narrow validation passes.
9. Review the final diff for regressions.
10. Summarize changed files, validation commands, results, and residual risks.

For trivial tasks, make the minimal edit and still summarize the diff.

## Scope control

Do not modify unrelated files.
Do not reformat entire files unless formatting is the explicit task.
Do not rename public APIs, database columns, routes, or exported symbols unless explicitly requested.
Do not introduce framework-level changes for a localized bug.
Do not silently change behavior outside the task scope.

## Dependencies

Do not add production dependencies without explicit approval.
Before adding any dependency, explain:

- Why existing dependencies are insufficient.
- Runtime impact.
- Security and maintenance risk.
- License risk if relevant.
- Alternative implementation without the dependency.

Development-only dependencies require the same justification if they affect CI or developer workflow.

## Security and privacy rules

Never print, log, commit, or expose secrets, API keys, tokens, credentials, private keys, cookies, or personal data.
Never edit `.env`, credential files, deployment secrets, or cloud credentials unless explicitly asked.
Never weaken authentication, authorization, validation, sandboxing, rate limits, or audit logging to make tests pass.
Never bypass failing tests by deleting assertions or reducing coverage.

## Database and migration rules

Treat database migrations as high-risk.
Before changing schema, identify:

- Backward compatibility.
- Rollback strategy.
- Data migration safety.
- Locking and downtime risk.
- Idempotency.
- Impact on old application versions.

Do not modify production migration history unless explicitly requested.
Prefer additive migrations over destructive changes.

## Error handling and observability

Errors must be actionable and must not leak secrets.
Prefer typed/domain-specific errors where the codebase already uses them.
Add logging only when it improves diagnosis.
Do not create noisy logs on hot paths.
Maintain existing log format and correlation identifiers.

## Performance and scalability

For hot paths, review:

- Algorithmic complexity.
- N+1 database queries.
- I/O blocking.
- Memory growth.
- Cache correctness.
- Retry storms.
- Timeout behavior.

Do not optimize prematurely, but do not introduce obvious latency or scalability regressions.

## Testing policy

When behavior changes, add or update tests.
Prioritize:

- Regression tests for the reported bug.
- Boundary cases.
- Failure paths.
- Idempotency and retry behavior.
- Authorization/security cases.
- Serialization/deserialization compatibility.

Do not remove or weaken tests to make the suite pass.
If tests cannot be run, explain why and specify the exact command the human should run.

## Validation commands

Use the project’s actual commands. If unknown, discover them from README, package files, CI config, Makefile, pyproject, package.json, or similar files.

Common examples:

```bash
pytest
ruff check .
mypy .
npm test
npm run lint
npm run typecheck
pnpm test
pnpm lint
go test ./...
cargo test
```

Do not invent a command if the repository does not support it. State uncertainty.

## Final response format

Always end implementation tasks with:

```text
Changed files:
- <file>: <what changed>

Validation:
- <command>: <pass/fail/not run and why>

Human review focus:
- <specific files/logic to inspect>
```
What to do next:
- ...



## When to ask before editing

Ask before editing when:

- Requirements are materially ambiguous.
- Multiple architecture options have different long-term costs.
- The task requires adding dependencies.
- The task requires changing public API, database schema, authentication, authorization, billing, deployment, or secrets.
- The task could delete or rewrite significant code.

If ambiguity is minor and a safe assumption exists, state the assumption and proceed with the smallest reversible change.
