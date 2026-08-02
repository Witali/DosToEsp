# Project workflow

## Product language

- The application is English-only. Keep all user-facing UI, commands, prompts,
  status messages, errors, help text and product documentation in English.
- Developer conversations and external notes may use another language, but
  text shipped as part of the application must remain English.

## Git commits

- Commit every logically complete, meaningful change as a separate focused
  commit.
- Stage only files that belong to that change. Preserve unrelated user work
  and generated or temporary files.
- Use a concise commit message describing the completed change.

## Push cadence

- After creating a commit, count commits that have not reached the configured
  upstream with `git rev-list --count @{upstream}..HEAD`.
- Push the current branch when that count reaches three. A successful push
  starts the count again from zero.
- Do not push fewer than three new commits unless the user explicitly requests
  an earlier push.
- The commit that introduces this file is the first commit in its push cycle.
