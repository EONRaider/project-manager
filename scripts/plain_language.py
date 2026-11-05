"""Plain-language check for what the decider reads. One script, two hook events.

- **PreToolUse, matcher ``AskUserQuestion``** (settings flag ``question_check``). Every
  question's ``question`` and ``header``, and each option's ``label``, ``description`` and
  ``preview`` are scanned, with fenced blocks in a preview left out. Any shorthand denies the
  call, quoting up to five matches. ``answers``, ``annotations`` and ``metadata`` are never
  scanned.
- **Stop** (settings flag ``plain_language_stop``). ``last_assistant_message`` is scanned with
  its fenced blocks and its Sources part left out. Any shorthand sends the reply back once for a
  plain rewrite. Skipped when ``stop_hook_active`` is true, the rewrite's own stop.

The Sources part runs from the last standalone Sources heading to the end, when no later markdown
heading at the same level or above follows it. Without such a heading, it is the reply's trailing
run of blank lines, list items and lines that open with the word.

Shorthand is one pattern list shared by both events: the project's own id prefixes from
settings, issue and pull-request numbers, comment numbers, file names with a code or document
extension, paths, line and section citations, and commit hashes. URLs are removed first, so a
link never matches. Every pattern starts at a token boundary and has no nested quantifier, so the
scan stays linear in the text's length.

Fail-open policy: this guards quality, not security. An internal error prints one stderr line
starting ``plain_language:`` and exits 1, which Claude Code treats as a non-blocking error.
"""

from __future__ import annotations

import functools
import json
import re
import sys
from collections.abc import Iterable, Mapping
from typing import Any

import pm_settings

PREFIX = "plain_language"

RULE_LINE = "Rule: the plain-language rule of the project-manager method."

MAX_QUOTED = 5

FILE_EXTENSIONS = (
    "py", "rs", "go", "c", "h", "cpp", "hpp", "cc", "java", "kt", "rb", "php", "cs", "swift",
    "md", "rst", "json", "yml", "yaml", "toml", "ini", "cfg", "sh", "zsh", "bash", "ts", "tsx",
    "js", "jsx", "mjs", "svelte", "vue", "lock", "feature", "html", "css", "scss", "sql", "txt",
)  # fmt: skip

TECH_NAME_ALLOWLIST = (
    "Node.js",
    "Next.js",
    "Vue.js",
    "Nuxt.js",
    "Three.js",
    "Chart.js",
    "D3.js",
)

PATH_PREFIXES = ("./", "../", "~/")

ABSOLUTE_PATH_ROOTS = (
    "home", "tmp", "etc", "usr", "var", "run", "opt", "root", "mnt", "srv", "proc", "dev", "sys",
    "Users", "Library", "Applications", "private", "Volumes",
)  # fmt: skip

LINK_DOMAIN_SUFFIXES = (
    "com", "org", "net", "io", "ai", "dev", "app", "co", "gg", "me", "edu", "gov", "uk", "de",
)  # fmt: skip

PATH_MARKER_CHARS = frozenset("_-.")

_LINK_CHARS = r"[^\s`'\"()<>\[\]]"
URL_PATTERN = re.compile(
    r"https?://\S+"
    r"|(?<![^\s`'\"(<\[*_])(?:www\.|[^\s/`'\"()<>\[\]*_]*\.(?:"
    + "|".join(LINK_DOMAIN_SUFFIXES)
    + r")/)"
    + _LINK_CHARS
    + "*",
    re.IGNORECASE,
)

_EXT = "|".join(FILE_EXTENSIONS)

GENERIC_PATTERNS = (
    # Two or more digits: `#1` is an ordinal, `#12` is an issue or pull request. Exactly six
    # digits reads as a colour, such as `#112233`, and passes.
    re.compile(r"(?<![\w&])#(?!\d{6}(?!\w))\d{2,}(?!\w)"),
    re.compile(r"(?<![\w-])PR ?#?\d+(?!\w)"),
    re.compile(r"(?<![\w-])comment ?#?\d+(?!\w)", re.IGNORECASE),
    re.compile(r"(?<![\w.-])[\w.-]*\w\.(?i:" + _EXT + r")(?![\w-])(?::\d+(?:-\d+)?)?"),
    re.compile(r"(?<![\w-])lines? \d+(?: ?[-–] ?\d+)?(?!\w)", re.IGNORECASE),
    re.compile(r"(?<![\w-])L\d{2,}(?!\w)"),
    re.compile(r"§ ?\d+(?:\.\d+)*"),
    # A commit hash: 7 to 40 hex characters holding at least one digit and one letter, so words
    # such as "defaced" pass.
    re.compile(
        r"(?<![\w-])(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w-])"
    ),
)

_TOKEN_PATTERN = re.compile(r"[^\s`'\"()<>\[\]{}|,;*]+")
_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_SOURCES_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:[-*+]|\d+[.)])\s+)?[*_]{0,3}sources?[*_]{0,3}:?[*_]{0,3}\s*$",
    re.IGNORECASE,
)
_MARKDOWN_HEADING = re.compile(r"^\s*(#{1,6})\s")
_SOURCES_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:[-*+]|\d+[.)])\s+)?[*_]{0,3}sources?(?:\s*$|\s*:|[*_]+(?:\s|:|$))",
    re.IGNORECASE,
)

_PREFIX_SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9]{0,15}")


class ShapeError(Exception):
    """The hook input does not have the shape this hook was written for."""


class Scanner:
    """Finds shorthand in text, using the project's own id prefixes and top-level folders."""

    def __init__(self, shorthand: pm_settings.Shorthand) -> None:
        """Build the pattern list for one project.

        Args:
            shorthand: The project's id prefixes and top-level folder names.
        """
        prefixes = [p for p in shorthand.id_prefixes if _PREFIX_SHAPE.fullmatch(p)]
        patterns = list(GENERIC_PATTERNS)
        if prefixes:
            joined = "|".join(re.escape(p) for p in prefixes)
            patterns.insert(
                0, re.compile(r"(?<![\w-])(?:" + joined + r")-\d+(?![\w-])")
            )
        self._patterns = tuple(patterns)
        self._top_level = frozenset(shorthand.top_level_dirs)
        self._allow = frozenset(name.lower() for name in TECH_NAME_ALLOWLIST)
        self.is_path = functools.lru_cache(maxsize=4096)(self._is_path)

    def _is_path(self, token: str) -> bool:
        if "/" not in token:
            return False
        for prefix in PATH_PREFIXES:
            if token.startswith(prefix) and len(token) > len(prefix):
                return True
        segments = token.split("/")
        if token.startswith("/"):
            return (
                segments[1] in ABSOLUTE_PATH_ROOTS
                and len(segments) >= 3
                and bool(segments[2])
            )
        if segments[0] in self._top_level and len(segments) >= 2 and segments[1]:
            return True
        with_letters = [s for s in segments if any(c.isalpha() for c in s)]
        return (
            len(with_letters) >= 3
            and all(segments)
            and any(c in PATH_MARKER_CHARS for c in token)
        )

    def find(self, text: str) -> list[str]:
        """Every shorthand snippet in ``text``, distinct, in order of first appearance.

        Args:
            text: The text to scan.

        Returns:
            The snippets found, longest first where two start at the same place, with any
            snippet that lies inside an earlier one dropped.
        """
        text = URL_PATTERN.sub(" ", text)
        found: list[tuple[int, str]] = []

        def collect(matches: Iterable[tuple[int, str]]) -> None:
            mine: set[str] = set()
            for start, snippet in matches:
                if snippet in mine or snippet.lower() in self._allow:
                    continue
                mine.add(snippet)
                found.append((start, snippet))
                if len(mine) >= MAX_QUOTED:
                    return

        for pattern in self._patterns:
            collect((m.start(), m.group()) for m in pattern.finditer(text))
        tokens = (
            (m.start(), m.group().rstrip(".:!?")) for m in _TOKEN_PATTERN.finditer(text)
        )
        collect((start, token) for start, token in tokens if self.is_path(token))
        seen: dict[str, None] = {}
        covered_to = -1
        for start, snippet in sorted(found, key=lambda item: (item[0], -len(item[1]))):
            end = start + len(snippet)
            if end <= covered_to:
                continue
            covered_to = end
            seen.setdefault(snippet)
        return list(seen)


def unfenced_lines(text: str) -> list[str]:
    """The lines of ``text`` outside fenced code blocks. An unclosed fence runs to the end.

    Args:
        text: Markdown text.

    Returns:
        The lines that sit outside every fenced block.
    """
    kept: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        if fence is not None:
            stripped = line.strip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            continue
        opening = _FENCE_OPEN.match(line)
        if opening:
            fence = opening.group(1)
            continue
        kept.append(line)
    return kept


def sources_start(lines: list[str]) -> int:
    """The index where the Sources part of ``lines`` begins, or ``len(lines)`` when none.

    Args:
        lines: A reply's lines, fenced blocks already removed.

    Returns:
        The first line index of the Sources part.
    """
    headings = [i for i, line in enumerate(lines) if _SOURCES_HEADING.match(line)]
    if headings:
        own = _MARKDOWN_HEADING.match(lines[headings[-1]])
        level = len(own.group(1)) if own else 6
        later = (
            _MARKDOWN_HEADING.match(line)
            for line in lines[headings[-1] + 1 :]
            if not _SOURCES_HEADING.match(line)
        )
        if not any(match and len(match.group(1)) <= level for match in later):
            return headings[-1]
    start = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if _SOURCES_LINE.match(line):
            start = i
        elif line.strip() and not _LIST_ITEM.match(line):
            break
    return start


def reply_text(message: str) -> str:
    """``message`` without its fenced code blocks and its Sources part.

    Args:
        message: A finished reply.

    Returns:
        The text the decider reads as prose.
    """
    lines = unfenced_lines(message)
    return "\n".join(lines[: sources_start(lines)])


def _quoted(snippets: list[str]) -> str:
    return ", ".join(f'"{s}"' for s in snippets[:MAX_QUOTED])


def deny_reason(snippets: list[str]) -> str:
    """The reason given when a question is refused.

    Args:
        snippets: The shorthand found.

    Returns:
        A one-paragraph instruction to rewrite the question.
    """
    return (
        f"This question carries internal shorthand: {_quoted(snippets)}. Rewrite the question "
        "and its options in plain words, saying what each thing is. Put ids, file names and "
        "citations in the chat text under a Sources heading, never in the question. "
        + RULE_LINE
    )


def block_reason(snippets: list[str]) -> str:
    """The reason given when a finished reply is sent back.

    Args:
        snippets: The shorthand found.

    Returns:
        A one-paragraph instruction to rewrite the reply.
    """
    return (
        "This reply carries internal shorthand outside code blocks and the Sources part: "
        f"{_quoted(snippets)}. Write a plain rewrite of the reply below it, moving ids, file "
        "names and citations under a Sources heading at the end. Put drafts shown for approval "
        "in a fenced block. Run no tools and redo no work; this is a rewrite only. "
        + RULE_LINE
    )


def _text_field(container: Mapping[str, Any], key: str) -> str:
    value = container.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ShapeError(f"{key} is not a string")
    return value


def question_texts(tool_input: object) -> list[str]:
    """The scanned text of every question in an ``AskUserQuestion`` tool input.

    Args:
        tool_input: The tool call's input.

    Returns:
        Each scanned field's text.

    Raises:
        ShapeError: When the input is not shaped like an ``AskUserQuestion`` call.
    """
    if not isinstance(tool_input, dict) or not isinstance(
        tool_input.get("questions"), list
    ):
        raise ShapeError("tool_input.questions is not a list")
    texts: list[str] = []
    for question in tool_input["questions"]:
        if not isinstance(question, dict):
            raise ShapeError("a question is not an object")
        texts += [_text_field(question, "question"), _text_field(question, "header")]
        options = question.get("options") or []
        if not isinstance(options, list):
            raise ShapeError("options is not a list")
        for option in options:
            if not isinstance(option, dict):
                raise ShapeError("an option is not an object")
            texts += [_text_field(option, "label"), _text_field(option, "description")]
            texts.append("\n".join(unfenced_lines(_text_field(option, "preview"))))
    return texts


def decide(
    payload: object, env: Mapping[str, str] | None = None
) -> dict[str, Any] | None:
    """The output document for one hook input, or ``None`` to let it through silently.

    Args:
        payload: The decoded hook input.
        env: The environment to read ``CLAUDE_PROJECT_DIR`` from. Defaults to ``os.environ``.

    Returns:
        The hook's JSON output, or ``None``.

    Raises:
        ShapeError: When the input is not shaped like a hook input this script handles.
    """
    if not isinstance(payload, dict):
        raise ShapeError("input is not a JSON object")
    event = payload.get("hook_event_name")
    if event == "PreToolUse" and payload.get("tool_name") == "AskUserQuestion":
        settings = pm_settings.enabled_settings("question_check", PREFIX, env)
        if settings is None:
            return None
        scanner = Scanner(settings.shorthand)
        texts = question_texts(payload.get("tool_input"))
        snippets = list(dict.fromkeys(s for text in texts for s in scanner.find(text)))
        if not snippets:
            return None
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_reason(snippets),
            }
        }
    if event == "Stop":
        if payload.get("stop_hook_active") is True:
            return None
        settings = pm_settings.enabled_settings("plain_language_stop", PREFIX, env)
        if settings is None:
            return None
        message = _text_field(payload, "last_assistant_message")
        snippets = Scanner(settings.shorthand).find(reply_text(message))
        if not snippets:
            return None
        return {"decision": "block", "reason": block_reason(snippets)}
    return None


def main() -> int:
    """Read one hook input on stdin and write the hook's output, if any, on stdout.

    Returns:
        0 normally, 1 after an internal error, which Claude Code treats as non-blocking.
    """
    try:
        output = decide(json.loads(sys.stdin.read()))
    except Exception as exc:  # noqa: BLE001 -- fail open on any internal error
        detail = " ".join(str(exc).split())
        print(
            f"{PREFIX}: check skipped after an internal error: {detail}",
            file=sys.stderr,
        )
        return 1
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
