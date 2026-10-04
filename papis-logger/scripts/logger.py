"""Papis-native JSON reads, additive tags, and append-only motivation notes."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

import papis.api
import papis.config
import papis.document


def emit(value):
    print(json.dumps(value, ensure_ascii=False, default=str))


def documents(query=""):
    return papis.api.get_documents_in_lib(search=query)


def tags_of(doc):
    tags = doc.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        raise ValueError(f"Non-list or non-string tags in {doc.get_main_folder()}; "
                         "inspect the existing convention before changing it.")
    return tags


def record(doc):
    result = {key: doc[key] for key in (
        "title", "author", "author_list", "year", "doi", "arxivid", "ref", "url",
        "abstract", "tags", "notes", "files", "papis_id"
    ) if key in doc}
    result["folder"] = str(Path(doc.get_main_folder()).resolve())
    return result


def paginated(args):
    docs = documents(args.query if args.command == "search" else "")
    docs.sort(key=lambda d: (str(d.get("title", "")).casefold(), d.get_main_folder()))
    result = {
        "library": papis.config.get_lib_name(), "total": len(docs),
        "offset": args.offset,
        "documents": [record(d) for d in docs[args.offset:args.offset + args.limit]],
    }
    result["next_offset"] = (args.offset + args.limit
                             if args.offset + args.limit < len(docs) else None)
    if args.command == "catalog":
        counts = Counter()
        warnings = []
        for doc in docs:
            try:
                counts.update(set(tags_of(doc)))
            except ValueError as exc:
                warnings.append(str(exc))
        result["tag_counts"] = dict(sorted(counts.items()))
        result["warnings"] = warnings
    return result


def selected(folder):
    path = Path(folder).expanduser().resolve(strict=True)
    # Exact membership also respects the selected library's ignored directories.
    if not any(Path(d.get_main_folder()).resolve() == path for d in documents()):
        raise ValueError("Document folder is not in the selected Papis library.")
    return path


@contextmanager
def locked_document(folder):
    import fcntl
    path = selected(folder)
    with (path / ".papis-logger.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Read fresh metadata after acquiring the lock, rather than saving a cache copy.
        yield papis.document.Document(str(path))


def add_tags(args):
    proposed = list(dict.fromkeys(args.tag))
    if any(not t.strip() or "\n" in t or "\r" in t for t in proposed):
        raise ValueError("Tags must be nonblank, single-line strings.")
    known = set()
    for doc in documents():
        try:
            known.update(tags_of(doc))
        except ValueError:
            continue
    unknown = set(proposed) - known
    if unknown and not args.allow_new:
        raise ValueError(f"New tags require an explicit user instruction or accepted "
                         f"proposal and --allow-new: {sorted(unknown)}")
    with locked_document(args.folder) as doc:
        original = tags_of(doc)
        added = [tag for tag in proposed if tag not in original]
        if added:
            doc["tags"] = original + added
            papis.api.save_doc(doc)
            actual = papis.document.Document(doc.get_main_folder())
            if actual.get("tags") != original + added:
                raise RuntimeError("Tag verification failed; inspect the document before retrying.")
        return {"folder": doc.get_main_folder(), "added_tags": added,
                "tags": doc.get("tags", [])}


def note_target(doc):
    from papis.format import format as papis_format
    from papis.paths import normalize_path_part

    root = Path(doc.get_main_folder()).resolve()
    name = doc.get("notes")
    if name is None and "notes" not in doc:
        name = normalize_path_part(papis_format(
            papis.config.getformatpattern("notes-name"), doc, default="notes.tex"))
    if not isinstance(name, str) or not name.strip() or "\n" in name or "\r" in name:
        raise ValueError("Notes must name one text file; inspect the notes field first.")
    relative = Path(name)
    target = (root / relative).resolve()
    if relative.is_absolute() or not target.is_relative_to(root) or target == root:
        raise ValueError("Notes path is outside the document folder; choose a destination first.")
    if target.suffix.lower() not in {".md", ".markdown", ".txt", ".org", ".rst", ".tex"}:
        raise ValueError("Unsupported notes format; choose a supported text destination first.")
    if target == Path(doc.get_info_file()).resolve() or target in {
        (root / f).resolve() for f in doc.get("files", [])
    }:
        raise ValueError("Notes path overlaps metadata or an attached paper.")
    if target.exists() and not target.is_file():
        raise ValueError("Notes destination is not a regular file.")
    return name, target


def append_note(args):
    reason = Path(args.reason_file).read_text(encoding="utf-8").strip()
    if not reason:
        raise ValueError("A nonblank user-supplied reason is required.")
    query = Path(args.query_file).read_text(encoding="utf-8").strip() if args.query_file else None
    if args.kind == "retrieval" and not query:
        raise ValueError("Retrieval notes require the original query via --query-file.")
    if args.kind == "interest" and query is not None:
        raise ValueError("--query-file is only used with retrieval notes.")
    event = str(uuid.UUID(args.event_id))
    digest = hashlib.sha256(json.dumps(
        [args.kind, reason, query], ensure_ascii=False).encode("utf-8")).hexdigest()
    token = f"papis-logger:{event}:{digest}"
    with locked_document(args.folder) as doc:
        name, path = note_target(doc)
        old = path.read_bytes() if path.exists() else b""
        old_text = old.decode("utf-8")
        tex = path.suffix.lower() == ".tex"
        marker = f"% {token}" if tex else f"<!-- {token} -->"
        # Match complete marker lines; one event ID cannot silently acquire a new meaning.
        prefix = f"% papis-logger:{event}:" if tex else f"<!-- papis-logger:{event}:"
        markers = [line for line in old_text.splitlines() if line.startswith(prefix)]
        if markers:
            if markers != [marker]:
                raise ValueError("Event ID already exists with different content; inspect before retrying.")
            # Recover the link if a previous attempt appended but failed to save metadata.
            if "notes" not in doc:
                doc["notes"] = name
                papis.api.save_doc(doc)
            return {"folder": doc.get_main_folder(), "notes": str(path),
                    "event_id": event, "appended": False}

        title = "Why saved" if args.kind == "interest" else "Why retrieved"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [f"{timestamp} — {title}"]
        if query is not None:
            lines += ["Search request:", query, "User's reason:"]
        lines += [reason]
        body = "\n".join(lines)
        if tex:
            body = "\n".join("% " + line for line in body.split("\n"))
        # A completion marker follows the body, so a truncated write is not
        # mistaken for a completed event on a retry.
        entry = (body + "\n" + marker + "\n").encode("utf-8")

        # Honor Papis's template only when creating a new notes file. Existing bytes
        # are never rewritten, including their newline conventions.
        template = b""
        if not path.exists():
            template_path = Path(papis.config.getstring("notes-template")).expanduser()
            if template_path.is_file():
                from papis.format import format as papis_format
                template = papis_format(template_path.read_text(encoding="utf-8"), doc).encode("utf-8")
        previous = old or template
        separator = b"" if not previous else (b"\n" if previous.endswith(b"\n") else b"\n\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as stream:
            stream.write(template + separator + entry)
            stream.flush()
            os.fsync(stream.fileno())
        if "notes" not in doc:
            doc["notes"] = name
            papis.api.save_doc(doc)
        if path.read_bytes() != old + template + separator + entry:
            raise RuntimeError("Note verification failed; inspect the file before retrying.")
        if papis.document.Document(doc.get_main_folder()).get("notes") != name:
            raise RuntimeError("Notes link verification failed; inspect before retrying.")
        return {"folder": doc.get_main_folder(), "notes": str(path),
                "event_id": event, "appended": True}


def positive(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def nonnegative(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("catalog", "search"):
        cmd = sub.add_parser(name)
        if name == "search":
            cmd.add_argument("query", help="Native Papis query (metadata, not PDF full text)")
        cmd.add_argument("--limit", type=positive, default=40)
        cmd.add_argument("--offset", type=nonnegative, default=0)
    show = sub.add_parser("show")
    show.add_argument("--folder", required=True)
    tag = sub.add_parser("tag")
    tag.add_argument("--folder", required=True)
    tag.add_argument("--tag", action="append", required=True)
    tag.add_argument("--allow-new", action="store_true")
    note = sub.add_parser("note")
    note.add_argument("--folder", required=True)
    note.add_argument("--kind", choices=("interest", "retrieval"), required=True)
    note.add_argument("--reason-file", required=True)
    note.add_argument("--query-file")
    note.add_argument("--event-id", required=True, help="UUID; reuse only for retries of this event")
    args = parser.parse_args()
    try:
        if args.command in ("catalog", "search"):
            result = paginated(args)
        elif args.command == "show":
            doc = papis.document.Document(str(selected(args.folder)))
            result = {"folder": doc.get_main_folder(), "metadata": dict(doc)}
        elif args.command == "tag":
            result = add_tags(args)
        else:
            result = append_note(args)
        emit(result)
    except Exception as exc:
        emit({"error": str(exc), "type": type(exc).__name__})
        sys.exit(1)


if __name__ == "__main__":
    main()
