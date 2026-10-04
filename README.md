# Papis Logger

A portable skill for Codex and Claude Code that keeps papers, tags, and research
intent in your local Papis library.

- **Track papers:** resolve and import requested papers, check for duplicates,
  and automatically append applicable tags from your library's vocabulary.
- **Remember why:** ask why a paper interests you, then append your answer to its
  notes. When you find a paper, ask what you need it for and log that reason too.
- **Improve tags:** suggest missing tags for themes shared by at least two works,
  with supporting papers. Apply inferred new tags after you accept the proposal.

Reasons you already gave are recorded without asking twice. Searches return
results before asking why, and only selected results receive notes. Declining a
prompt leaves notes unchanged. Existing notes are preserved, and retries of the
same logging event do not duplicate entries.

## Install

Requires local Papis (tested with **0.16.1**) on macOS or Linux. The agent must be
able to run shell commands and access your library. This targets local Codex and
Claude Code; installing a skill in a cloud chat does not grant it local access.

### Install from GitHub with `npx skills`

With Node.js/npm installed, run the command for your agent from any directory:

```sh
# Codex
npx skills add ftripier/Papis-logger-skill --skill papis-logger -g -a codex

# Claude Code
npx skills add ftripier/Papis-logger-skill --skill papis-logger -g -a claude-code

# Both
npx skills add ftripier/Papis-logger-skill --skill papis-logger -g -a codex claude-code
```

`-g` installs for your user across projects. For a project-only installation,
run the command from that project's directory and omit `-g`. This installs the
skill and its bundled helper scripts; Papis must be installed separately.
See the [Skills CLI documentation](https://github.com/vercel-labs/skills#options)
for installation options.

To check that the repository's skill is discoverable without installing it:

```sh
npx skills add ftripier/Papis-logger-skill --list
```

Start a new agent session if the skill does not appear.

### Alternative: install from a local checkout

After cloning this repository, run one of these commands from its directory:

```sh
python3 install.py codex
python3 install.py claude
# Or install for both:
python3 install.py both
```

The installer copies the same `papis-logger/` directory to
`~/.agents/skills/papis-logger` for Codex or `~/.claude/skills/papis-logger` for
Claude Code. These are the documented [Codex](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code](https://code.claude.com/docs/en/skills) skill locations.
Start a new session if the skill does not appear.

For a project or a custom skill location:

```sh
python3 install.py both --project /path/to/project
python3 install.py codex --skills-dir "$HOME/.codex/skills"
```

Project installs use `.agents/skills/` and `.claude/skills/` inside the specified
project. `--skills-dir` supports older/custom Codex layouts; it is the parent
directory, not the final `papis-logger` directory. Install in one discovery
location per host to avoid duplicates. Use `--replace` to update an installation;
its previous copy is retained in a sibling `skill-backups/` directory outside
skill discovery. Installation does not configure Papis or modify the library.

You can also copy `papis-logger/` manually into either host's skills directory.
The shared `SKILL.md` contains no host-specific tool requirements; `agents/openai.yaml`
only supplies Codex UI metadata.

## Use

In Codex, invoke `$papis-logger`; in Claude Code, invoke `/papis-logger`, or ask
for a Papis task naturally:

> Track this DOI in Papis and tag it based on my existing library.

> Find the paper about correlated noise and surface-code decoding.

> Look through my quantum-error-correction papers and suggest missing tags.

Specify a library when you want something other than Papis's default. Tracking
is on demand; this skill does not run a background watcher. The model performs
paper matching and thematic judgment. A bundled helper handles paginated metadata
queries, exact-target tag updates, and timestamped note appends through Papis.

See [the skill](papis-logger/SKILL.md) for the full workflow and
[Papis integration](papis-logger/references/papis.md) for commands, note formats,
and failure recovery. Unsupported or ambiguous note storage is reported for a
destination decision rather than replaced.

## Validate

```sh
python3 -m unittest discover -s tests -v
```

Tests invoke the real Papis CLI against temporary libraries with an isolated
configuration and cache. They do not import network papers or use your library.
They check storage behavior and installation; semantic tag quality and follow-up
questions remain agent behavior, with review cases in [tests/scenarios.md](tests/scenarios.md).
