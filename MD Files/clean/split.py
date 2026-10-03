"""split.py - split cleaned agreement text into clauses.

split_clauses(text, default_heading="") -> [{"id", "heading", "text"}, ...]

Layers (in order):
 1. Boundaries - a new clause starts at:
      markdown headings ('## ...')            (a "heading" that is really a sentence is body text)
      numbered items   ('1.', '2.3)')         lettered items ('a.', '(b)', 'iv.')
      bold titles      ('**Privacy** ...')    short ALL-CAPS lines
      plain title lines ('Communications', 'Consent to advertisements:')
    Items without a title of their own are named after their first words, never 'Item 3'.
    Lettered / untitled numbered items are named 'Parent title > item title'.
 2. Text before the first boundary of a section is split paragraph by paragraph.
    A bullet list always stays with the line that introduces it, and a lead-in line
    ending in ':' always moves forward to the list or item it introduces.
 3. Chunks under MIN_LEN characters are merged into a neighbour.
 4. Chunks over MAX_LEN are split at paragraph/list-item breaks, then at sentence breaks,
    never leaving a bullet list or a ':' lead-in stranded at a cut.

Expects text from extract.clean_text(): one paragraph or list item per line.
Indented lines (2+ spaces) are treated as sub-items and stay inside their parent clause.
"""
import math
import re

from extract import ALL_CAPS, MD_HEADING

MIN_LEN = 150
MAX_LEN = 1500
HEADING_MAX = 100          # a longer markdown "heading" is really a sentence
TITLE_MAX_CHARS = 80       # longest line still accepted as a title
TITLE_MAX_WORDS = 12
COLON_TITLE_MAX_WORDS = 6  # 'Consent to advertisements:' is a title; a long lead-in is not
SNIPPET_WORDS = 8
LEAD_IN_MAX = 200          # a lead-in longer than this is not repeated when a list is cut

BULLET_LINE = re.compile(r"^[-*\u2022]\s+")
NUMBERED = re.compile(r"^(?P<num>\d+(?:\.\d+)*)[.)]\s+(?P<rest>\S.*)$")
LETTERED = re.compile(r"^\(?(?P<num>[a-z]|[ivx]{2,4})[.)]\s+(?P<rest>\S.*)$")
BOLD_START = re.compile(r"^(?:\*\*|__)(?P<title>[^*_\n]{2,80}?)(?:\*\*|__)\s*:?\s*(?P<body>.*)$")
BOLD_LABEL = re.compile(r"^(?:\*\*|__)(?P<num>\d+(?:\.\d+)*|[a-z]{1,4})[.)](?:\*\*|__)\s*(?P<rest>\S.*)$")
LABEL_PREFIX = re.compile(r"^\(?(?:\d+(?:\.\d+)*|[a-z]|[ivx]{2,4})[.)]\s+")
FIRST_SENTENCE = re.compile(r"^(?P<t>[^.:!?]{2,80}?)[.:]\s+(?P<body>\S.*)$")
ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")

_STOPWORDS = {"a", "an", "and", "or", "of", "to", "the", "for", "in", "on", "by", "with", "at",
              "from", "as", "vs", "per", "is", "&"}
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "inc.", "ltd.", "pvt.", "co.", "mr.", "mrs.", "dr.", "u.s.", "vs.", "cf.")
_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[\"\u201c'(\[]?[A-Z0-9])")
_QUOTES = "(\"'\u201c\u2018"


# ---------- helpers ----------

def _plain(s):
    """Remove markdown emphasis markers (**bold**, *italic*)."""
    return ITALIC.sub(r"\1", s.replace("**", ""))


def _snippet(text, words=SNIPPET_WORDS):
    parts = text.split()
    out = " ".join(parts[:words]).rstrip(" ,;:.-")
    return out + "\u2026" if len(parts) > words else out


def _looks_like_title(text):
    """Short, no sentence punctuation or date, every content word capitalised: 'Platform for Transaction and Communication'."""
    t = text.strip()
    if (not t or len(t) > TITLE_MAX_CHARS or t[-1] in ".!?;,:" or re.search(r"[:|]|https?://|www\.|@", t)
            or re.search(r"\b(?:19|20)\d{2}\b", t)):
        return False
    words = t.split()
    if len(words) > TITLE_MAX_WORDS or not any(ch.isalpha() for ch in t):
        return False
    content = [w for w in words if w.lower() not in _STOPWORDS and any(ch.isalnum() for ch in w)]
    if not content:
        return False
    first = [w.lstrip(_QUOTES)[:1] for w in content]
    return first[0].isupper() and all(ch.isupper() or ch.isdigit() for ch in first)


def _lead_title(rest):
    """'General. The service...' or '**General.** The service...' -> ('General', 'The service...')."""
    b = BOLD_START.match(rest)
    if b:
        return b.group("title").strip().rstrip(".:"), b.group("body").strip()
    m = FIRST_SENTENCE.match(rest)
    if m and _looks_like_title(m.group("t")):
        return m.group("t").strip(), m.group("body").strip()
    return None


def _item(rest, titled_level):
    """A numbered or lettered item -> (heading, body, level, real_title)."""
    lead = _lead_title(rest)
    if lead:
        return lead[0], lead[1], titled_level, True
    if (len(rest) <= TITLE_MAX_CHARS and len(rest.split()) <= TITLE_MAX_WORDS and "," not in rest
            and not rest.endswith((".", ":", ";", ","))):
        return rest.strip(), "", titled_level, True  # short line on its own = a title like '1. Definitions'
    return _snippet(rest), rest, "sub", False  # no title of its own: name it after its first words


# ---------- layer 1 and 2: boundaries ----------

def _boundary(line, prev="", nxt=""):
    """If this line starts a new clause return (heading, body, level, real_title); otherwise None.

    level is 'top' (sets the parent title for what follows) or 'sub' (an item inside a parent).
    real_title is False when the heading is only the item's first words.
    """
    if len(line) - len(line.lstrip()) >= 2:  # indented = sub-item
        return None
    line = line.strip()
    if BULLET_LINE.match(line):
        return None
    m = BOLD_LABEL.match(line)  # '**g.** Disputes...' -> 'g. Disputes...'
    if m:
        line = f"{m.group('num')}. {m.group('rest')}"
    m = NUMBERED.match(line)
    if m:
        return _item(m.group("rest"), "top")
    m = LETTERED.match(line)
    if m:
        return _item(m.group("rest"), "sub")
    b = BOLD_START.match(line)
    if b:
        title, body = b.group("title").strip(), b.group("body").strip()
        label = LABEL_PREFIX.match(title)  # '**d. Cancellation.**' = an item written all in bold
        if label:
            level = "top" if title[0].isdigit() else "sub"
            return title[label.end():].strip().rstrip(".:"), body, level, True
        return title.rstrip(":"), body, "top", True
    if ALL_CAPS.match(line):
        return line, "", "top", True
    if prev.endswith(":") or not nxt:  # a line after a lead-in is a list item, not a title
        return None
    if line.endswith(":"):
        t = line[:-1].strip()
        if t[:1].isupper() and len(t.split()) <= COLON_TITLE_MAX_WORDS and not re.search(r"[,|]|https?://", t):
            return t, "", "top", True
        return None
    if _looks_like_title(line):
        return line, "", "top", True
    return None


def _is_title(text):
    """A real markdown heading is short and is not a sentence."""
    return len(text) <= HEADING_MAX and not text.endswith(".")


def _sections(text):
    """Split into [(markdown_heading, [lines])]."""
    sections, title, lines = [], "", []
    for ln in text.split("\n"):
        m = MD_HEADING.match(ln)
        if m and _is_title(m.group(1).strip()):
            sections.append((title, lines))
            title, lines = m.group(1).strip(), []
        elif m:
            lines.append(m.group(1).strip())  # sentence written as a heading: keep it as text
        else:
            lines.append(ln)
    sections.append((title, lines))
    return [(t, ls) for t, ls in sections if any(x.strip() for x in ls)]


def _compose(parent, heading):
    """'Parent > heading', with a long parent shortened so headings stay readable."""
    if not parent:
        return heading
    if len(parent) > 40:
        parent = parent[:40].rsplit(" ", 1)[0].rstrip(" ,;:.-") + "\u2026"
    return f"{parent} > {heading}"


def _blocks(section, lines):
    lines = [ln for ln in lines if ln.strip()]
    blocks, cur, parent = [], None, section

    def flush():
        if cur is not None:
            blocks.append({"section": section, "heading": cur["heading"], "title": cur["title"],
                           "text": "\n".join(cur["lines"]).strip()})

    for i, ln in enumerate(lines):
        prev = lines[i - 1].strip() if i else ""
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        start = _boundary(ln, prev, nxt)
        if start:
            title, body, level, real = start
            carry = None
            if cur is not None and len(cur["lines"]) > 1 and cur["lines"][-1].endswith(":"):
                carry = cur["lines"].pop()  # a lead-in belongs to the item that follows it
            flush()
            if level == "top":
                parent, heading = title, title
            else:
                heading = _compose(parent, title)
            cur = {"title": title if real else "", "heading": heading, "headed": True,
                   "lines": ([carry] if carry else []) + ([body] if body else [])}
        elif cur is not None and not cur["headed"] and (
            BULLET_LINE.match(ln.strip()) or cur["lines"][-1].endswith(":")
        ):
            cur["lines"].append(ln.strip())  # list items stay with the line that introduces them
        elif cur is None or not cur["headed"]:
            flush()  # paragraph before the first boundary: one block per paragraph
            cur = {"title": "", "heading": "", "headed": False, "lines": [ln.strip()]}
        else:
            cur["lines"].append(ln.strip())
    flush()
    return blocks


# ---------- layer 3: merge short ----------

def _join(a, b):
    b_text = f"{b['title']}: {b['text']}" if b["title"] and b["text"] else (b["title"] or b["text"])
    text = "\n\n".join(p for p in (a["text"], b_text) if p)
    return {"section": a["section"], "heading": a["heading"] or b["heading"],
            "title": a["title"] or b["title"], "text": text}


def _can_merge(a, b, max_len, same_section):
    if same_section and a["section"] != b["section"]:
        return False
    return len(a["text"]) + len(b["text"]) + len(b["title"]) + 4 <= max_len


def _merge_short(blocks, min_len, max_len, same_section):
    """Merge each short block into the shorter of its neighbours.

    A block with no body text (just a title), or one that ends in ':' (a lead-in),
    always goes forward, onto what it introduces.
    """
    blocks, i = list(blocks), 0
    while i < len(blocks):
        b = blocks[i]
        leads = b["text"].rstrip().endswith(":")
        if len(b["text"]) >= min_len and not leads:
            i += 1
            continue
        prev = blocks[i - 1] if i > 0 and _can_merge(blocks[i - 1], b, max_len, same_section) else None
        nxt = blocks[i + 1] if i + 1 < len(blocks) and _can_merge(b, blocks[i + 1], max_len, same_section) else None
        if nxt and (not b["text"] or leads or not prev or len(nxt["text"]) <= len(prev["text"])):
            blocks[i:i + 2] = [_join(b, nxt)]
        elif prev and not leads:
            blocks[i - 1:i + 1] = [_join(prev, b)]
            i -= 1
        else:
            i += 1
    return blocks


# ---------- layer 4: split long ----------

def _sentences(text):
    parts, start = [], 0
    for m in _SENT_END.finditer(text):
        if text[start:m.start()].lower().endswith(_ABBREVIATIONS):
            continue  # 'e.g.' / 'Inc.' etc. are not sentence ends
        parts.append(text[start:m.start()])
        start = m.end()
    parts.append(text[start:])
    return [p for p in parts if p.strip()]


def _hard_wrap(text, max_len):
    """Last resort for a single sentence longer than max_len: cut at spaces."""
    words, parts, cur = text.split(" "), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_len:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        parts.append(cur)
    return parts


def _break_long(sentence, max_len):
    """A single sentence over max_len: split at semicolons, then (last resort) at spaces."""
    pieces = []
    for chunk in re.split(r"(?<=;)\s+", sentence):
        pieces.extend(_hard_wrap(chunk, max_len) if len(chunk) > max_len else [chunk])
    return pieces


def _split_long(text, max_len):
    if len(text) <= max_len:
        return [text]
    units = []  # (text, joiner placed before it when packed)
    for para in (p.strip() for p in text.split("\n") if p.strip()):
        if len(para) <= max_len:
            units.append((para, "\n"))
            continue
        for k, sent in enumerate(_sentences(para)):
            for j, piece in enumerate(_break_long(sent, max_len) if len(sent) > max_len else [sent]):
                units.append((piece, "\n" if k == 0 and j == 0 else " "))
    total = sum(len(u) for u, _ in units)
    target = total / math.ceil(total / max_len)  # aim for evenly sized parts
    parts, cur, lead_in = [], "", ""
    for u, joiner in units:
        if not BULLET_LINE.match(u):
            lead_in = u if u.rstrip().endswith(":") else ""  # the line that introduces the bullets below it
        if not cur:
            cur = u
            continue
        overflow = len(cur) + len(joiner) + len(u) > max_len
        # prefer cuts before a normal paragraph: never cut before a bullet or right after a ':' lead-in
        wanted = len(cur) >= target and not BULLET_LINE.match(u) and not cur.rstrip().endswith(":")
        if overflow or wanted:
            lead = ""
            if "\n" in cur and cur.rstrip().rsplit("\n", 1)[1].endswith(":"):
                cur, lead = cur.rstrip().rsplit("\n", 1)  # carry a trailing lead-in over the cut
                lead += joiner
            elif BULLET_LINE.match(u) and lead_in and len(lead_in) <= LEAD_IN_MAX and len(lead_in) + 1 + len(u) <= max_len:
                lead = lead_in + "\n"  # cut inside a list: repeat its lead-in so the part stands alone
            parts.append(cur)
            cur = lead + u
        else:
            cur = f"{cur}{joiner}{u}"
    if cur:
        parts.append(cur)
    return parts


# ---------- public API ----------

def split_clauses(text, min_len=MIN_LEN, max_len=MAX_LEN, default_heading=""):
    blocks = []
    for title, lines in _sections(text):
        blocks.extend(_blocks(title, lines))

    pieces = []
    for b in blocks:
        parts = _split_long(b["text"], max_len)
        for k, part in enumerate(parts, 1):
            heading = b["heading"]
            if len(parts) > 1 and heading:
                heading = f"{heading} (part {k}/{len(parts)})"
            pieces.append({"section": b["section"], "heading": heading, "title": b["title"], "text": part})

    pieces = _merge_short(pieces, min_len, max_len, same_section=True)
    pieces = _merge_short(pieces, min_len, max_len, same_section=False)

    return [
        {
            "id": i,
            "heading": _plain(p["heading"] or p["section"] or default_heading),
            "text": _plain(p["text"]),
        }
        for i, p in enumerate(pieces, 1)
        if p["text"].strip()
    ]


if __name__ == "__main__":
    import statistics
    import sys

    from extract import load_agreement

    for path in sys.argv[1:]:
        agreement = load_agreement(path)
        for doc in agreement["documents"]:
            clauses = split_clauses(doc["text"], default_heading=doc["title"])
            lens = [len(c["text"]) for c in clauses]
            print(f"\n{agreement['company']} / {doc['title']}: {len(clauses)} clauses, "
                  f"min {min(lens)}, median {int(statistics.median(lens))}, max {max(lens)}")
            for c in clauses:
                print(f"  {c['id']:>3}  {len(c['text']):>5}  {c['heading'][:50]:<50}  {c['text'][:50]!r}")
