"""run.py - clean and split every agreement in samples/, save the results in end/.

Put this file next to extract.py and split.py, with a folder called samples/ beside it.
Run:  python run.py

For each samples/<name>.md it writes end/<name>.json:
{
  "company": ..., "collected": ..., "source_file": "<name>.md",
  "documents": [
    {"title": ..., "source": <url>, "clauses": [{"id", "heading", "text"}, ...]}
  ]
}
"""
import json
import statistics
from pathlib import Path

from extract import load_agreement
from split import MAX_LEN, MIN_LEN, split_clauses

BASE = Path(__file__).resolve().parent  # the folder this script lives in
SAMPLES = BASE / "samples"
OUT = BASE / "end"


def problems(clauses):
    """Count clauses that still look wrong, so they can be read by eye."""
    found = {
        "empty heading": sum(not c["heading"].strip() for c in clauses),
        "heading over 100 chars": sum(len(c["heading"]) > 100 for c in clauses),
        "ends with ':'": sum(c["text"].rstrip().endswith(":") for c in clauses),
        "under %d chars" % MIN_LEN: sum(len(c["text"]) < MIN_LEN for c in clauses),
        "over %d chars" % MAX_LEN: sum(len(c["text"]) > MAX_LEN for c in clauses),
    }
    return {k: v for k, v in found.items() if v}


def main():
    if not SAMPLES.is_dir():
        raise SystemExit(f"Folder not found: {SAMPLES}\nCreate it and put your .md files inside.")
    files = sorted(SAMPLES.glob("*.md"))
    if not files:
        raise SystemExit(f"No .md files found in {SAMPLES}")

    OUT.mkdir(exist_ok=True)
    done = 0
    for path in files:
        try:
            agreement = load_agreement(path)
            documents = []
            for doc in agreement["documents"]:
                clauses = split_clauses(doc["text"], default_heading=doc["title"])
                documents.append({"title": doc["title"], "source": doc["source"], "clauses": clauses})
            result = {
                "company": agreement["company"],
                "collected": agreement["collected"],
                "source_file": path.name,
                "documents": documents,
            }
            target = OUT / f"{path.stem}.json"
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            lens = [len(c["text"]) for d in documents for c in d["clauses"]]
            print(f"OK    {path.name:<25} {len(documents)} document(s), {len(lens)} clauses, "
                  f"median {int(statistics.median(lens))} chars -> end/{target.name}")
            for d in documents:
                bad = problems(d["clauses"])
                if bad:
                    print("      check:", ", ".join(f"{n} x {k}" for k, n in bad.items()), f"({d['title']})")
            done += 1
        except Exception as exc:  # keep going so one bad file doesn't stop the rest
            print(f"FAIL  {path.name:<25} {type(exc).__name__}: {exc}")

    print(f"\n{done}/{len(files)} files saved in {OUT}")


if __name__ == "__main__":
    main()
