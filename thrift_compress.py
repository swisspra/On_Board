"""Vendored token-thrift text transform.

This module intentionally exposes only pure text -> text helpers.  CLI, file
walking, backup, and token-estimation code from the upstream script are not
vendored into the MCP server.
"""

import re

BUDGETS = ("lossless", "verbatim", "light", "medium", "aggressive")
_PROTECTED = (
    re.compile(r"`[^`]*`"),
    re.compile(r"https?://\S+"),
    re.compile(r"(?<!\w)(?:~|\.{0,2}/|[A-Za-z]:\\)[\w./\\-]+"),
    re.compile(r"\$\{?[A-Z_][A-Z0-9_]*\}?"),
    re.compile(r"\b\d[\d,._:-]*\b"),
)
_MASK = re.compile("\x00([\ue000-\uf8ff])\x00")
_PHRASES = tuple((re.compile(p, re.I), s) for p, s in (
    (r"\bat this point in time\b", "now"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bin order to\b", "to"),
    (r"\bmake sure that\b", "ensure"),
    (r"\butilize\b", "use"),
    (r"\bdatabase\b", "DB"),
    (r"\bauthentication\b", "auth"),
    (r"\bconfiguration\b", "config"),
    (r"\brepository\b", "repo"),
    (r"\benvironment\b", "env"),
))
_FILLER = re.compile(r"\b(?:just|really|basically|actually|simply|quite|very|pretty)\b", re.I)
_PLEASANT = re.compile(r"\b(?:kindly|please)\b", re.I)
_LEADIN = re.compile(r"\b(?:please\s+)?(?:make sure to|remember to|always remember to|you should probably|might want to)\b", re.I)
_ARTICLES = re.compile(r"\b(?:a|an|the)\s+", re.I)
_MULTISPACE = re.compile(r"[ \t]{2,}")
_PUNCT_SPACE = re.compile(r"\s+([,.;:!?])")
_BOILER = re.compile(r"^\s*(?:hope this helps|let me know if|feel free to|thanks(?:!|\.)?)\b.*$", re.I)


def _mask(line: str, store: list[str]) -> str:
    def replace(match: re.Match) -> str:
        store.append(match.group(0))
        return "\x00" + chr(0xE000 + len(store) - 1) + "\x00"
    for pattern in _PROTECTED:
        line = pattern.sub(replace, line)
    return line


def _unmask(line: str, store: list[str]) -> str:
    return _MASK.sub(lambda m: store[ord(m.group(1)) - 0xE000], line)


def protected_tokens(text: str) -> list[str]:
    """Return protected code/path/URL/variable spans for fidelity checks."""
    tokens = []
    for pattern in _PROTECTED[:4]:
        tokens.extend(pattern.findall(text))
    return tokens


def _rank(budget: str) -> int:
    return BUDGETS.index(budget)


def _compress_line(line: str, budget: str, keep_articles: bool) -> str:
    store: list[str] = []
    line = _mask(line, store)
    if _rank(budget) >= _rank("light"):
        line = _LEADIN.sub("", line)
        line = _PLEASANT.sub("", line)
    if _rank(budget) >= _rank("medium"):
        line = _FILLER.sub("", line)
        for pattern, replacement in _PHRASES:
            line = pattern.sub(replacement, line)
        if not keep_articles and not line.lstrip().startswith("#"):
            line = _ARTICLES.sub("", line)
    line = _MULTISPACE.sub(" ", line)
    line = _PUNCT_SPACE.sub(r"\1", line).rstrip()
    return _unmask(line, store)


def compress(text: str, budget: str = "medium", keep_articles: bool = False) -> str:
    """Compress text while preserving frontmatter, code, tables, and tokens."""
    if budget not in BUDGETS:
        raise ValueError(f"budget must be one of {list(BUDGETS)}")
    lines = text.split("\n")
    frontmatter_end = None
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                frontmatter_end = index
                break
    output: list[str] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if frontmatter_end is not None and index <= frontmatter_end:
            output.append(line)
            continue
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence or stripped.startswith("|"):
            output.append(line)
            continue
        if _rank(budget) >= _rank("verbatim") and _BOILER.match(line):
            continue
        output.append(line if budget == "lossless" else _compress_line(line, budget, keep_articles))

    result: list[str] = []
    previous = None
    blank = False
    for line in output:
        if not line.strip():
            if blank:
                continue
            blank = True
            previous = None
        else:
            blank = False
            if line == previous:
                continue
            previous = line
        result.append(line)
    while result and not result[-1].strip():
        result.pop()
    return "\n".join(result) + "\n"


def compress_digest(text: str, budget: str = "medium") -> str:
    """Compress digest body while keeping markdown titles/headings verbatim."""
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("##"):
            lines.append(line)
            continue
        match = re.match(r"^(.*?\*\*.*?\*\*)(.*)$", line)
        if match:
            lines.append(match.group(1) + compress(match.group(2), budget).rstrip("\n"))
        else:
            lines.append(compress(line, budget).rstrip("\n"))
    return "\n".join(lines) + "\n"


def fidelity(source: str, compressed: str) -> float:
    """Return the fraction of protected spans still present verbatim."""
    tokens = protected_tokens(source)
    return 1.0 if not tokens else sum(token in compressed for token in tokens) / len(tokens)
