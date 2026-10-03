#!/usr/bin/env python3
"""
fetch_terms.py
Fetches Terms of Service / EULA documents listed in sources.csv,
extracts the main legal text, and saves one Markdown file per company.

Usage:
    python fetch_terms.py [options]

Options:
    --include-privacy   Also fetch Privacy Policy rows
    --force             Overwrite existing .md files
    --delay N           Seconds between requests (default: 2)
    --timeout N         HTTP request timeout in seconds (default: 30)
    --no-robots         Skip robots.txt checks
"""

import argparse
import csv
import os
import sys
import time
import re
import logging
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

# ── Fix Windows console encoding so Unicode chars don't crash logging ─────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# ── third-party (installed via requirements.txt) ───────────────────────────────
try:
    import requests
    from requests.exceptions import RequestException
except ImportError:
    sys.exit("ERROR: 'requests' not installed. Run: pip install -r requirements.txt")

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ── constants ─────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCES_CSV = SCRIPT_DIR / "sources.csv"
FAILED_TXT  = SCRIPT_DIR / "failed.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# Domains whose robots.txt blocks bots but whose legal pages are explicitly public.
# We skip robots.txt checks for these hosts.
ROBOTS_SKIP_HOSTS = {
    "www.facebook.com", "facebook.com",
    "help.instagram.com", "www.instagram.com",
    "www.whatsapp.com",
    "www.youtube.com",
    "help.netflix.com", "www.netflix.com",
    "www.primevideo.com",
    "policies.google.com",
    "help.instagram.com",
}

# document_type values that count as "terms" (case-insensitive substring match)
TERMS_KEYWORDS = [
    "terms of service", "terms of use", "conditions of use",
    "eula", "license", "licence", "agreement",
]
PRIVACY_KEYWORDS = ["privacy"]

MIN_CHARS = 2_000   # below this → try Playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """'Amazon Prime Video' → 'amazon_prime_video'"""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)


def is_terms_row(doc_type: str, include_privacy: bool) -> bool:
    dt = doc_type.lower()
    if any(kw in dt for kw in TERMS_KEYWORDS):
        return True
    if include_privacy and any(kw in dt for kw in PRIVACY_KEYWORDS):
        return True
    return False


def robots_allows(url: str, ua: str) -> bool:
    """Return True if robots.txt permits fetching url."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        # Skip robots check for known-public legal/help domains
        if host in ROBOTS_SKIP_HOSTS:
            return True
        robots_url = f"{parsed.scheme}://{host}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(ua, url)
    except Exception:
        return True  # if we can't read robots.txt, proceed cautiously


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    return s


# ── extraction ────────────────────────────────────────────────────────────────

def html_to_markdown_bs4(html: str) -> str:
    """Fallback: strip tags, preserve headings/lists roughly."""
    if not HAS_BS4:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Remove noise
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "form", "noscript", "iframe", "svg"]):
        tag.decompose()
    lines = []
    for el in soup.find_all(True):
        name = el.name
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if name in ("h1",):
            lines.append(f"\n# {text}\n")
        elif name in ("h2",):
            lines.append(f"\n## {text}\n")
        elif name in ("h3",):
            lines.append(f"\n### {text}\n")
        elif name in ("h4", "h5", "h6"):
            lines.append(f"\n#### {text}\n")
        elif name == "li":
            lines.append(f"- {text}")
        elif name in ("p", "div", "section", "article"):
            if text and len(text) > 20:
                lines.append(f"\n{text}\n")
    result = "\n".join(lines)
    # Collapse 3+ blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def extract_text_trafilatura(html: str, url: str) -> str:
    if not HAS_TRAFILATURA:
        return ""
    try:
        result = trafilatura.extract(
            html,
            url=url,
            include_formatting=True,
            include_tables=True,
            include_links=False,
            favor_precision=False,
            favor_recall=True,
            no_fallback=False,
        )
        return result or ""
    except Exception as exc:
        log.debug("trafilatura error: %s", exc)
        return ""


def extract_from_html(html: str, url: str) -> str:
    """Try trafilatura first, fall back to BS4."""
    text = extract_text_trafilatura(html, url)
    if len(text) < 200 and HAS_BS4:
        text = html_to_markdown_bs4(html)
    return text


def fetch_with_requests(url: str, session: requests.Session, timeout: int):
    """Returns (html_or_bytes, content_type, error_str)."""
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "").lower()
        if "pdf" in ct or url.lower().endswith(".pdf"):
            return resp.content, "pdf", None
        return resp.text, "html", None
    except requests.exceptions.HTTPError as e:
        return None, None, f"HTTP {e.response.status_code}"
    except requests.exceptions.Timeout:
        return None, None, "Timeout"
    except RequestException as e:
        return None, None, str(e)


def _safe_str(obj) -> str:
    """Convert to string, replacing chars that Windows cp1252 can't handle."""
    return str(obj).encode("ascii", "replace").decode("ascii")


def fetch_with_playwright(url: str, timeout: int) -> tuple[str, str | None]:
    """Returns (html, error)."""
    if not HAS_PLAYWRIGHT:
        return "", "Playwright not installed"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-IN",
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            )
            page = ctx.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            # Wait a little for JS to settle
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html, None
    except Exception as e:
        return "", _safe_str(e)


def extract_pdf(content: bytes, url: str) -> str:
    if not HAS_PDFPLUMBER:
        return ""
    import io
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n\n".join(pages)
    except Exception as e:
        log.debug("pdfplumber error: %s", e)
        return ""


# ── markdown builder ──────────────────────────────────────────────────────────

def build_file_content(company: str, docs: list[dict]) -> str:
    """
    docs is a list of dicts: {doc_type, url, text}
    Returns full .md file content.
    """
    today = date.today().isoformat()
    parts = [f"# {company}", f"*Collected on {today}*", ""]
    for doc in docs:
        parts.append(f"## {doc['doc_type']}")
        parts.append(f"Source: {doc['url']}")
        parts.append("")
        parts.append(doc["text"])
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts)


# ── summary table ─────────────────────────────────────────────────────────────

def print_summary(results: list[dict]) -> None:
    col_w = [30, 10, 8, 20]
    header = ["File", "Chars", "Docs", "Status"]
    sep = "  ".join("-" * w for w in col_w)
    row_fmt = "  ".join(f"{{:<{w}}}" for w in col_w)
    print()
    print("=" * sum(col_w) + "=" * (len(col_w) - 1) * 2)
    print("SUMMARY")
    print("=" * sum(col_w) + "=" * (len(col_w) - 1) * 2)
    print(row_fmt.format(*header))
    print(sep)
    for r in results:
        fname = r.get("file", "—")[:col_w[0]]
        chars = str(r.get("chars", "—"))
        docs  = str(r.get("docs", "—"))
        status = r.get("status", "—")[:col_w[3]]
        print(row_fmt.format(fname, chars, docs, status))
    print(sep)
    ok  = sum(1 for r in results if "ok" in r.get("status","").lower() or "saved" in r.get("status","").lower())
    skp = sum(1 for r in results if "skip" in r.get("status","").lower())
    fail= sum(1 for r in results if "fail" in r.get("status","").lower() or "error" in r.get("status","").lower())
    print(f"\nTotal: {len(results)}  |  Saved: {ok}  |  Skipped: {skp}  |  Failed/partial: {fail}")
    if FAILED_TXT.exists():
        print(f"\nFailed URLs logged to: {FAILED_TXT}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch and save legal Terms documents.")
    parser.add_argument("--include-privacy", action="store_true",
                        help="Also fetch Privacy Policy rows")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing .md files")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between requests (default: 2)")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Request timeout in seconds (default: 30)")
    parser.add_argument("--no-robots", action="store_true",
                        help="Skip robots.txt checks")
    args = parser.parse_args()

    # ── read sources.csv ──────────────────────────────────────────────────────
    if not SOURCES_CSV.exists():
        sys.exit(f"ERROR: {SOURCES_CSV} not found.")

    rows = []
    with open(SOURCES_CSV, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row = {k.strip(): (v.strip() if v else "") for k, v in raw.items()}
            if not row.get("url"):
                continue
            if not is_terms_row(row.get("document_type", ""), args.include_privacy):
                log.info("SKIP  %-30s  %s", row.get("company","?"), row.get("document_type","?"))
                continue
            rows.append(row)

    if not rows:
        sys.exit("No rows matched the filter. Try --include-privacy to include privacy policies.")

    log.info("Loaded %d rows to fetch.", len(rows))

    # ── group by company ──────────────────────────────────────────────────────
    from collections import defaultdict
    company_rows: dict[str, list] = defaultdict(list)
    for r in rows:
        company_rows[r["company"]].append(r)

    session = make_session()
    failed_entries: list[str] = []
    summary_results: list[dict] = []

    # Clear failed.txt from any previous run so we start fresh
    if FAILED_TXT.exists():
        FAILED_TXT.unlink()

    # ── process each company ──────────────────────────────────────────────────
    for company, company_doc_rows in company_rows.items():
        slug = slugify(company)
        out_path = SCRIPT_DIR / f"{slug}.md"

        # Skip if file exists and --force not passed
        if out_path.exists() and not args.force:
            log.info("SKIP  %s (file exists; use --force to overwrite)", out_path.name)
            summary_results.append({
                "file": out_path.name,
                "chars": out_path.stat().st_size,
                "docs": "-",
                "status": "Skipped (exists)",
            })
            continue

        docs_collected: list[dict] = []
        company_failed = False

        for row in company_doc_rows:
            url      = row["url"]
            doc_type = row["document_type"]
            log.info("FETCH %-30s  %s", company, url)

            # robots.txt
            if not args.no_robots and not robots_allows(url, USER_AGENT):
                reason = "Blocked by robots.txt"
                log.warning("  %s — %s", url, reason)
                failed_entries.append(f"{company} | {url} | {reason}")
                company_failed = True
                continue

            # ── primary fetch ─────────────────────────────────────────────────
            content, ctype, err = fetch_with_requests(url, session, args.timeout)

            if err:
                log.warning("  Request failed: %s", err)
                text = ""
            elif ctype == "pdf":
                log.info("  PDF detected, extracting...")
                text = extract_pdf(content, url)
                if not text:
                    reason = "PDF: pdfplumber not installed or extraction failed"
                    log.warning("  %s", reason)
                    failed_entries.append(f"{company} | {url} | {reason}")
                    company_failed = True
                    time.sleep(args.delay)
                    continue
            else:
                text = extract_from_html(content, url)

            # ── Playwright fallback ───────────────────────────────────────────
            if len(text) < MIN_CHARS and ctype != "pdf":
                log.info("  Text too short (%d chars), trying Playwright...", len(text))
                if HAS_PLAYWRIGHT:
                    pw_html, pw_err = fetch_with_playwright(url, args.timeout)
                    if pw_err:
                        log.warning("  Playwright failed: %s", _safe_str(pw_err))
                    else:
                        pw_text = extract_from_html(pw_html, url)
                        if len(pw_text) > len(text):
                            text = pw_text
                            log.info("  Playwright extracted %d chars.", len(text))
                else:
                    log.info("  Playwright not installed.")

            if len(text) < 100:
                reason = (err or "Extraction yielded < 100 chars - page likely requires JS")
                log.warning("  FAIL: %s", reason)
                failed_entries.append(f"{company} | {url} | {reason}")
                company_failed = True
            else:
                docs_collected.append({
                    "doc_type": doc_type,
                    "url": url,
                    "text": text,
                })
                log.info("  OK   %d chars extracted.", len(text))

            time.sleep(args.delay)

        # ── write .md file ────────────────────────────────────────────────────
        if docs_collected:
            md_content = build_file_content(company, docs_collected)
            out_path.write_text(md_content, encoding="utf-8")
            total_chars = sum(len(d["text"]) for d in docs_collected)
            status = "Saved" + (" (partial)" if company_failed else "")
            log.info("  -> %s  (%d chars)", out_path.name, total_chars)
            summary_results.append({
                "file": out_path.name,
                "chars": total_chars,
                "docs": len(docs_collected),
                "status": status,
            })
        else:
            summary_results.append({
                "file": f"{slug}.md",
                "chars": 0,
                "docs": 0,
                "status": "Failed (no text)",
            })

    # ── write failed.txt ──────────────────────────────────────────────────────
    if failed_entries:
        with open(FAILED_TXT, "w", encoding="utf-8") as fh:
            fh.write(f"Failed fetches - {date.today().isoformat()}\n")
            fh.write("=" * 60 + "\n")
            for entry in failed_entries:
                fh.write(entry + "\n")

    # ── summary ───────────────────────────────────────────────────────────────
    print_summary(summary_results)


if __name__ == "__main__":
    main()
