"""extract.py - get clean agreement text.

Main entry points
    load_agreement(path)  -> reads a sample file in the project's .md format
                             (# Company / *Collected on ...* / ## Document + Source: url)
    get_text(source)      -> a URL, a .pdf path, a .txt/.md path, or raw pasted text
    clean_text(text)      -> shared cleaning step used by both
"""
import difflib
import html
import re
from pathlib import Path

# Patterns shared with split.py
MD_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
LIST_START = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]\s|\(?(?:[a-z]|[ivx]{2,4})[.)]\s|[-*\u2022]\s|#{1,6}\s)")
BOLD_ONLY = re.compile(r"^\s*(?:\*\*|__)[^*_\n]{2,100}(?:\*\*|__)\s*:?\s*$")

ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9 ,&'\-/()]{5,80}$")
_BOLD_TITLE = re.compile(r"^\s*(?:\d+[.)]\s+)?(?:\*\*|__)(.+?)(?:\*\*|__)")

_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_RULE = re.compile(r"^\s*([-=])\1{2,}\s*$")  # '-----' or '=====' under a title, or a horizontal rule
# web-page chrome: words glued together by the page layout ('PolicyYour resource', 'Snapchat.Community')
_GLUE = re.compile(r"(?:[a-z]{3,}|[.!?)])[A-Z][a-z]{2,}")
_BULLET = re.compile(r"^\s*[-*\u2022]\s+(.+?)\s*$")


def _drop_toc(text):
    """Remove 'table of contents' bullet runs that just repeat headings or bold titles."""
    lines = text.split("\n")
    titles = set()
    for ln in lines:
        m = MD_HEADING.match(ln) or _BOLD_TITLE.match(ln)
        if m:
            titles.add(m.group(1).strip().rstrip(":").lower())
    if not titles:
        return text
    is_bullet = [bool(_BULLET.match(ln)) for ln in lines]
    keep = []
    for i, ln in enumerate(lines):
        in_run = is_bullet[i] and ((i > 0 and is_bullet[i - 1]) or (i + 1 < len(lines) and is_bullet[i + 1]))
        if in_run and difflib.get_close_matches(_BULLET.match(ln).group(1).lower(), titles, n=1, cutoff=0.8):
            continue
        keep.append(ln)
    return "\n".join(keep)


def _caps_like(line):
    """True for a line that is (nearly) all capitals, even a long one: part of a wrapped CAPS paragraph."""
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 10 and sum(c.isupper() for c in letters) / len(letters) >= 0.9


def _setext(lines):
    """'Title' directly followed by '-----' / '=====' is a heading; any such rule line is dropped."""
    out = []
    for ln in lines:
        if _RULE.match(ln):
            prev = out[-1].strip() if out else ""
            if prev and len(prev) <= 100 and not prev.endswith(".") and not LIST_START.match(prev):
                out[-1] = "## " + prev
            continue
        out.append(ln)
    return out


def _is_chrome(line):
    """A navigation/menu line copied from the web page, not agreement text."""
    s = line.strip()
    if s.count(" + ") >= 3:  # 'Privacy + Privacy Center + Privacy Principles + ...'
        return True
    if len(_GLUE.findall(s)) >= 2:
        return True
    m = MD_HEADING.match(s)
    if m:
        t = m.group(1).strip()
        return " " not in t and len(t) >= 18 and t.isupper()  # 'NEWSINVESTORSCAREERS'
    return False


def _is_link_line(line):
    """A line that looks like part of a footer link list."""
    s = line.strip()
    if not s or _RULE.match(s):
        return True
    m = MD_HEADING.match(s)
    if m:
        return len(m.group(1).split()) <= 3  # '## Legal', '## Company'
    b = _BULLET.match(s)
    if b:
        words = len(b.group(1).split())
        return words <= 6 and (words <= 3 or not b.group(1).endswith(".")) and not b.group(1).endswith(":")
    if re.match(r"^[A-Z][\w &]{2,30}: [-*\u2022] ", s):  # 'Advertising: * Snapchat Ads'
        return True
    return len(s.split()) <= 3 and not s.endswith(".")  # 'English (US)'


def _strip_footer(lines):
    """Remove a footer link list (6+ link-like lines) at the very end. Needs one line per link, so it runs before unwrapping."""
    i = len(lines)
    while i > 0 and _is_link_line(lines[i - 1]):
        i -= 1
    return lines[:i] if sum(1 for ln in lines[i:] if ln.strip()) >= 6 else lines


def clean_text(text, unwrap=True):
    """Normalise line endings, strip HTML tags, drop TOC bullets, re-join hard-wrapped lines.

    After cleaning, every paragraph or list item sits on ONE line, and blank lines
    separate blocks. split.py relies on that.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = html.unescape(_TAG.sub("", text))
    text = _drop_toc(text)
    # collapse runs of spaces inside a line (but keep leading indentation)
    lines = _strip_footer(_setext([re.sub(r"(?<=\S)[ \t]{2,}", " ", ln.rstrip()) for ln in text.split("\n")]))
    if unwrap:
        # an ALL-CAPS line is a title only if the next line is not also ALL-CAPS
        # (otherwise it is one line of a hard-wrapped capitals paragraph)
        title = [
            bool(ALL_CAPS.match(ln))
            and not (i + 1 < len(lines) and (ALL_CAPS.match(lines[i + 1]) or _caps_like(lines[i + 1])))
            for i, ln in enumerate(lines)
        ]
        out, out_title = [], []
        for ln, is_title in zip(lines, title):
            continues = (
                out
                and ln.strip()
                and out[-1].strip()
                and not LIST_START.match(ln)
                and not BOLD_ONLY.match(ln)
                and not BOLD_ONLY.match(out[-1])
                and not MD_HEADING.match(out[-1].strip())
                and not is_title
                and not out_title[-1]
            )
            if continues:
                out[-1] = out[-1] + " " + ln.strip()
            else:
                out.append(ln)
                out_title.append(is_title)
        lines = out
    lines = [ln for ln in lines if not _is_chrome(ln)]  # menus and glued navigation text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _next_nonblank(lines, i):
    while i < len(lines) and not lines[i].strip():
        i += 1
    return i


def load_agreement(path):
    """Parse one sample file.

    Returns {"company", "collected", "documents": [{"title", "source", "text"}]}.
    A '## Title' line starts a new document only if the next non-blank line is
    'Source: <url>'; other '##' lines are ordinary sections inside the document.
    A file without that structure is treated as a single document.
    """
    path = Path(path)
    lines = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
    company, collected, docs, cur = path.stem, None, [], None

    i = 0
    while i < len(lines):
        ln = lines[i]
        j = _next_nonblank(lines, i + 1)
        if ln.startswith("## ") and j < len(lines) and lines[j].startswith("Source:"):
            cur = {"title": ln[3:].strip(), "source": lines[j].split(":", 1)[1].strip(), "lines": []}
            docs.append(cur)
            i = j + 1
            continue
        if cur is None:
            m = re.match(r"#\s+(.+)", ln)
            if m:
                company = m.group(1).strip()
            m = re.match(r"\*Collected on (.+?)\*", ln)
            if m:
                collected = m.group(1).strip()
        else:
            cur["lines"].append(ln)
        i += 1

    if not docs:  # plain file: treat everything as one document
        docs = [{"title": company, "source": "", "lines": lines}]

    documents = [
        {"title": d["title"], "source": d["source"], "text": clean_text("\n".join(d["lines"]))}
        for d in docs
    ]
    return {"company": company, "collected": collected, "documents": documents}


# ---------- other input types (URL / PDF / raw text) ----------

def _read_pdf(path):
    import pdfplumber  # pip install pdfplumber

    with pdfplumber.open(path) as pdf:
        return "\n\n".join((page.extract_text() or "") for page in pdf.pages)


def _fetch_url(url):
    import requests  # pip install requests trafilatura beautifulsoup4

    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    try:
        import trafilatura

        main = trafilatura.extract(resp.text, include_comments=False)
        if main:
            return "\n\n".join(ln for ln in main.splitlines() if ln.strip())
    except ImportError:
        pass
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    return "\n\n".join(ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip())


def get_text(source):
    """Return cleaned text from a URL, a PDF path, a text/markdown path, or raw text.

    Sites that load their terms with JavaScript return little or nothing here;
    paste the text instead.
    """
    s = str(source).strip()
    if re.match(r"https?://\S+$", s):
        return clean_text(_fetch_url(s), unwrap=False)
    if "\n" not in s and len(s) < 500 and Path(s).is_file():
        p = Path(s)
        if p.suffix.lower() == ".pdf":
            return clean_text(_read_pdf(p))
        return clean_text(p.read_text(encoding="utf-8-sig"))
    return clean_text(s)
