#!/usr/bin/env python3
"""
fix_json.py - deterministic fixer for bugs in end/*.json
Applies bugs in order: 9, 7, 10, 1, 2, 3, 4, 5, 6, 8, 11
"""
import json, re, sys, os
from pathlib import Path
from copy import deepcopy

END_DIR = Path(__file__).parent / "end"
SAMPLES_DIR = Path(__file__).parent / "samples"

PART_LABEL_RE = re.compile(r'\(part (\d+)/(\d+)\)')
ITEM_LABEL_RE = re.compile(
    r'^([a-z])\. ([A-Za-z].*?)(?:\. |; |: |$)|'
    r'^([a-z])\. (.*?)$|'
    r'^\(([a-z])\) (.*?)$|'
    r'^([ivxlcdm]+)\. (.*?)$|'
    r'^(\d+)\. (.*?)$'
)

CHANGES_LOG = []  # list of dicts for the report


def log_change(fname, doc_title, bug_num, old_id, new_id, old_heading, new_heading, detail):
    CHANGES_LOG.append({
        'file': fname, 'doc': doc_title, 'bug': bug_num,
        'old_id': old_id, 'new_id': new_id,
        'old_heading': old_heading, 'new_heading': new_heading,
        'detail': detail
    })


def first_n_words(text, n=8):
    """Return first n words of text + ellipsis"""
    words = text.split()
    if len(words) <= n:
        return text
    return ' '.join(words[:n]) + '...'


def fix_file(fpath, fname):
    with open(fpath, encoding='utf-8') as f:
        data = json.load(f)

    changed = False
    for doc in data['documents']:
        dtitle = doc.get('title', '?')
        clauses = doc.get('clauses', [])

        # === BUG 9: Delete website junk clauses ===
        junk_indices = []
        for i, c in enumerate(clauses):
            text = c.get('text', '')
            heading = c.get('heading', '')
            # Only delete if EVERY line is junk
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            # Nav pattern: "A + B + C"
            nav_re = re.compile(r'^[A-Z][a-z]+(?: \+ [A-Z][a-z]+){2,}$')
            footer_words = {'Support', 'Cookie Settings', 'Careers', 'Help', '---'}
            # Check if this is pure junk
            is_junk = False
            if lines and all(nav_re.match(l) for l in lines):
                is_junk = True
            elif lines and all(l in footer_words or l.startswith('---') for l in lines):
                is_junk = True
            # Also check: glued words like "PolicyYour" throughout ALL lines
            glued_re = re.compile(r'[a-z]{2}[A-Z][a-z]{2}')
            if lines and all(glued_re.search(l) for l in lines) and len(lines) <= 3:
                is_junk = True
            if is_junk:
                junk_indices.append(i)
                log_change(fname, dtitle, '9', c.get('id'), None, heading, None, f'DELETED JUNK: {text[:120]}')

        if junk_indices:
            clauses = [c for i, c in enumerate(clauses) if i not in junk_indices]
            doc['clauses'] = clauses
            changed = True

        # === BUG 7: Heading debris ===
        for c in clauses:
            heading = c.get('heading', '')
            orig = heading
            # Remove **bold** markers
            heading = re.sub(r'\*\*([^*]+)\*\*', r'\1', heading)
            heading = re.sub(r'\*([^*]+)\*', r'\1', heading)
            # Remove trailing/leading dashes/equals
            heading = re.sub(r'^[-=]{4,}\s*', '', heading)
            heading = re.sub(r'\s*[-=]{4,}$', '', heading)
            heading = heading.strip()
            if heading != orig:
                log_change(fname, dtitle, '7', c.get('id'), c.get('id'), orig, heading, 'Heading debris removed')
                c['heading'] = heading
                changed = True

        # === BUG 10: Encoding/markup debris in text/heading ===
        MOJIBAKE_MAP = {
            'â€™': "'", 'â€œ': '"', 'â€': '"', 'Ã©': 'é',
            'â€¦': '…', 'â€"': '–', 'â€"': '—', '\ufffd': '',
            '&amp;': '&', '&lt;': '<', '&gt;': '>', '&nbsp;': ' ',
            '<br>': '\n', '<br/>': '\n', '<br />': '\n',
        }
        for c in clauses:
            for field in ('heading', 'text'):
                val = c.get(field, '')
                orig = val
                for bad, good in MOJIBAKE_MAP.items():
                    val = val.replace(bad, good)
                # Fix duplicate spaces
                val = re.sub(r'  +', ' ', val)
                if val != orig:
                    c[field] = val
                    log_change(fname, dtitle, '10', c.get('id'), c.get('id'), orig[:50], val[:50], f'Encoding/markup fixed in {field}')
                    changed = True

        # === BUG 1: Lettered/numbered items not split ===
        # Only for amazon_prime_video.json - specific known cases
        # We fix specific known problematic patterns
        new_clauses = []
        for c in clauses:
            text = c.get('text', '')
            heading = c.get('heading', '')
            cid = c.get('id')
            lines = text.split('\n')

            # Detect if text has embedded lettered sub-items at non-first lines
            # Pattern: lines starting with "x. Title. " or "x. Title" where x is a letter
            item_starts = []
            for idx, line in enumerate(lines):
                ls = line.strip()
                # Match "f. Payment Methods." or "g. Promotional Trials." at start of line (not first)
                if idx > 0:
                    m = re.match(r'^([a-z])\. ([A-Z][^.]*?)\.?\s', ls)
                    if m and len(ls) > 20:
                        item_starts.append((idx, m.group(1), m.group(2)))
                    # Also "i. Availability" style
                    m2 = re.match(r'^([a-z])\. ([A-Z][a-zA-Z ]+?)[\. ]', ls)
                    if m2 and not item_starts or (item_starts and item_starts[-1][0] != idx):
                        item_starts.append((idx, m2.group(1), m2.group(2).rstrip()))

            if item_starts:
                # Deduplicate
                seen = set()
                item_starts_dedup = []
                for it in item_starts:
                    if it[0] not in seen:
                        seen.add(it[0])
                        item_starts_dedup.append(it)
                item_starts = item_starts_dedup

                # Build split points: [0, idx1, idx2, ...]
                split_points = [0] + [x[0] for x in item_starts]
                segments = []
                for si, sp in enumerate(split_points):
                    end = split_points[si+1] if si+1 < len(split_points) else len(lines)
                    seg_lines = lines[sp:end]
                    segments.append('\n'.join(seg_lines).strip())

                if len(segments) > 1:
                    # Get the base parent heading (strip any existing part labels)
                    base_heading = PART_LABEL_RE.sub('', heading).strip().rstrip('>').strip()

                    for seg_i, (seg, item_info) in enumerate(zip(segments, [None] + item_starts)):
                        if not seg:
                            continue
                        if seg_i == 0:
                            # First segment keeps the original heading
                            new_c = {'id': cid, 'heading': heading, 'text': seg}
                        else:
                            label, item_title = item_info[1], item_info[2]
                            item_title = item_title.strip().rstrip('.')
                            new_heading = f'{base_heading} > {item_title}'
                            if len(new_heading) > 100:
                                new_heading = first_n_words(seg, 8)
                            new_c = {'id': cid, 'heading': new_heading, 'text': seg}
                            log_change(fname, dtitle, '1', cid, '(new)', heading, new_heading, f'Split item {label}. from clause')
                    # Only add split if all segments are valid (>= 50 chars)
                    if all(len(s) >= 50 for s in segments if s):
                        new_clauses.extend([{'id': cid, 'heading': (heading if si == 0 else f'{PART_LABEL_RE.sub("", heading).strip()} > {item_starts[si-1][2].strip().rstrip(".")}'), 'text': seg}
                                            for si, seg in enumerate(segments) if seg])
                        changed = True
                        continue
            new_clauses.append(c)

        if len(new_clauses) != len(clauses):
            doc['clauses'] = new_clauses
            clauses = new_clauses
            changed = True

        # === BUG 2: Fix bare label headings (g. (part 1/3) etc.) ===
        # For amazon_prime_video: clauses 28, 29, 30 (g. (part x/3)) and 31 (g. > Your legal rights)
        for c in clauses:
            heading = c.get('heading', '')
            cid = c.get('id')
            # Bare label like "g. (part 1/3)"
            m = re.match(r'^([a-z])\. \(part (\d+)/(\d+)\)$', heading.strip())
            if m:
                letter, k, n = m.group(1), m.group(2), m.group(3)
                # Look at the text to determine what this clause is about
                text = c.get('text', '')
                # For amazon prime video clause 28-30 (g. = Disputes/Conditions)
                # Extract from text: first noun phrase
                first_line = text.split('\n')[0].strip()
                # Check if text starts with the actual item title
                item_m = re.match(r'^([A-Z][^.]+?)\.', first_line)
                if item_m:
                    new_title = item_m.group(1).strip()
                else:
                    new_title = first_n_words(first_line, 6)
                new_heading = f'{new_title} (part {k}/{n})'
                if len(new_heading) > 100:
                    new_heading = first_n_words(text, 8) + f' (part {k}/{n})'
                log_change(fname, dtitle, '2', cid, cid, heading, new_heading, 'Fixed bare label heading')
                c['heading'] = new_heading
                changed = True

            # Stale g. > style heading like "g. > Your legal rights"
            m2 = re.match(r'^([a-z])\. > (.+)$', heading.strip())
            if m2:
                letter, sub = m2.group(1), m2.group(2)
                # Need to find what the parent heading was
                # Use the sub-part as the heading itself if valid
                new_heading = sub
                if len(new_heading) > 100:
                    new_heading = first_n_words(new_heading, 8)
                log_change(fname, dtitle, '2', cid, cid, heading, new_heading, 'Fixed stale g. > heading')
                c['heading'] = new_heading
                changed = True

        # === BUG 3: Heading > 100 chars ===
        for c in clauses:
            heading = c.get('heading', '')
            cid = c.get('id')
            if len(heading) > 100:
                # Truncate at the > separator if present
                if ' > ' in heading:
                    parts = heading.split(' > ')
                    parent = parts[0]
                    child = parts[1] if len(parts) > 1 else ''
                    if len(child) > 60:
                        child = first_n_words(child, 6)
                    new_heading = f'{parent} > {child}'
                    if len(new_heading) > 100:
                        new_heading = parent[:97] + '...'
                else:
                    new_heading = heading[:97] + '...'
                log_change(fname, dtitle, '3', cid, cid, heading[:80], new_heading, 'Heading truncated to <=100 chars')
                c['heading'] = new_heading
                changed = True

        # === BUG 3: Heading ends with period (sentence heading) ===
        for c in clauses:
            heading = c.get('heading', '')
            cid = c.get('id')
            stripped = heading.rstrip()
            # Skip numbered section headings like "1. Title"
            if re.match(r'^\d+\.', heading):
                continue
            if stripped.endswith('.') and not stripped.endswith('...'):
                # Move period out
                new_heading = stripped[:-1].strip()
                # Check for heading that ends with period
                if len(new_heading) <= 100 and new_heading:
                    log_change(fname, dtitle, '3', cid, cid, heading, new_heading, 'Removed trailing period from heading')
                    c['heading'] = new_heading
                    changed = True

        # === BUG 4: Generic headings ===
        for c in clauses:
            heading = c.get('heading', '')
            cid = c.get('id')
            if re.match(r'^Item \d+$', heading):
                text = c.get('text', '')
                new_heading = first_n_words(text, 8)
                log_change(fname, dtitle, '4', cid, cid, heading, new_heading, 'Generic heading replaced with text excerpt')
                c['heading'] = new_heading
                changed = True

        # === BUG 8: Fix non-contiguous part labels ===
        # Group by base heading within same document
        from collections import defaultdict, OrderedDict

        # Collect all part-label groups
        groups = defaultdict(list)
        for i, c in enumerate(clauses):
            h = c.get('heading', '')
            m = PART_LABEL_RE.search(h)
            if m:
                base = PART_LABEL_RE.sub('', h).strip().rstrip('>').strip()
                groups[base].append((i, int(m.group(1)), int(m.group(2))))

        for base, items in groups.items():
            items_sorted = sorted(items, key=lambda x: x[1])
            ks = [x[1] for x in items_sorted]
            ns = [x[2] for x in items_sorted]
            n_val = ns[0] if ns else len(items)

            # Check if all n are consistent
            if len(set(ns)) > 1:
                # Inconsistent n - skip (needs human review)
                continue

            # Check if k is contiguous 1..n
            expected_ks = list(range(1, n_val + 1))
            if ks == expected_ks:
                continue  # OK

            # If part 1 is missing and rest are there, renumber starting from 1
            if set(ks) == set(range(2, n_val + 1)) or (len(ks) < n_val and 1 not in ks):
                # Determine new n
                new_n = len(items)
                for rank, (idx, old_k, old_n) in enumerate(items_sorted):
                    new_k = rank + 1
                    c = clauses[idx]
                    old_heading = c['heading']
                    new_heading = PART_LABEL_RE.sub(f'(part {new_k}/{new_n})', old_heading)
                    if new_heading != old_heading:
                        log_change(fname, dtitle, '8', c.get('id'), c.get('id'), old_heading, new_heading, f'Part label renumbered {old_k}/{old_n} -> {new_k}/{new_n}')
                        c['heading'] = new_heading
                        changed = True

        # === BUG 11: Renumber ids 1..N ===
        for i, c in enumerate(clauses):
            if c.get('id') != i + 1:
                old_id = c.get('id')
                c['id'] = i + 1
                changed = True

    return data, changed


def main():
    files = sorted(END_DIR.glob('*.json'))
    for fp in files:
        fname = fp.name
        data, changed = fix_file(fp, fname)
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f'Fixed: {fname}')
        else:
            print(f'No changes: {fname}')

    if CHANGES_LOG:
        print(f'\n--- Changes made: {len(CHANGES_LOG)} ---')
        for ch in CHANGES_LOG:
            print(f'  [{ch["bug"]}] {ch["file"]} clause {ch["old_id"]}: {ch["detail"][:80]}')


if __name__ == '__main__':
    main()
