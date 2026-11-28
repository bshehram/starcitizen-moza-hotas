# `prompts/` — the prompts my Claude Code sessions run on

The prompts that organize how Claude works in this repo: a lead session that decides and
checks, and a crew of sub-agents that does the work.

- **[`SCBOT-README.md`](SCBOT-README.md)** is the guide: the roles, the limits on how full a
  context may get and what enforces each one, the work queue, how to start each kind of
  session, and how to install or remove the settings behind it. Start there.
- `SCBOT-ARCHITECT.md` and `SCBOT-WORKER.md` are the two role prompts, written for Claude.
- `agents/` and `settings/` hold the sources of the sub-agent definitions and the Claude Code
  settings. They do nothing here: the install step in the guide copies them into place.

None of this is needed to use the binding profile. Back to the [root README](../README.md).
