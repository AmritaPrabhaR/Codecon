#!/usr/bin/env python3
"""
validate.py - checks every required-format rule and bug 1-10 against end/*.json
Exit code 1 if any violation is found.
"""
import json, re, sys, os
from pathlib import Path
from collections import defaultdict

END_DIR = Path(__file__).parent / "end"

VIOLATIONS = []

def viol(fname, doc_title, clause_id, bug_num, message):
    VIOLATIONS.append({
        "file": fname, "doc": doc_title, "clause": clause_id,
        "bug": bug_num, "message": message
    })

ITEM_LABEL_RE = re.compile(
    r'(?m)^(?:[a-z]\. |[ivxlcdm]+\. |\([a-z]\) |\([ivxlcdm]+\) |\d+\. )'
)
BARE_LABEL_HEADING_RE = re.compile(r'^[a-z]\.\s*(\(part \d+/\d+\))?$')
STALE_LABEL_HEADING_RE = re.compile(r'^[a-z]\. > ')
MOJIBAKE_RE = re.compile(r'â€™|Ã©|Ã\\xa9|\\ufffd|\ufffd')
HTML_TAG_RE = re.compile(r'<[a-zA-Z][^>]*>|&amp;|&lt;|&gt;|&nbsp;|<br\s*/?>')
HEADING_DEBRIS_RE = re.compile(r'\*\*|\*[^*]|^\*$|-{4,}|={4,}')
PART_LABEL_RE = re.compile(r'\(part (\d+)/(\d+)\)')
JUNK_NAV_RE = re.compile(r'\b[A-Z][a-z]+(?: \+ [A-Z][a-z]+){2,}')
TEXT_MIN = 150
TEXT_MAX = 1500

def check_file(fpath):
    fname = fpath.name
    with open(fpath, encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            viol(fname, '?', '?', 'FORMAT', f'Invalid JSON: {e}')
            return

    for k in ('company', 'collected', 'source_file', 'documents'):
        if k not in data:
            viol(fname, '?', '?', 'FORMAT', f'Missing top-level key: {k}')

    documents = data.get('documents', [])
    for doc in documents:
        dtitle = doc.get('title', '?')
        clauses = doc.get('clauses', [])
        for k in ('title', 'source', 'clauses'):
            if k not in doc:
                viol(fname, dtitle, '?', 'FORMAT', f'Document missing key: {k}')

        ids = [c.get('id') for c in clauses]
        expected = list(range(1, len(clauses)+1))
        if ids != expected:
            viol(fname, dtitle, str(ids[:10]), '11', f'IDs not contiguous 1..N: got {ids[:20]}')

        for i, c in enumerate(clauses):
            cid = c.get('id', '?')
            extra_keys = set(c.keys()) - {'id', 'heading', 'text'}
            if extra_keys:
                viol(fname, dtitle, cid, 'FORMAT', f'Extra keys: {extra_keys}')
            for k in ('id', 'heading', 'text'):
                if k not in c:
                    viol(fname, dtitle, cid, 'FORMAT', f'Missing clause key: {k}')
            heading = c.get('heading', '')
            text = c.get('text', '')
            if not heading or not heading.strip():
                viol(fname, dtitle, cid, 'FORMAT', 'Empty heading')
            if len(heading) > 100:
                viol(fname, dtitle, cid, '3', f'Heading > 100 chars ({len(heading)}): {heading[:60]}...')
            if heading.rstrip().endswith('.') and not heading.rstrip().endswith('...') and not re.match(r'^\d+\.', heading):
                viol(fname, dtitle, cid, '3', f'Heading ends with full stop: {heading[:60]}')
            if BARE_LABEL_HEADING_RE.match(heading.strip()):
                viol(fname, dtitle, cid, '2', f'Bare label heading: {heading}')
            if STALE_LABEL_HEADING_RE.match(heading.strip()):
                viol(fname, dtitle, cid, '2', f'Stale g.-style heading: {heading}')
            if re.match(r'^Item \d+$', heading):
                viol(fname, dtitle, cid, '4', f'Generic heading: {heading}')
            if HEADING_DEBRIS_RE.search(heading):
                viol(fname, dtitle, cid, '7', f'Heading debris: {heading}')
            if MOJIBAKE_RE.search(text) or MOJIBAKE_RE.search(heading):
                viol(fname, dtitle, cid, '10', 'Mojibake detected')
            if HTML_TAG_RE.search(text) or HTML_TAG_RE.search(heading):
                viol(fname, dtitle, cid, '10', 'HTML tag/entity detected')
            tlen = len(text)
            if tlen < TEXT_MIN:
                viol(fname, dtitle, cid, 'FORMAT', f'Text < {TEXT_MIN} chars ({tlen}): {text[:60]}')
            if tlen > TEXT_MAX:
                viol(fname, dtitle, cid, 'FORMAT', f'Text > {TEXT_MAX} chars ({tlen}) [soft/review]')
            if text.rstrip().endswith(':'):
                viol(fname, dtitle, cid, '5', f'Text ends with colon (stranded lead-in?): ...{text.rstrip()[-60:]}')
            if JUNK_NAV_RE.search(text):
                viol(fname, dtitle, cid, '9', f'Possible nav-menu junk: {text[:80]}')
            lines = text.split('\n')
            label_lines = [(idx, l.strip()[:60]) for idx, l in enumerate(lines) if idx > 0 and ITEM_LABEL_RE.match(l.strip())]
            if label_lines:
                viol(fname, dtitle, cid, '1', f'Possible unsplit items at line(s) {[x[0] for x in label_lines[:3]]}: {[x[1] for x in label_lines[:3]]}')
            first_line = lines[0].strip() if lines else ''
            if first_line.startswith(('-', '*', 'bullet')):
                m = PART_LABEL_RE.search(heading)
                if not (m and int(m.group(1)) > 1):
                    if i > 0:
                        prev_text = clauses[i-1].get('text', '').rstrip()
                        if not prev_text.endswith(':'):
                            viol(fname, dtitle, cid, '6', 'Possible orphan bullet start without lead-in colon in previous clause')

        groups = defaultdict(list)
        for c in clauses:
            h = c.get('heading', '')
            m = PART_LABEL_RE.search(h)
            if m:
                base = PART_LABEL_RE.sub('', h).strip().rstrip('>').strip()
                groups[base].append((c.get('id'), int(m.group(1)), int(m.group(2))))
        for base, items in groups.items():
            items_sorted = sorted(items, key=lambda x: x[1])
            n_declared = items_sorted[0][2]
            if len(set(x[2] for x in items_sorted)) > 1:
                viol(fname, dtitle, '?', '8', f'Inconsistent n in part labels for "{base}": {items_sorted}')
            ks = [x[1] for x in items_sorted]
            expected_ks = list(range(1, n_declared+1))
            if ks != expected_ks:
                viol(fname, dtitle, '?', '8', f'Non-contiguous part labels for "{base}": got k={ks}, expected {expected_ks}')

def main():
    files = sorted(END_DIR.glob('*.json'))
    if not files:
        print(f'No JSON files found in {END_DIR}')
        sys.exit(1)
    for fp in files:
        check_file(fp)
    if VIOLATIONS:
        print(f'\n{"="*70}')
        print(f'VALIDATION REPORT -- {len(VIOLATIONS)} violation(s) found')
        print(f'{"="*70}\n')
        current_file = None
        for v in VIOLATIONS:
            if v["file"] != current_file:
                current_file = v["file"]
                print(f'\n-- {current_file} ----------------')
            print(f'  [Bug {str(v["bug"]):6}] clause {str(v["clause"]):>5} | {str(v["doc"])[:40]}')
            print(f'             {v["message"]}')
        print(f'\n{"="*70}')
        print(f'Total: {len(VIOLATIONS)} violation(s)')
        sys.exit(1)
    else:
        print('All files PASS validation.')
        sys.exit(0)

if __name__ == '__main__':
    main()
