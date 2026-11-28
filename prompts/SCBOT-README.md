# SCBOT crew: how the setup works

This is the guide to how my Claude Code sessions in this repo organize their work: one lead
session that decides and checks, a crew of sub-agents that does the work, and limits on how
full any of their contexts may get. It covers the roles, each limit and what enforces it, the
work queue, how to start each kind of session, and how to install, test and remove the parts
that live in Claude Code's settings.

Nothing described here is active until the install steps below have been run. The files in
this folder are sources. Claude Code reads settings and sub-agent definitions only from
`.claude/` folders, and that folder is git-ignored in this repo. *Before the install* says
what holds until then.

## The idea

A long session fills its context, and when Claude Code's automatic compaction then summarizes
it, details get lost. So compaction is switched off, and the work is arranged so that no
context needs it:

- **The lead** is the session I start. It talks to me, decides, writes briefs, checks what
  comes back and commits. It does as little of the reading and building as it can.
- **The crew** is up to six sub-agents running at once, each in a fresh context of its own.
  A sub-agent gets a written brief, does the work, leaves its detail in files, and hands back a
  short report.
- **Every context has a line.** A sub-agent hands over at 80 percent of its window. A lead
  stops taking new work at 90 percent, waits for its crew to finish, and closes itself. A new
  session picks up from the repo, the notes and the queue.

## The roles

| Role | Model | What it does | Its prompt |
| --- | --- | --- | --- |
| Orchestrator | Whatever the session is set to | The usual lead: any request, my gameplay and repo routines, and running a crew | `SCBOT.md` in the repo root |
| Architect | Claude Fable 5.2, xhigh effort | Deep research, reviews of plans, designs and builds, architecture, application design, UI and visual design. Writes plans, designs, mockups and review reports. Never the implementation | `SCBOT-ARCHITECT.md` in this folder |
| Worker | Claude Opus 5.5, xhigh effort | The workhorse: builds from a plan, fixes, tests, checks, reads logs and data, does mechanical edits, and takes review passes that are mostly running things | `SCBOT-WORKER.md` in this folder |

Each role prompt covers two cases: the role as a crew member of some lead, and the role as a
lead of its own.

**Who reviews is a change from before.** Until 2026-11-28 every review in this project was run
by a Worker (Opus 5.5). The prompts now give reviews to the Architect by default, because my
description of that role put review in it, beside deep research, design and architecture. A
Worker still takes a pass that is mostly running things: a mutation run, or the confirming run
after a fix round. If I want code review back with the Worker, it is one paragraph in
`SCBOT.md` (*Who reviews*) and one bullet in each role prompt.

## Starting each kind of session

Open a new session and type the file, alone or followed by the request.

| I want | Type | Model to pick first |
| --- | --- | --- |
| The orchestrator | `@SCBOT.md` | My usual choice |
| An Architect as lead, with its own crew | `@prompts/SCBOT-ARCHITECT.md` | Fable 5.2 (`/model fable`, or the model picker) |
| A Worker as lead, with its own crew | `@prompts/SCBOT-WORKER.md` | Opus 5.5 (`/model opus`, or the model picker) |

The model of a session I start is my choice in the client. Nothing switches it for me. If I
start a role on the wrong model, the role prompt tells the session to say so and ask me, and
the guard, once installed, tells it too.

A lead starts a crew member by its type, `scbot-architect` or `scbot-worker`. The type's
definition sets the model and the effort level, so a crew member is always on the right one.

Starting a role with `claude --agent scbot-worker` is not the way to do it. That flag replaces
Claude Code's whole system prompt with the definition, and the definition takes the sub-agent
tool away, so such a session could not run a crew.

## The limits, and what enforces each

"Claude Code" below means a documented setting that the program itself applies. "Guard" means
the script `tools/scbot.py`, run by Claude Code's hooks before each tool call. "Instruction"
means the prompts ask for it and nothing checks. Before the install, every row is instruction
only.

| Rule | Enforced by | What happens at the edge |
| --- | --- | --- |
| No automatic compaction, in any project | Claude Code: `autoCompactEnabled` and `idleCompaction` set to `false` in the user settings and again in this project's settings, plus `DISABLE_AUTO_COMPACT=1`. Guard: refuses an automatic compaction if some settings file turns it back on | With compaction off, a context that fills completely stops with "Context limit reached". The lines below exist so that it never gets there. The typed `/compact` command is not blocked |
| A lead stops at 90 percent of its context | Guard: from 90 percent it refuses to start or resume a sub-agent and tells the session it is pending closing. Instruction: the session takes on no new work, says "pending closing, waiting on N sub-agents", records each report, leaves notes, and closes | The session is never cut off. Work that comes back after 90 percent is not committed unreviewed: it stays uncommitted, is snapshotted to a work-in-progress branch, and is listed as "built, not reviewed". At 96 percent the guard also refuses to open more files beyond the session's own notes, memory and saved reports, so the rest of the reserve goes to the closing note. Pending closing follows the meter: if the context falls back under 90 percent (a `/compact` I type, for one), the session is told it is no longer pending |
| A lead closes itself | Guard: after the session runs `scbot.py close`, every further prompt is refused with a message that says where its closing note is | Claude Code's own "end conversation" tool is not available in the VS Code panel, so the refusal is what makes the close real. `scbot.py reopen` undoes it |
| A running sub-agent is never stopped to close sooner | By design: the guard only ever refuses a new tool call and never ends an agent. Instruction: the lead waits | The last 10 percent of a lead's context is the reserve for this. Reports are short so that six of them fit |
| A sub-agent hands over at 80 percent of its context | Guard: tells it at 60, 75 and 80 percent, and at 80 refuses reading and searching while leaving writing, commands, messaging and reporting open. Instruction: at 60 it plans the rest of the task to fit, at 75 it wraps up (finishes the step in hand, leaves no half-edited file, and can say exactly which tests pass and which fail), at 80 only the handoff note and the report are left | A fresh sub-agent continues from the handoff note. The guard sees tool calls only: a `cat` through the shell still reads a file, and a `claude` started from the shell is not counted. So the cap on reading is a prompt to wrap up, not a wall |
| At most six sub-agents running at once per session | Claude Code: `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=6`. Guard: counts the running ones itself, for the sub-agent tool and the `Workflow` tool alike, and also refuses a message that would restart a finished sub-agent while six run. Each start it lets through holds a slot until the sub-agent is seen starting, so several starts in one message cannot all pass the count | When one finishes, the next may start. There is no limit on how many a session starts over its life. The count mends itself: a sub-agent whose transcript has been silent for 30 minutes, or whose session ended, no longer counts, and counts again as soon as it acts again. `python tools/scbot.py crew --session SCBOT-1` lists them, and `crew clear --session SCBOT-1 <id>` frees the slot of one that has really ended (one active in the last five minutes only with `--force`). The guard cannot stop a workflow from starting several agents at once: it counts each one and refuses the next start while six or more run |
| A sub-agent does not start sub-agents | Instruction: it is a rule in both role prompts, because a lead's six count only what it started and a nested agent's report would never reach the lead. Claude Code: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` withholds the tool, and the two definitions remove it. Guard: refuses the call if one ever gets through | Three locks behind the rule, any one of which is enough |
| Architect on Fable 5.2 only, Worker on Opus 5.5 only, both at xhigh | Claude Code: each definition names its model and effort. Guard: refuses a call that asks for another model or effort for those two types | For a session I start myself, the model is my own choice |
| The Architect does not write the implementation | Guard: refuses a `scbot-architect` sub-agent's file edits to the profile, the tools, the dashboard's code, page and tests, and the generated folders. Instruction: the rest, and all of it for a session I start with the Architect's prompt, which the guard treats as a lead like any other | It can still run commands, so this is a fence, not a wall |
| A question for me reaches me | Claude Code: a lead has the question tool, a sub-agent does not. Instruction: a sub-agent sends its question to its lead and keeps working on what does not depend on it. The lead asks me and passes my answer back | A sub-agent with nothing else to do ends with the question at the top of its report, and the lead resumes it with the answer |
| A crew member's final report is at most 6,000 characters | Guard: sends a longer one back from a `scbot-architect` or `scbot-worker`, saves the full text to a file, and asks for a summary that names the file. It sends one back at most twice, so it can never loop. Other sub-agent types have no length rule | Every final report is also saved under `.claude/scbot/reports/`, so it survives a lead that has closed |
| Sessions do not collide | Guard: gives each session a label (SCBOT-1, SCBOT-2 and so on), unique among the live sessions, and tells it which others are live. A session that comes back after a day idle may find its label taken, and is then given a new one. The queue refuses a claim on files another live session holds. Instruction: the rest, including committing by path and never stashing or resetting a tree that agents are working in | See the work queue below |
| Nothing personal is published | Instruction: a privacy scan runs before every push. It is a script that exits non-zero on any hit, so a commit chained after it stops | The project's copy of that script is a local helper and is not tracked |

### How the guard knows how full a context is

A session cannot see its own context meter, and Claude Code's hooks are not told it either.
The guard reads it from the session's transcript file: the newest reply there records how many
tokens were sent. It measures that against the model's window, which is one million tokens for
Fable 5.2 and Opus 5.5.

Two things follow. The transcript's format belongs to Claude Code and can change with an
update. And the window size comes from a small table in the script. Three separate readings
above the table's figure prove the table wrong: the guard then measures that model against one
million tokens, never more, and says so (only `SCBOT_CONTEXT_WINDOW` sets a larger window). A
reading above every window is taken as a bad reading: it is not used, with a warning, and the
limits stay on. So the guard is built to fail open: when it cannot do its job (a figure
it cannot read, a transcript it cannot find, a model it has no window for, records it cannot
write, a fault of its own) it lets the call through, tells the session and me (again at most
every five minutes), and writes a line to `.claude/scbot/guard.log`. A guard that failed
closed would freeze every session and sub-agent on the PC at once. For the same reason the
hooks start it through a small launcher that ends with exit code 0 whatever happens: a
missing or broken script lets everything through.

The guard speaks only when a line is reached. It shows no running meter, because Anthropic's
guidance for Fable 5.2 is that a token budget shown to the model changes how much it spends.

### Seeing what the guard sees

```
python tools/scbot.py meter
python tools/scbot.py crew --session SCBOT-1
python tools/scbot.py crew clear --session SCBOT-1 <id>
```

`meter` prints the context of the session and of each of its sub-agents. `crew` lists a
session's sub-agents and whether each counts as running, which is where to look when a start
is refused although fewer than six are at work. `crew clear` frees the slot of one that has
really ended and is still counted.

## Before the install

Until the install has been run, none of the guard's behavior exists, and this is what holds:

- **Compaction is still on.** Claude Code's defaults apply: a conversation is summarized near
  the end of its window, and one over 200,000 tokens is summarized after sitting idle for
  about an hour.
- **Every limit is an instruction.** The prompts ask a lead to count its own sub-agents, to
  put the rules in each brief, and to stop at its line. Nothing refuses anything.
- **Sessions have no labels,** so the queue's `claim`, `close` and `status --session` do not
  work. `add`, `list`, `note` and `done` do.
- **The two sub-agent types do not exist yet,** because the install puts their definitions in
  place. Until then a lead starts a crew member as the general-purpose type, with the model
  named in the call (Opus 5.5 for a Worker, Fable 5.2 for an Architect) at xhigh effort, and a
  first line that tells it to read its role prompt.
- **The meter can be read by hand.** This prints how full the current session's context is,
  and each of its sub-agents', in percent, using the same code the guard uses:
  ```
  python tools/scbot.py meter
  ```
  It takes the session whose transcript in this repo's project folder was written last, which
  is the one running the command. `--transcript PATH` names another one. In the VS Code panel I
  can also see the meter myself: the prompt box shows it once a session is half full.

## The work queue

The queue is a folder of small task files, `.claude/scbot/queue/`, and a few commands. It
exists for two things: several sessions working at once, and work that has to outlive a
session that closed at its line.

```
python tools/scbot.py queue list
python tools/scbot.py queue add --title "Wire stage 3" --role worker --files "dashboard/scdash/*" --session SCBOT-1
python tools/scbot.py queue claim T001 --session SCBOT-1
python tools/scbot.py queue done T001 --session SCBOT-1 --commit abc1234
python tools/scbot.py status --session SCBOT-1
```

- A task has a title, a role, the files it will touch, a brief (`T001.brief.md` beside it),
  and a state: open, claimed, blocked, done or dropped.
- A claim is refused when another live session holds the task, or holds files that overlap.
- Memory files and the game plan page are claimed the same way, so that each has one writer at
  a time: a memory file is named `memory/<file name>` and the page `game-plan-page`.
- When a session closes, its claimed tasks go back to open, marked "handed over", with a
  pointer to its closing note.
- Only leads use the queue. A sub-agent reads its brief and nothing else.
- The queue does not replace a plan. `dashboard/PLAN.md` still says what is to be built and
  where the build stands. The queue only says who has what right now.

**What needs an entry, and a reviewer.** An edit a lead can make and commit in one go (a few
lines, one file, checked by a command it runs) needs neither. Neither does a job that writes
nothing, such as answering a question from the logs. A log check that updates memory or the
page claims those two like any other writer. Anything built, or that touches code another agent
will rely on, gets a queue entry and a review, whether one session is running or three.

Claude Code has a shared task list and an experimental "agent teams" feature. Neither is used
here. The task tools are off by default on these models and add their own text to every
context, and agent teams run only in the terminal. A folder of files needs neither.

## Installing

Read this whole section first. Claude Code picks up a changed hook in **running** sessions
within seconds, so install at a quiet moment, when no session has sub-agents at work.

The install switches compaction off and installs the guard in one step. With compaction off and
no guard, a session that fills up simply stops.

1. Run the tests. They use temporary folders only.
   ```
   python tools/test_scbot.py
   ```
2. See what would change, without changing anything.
   ```
   python tools/scbot.py install --scope all --dry-run
   ```
3. Install.
   ```
   python tools/scbot.py install --scope all
   ```
   For this project it copies `tools/scbot.py` to `.claude/scbot/bin/`, copies
   `prompts/agents/*.md` to `.claude/agents/`, and merges
   `prompts/settings/scbot.project-settings.json` into `.claude/settings.json`: the guard's
   hooks, the two limits on sub-agents, and compaction off. For every project it merges three
   values into `~/.claude/settings.json` that switch compaction off, and adds no hooks there.
   It keeps every setting already in both files and saves a backup beside each before it
   writes. Each hook it writes names the Python that ran the install and the installed script
   by their full paths. It refuses, and changes nothing, when a settings file is not plain JSON
   (a comment in it is enough) and says why. And it first lists any session of this repo that
   is already past its line and would be held at once: it then stops, and `--yes` installs
   anyway. `--python PATH` names another interpreter for the hooks to call.
4. Check it.
   ```
   python tools/scbot.py check
   ```
   Besides the copies and the settings, it runs each hook exactly as the settings write it, to
   prove the Python there works, and it ends with every value that can be set, its default
   and its current value.
5. Start a new session. The sub-agent limits are environment values, which a session reads
   when it starts.

After a change to `tools/scbot.py` or to a file in `prompts/agents/`, run
`python tools/scbot.py install --scope project` again: `check` fails until the installed
copies match.

One thing to know about my other projects: after step 3 compaction is off there too, and the
guard does not run there. A long session in another project gets no warning and stops at
"Context limit reached". The typed `/compact` command is not blocked by this setup, and there
it is the way out. Whether it should be blocked too is still an open question.

### After the install: the first-install checklist

None of this had run inside Claude Code when it was written. These twelve steps turn
"documented" into "seen". Steps 1 and 2 are the install itself, repeated so that the list can
be followed from top to bottom.

1. Run `python tools/scbot.py install --scope all --dry-run`. If it lists a session that is
   already past its line, close that session first.
2. Run `python tools/scbot.py install --scope all`, then `python tools/scbot.py check`. Every
   line should say PASS.
3. Open a new session and type `/hooks`. The guard should be listed on 8 events, and the
   session's first reply should name its label, such as SCBOT-1.
4. Ask that session for a Worker that runs `echo hi`. `python tools/scbot.py crew --session
   SCBOT-N`, with the session's own label, should show the Worker running and then done, and
   its report should be under `.claude/scbot/reports/`.
5. Have the session send that Worker one more message. `crew` should show it running again,
   and then done.
6. Start a Worker on something long in the background and stop it from `/tasks`. `crew`
   should show it done within a minute.
7. Ask for a Worker started with `isolation: worktree` that runs `echo hi`. It should run
   without being blocked.
8. If the Workflow tool is offered, run a workflow with one agent. The agent should appear
   in `crew`.
9. Check that a broken hook cannot block work. In an empty folder outside this repo, add
   `.claude/settings.json` with a PreToolUse hook whose command is `C:\nowhere\python.exe`.
   Start `claude` there and ask for `echo hi`: it must run. Then delete the folder.
10. Check that the guard says so when it cannot do its job. Run `attrib +r` on the session's
    `session.json` under `.claude/scbot/state/`, wait a minute, and have the session make one
    tool call: a warning from the guard should show. Then run `attrib -r` on the file.
11. Check the closing. Put `"SCBOT_LEAD_LIMIT": "5"` in the `env` block of
    `.claude/settings.local.json` and start a new session: it should be pending closing and
    refuse to start a sub-agent. Take the line out again.
12. To remove it all: `python tools/scbot.py uninstall`.


### Removing it

```
python tools/scbot.py uninstall
```

This takes the guard's hooks out of both settings files, puts back the values that were there
before, which switches compaction back on, and deletes the installed copies. A settings file
nobody has edited since the install gets its old bytes back exactly. In one that was edited,
only the guard's own entries come out and every other change stays. A file it never changed is
not touched, and an install that stopped half way is undone the same way. The queue, notes and
reports stay. To switch the guard off for a moment without removing it, add
`"SCBOT_GUARD": "off"` to the `env` block of `.claude/settings.local.json`.

## Values that can be changed

Set these in the `env` block of `.claude/settings.json`.

| Value | Default | What it does |
| --- | --- | --- |
| `SCBOT_LEAD_LIMIT` | 90 | The percent at which a lead is pending closing |
| `SCBOT_CREW_LIMIT` | 80 | The percent at which a sub-agent hands over |
| `SCBOT_CREW_MAX` | 6 | Sub-agents running at once. Change `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` to match |
| `SCBOT_FORK_MAX` | 40 | The percent of a lead's context from which a fork of the lead is refused |
| `SCBOT_REPORT_MAX_CHARS` | 6000 | The longest final report from an Architect or a Worker crew member |
| `SCBOT_SILENT_MINUTES` | 30 | A sub-agent silent for this long stops counting as running |
| `SCBOT_WARN_MINUTES` | 5 | How often the guard repeats a warning that it let a call through because it could not do its job |
| `SCBOT_CONTEXT_WINDOW` | not set | Overrides the window size the guard assumes, in tokens |
| `SCBOT_TITLE` | not set | `1` names each session's tab after its label |
| `SCBOT_GUARD` | not set | `off` switches the guard off |

The numbers are also written into the prompts, so a changed default has to be changed there
too. `prompts/CLAUDE.md` lists the places.

Two more choices are in the sub-agent definitions. `cacheTtl: 1h` keeps a sub-agent's prompt
cache for an hour, so one that is resumed after the lead's checks does not pay to re-read its
whole context. Remove the two lines to go back to five minutes. And a sub-agent starts with
the repo's root `CLAUDE.md` in its context, which costs about 4 percent of its window. Adding
`omitClaudeMd: true` to a definition would save that, at the price of the sub-agent not
knowing the project's layout until it reads it.

## What is tested, and what is only documented

This section is a dated record. Whoever runs the first install updates it with what was seen.

Tested on this PC on 2026-11-28, with Claude Code 2.1.332:

- The guard's decisions, against made-up transcripts: 88 tests, and 65 deliberate faults in
  the script that the tests all caught. That is after a fix round that followed an independent
  review of the script.
- Reading real transcripts: 27 leads and 90 sub-agents measured. The guard's figure matched a
  full read of every lead, and Claude Code's own figure for 15 sub-agents. A hook call took
  about 60 to 70 ms on a busy PC, where Python alone took 39 ms to start.
- Install, check and uninstall, in a temporary folder.

Read in Anthropic's documentation the same day, and not yet tried in a live session:

- Every setting name and hook field above. The documentation gives a minimum version for
  several of them, the highest being 2.1.290, and the command-line copy on this PC is newer.
  The VS Code extension bundles its own copy, whose version was not checked.
- That the hooks run inside sub-agents with the sub-agent's id. The documentation says so.
- That switching compaction off also covers sub-agents. The documentation does not say. The
  guard holds a sub-agent at 80 percent, far below where compaction would start, and refuses
  an automatic compaction if one is ever attempted.
- That Claude Code may still clear old tool results from a long context. The documentation
  mentions it and names no switch for it.

## Sources

Claude Code documentation, at `https://code.claude.com/docs/en/`: `sub-agents` (definitions,
models, tools, the limit on running sub-agents, nesting, resuming), `hooks` (events, inputs,
decisions), `settings` and `settings-reference` (scopes, `autoCompactEnabled`,
`idleCompaction`), `env-vars`, `model-config` (context windows), `tools-reference`,
`cross-session-messaging`, `best-practices` and `costs`.

Anthropic's prompting guides, at
`https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/`:
`claude-prompting-best-practices`, `prompting-claude-fable-5-2` and `prompting-claude-opus-5-5`.

Anthropic engineering articles, at `https://www.anthropic.com/engineering/`:
`multi-agent-research-system` (what a brief needs, results kept in files, about fifteen times
the tokens of a chat) and `effective-context-engineering-for-ai-agents` (notes outside the
context, sub-agents returning short summaries, what compaction can lose).

One thing in that guidance cuts against this setup, and is worth knowing. Anthropic's current
advice is that running out of context is rarely the reason to use a sub-agent any more, and
that a sub-agent costs tokens and start-up time and does not by itself give a better answer. A
fresh reviewer is the exception. My rule stands as `SCBOT.md` states it: the lead hands out
everything that reads a lot, builds, tests, researches, designs or reviews. The guidance is
the reason the lead keeps the one-go edits for itself.
