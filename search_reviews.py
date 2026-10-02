#!/usr/bin/env python3
"""Search Isis, Osiris, History of Science and BJHS (1980-2026) for review-type
articles on vernacular / popular / everyday science and technology.

Data: Crossref (bibliographic records) + OpenAlex (abstract back-fill).
Output: results.md (TOC table + entries), results.json, results.csv.

Usage:  python3 search_reviews.py [--out DIR] [--from 1980] [--until 2026]
        python3 search_reviews.py --selftest
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

MAILTO = "wizfrank821@gmail.com"  # polite-pool identification for both APIs
CR = "https://api.crossref.org"
OA = "https://api.openalex.org"

JOURNALS = {
    "Isis": ["0021-1753", "1545-6994"],
    "Osiris": ["0369-7827", "1933-8287"],
    "History of Science": ["0073-2753", "1753-8564"],
    "BJHS": ["0007-0874", "1474-001X"],
}

# (regex, weight). Matched case-insensitively on title (x3) and abstract (x1).
TOPIC_TERMS = [
    (r"vernacular", 3),
    (r"popular(?:i[sz]ation|i[sz]ing|i[sz]ers?)?\s+(?:science|scientific|knowledge|technolog|medicine|astronomy|natural|culture)", 3),
    (r"popular(?:i[sz]ation|i[sz]ing|i[sz]ers?)", 3),
    (r"popular science", 3),
    (r"science (?:and|for|in) (?:the )?(?:public|people|popular|print|everyday)", 3),
    (r"public(?:s)? (?:science|understanding|engagement|knowledge)", 2),
    (r"everyday (?:science|technolog|knowledge|life|practice|object|material)", 3),
    (r"ordinary (?:people|science|technolog)", 2),
    (r"lay (?:knowledge|science|audience|expertise|reader|public)", 2),
    (r"amateur", 2),
    (r"artisan|craft(?:s|sm[ae]n)?\b|practitioner knowledge|tacit knowledge|vulgari[sz]", 2),
    (r"mechanics'? institute|science lecture|public lecture|almanac|chapbook|cheap print|periodical", 1),
    (r"domestic (?:science|technolog)|household|folk|popular culture|non-elite|local knowledge|indigenous knowledge", 1),
    (r"science communication|science writing|science journalism|science in the media|science fiction", 1),
]

# Genre (review-type) markers.
GENRE_TERMS = [
    (r"literature review|review of the literature|review essay|essay review|critical essay|bibliograph(?:ic|y) essay", 3),
    (r"historiograph", 3),
    (r"state of the (?:field|art)|field review|survey of|overview of|agenda|prospects|new directions|stocktaking|assessment of the field", 3),
    (r"rethinking|reconsidering|reassess|revisit|towards a|toward a|what is|the problem of|approaches to|perspectives on", 2),
    (r"\breview(?:s|ed|ing)?\b|\bsurvey\b|\boverview\b|introduction|critical (?:review|survey)|recent (?:work|scholarship|literature)", 1),
    (r"focus section|focus:|special issue|themed issue|this volume|this issue", 1),
]

DEFAULT_EXCLUDE_TITLE = re.compile(r"^(?:front|back) matter|^index$|^notes? on contributors|^editorial board|^corrigendum|^erratum|^errata|^about the", re.I)


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"^\s*abstract\s*[:.]?\s*", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def score(text, terms):
    total, hits = 0, []
    for rx, w in terms:
        m = re.search(rx, text, flags=re.I)
        if m:
            total += w
            hits.append(m.group(0).strip().lower())
    return total, hits


def page_count(page):
    m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", page or "")
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if b >= a:
            return b - a + 1
        # abbreviated ranges like 123-7
        return int(str(a)[: len(str(a)) - len(m.group(2))] + m.group(2)) - a + 1
    return None


def classify(rec):
    """Add topic/genre scores and tier to a record dict. Returns tier or None."""
    title = rec["title"]
    abstract = rec.get("abstract", "")
    if DEFAULT_EXCLUDE_TITLE.search(title):
        return None
    t_title, h_title = score(title, TOPIC_TERMS)
    t_abs, h_abs = score(abstract, TOPIC_TERMS)
    topic = t_title * 3 + t_abs
    g_title, gh_title = score(title, GENRE_TERMS)
    g_abs, gh_abs = score(abstract, GENRE_TERMS)
    genre = g_title * 2 + g_abs
    pages = page_count(rec.get("page"))
    rec["pages"] = pages
    # Plain book reviews: short, no abstract, no explicit review-essay marker.
    strong_genre = g_title >= 3 or g_abs >= 3
    if rec.get("type") == "book-review" and not strong_genre:
        return None
    if pages is not None and pages <= 4 and not strong_genre:
        return None
    # Osiris volume introductions: the volume theme stands in for the topic.
    if rec["journal"] == "Osiris" and re.match(r"^introduction\b", title, re.I):
        genre = max(genre, 6)
        topic += rec.get("volume_topic", 0)
    rec["topic_score"], rec["genre_score"] = topic, genre
    rec["topic_hits"] = sorted(set(h_title + h_abs))
    rec["genre_hits"] = sorted(set(gh_title + gh_abs))
    if topic >= 3 and genre >= 6 and strong_genre:
        return "high"
    if topic >= 3 and genre >= 3:
        return "medium"
    if topic >= 1 and genre >= 6 and strong_genre:
        return "medium"
    if topic >= 6 and pages and pages >= 20 and genre >= 2:
        return "medium"
    return None


# ---------------------------------------------------------------- fetching
SESSION = requests.Session()
SESSION.headers["User-Agent"] = f"vernacular-science-review-search/1.0 (mailto:{MAILTO})"


def get_json(url, params=None, tries=5):
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** i)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if i == tries - 1:
                raise
            print(f"  retry ({e.__class__.__name__}) ...", file=sys.stderr)
            time.sleep(2 ** i)


def fetch_crossref(issn, y0, y1):
    cursor, out = "*", []
    fields = "DOI,title,author,issued,volume,issue,page,abstract,type,container-title,URL,subtype"
    while True:
        data = get_json(f"{CR}/journals/{issn}/works", {
            "filter": f"from-pub-date:{y0},until-pub-date:{y1}",
            "rows": 1000, "cursor": cursor, "select": fields, "mailto": MAILTO})
        msg = data["message"]
        items = msg.get("items", [])
        if not items:
            break
        out.extend(items)
        cursor = msg.get("next-cursor")
        print(f"  {issn}: {len(out)}/{msg.get('total-results')}", file=sys.stderr)
        if not cursor:
            break
    return out


def to_rec(item, journal):
    title = strip_tags(" ".join(item.get("title") or []))
    if not title:
        return None
    year = (item.get("issued", {}).get("date-parts") or [[None]])[0][0]
    authors = "; ".join(
        " ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "")
        for a in item.get("author", []))
    return {
        "journal": journal, "title": title, "authors": authors, "year": year,
        "volume": item.get("volume", ""), "issue": item.get("issue", ""),
        "page": item.get("page", ""), "doi": item.get("DOI", ""),
        "url": item.get("URL", ""), "type": item.get("type", ""),
        "abstract": strip_tags(item.get("abstract", "")),
    }


def oa_abstract(doi):
    try:
        w = get_json(f"{OA}/works/https://doi.org/{doi}", {"mailto": MAILTO, "select": "abstract_inverted_index"})
    except requests.RequestException:
        return ""
    inv = (w or {}).get("abstract_inverted_index")
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


# ------------------------------------------------------------------ output
def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def write_outputs(recs, outdir, y0, y1):
    outdir.mkdir(parents=True, exist_ok=True)
    order = {"high": 0, "medium": 1}
    recs.sort(key=lambda r: (order[r["tier"]], r["journal"], r["year"] or 0))
    for i, r in enumerate(recs, 1):
        r["id"] = i
    L = [f"# Review-type articles on vernacular / popular / everyday science & technology",
         "", f"Journals: Isis, Osiris, History of Science, BJHS · Years: {y0}–{y1} · "
         f"Generated {time.strftime('%Y-%m-%d')} from Crossref + OpenAlex · {len(recs)} candidates", "",
         "Tier **high** = topic and review-genre markers both strong; **medium** = one side weaker, check manually.", "",
         "## Table of contents", "",
         "| # | Tier | Year | Journal | Title | Author(s) | Matched terms |", "|---|---|---|---|---|---|---|"]
    for r in recs:
        L.append(f"| [{r['id']}](#r{r['id']}) | {r['tier']} | {r['year']} | {r['journal']} | "
                 f"{md_escape(r['title'])} | {md_escape(r['authors'])} | "
                 f"{md_escape(', '.join(r['topic_hits'][:4]))} |")
    L += ["", "## Entries", ""]
    for r in recs:
        vol = f"{r['volume']}" + (f"({r['issue']})" if r["issue"] else "")
        L += [f'<a id="r{r["id"]}"></a>', f"### {r['id']}. {r['title']}", "",
              f"- **Author(s):** {r['authors'] or 'n/a'}",
              f"- **Journal:** {r['journal']} {vol}, {r['year']}" + (f", pp. {r['page']}" if r["page"] else ""),
              f"- **DOI:** [{r['doi']}](https://doi.org/{r['doi']})",
              f"- **Tier:** {r['tier']} (topic {r['topic_score']}, genre {r['genre_score']})",
              f"- **Topic terms:** {', '.join(r['topic_hits']) or '—'}",
              f"- **Genre terms:** {', '.join(r['genre_hits']) or '—'}",
              "", f"**Abstract:** {r['abstract'] or '_No abstract available in Crossref/OpenAlex._'}", ""]
    (outdir / "results.md").write_text("\n".join(L), encoding="utf-8")
    (outdir / "results.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["id", "tier", "year", "journal", "title", "authors", "volume", "issue", "page", "doi", "topic_hits", "genre_hits", "abstract"]
    with open(outdir / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({**r, "topic_hits": "; ".join(r["topic_hits"]), "genre_hits": "; ".join(r["genre_hits"])})


# -------------------------------------------------------------------- main
def run(outdir, y0, y1):
    all_recs = []
    for name, issns in JOURNALS.items():
        seen = set()
        for issn in issns:
            print(f"[{name}] {issn}", file=sys.stderr)
            for it in fetch_crossref(issn, y0, y1):
                if it.get("DOI") in seen:
                    continue
                seen.add(it.get("DOI"))
                rec = to_rec(it, name)
                if rec and rec["year"] and y0 <= rec["year"] <= y1:
                    all_recs.append(rec)
        print(f"[{name}] {len(seen)} records", file=sys.stderr)

    # Osiris: a volume whose other articles hit the topic often has a programmatic intro.
    vol_topic = {}
    for r in all_recs:
        if r["journal"] == "Osiris":
            vol_topic[r["volume"]] = vol_topic.get(r["volume"], 0) + (1 if score(r["title"], TOPIC_TERMS)[0] >= 3 else 0)
    for r in all_recs:
        if r["journal"] == "Osiris":
            n = vol_topic.get(r["volume"], 0)
            r["volume_topic"] = 3 if n >= 2 else 0

    # First pass without abstracts; back-fill abstracts for plausible candidates, then re-score.
    cands = []
    for r in all_recs:
        # Cheap pre-filter so OpenAlex is only hit for relevant-looking items.
        pages = page_count(r["page"])
        if DEFAULT_EXCLUDE_TITLE.search(r["title"]) or (pages is not None and pages <= 4 and score(r["title"], GENRE_TERMS)[0] < 3):
            continue
        if not r["abstract"]:
            cands.append(r)
    print(f"Back-filling abstracts for {len(cands)} items via OpenAlex ...", file=sys.stderr)
    for k, r in enumerate(cands, 1):
        r["abstract"] = oa_abstract(r["doi"]) if r["doi"] else ""
        if k % 200 == 0:
            print(f"  {k}/{len(cands)}", file=sys.stderr)
        time.sleep(0.05)

    hits = []
    for r in all_recs:
        tier = classify(r)
        if tier:
            r["tier"] = tier
            hits.append(r)
    write_outputs(hits, outdir, y0, y1)
    print(f"Done: {len(hits)} candidates -> {outdir/'results.md'}", file=sys.stderr)


def selftest():
    mk = lambda **k: {"journal": "Isis", "type": "journal-article", "page": "100-130", "abstract": "", **k}
    cases = [
        (mk(title="Popular Science in Britain: A Historiographical Review"), {"high"}),
        (mk(title="Rethinking the Vernacular in the History of Science", abstract="A review essay on recent scholarship."), {"high", "medium"}),
        (mk(title="Artisans and Natural Knowledge: A Critical Survey"), {"high", "medium"}),
        (mk(title="The Chemistry of Dyes", page="1-30"), set()),
        (mk(title="Popular Astronomy", page="400-402", type="book-review"), set()),
        (mk(title="Front Matter", page="1-4"), set()),
        (mk(title="Introduction", journal="Osiris", volume_topic=3, abstract="popular science in the nineteenth century"), {"medium", "high"}),
    ]
    ok = True
    for rec, want in cases:
        got = classify(rec)
        good = (got in want) if want else (got is None)
        ok &= good
        print("OK  " if good else "FAIL", rec["title"], "->", got)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output")
    ap.add_argument("--from", dest="y0", type=int, default=1980)
    ap.add_argument("--until", dest="y1", type=int, default=2026)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    run(Path(a.out), a.y0, a.y1)
