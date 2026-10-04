# Papis commands and storage

The helper is tested with Papis 0.16.1 on macOS and uses the public Papis Python
API through `papis exec`. Papis must be installed on the machine where the agent
runs and have access to the intended library. The write lock uses `fcntl`
(macOS/Linux). No separate Python dependencies, MCP server, or API key are needed.
For another Papis version, inspect its local `--help` and test on a disposable
library before relying on writes if an API differs.

## Command setup

Set `PAPIS_LOGGER_DIR` to the absolute directory containing this skill's
`SKILL.md`. It is a placeholder below, not a preconfigured environment variable.
Pass `--config /path/to/config` and `--lib NAME_OR_PATH` **before** `exec`, `add`,
or another Papis subcommand. Omit these only when using the configured default.

```sh
papis --version
papis list --libraries
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" catalog --limit 40
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" catalog --offset 40 --limit 40
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" search 'tags:decoding'
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" search 'title:"surface code"'
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" show --folder /absolute/paper/folder
```

Run `papis exec .../scripts/run.py -- --help` for helper help. Do not run the
bootstrap with a system Python that lacks Papis. `run.py` ensures a normal Python
module namespace despite `papis exec`'s execution scope.

`catalog` and `search` return JSON with `total`, `documents`, and `next_offset`.
Follow `next_offset` until null when a complete scan is needed. Catalog tag counts
cover the entire selected library, even when the returned document page is small.
Results include abstracts when available. `show` returns full metadata.
Native Papis query syntax varies with the configured database backend; if a field
query fails, check `papis list --help` and use a simple text query or inspect
catalog pages. No result means an empty document list; an error exits nonzero.

## Adding papers

Search for duplicates first (identifier, then title/authors), and inspect
`papis add --help` / `papis add --list-importers` on the installed version.
Use a DOI or arXiv importer when possible; use verified YAML metadata for a local
PDF with no usable identifier. Never pass an arbitrary URL as a local filename.

```sh
papis --lib papers add --batch --no-confirm --no-edit --no-open --no-git \
  --no-move --no-link --no-auto-doctor --no-fetch-citations \
  --from doi '10.1234/example'

papis --lib papers add --batch --no-confirm --no-edit --no-open --no-git \
  --no-move --no-link --no-auto-doctor --no-fetch-citations \
  --from arxiv '2401.01234'

papis --lib papers add --batch --no-confirm --no-edit --no-open --no-git \
  --no-move --no-link --no-auto-doctor --no-fetch-citations \
  --from yaml /absolute/verified-metadata.yaml /absolute/paper.pdf
```

These identifiers illustrate syntax; do not import them as test data into the
user's library. Use `--no-download-files` for a requested metadata-only entry.
For an unavailable PDF, verify whether the importer already created the record
before attempting a metadata-only import. All import results must be read back;
an exit code alone does not establish which paper was saved.

Do not use `--set notes` for prose: Papis's `notes` field is a filename. Avoid
`--set tags` as it can create a scalar instead of a list. After import, use the
helper's additive tagging and note commands on an exact returned folder.

## Applying tags

```sh
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" tag \
  --folder /absolute/paper/folder --tag decoding --tag 'quantum-error-correction'
```

This preserves all existing tags and metadata fields, saves via Papis (including
its database update), and verifies the saved list. Repeating the same operation
does not duplicate tags. Unknown tags fail unless `--allow-new` is included for
an explicit user tag or an accepted proposal. This option does not decide what
is authorized; the agent must follow the conversation and skill instructions.
Legacy scalar tags are reported rather than silently split or converted.

## Logging reasons

Write the user's actual answer to a temporary UTF-8 file with a file-writing
tool; write the original search request to another file for a retrieval. Avoid
interpolating user prose into shell commands. Use a securely created temporary
directory and delete only those temporary input files after verified success.
Internal newlines and Unicode are retained; leading/trailing whitespace is trimmed.

Generate an event ID once (for example, `python3 -c 'import uuid; print(uuid.uuid4())'`),
retain it through retries, and substitute it for `EVENT_UUID` below:

```sh
papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" note \
  --folder /absolute/paper/folder --kind interest \
  --reason-file /temporary/reason.txt --event-id EVENT_UUID

papis --lib papers exec "$PAPIS_LOGGER_DIR/scripts/run.py" note \
  --folder /absolute/paper/folder --kind retrieval \
  --reason-file /temporary/reason.txt --query-file /temporary/query.txt \
  --event-id EVENT_UUID
```

The helper appends a UTC timestamp, the event label, the user's words, and a
completion marker. Retrieval events also contain the original query. The marker
contains the UUID and a content hash; a retry of the same event is a no-op, while
reusing its UUID for different content fails. Use a new UUID for a new occasion.

The existing `notes` link is used. If absent, the configured `notes-name` and
`notes-template` are honored and a link is saved in metadata. Existing note bytes
are preserved. Markdown, plain text, Org, and reStructuredText get a plain text
entry with an HTML-style marker; TeX entries and markers are comments. Binary
notes, ambiguous notes lists, non-UTF-8 text, paths escaping the document folder,
and paths overlapping metadata or attachments are rejected without rewriting
their content. These cases need an explicit destination decision.

A per-document `.papis-logger.lock` serializes helper writes. Other editors and
Papis processes do not share that lock; avoid simultaneous manual edits. If a
write fails, inspect both notes and metadata before retrying. Notes and metadata
are separate files, so failures can leave partial success. Helper writes use
Papis's normal metadata serializer, which may change YAML formatting/comments.

## Upstream documentation

- [Papis add](https://papis.readthedocs.io/en/latest/commands/add.html)
- [Papis quick guide, including notes](https://papis.readthedocs.io/en/latest/quick_guide.html)
- [Papis source](https://github.com/papis/papis)
