# SCBOT: Star Citizen session brief

This is my standing brief for a new Claude Code session in this folder: the prompt that starts
every conversation about this project and my Star Citizen work. It says what we work on here,
how to get up to speed, how I like to work, and what you can do without asking.

It doesn't repeat what you already have. [`CLAUDE.md`](CLAUDE.md) is loaded for you and is the
full reference for my control bindings. The memory directory holds what earlier sessions learned,
and its index is loaded too. This file tells you how to use them. It states each preference
briefly, and memory keeps the detail, the dates and the exceptions, so a shorter statement here
is not a disagreement. Where the two really do conflict, follow the one I stated more recently
(memory notes carry dates, and `git log` dates the lines here) and tell me, so the other gets
fixed.

**How I use it.** I start a session with `@SCBOT.md`, alone or followed by a request. Alone
means *ramp up and tell me where things stand*. With a request, do the request: *How I work*,
*What counts as known* and *Leaving things for the next session* always apply, and you read
whatever part of *Ramping up* the request needs.

## What happens in this folder

I play Star Citizen, and I use Claude here for three kinds of work.

1. **The control profile.** This git repo is my MOZA HOTAS binding profile, `MOZA.xml`, with its
   docs, reference cards and tools. It is public on GitHub, and everything goes straight to `main`.
2. **Playing the game.** I play, then ask you to read the game's logs and my screenshots and tell
   me what happened and what comes next. You plan my mining, refining and crafting from the game's
   own data, and you keep my bookmarked game plan page current.
3. **The PC, when it gets in the way.** For example the USB dropouts of November 2026.

You can't watch me play. What you can see is the game's log, my screenshots, the game's data
files, the game's saved copy of my bindings, and what I tell you. A lot of the judgment in this
work is about what that evidence shows and what it doesn't.

## Ramping up

When I ask you to ramp up, or start a session with only this file, the outcome I want is that you
can tell me where things stand and then act without me re-explaining anything. It is nearly all
reading, so run the independent reads in parallel. These are the sources, in the order they build
on each other.

1. **My preferences in full.** Read the memory files whose frontmatter type is `feedback` or
   `user`. They are short, and the index lines leave out the reasons and the exceptions.
2. **What I'm working toward.** Read the goal files the index marks as current, plus
   `game-plan-artifact`, `sc-game-log-reading` and `sc-screenshots`. Open the rest when the work
   touches them. `sc-4103-gameplay-facts` is large: read it whole unless the request is only
   about the repo.
3. **The repo.** `git status` and `git log -15`, then `python tools/gamedata.py check` and
   `python tools/validate_actionmaps.py`. Both tools only read. Between them they show whether
   the profile is valid for the installed build and whether the game holds what `MOZA.xml`
   declares. If the working tree holds changes left by an earlier session, look at what they are
   and tell me before you build on them or commit them.
4. **The plan.** Read the live game plan page. Its *Now* list is my objectives in priority order.
5. **What I've done since.** Look for game sessions and screenshots newer than the page's latest
   *Recent* entry. If there are any, read them, bring memory and the page up to date with what
   they show, and ask me about what they can't show. A session that is still running gets
   reported as in progress, not written up as finished.

Then report briefly: where I am on the *Now* list and the next step, what has changed since the
page was last updated, what is waiting on me (things to test in a ship, decisions to make), and
anything that looks off, such as a validator difference, a new game build, or joysticks
enumerated in the wrong order. I don't need the docs summarized back to me.

## Where things live

`LIVE` is `C:\Program Files\Roberts Space Industries\StarCitizen\LIVE`. This repo sits inside it,
at `LIVE\user\client\0\controls\mappings`.

| What | Where | Worth knowing |
| --- | --- | --- |
| Bindings, hardware, device settings, and every binding decision with its reason | `CLAUDE.md` | Already in your context. §4 is the binding table, §6 the dated issue log (including what is still a trial or unflown), §10 the validation workflow, §11 the fleet. |
| My preferences, goals, game facts and methods | The memory directory (its path is in your system prompt) | Only the index, `MEMORY.md`, is loaded. The topic files hold the detail and the reasons. |
| The current plan and my progress | The game plan page, a private artifact | Memory `game-plan-artifact` has the link and the update routine. |
| Recent changes to the repo | `git log` | The commit messages say what changed and why. |
| What I did in game | `LIVE\Game.log` for the current or last launch, `LIVE\logbackups\` for earlier ones | Times inside the logs are UTC. Backup file names and screenshot names use my local time, Pacific. If `StarCitizen.exe` is running, `Game.log` is a session in progress. Memory `sc-game-log-reading` lists the useful markers and what the log can't show. |
| My screenshots | `LIVE\screenshots\` (the game's own) and `%USERPROFILE%\Videos\Captures\` (Game Bar) | The game blacks out its own shots of terminals, so terminal screens come from Game Bar. Memory `sc-screenshots`. |
| The game's data | `LIVE\Data.p4k`, read with `tools/gamedata.py` | Ground truth for actions, labels and stock bindings. `Game2.dcb` inside it holds the item, ore and blueprint records; memory `sc-datacore-reading` says how to read it. Run these with plain `python`: `python -I` hides the folder that holds the `zstandard` package. |
| The installed build | `LIVE\build_manifest.id` | Compare it with the build `CLAUDE.md` names to see whether a patch has landed. |
| The bindings the game holds | `LIVE\user\client\0\Profiles\default\actionmaps.xml` | Rewritten when I load the profile and quit, so while the game runs it shows my previous session. `tools/validate_actionmaps.py` compares it with `MOZA.xml`. |
| Community data: missions, recipes, prices, ship stats | Memory `sc-community-tools` | Says which sources can be scripted and which forbid it. |

## How I work

- **I'm not in a rush, and I want the complete, correct result.** Plan so the finished thing
  comes out right the first time: every material at the target quality, then the whole set crafted
  together. I've turned down interim versions offered to save time, such as "craft now, upgrade
  later" or three armor pieces now and the helmet later, so leave those out. The same goes for
  repo work.
- **It's my repo and my layout, and you keep it correct.** Which control does what is my
  decision. If a change means moving or displacing a control I didn't mention, show me the options
  and what each one displaces before you edit; a control I use often shouldn't end up sharing a
  key just because the key was free. The docs, the cards and the tools are yours to maintain: when
  a statement has gone stale or a tool misses a failure we actually hit, fix it as part of the
  change you're making, and take notes out once they are settled. Leave the structure of things
  that work as it is unless I ask.
- **Commit and push to `main` as soon as a change is finished and checked.** Git is my source of
  truth and my rollback point, so there's no need to wait for "ship it" or to branch. One commit
  per logical change, with every file that describes the change in it. Scratch files go in your
  scratchpad so the repo stays clean. A copy of `MOZA.xml` never sits anywhere under this folder
  with an `.xml` name, git-ignored or not: the game lists profile files from subfolders too, and
  a session's before-copy once showed up in my profile menu as "MOZA (1)".
- **The rig is for ships only.** On foot and in ground vehicles I use an Xbox controller on the
  game's stock layout, so on-foot and ground bindings would be clutter. The few entries in those
  actionmaps are clears of stock defaults, and they stay.
- **My fleet changes often.** I melt and re-pledge ships regularly. Treat the fleet list as a
  snapshot, and change the docs when I confirm a change, not while I'm considering one. I don't
  want housekeeping reminders about claiming, retrieving or refitting ships. A step in a plan we
  made, such as fitting a drive I crafted for a ship, is part of the plan and not a reminder.
- **When a crash or a bug costs me progress, that's the game's fault.** Read what happened before
  you advise, and suggest a precaution only if it would have changed the outcome.
- **My ore is for crafting, not for sale.** Recommend Pyrometric Chromalysis by default: it gives
  the same yield as the slow methods, and a few thousand aUEC to save hours is worth it to me.
- **Community tools: source, not binaries.** I don't like precompiled programs from community
  projects. If someone's tool would do a job, it has to be open source and we build or run it
  from source ourselves; a project with no license doesn't count as open source. Otherwise we
  build our own.
- **Subagents: Opus 5.5 by default, Fable 5.2 for advanced design and research.** Run every
  subagent at xhigh effort. Opus 5.5 is the general workhorse and does the implementation:
  building, fixing, checking. Start a subagent on Fable 5.2 when the task is advanced design or
  research, such as laying out a dashboard page or a deep dive into community tools or the
  game's data. Choose per task, by what the task needs.
- **The repo is public; memory is not.** Account details, the game plan link, and PC details
  beyond what the bindings need (the rig and its USB wiring are already in `CLAUDE.md`) stay in
  memory. Keep my name, email and machine details out of web requests as well.
- **How I write.** Quickly, in lower case, with typos, and often as several short messages while
  you're still working. Treat them as one request in which later messages refine earlier ones. A
  garbled word is usually a game term.
- **How to answer.** I haven't seen your tool calls or the files you opened, and I'm often
  switching in from the game. Lead with what you found or did, in plain words, and explain any
  label you made up during the work. On a long job, say in a line what you're about to do, give a
  short update now and then, and close with a recap that stands on its own: what you found, what
  you did, what's next. Use a table for routes and numbers, and give times in my local time.
  Read the current time from the PC's clock before you write it, in a reply or a note: a
  session once wrote "about 11 AM" at 5:30 AM.
- **American English.** I'm American, so write American spelling and usage everywhere: replies,
  the docs, memory, the page and commit messages. That means "center", "armor" and "catalog", and
  dates written month first. Text quoted from the game keeps the game's own spelling.

### What needs no approval, and what does

Go ahead with these without asking:

- reading what the work needs: the repo, memory, the game's logs, data files and saved profile,
  my screenshots, the Windows event logs (the launcher's `loginData.json` and `launcherData.json`
  are the exception; nothing here needs them);
- running the repo's tools, and writing and running scratch scripts in your scratchpad;
- editing this repo's files as a change needs, then committing and pushing to `main`;
- updating memory, and republishing the game plan page to its existing link;
- installing ordinary dev tools such as pip packages (tell me what you installed);
- searching the web, reading public pages, and fetching game data from the sources memory lists
  as scriptable;
- starting subagents (the *Subagents* line above says on which model).

Ask me before these:

- editing the game's own files outside this repo, such as `Profiles\default\actionmaps.xml` or
  `attributes.xml` (and only with the game closed, because the game rewrites them when it exits);
- starting or closing the game or MOZA Cockpit;
- changing a Windows or Claude Code setting, installing a driver, or running an installer that
  needs admin rights;
- anything that costs money;
- moving or displacing a control I didn't mention;
- anything else that would be hard to undo.

## What counts as known

Most of the mistakes in this project came from something unverified being written down as fact.
So the docs, memory and the page all mark how each thing is known, and I want that kept up.

- **Loaded is not flown.** A binding passes through four states: written in `MOZA.xml`, passing
  `gamedata.py check`, accepted by the game (its export matches after I load the profile and
  quit), and working in a ship. Say which state a thing is in. Only I can report the last one.
- **Say where a game fact comes from.** Read from the game's files (`[game]` in the docs), taken
  from a community source (`[ref]`), seen in my log or a screenshot, or told to you by me.
  Second-hand stays labeled second-hand until it has been checked.
- **The log is silent about a lot.** It doesn't record what I mined or carried, or the start of a
  refinery job; memory `sc-game-log-reading` has the full list. When it is silent, ask me or look
  for a screenshot instead of filling the gap.
- **Notes are dated.** Memory and the docs record what was true when they were written. When one
  names a file, a setting or a game behavior that matters to what you're doing, check it against
  the thing itself, and correct the note if it has drifted.
- **Label your own inferences.** "I think", "probably" and "unverified" are all fine. A guess
  stated as fact is what I don't want.

## Things I ask for often

**"Check the logs."** I usually ask this right after playing, often with "and screenshots". Find
what is new since the page's latest *Recent* entry, in `Game.log`, `logbackups` and the
screenshot folders. Tell me what happened: where I went, which ships I used, the notices that
matter (refinery orders, blueprints, deliveries), any death or crash, and whether the joysticks
came up in the right order. Say what the evidence can't show. Then update memory and the page in
the same turn. Start from the repo's own reader instead of writing a scratch parser:
`python dashboard/scdash.py timeline --list --since <date>` lists the sessions with their local
start, length and how each ended, and `python dashboard/scdash.py timeline <part of a backup's
name>` prints one session's timeline. It shows what its parser knows; go to the raw log for
anything it leaves out.

**Changing a binding.** `CLAUDE.md` §10.3 has the workflow. The change is done when all of this
is true:

- the action sits in its true actionmap with a single `<rebind>`, because the game keeps one
  joystick input per action;
- anything else on the same input is either in a map that isn't live at the same time or shares
  the input on purpose, like the tap/hold pairs and the door pairs (`CLAUDE.md` §2.3, §2.5, §5);
- `python tools/gamedata.py check` passes;
- everything that describes the binding agrees: the XML comment, the card rows in
  `tools/regen_cards.py` and the regenerated cards, `CLAUDE.md` (the §4 table, §5 if the reuse
  changed, a dated §6 item), the binding counts wherever they are quoted, `README.md` (badge and
  status), `reference/MOZA_BINDINGS.html`, any folder README or `CLAUDE.md` that mentions it, and
  the controls note on the game plan page;
- it is committed and pushed, and you've told me it is written but not loaded.

Two steps follow later and depend on me. After I load it in game and quit, run
`python tools/validate_actionmaps.py`. A binding removed from the file lingers in the game until
I clear it in the Keybindings menu, or you take it out of the saved profile with my OK
(`CLAUDE.md` §2.5). After I fly it, record what I report and take out the "unverified" notes it
settles.

**Plans: routes, mining, refining, crafting.** Work from the game's own records first and the
scriptable community sources second, and give me numbers with their source: distances, refinery
bonuses, quality bands, what I need against what I hold. Recommend one plan, and raise an
alternative only when it is a real choice for me to make. Put the result in the goal's memory
file and on the page.

**The game plan page.** It is the one place I look to see what I'm doing next. After every
session I report, update it and republish it to the same link, following the routine in memory
`game-plan-artifact`.

**A new game patch.** `python tools/gamedata.py check` shows whether a bound action was renamed,
moved or removed and whether new stock defaults overlap my controls. `python tools/gamedata.py
catalog` regenerates the action catalog. `CLAUDE.md` §7 lists the version stamps to update.

**PC trouble.** Memory `pc-usb-dropouts` has the hardware, the USB wiring and the Windows logs
that show a device dropping. Diagnose from the logs.

## Leaving things for the next session

A session can end without warning, and the next one starts from the repo, memory and the page,
not from this conversation. So keep them current as you go instead of at the end.

- **The repo** is committed and pushed, with nothing half-done in the working tree.
- **Memory** has the goal file updated with dated facts, and an index that is still true: the
  goal I'm on marked as current, finished ones marked done. Correct or delete notes that are
  wrong or superseded. That includes old cautions: when the reason behind one no longer holds,
  remove it, and where a rule has exceptions, write its scope and reason instead of an absolute.
- **The page** is republished with a *Recent* entry for what happened.
- **Anything only I can do**, such as flying a test, loading the profile or making a decision, is
  written where the next session will find it: `CLAUDE.md` §6 for bindings, the goal's memory
  file and the page for gameplay.
- **What was tried and didn't work** is written down with the reason, so the next session
  doesn't try it again. `CLAUDE.md` §6 is where that goes for bindings.

This file holds standing preferences and routines; current state doesn't belong in it. When I
state a new standing preference or change a routine, update it here as well as in memory, and
tell me what you changed. Add a line for a mistake a session actually made, and take a line out
when it has stopped earning its place.
