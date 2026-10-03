Build the core pipeline first as a simple web app, and add the overlay later. The overlay is your standout feature, but it only works if the summarising and flagging already do.

**First steps (this week)**

1. **Collect 10-15 real agreements.** Pick ones people actually click through, like WhatsApp, Instagram, Swiggy, Zomato, Paytm or a streaming app. Save them as text. They become your test set and your demo material.
2. **Build the extraction and clause-splitting step.** Take pasted text or a URL, clean it (BeautifulSoup for pages, pdfplumber for PDFs), and split it into clauses using numbered headings, section titles and paragraph breaks. Check that the splits look sensible on your 10-15 documents before going further.
3. **Add rule-based risk flags.** Start with keyword and regex rules for the categories you promised: data collection, third-party sharing, auto-renewal and cancellation, arbitration and liability limits. It's crude but it works immediately, and it gives you a baseline to beat.

**Next steps**

4. **Summarise each clause in plain language.** Use an LLM API with a strict prompt that explains only that clause, in simple words, and outputs JSON (summary, risk level, category). Always show the original clause beside the summary, so users can verify it and you avoid hallucinated claims.
5. **Upgrade the flagging.** Embed clauses with sentence-transformers and train a small classifier, or compare against the LLM's labels. For labelled data, look at ToS;DR (community-rated clauses) and the CLAUDETTE unfair-clauses dataset. Check their licences before using them.
6. **Build the UI.** FastAPI for the backend and React for the frontend is enough. Show clause cards colour-coded by risk, with a top summary like "3 high-risk clauses found".
7. **Add regional languages.** Translate the summaries into Malayalam and Hindi. Have a native speaker check the output for the main risk categories, since machine translation of legal-ish text can go wrong.
8. **Build the overlay.** Turn it into a Chrome extension that detects a terms page or checkbox and shows the summary panel next to it. Then you can demo the "at the moment of consent" idea live.

**How to show it works**
Hand-label about 20-30 clauses as risky or not, and report how many your flags catch and how many false alarms you get. Judges respond well to a small number like that. Also add a "not legal advice" note.

If you want, I can write starter code for steps 2 and 3, or a week-by-week timeline sized to your deadline. Which would help more?


Yes, you can use an AI or agentic IDE for this step. Tools like Cursor, GitHub Copilot's agent mode or Claude Code all work. This step is small and well-defined, so they do it well. Two cautions: review what it writes and test it on your own saved agreements, and make sure you can explain each part, because you'll be asked how it works in the pitch.

**What step 2 involves**

1. **Get the text.** Use whichever fits the input:
   - pasted text: use as is
   - URL: `requests` plus `trafilatura` or BeautifulSoup to pull the main content
   - PDF: `pdfplumber`

   Some sites load their terms with JavaScript and fetch nothing. For those, fall back to pasting the text.

2. **Clean it.** Remove menus, footers and cookie banners, and normalise whitespace and line breaks.

3. **Split into clauses** in layers:
   - First, split on headings and numbered sections, such as lines that start with "1.", "2.3" or ALL-CAPS titles.
   - If a document has no clear headings, split on blank lines instead.
   - Merge chunks that are too short (under roughly 150 characters) into their neighbour, and split chunks that are too long (over roughly 1,500 characters) at sentence boundaries.

   A simple pattern to start from for headings:

   ```python
   HEADING = re.compile(r'^\s*(\d+(\.\d+)*[.)]?\s+\S|[A-Z][A-Z \-]{5,}$)', re.M)
   ```

4. **Output a clean structure.** Return a list like `{id, heading, text}` per clause, ready for steps 3 and 4.

5. **Check it.** Run it on your 10-15 saved documents. Print the clause count and lengths, then read a few results by eye. If clauses are cut in the middle of a sentence or merged into giant blocks, adjust the rules.

**A prompt you can give the agentic IDE**

> Build a Python module `extract.py` with `get_text(source)` that accepts a URL, a PDF path, or raw text and returns cleaned text. Then build `split.py` with `split_clauses(text)` that splits on numbered headings and ALL-CAPS titles, falls back to blank lines, merges chunks under 150 characters, and splits chunks over 1,500 characters at sentence boundaries. Return a list of dicts with `id`, `heading`, `text`. Add pytest tests using the sample files in `samples/`. Explain each function briefly.

Asking for tests matters because they show whether it works on real documents, not just whether it runs.

If you want, I can write the full `extract.py` and `split.py` for you as files.