# `prompts/` — working notes for Claude

The prompts and settings sources behind the SCBOT crew: one lead session, up to six sub-agents,
and a line on every context. The user's own guide is [`SCBOT-README.md`](SCBOT-README.md); it
has the design, the table of what enforces each limit, and the install steps. This file is for
whoever edits the folder.

## What is here

| File | Read by | Notes |
| --- | --- | --- |
| [`SCBOT-ARCHITECT.md`](SCBOT-ARCHITECT.md), [`SCBOT-WORKER.md`](SCBOT-WORKER.md) | Claude: a crew member of that role, or a lead the user starts with `@prompts/<file>` | Claude docs, like [`../SCBOT.md`](../SCBOT.md): they may link to `CLAUDE.md` files and to each other. Written in the user's voice. |
| [`SCBOT-README.md`](SCBOT-README.md), [`README.md`](README.md) | The user | Human docs: they follow the README rule and link only to README files. They name the Claude docs without linking to them. |
| [`agents/scbot-architect.md`](agents/scbot-architect.md), [`agents/scbot-worker.md`](agents/scbot-worker.md) | Claude Code, once installed | Sub-agent definitions. Sources only: the installed copies are in `.claude/agents/`. |
| `settings/scbot.project-settings.json`, `settings/scbot.user-settings.json` | Claude Code, once merged | Settings fragments. The `_about` key is left out at install. |

The script is [`../tools/scbot.py`](../tools/scbot.py): the guard that the hooks run, the work
queue, and `install` / `uninstall` / `check` / `status` / `close`. Its tests are
`../tools/test_scbot.py`. Its state, the queue, notes and saved reports are under
`.claude/scbot/` in the repo root, git-ignored. Research notes from the design session are in
`.claude/scbot/research/`.

## What you need to know

- **Nothing here is live.** Claude Code reads `.claude/settings.json`, `~/.claude/settings.json`
  and `.claude/agents/`. `python tools/scbot.py install` copies and merges these sources into
  place, and the hooks then call the installed copy of the script at
  `.claude/scbot/bin/scbot.py`, so an edit to `tools/scbot.py` cannot break running sessions.
  After editing the script or a definition, run the tests, then `install --scope project`
  again. `python tools/scbot.py check` fails until the copies match.
- **Installing changes Claude Code settings,** which needs the user's OK, and a changed hook
  reaches running sessions within seconds. Install only at a quiet moment.
- **The definitions' bodies are short on purpose.** A sub-agent's system prompt is the
  definition's body, and it tells the agent to read its role prompt first. That keeps one
  source for each role, used the same way by a crew member and by a stand-alone lead. Put role
  guidance in the role prompt, not in the body. The body repeats only the rules that must hold
  before the file has been read.
- **Model, effort and the missing `Agent` tool are set in the frontmatter.** Use full model
  IDs: an alias such as `opus` can resolve to the parent's version of that family. Do not
  suggest `claude --agent scbot-worker` for a stand-alone lead: it replaces the whole system
  prompt and, with `Agent` disallowed, such a session cannot run a crew.
- **The numbers appear in several places and have to change together:** the lead's lines (70,
  90, 96), the crew's three steps (60 plan the rest to fit, 75 wrap up, 80 only the handoff
  note and the report), a fork refused from 40, six running at once, and 6,000 characters for a
  crew member's report. They are defaults in `tools/scbot.py`, and they are stated in both role
  prompts, both definition bodies, `../SCBOT.md` (*Running a crew*, *Context budget*) and
  `SCBOT-README.md`. The crew's three steps are worded the same in all five prompt files: keep
  them so. The settings fragment carries the six a second time, as
  `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`.
- **A few preferences are restated in the role prompts** because a crew member acts on them:
  the complete result, whose decision a layout is, nothing personal in a tracked file, source
  and license for community code, and the profile-copy rule. Their home is `../SCBOT.md`,
  *How I work*. When one changes there, change it in both role prompts in the same commit.
- **Say what the guard does as "when installed".** Until the user has run the install, every
  limit is an instruction. `../SCBOT.md` and both role prompts each have an *Until the guard
  is installed* part, and the guide has *Before the install*: keep the four in step, and
  keep every command they name true of the script.
- **Who reviews:** the Architect by default, a Worker for a pass that is mostly running
  things. It is stated in `../SCBOT.md` (*Running a crew*), both role prompts, both
  definitions' descriptions and the guide. Until 2026-11-28 Workers ran every review here.
- **A crew member never commits, pushes or stages; a stand-alone lead commits and pushes.**
  For a crew member the role prompt wins over the lead-only habits in `../SCBOT.md`.
- **Dated state lives in two places:** the guide's *What is tested, and what is only
  documented*, and the list below. Whoever runs the first install updates both.
- **The guard fails open and never ends an agent.** It only refuses a new tool call, with the
  reason. Keep both properties: the user's rule is that a sub-agent is never halted in the
  middle of its work, and a guard that failed closed would freeze every session at once.
- **The guard says nothing below a line.** Anthropic's guide for Fable 5.2 says a token budget
  shown to the model changes how much it spends, so there is no running meter.
- **The role prompts hold standing guidance only,** like `SCBOT.md`: no current state, and a
  reason with every rule. When the user states a new standing preference, it goes in `SCBOT.md`
  and memory first, and into a role prompt only if a crew member has to act on it.
- **These files are public.** Nothing personal: no name, handle, e-mail, PC name, account
  detail or path under the user's profile. `~/.claude/` is fine as a generic path.

## What Claude Code does that this design leans on

Read in the official documentation on 2026-11-28 (`https://code.claude.com/docs/en/`, the page
named in each line). Nothing in this list has been seen working in a live session yet, because
nothing is installed: `SCBOT-README.md` has the checks for the first install.

- `autoCompactEnabled: false` and `idleCompaction: false` in any settings file, and
  `DISABLE_AUTO_COMPACT=1` (`settings-reference`, `env-vars`). Whether they cover sub-agents is
  not documented. A `PreCompact` hook can block a compaction (`hooks`).
- `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (default 20) and
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` (`sub-agents`). Resuming a finished sub-agent takes
  a slot without the limit being checked, which is why the guard checks it too.
- Every sub-agent loses `AskUserQuestion`, and a background sub-agent keeps `SendMessage`
  (`sub-agents`, *Available tools*). So a sub-agent's question travels through its lead.
- Hooks get `session_id`, `transcript_path`, and inside a sub-agent `agent_id` and
  `agent_type`, but no context figure (`hooks`). The status line does get one, but the VS Code
  panel has no status line. The guard reads the transcript instead:
  `<project>/<session>.jsonl`, and `<project>/<session>/subagents/agent-<id>.jsonl` for a
  sub-agent. That format is internal. Seen on this PC with Claude Code 2.1.332: the newest
  `assistant` entry has `message.usage` and `message.model`.
- Fable models and Opus 4.7 and later have a 1M window (`model-config`). The window is not in
  the transcript, so the script has a table (`window_for`). Update it for a new model.
- `SubagentStart` can add context to a sub-agent and `SessionStart` to a session. `PreToolUse`
  can deny with a reason. `SubagentStop` and a `PreToolUse` on `SubagentHandback` see the
  final report (`hooks`).
- `EndConversation` is not offered in the VS Code panel and is not for this (`tools-reference`),
  so a closed session is one whose prompts the guard refuses.
- A fork inherits its parent's whole conversation (`sub-agents`), so the guard refuses one once
  the lead is 40 percent full.
- Sessions on one PC can list and message each other (`cross-session-messaging`). A message
  from a peer is never the user's approval.
