# fetch_terms.py — README

Fetches Terms of Service / EULA documents listed in `sources.csv`,
extracts the main legal text, and saves one Markdown file per company.

---

## Quick start

```bash
cd d:\Codecon

# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Install Playwright's Chromium browser for JS-heavy pages
playwright install chromium

# 4. Run
python fetch_terms.py
```

---

## CLI flags

| Flag | Default | Effect |
|---|---|---|
| `--include-privacy` | off | Also fetch Privacy Policy rows from sources.csv |
| `--force` | off | Overwrite existing `.md` files |
| `--delay N` | 2 | Seconds to wait between requests |
| `--timeout N` | 30 | HTTP request timeout in seconds |
| `--no-robots` | off | Skip robots.txt checks |

Example — fetch everything including privacy, overwrite existing files:
```bash
python fetch_terms.py --include-privacy --force --delay 3
```

---

## Output files

| File | Description |
|---|---|
| `<company>.md` | Extracted legal text for that company (e.g. `whatsapp.md`) |
| `amazon_prime_video.md` | Multi-word company names use underscores |
| `failed.txt` | URLs that could not be fetched, with reasons |

Each `.md` file is structured:
```
# Company Name
*Collected on YYYY-MM-DD*

## Terms of Service
Source: https://…

<extracted text>

---
```

---

## Extraction pipeline

1. **requests** — plain HTTP GET with a real browser User-Agent
2. **trafilatura** — extracts main article text, preserving headings and lists
3. **BeautifulSoup** — fallback if trafilatura returns < 200 chars
4. **Playwright (headless Chromium)** — used only if the extracted text is < 2,000 chars (page likely requires JavaScript). Skipped gracefully if not installed.
5. **pdfplumber** — used if the URL points to a PDF. Skipped gracefully if not installed.

---

## Document-type filter

Rows are fetched if `document_type` contains (case-insensitive):
`Terms of Service`, `Terms of Use`, `Conditions of Use`, `EULA`, `license`, `licence`, `agreement`

Pass `--include-privacy` to also include rows containing `privacy`.

---

## Assumptions

1. **sources.csv lives in the same folder as the script.** The script resolves paths relative to its own `__file__`, not `cwd`.
2. **UTF-8 with BOM** is handled (`encoding="utf-8-sig"`).
3. **One `.md` file per company.** If a company has multiple ToS documents (e.g., Amazon has both "Conditions of Use" and "Prime Video Terms"), all go into the same file as separate `##` sections.
4. **Playwright is optional.** If not installed, JS-heavy pages are logged to `failed.txt` and the script continues.
5. **pdfplumber is optional.** If a URL serves a PDF and pdfplumber is not installed, the URL is logged to `failed.txt`.
6. **robots.txt is respected by default.** Pass `--no-robots` to bypass. Some sites (e.g. amazon.in) block bots via robots.txt; those will be logged as failures.
7. **Amazon India pages return 403.** Amazon aggressively blocks non-browser HTTP clients. Even with a real UA the Help Centre pages return 403. Playwright may succeed but is not guaranteed. Entries are logged to `failed.txt`.
8. **Flipkart legal pages are JS-rendered.** The static HTML is a product search page. Playwright is required to get the real content.
9. **The 2-second delay applies between individual URL requests**, not between companies.
10. **No existing files outside the three listed are touched** (`fetch_terms.py`, `requirements.txt`, `README.md`).
