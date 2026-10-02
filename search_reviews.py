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
import html
import json
import os
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
    (r"\bvernaculars?\b", 3),
    (r"popular(?:i[sz]ation|i[sz]ing|i[sz]ers?)?\s+(?:science|scientific|knowledge|technolog|medicine|astronomy|natural|culture)", 3),
    (r"popular(?:i[sz]ation|i[sz]ing|i[sz]ers?)", 3),
    (r"popular science", 3),
    (r"science (?:and|for|in) (?:the )?(?:public|people|popular|print|everyday)", 3),
    (r"public(?:s)? (?:science|understanding|engagement|knowledge)", 2),
    (r"everyday (?:science|technolog|knowledge|practice|object|material|world)", 3),
    (r"everyday life", 1),
    (r"ordinary (?:people|science|technolog)", 2),
    (r"lay (?:knowledge|science|audience|expertise|reader|public)", 2),
    (r"\bamateurs?\b", 2),
    (r"\bartisan|\bcraft(?:s|sm[ae]n)?\b|practitioner knowledge|tacit knowledge|vulgari[sz]", 2),
    (r"mechanics'? institute|science lecture|public lecture|almanac|chapbook|cheap print|periodical", 1),
    (r"domestic (?:science|technolog)|household|\bfolk\b|popular culture|non-elite|local knowledge|indigenous knowledge", 1),
    (r"science communication|science writing|science journalism|science in the media|science fiction", 1),
]

# Genre (review-type) markers.
GENRE_TERMS = [
    (r"literature review|review of the literature|review essay|essay review|critical essay|bibliograph(?:ic|y) essay", 3),
    (r"historiograph", 3),
    (r"state of the (?:field|art)|field review|survey of|overview of|(?:research |new )?agenda\b|prospects|new directions|stocktaking|assessment of the field", 3),
    (r"rethinking|reconsidering|reassess|revisit|towards a|toward a|the problem of|approaches to|perspectives? (?:on|from)|in (?:national|global|comparative|transnational) perspective", 2),
    (r"reflections? on|historians|suggestions? from|varieties of|genres,|categories,|ready for|past, present|new histor|presidential address", 2),
    (r"\breview(?:s|ed|ing)?\b|\bsurvey\b|\boverview\b|introduction|critical (?:review|survey)|recent (?:work|scholarship|literature)", 1),
    (r"focus section|focus:|special issue|themed issue|this volume|this issue", 1),
]

ABSTRACT_STRONG = re.compile(
    r"review essay|literature review|review of the (?:recent )?(?:literature|scholarship)|historiograph(?:y|ical) (?:review|survey|overview|essay)"
    r"|state of the (?:field|art)|surveys? (?:the )?(?:recent |existing )?(?:literature|scholarship|field)"
    r"|this (?:article|essay|introduction|paper) (?:reviews|surveys|takes stock|considers the historiography)", re.I)

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


# Reviews of a field talk about the literature AND argue/reflect in the first person;
# an ordinary research article usually does only one of the two.
FIELD_CUES = re.compile(r"historiograph|literature|scholarship|\bhistorians\b|\bthe field\b|\bfield of\b", re.I)
ESSAY_CUES = re.compile(
    r"this (?:essay|introduction|afterword|special issue|forum|section|volume|collection)|we (?:should|suggest|propose)|suggests that|\bagenda\b"
    r"|rethink|reassess|reconsider|reflections?|perspectives?|categor|conceptual|definition|reconceptuali", re.I)
FRAMING_TITLE = re.compile(r"^(?:introduction|afterword|epilogue|preface|foreword|editorial)\b", re.I)
EXCLUDE_DOIS = {
    "10.1177/007327531305100202",  # Staley, historiography of physics: off-topic (excluded by user)
}
STRONG_TOPIC = [t for t in TOPIC_TERMS if t[1] >= 3]


def classify(rec):
    """Add topic/genre evidence and tier to a record dict. Returns tier or None.

    Needs BOTH (a) a core topic signal and (b) a review/field-essay signal."""
    title = rec["title"]
    abstract = rec.get("abstract", "")
    if DEFAULT_EXCLUDE_TITLE.search(title) or rec.get("doi", "").lower() in EXCLUDE_DOIS:
        return None
    pages = page_count(rec.get("page"))
    rec["pages"] = pages
    t_title, h_title = score(title, STRONG_TOPIC)
    t_abs, h_abs = score(abstract, STRONG_TOPIC)
    g_title, gh_title = score(title, GENRE_TERMS)
    m = ABSTRACT_STRONG.search(abstract)
    framing = bool(FRAMING_TITLE.match(title)) or ("introduction" in title.lower()[:14])
    cluster = bool(rec.get("cluster"))

    title_strong = g_title >= 3
    title_weak = g_title >= 2
    abs_genre = bool(m) or bool(FIELD_CUES.search(abstract) and ESSAY_CUES.search(abstract))
    if rec["journal"] == "Osiris" and framing and rec.get("volume_topic"):
        t_abs += rec["volume_topic"]
    core = t_title >= 3 or t_abs >= 6 or (cluster and t_abs >= 3)

    if rec.get("type") == "book-review" and not title_strong:
        return None
    if pages is not None and pages <= 4 and not title_strong:
        return None
    if not core:
        return None

    evidence = list(gh_title) if (title_weak or title_strong) else []
    if m:
        evidence.append(m.group(0).lower())
    elif abs_genre:
        evidence.append("field+essay cues in abstract")
    if framing:
        evidence.append("introduction/afterword")
    if cluster:
        evidence.append("themed cluster")
    rec["topic_score"] = t_title * 3 + t_abs
    rec["genre_score"] = len(evidence)
    rec["topic_hits"] = sorted(set(h_title + h_abs))
    rec["genre_hits"] = evidence

    if title_strong or ((title_weak or framing) and (abs_genre or cluster)) or (framing and t_title >= 3):
        return "high"
    if cluster and not (abs_genre or title_weak or framing):
        return None
    if title_weak or framing:
        return "medium"
    if abs_genre and (t_title >= 3 or t_abs >= 9):
        return "medium"
    return None


def mark_clusters(recs):
    """Flag topical articles that sit next to other topical articles in the same
    issue (typically an Isis Focus section or a themed set of essays)."""
    groups = {}
    for r in recs:
        pc = page_count(r.get("page"))
        if r["journal"] == "Osiris" or pc is None or pc < 5 or score(r["title"] + " " + r.get("abstract", ""), STRONG_TOPIC)[0] < 3:
            continue
        m = re.match(r"\d+", r.get("page") or "")
        r["_start"] = int(m.group(0)) if m else 0
        r["_end"] = r["_start"] + pc - 1
        groups.setdefault((r["journal"], r["year"], r["volume"], r["issue"]), []).append(r)
    for g in groups.values():
        g.sort(key=lambda r: r["_start"])
        for a, b in zip(g, g[1:]):
            if b["_start"] - a["_end"] <= 2:
                a["cluster"] = b["cluster"] = True


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
    fields = "DOI,title,author,issued,volume,issue,page,abstract,type,container-title,URL"
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


def oa_abstracts(dois, api_key, batch=50):
    """Batch back-fill abstracts from OpenAlex; returns {doi_lower: abstract}."""
    out = {}
    for i in range(0, len(dois), batch):
        chunk = dois[i:i + batch]
        params = {"filter": "doi:" + "|".join(chunk), "per-page": batch,
                  "select": "doi,abstract_inverted_index", "mailto": MAILTO, "api_key": api_key}
        try:
            r = SESSION.get(f"{OA}/works", params=params, timeout=60)
            if r.status_code == 429:
                print("  OpenAlex budget exhausted; stopping back-fill.", file=sys.stderr)
                break
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  OpenAlex error {e.__class__.__name__}; skipping chunk", file=sys.stderr)
            continue
        for w in r.json().get("results", []):
            inv = w.get("abstract_inverted_index")
            if not inv:
                continue
            pos = {ix: word for word, idxs in inv.items() for ix in idxs}
            out[(w.get("doi") or "").replace("https://doi.org/", "").lower()] = " ".join(pos[k] for k in sorted(pos))
        if (i // batch) % 10 == 0:
            print(f"  {min(i + batch, len(dois))}/{len(dois)}", file=sys.stderr)
    return out


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


# ------------------------------------------------------------- book reviews
# Book reviews carry the book citation as the "title" and the reviewer as "author",
# with no abstract, so the match can only use the words in the book's title.
BROAD_BOOK_TERMS = re.compile(
    r"\bpopular\b|\bpublic (?:lectures?|science|knowledge|understanding|sphere)|\bscience (?:and|in|for) (?:the )?(?:public|people|print|culture|society|everyday)"
    r"|\blectur(?:e|ers|ing)\b|exhibit|museum|spectacle|\breaders?\b|\breading\b|newspaper|magazine|periodical|publishing|\bprint\b|textbook|encyclop[a]?edi"
    r"|\bartisans?\b|\bcrafts?(?:men)?\b|workshop|mechanics|\bamateurs?\b|domestic|everyday|vernacular|\blay\b|entertain|theatre|\bwonder|\bwomen and science"
    r"|\bchildren|\bhobby|\bhome\b|\bhousehold|kitchen|garden|\bcommon\b|ordinary|\bfolk", re.I)
NON_BOOK_TITLE = re.compile(
    r"^(?:in reply|reply|letters?|notes on contributors|index|front matter|back matter|corrigend|errat|editorial|obituary|announcement|call for|"
    r"notices of books|books received|isis current bibliography|society for the history|corrections?|about the authors?)", re.I)


def clean_citation(t):
    t = html.unescape(t)
    for _ in range(3):
        t = re.sub(r"\b([A-Z]) ([A-Z]{2,})\b", r"\1\2", t)  # small-caps artefact "R OSALIND" -> "ROSALIND"
    return re.sub(r"\s+", " ", t).strip()


def classify_book_review(rec):
    title = rec["title"]
    pc = page_count(rec.get("page"))
    if pc is None or pc > 6 or NON_BOOK_TITLE.search(title) or rec["journal"] == "Osiris":
        return None
    cit = clean_citation(title)
    strong, sh = score(cit, TOPIC_TERMS)
    broad = sorted({m.group(0).lower() for m in BROAD_BOOK_TERMS.finditer(cit)})
    rec["citation"] = cit
    rec["topic_hits"] = sh + broad
    if strong >= 3:
        return "strong"
    if strong >= 1 or len(broad) >= 2:
        return "broad"
    return None


def write_book_reviews(recs, outdir, y0, y1):
    order = {"strong": 0, "broad": 1}
    recs.sort(key=lambda r: (order[r["tier"]], r["year"] or 0, r["journal"]))
    for i, r in enumerate(recs, 1):
        r["id"] = i
    n_s = sum(r["tier"] == "strong" for r in recs)
    L = ["# Book reviews on vernacular / popular / everyday science & technology", "",
         f"Journals: Isis, History of Science, BJHS (Osiris carries no book reviews) · {y0}–{y1} · generated {time.strftime('%Y-%m-%d')} "
         f"· {len(recs)} reviews ({n_s} strong, {len(recs) - n_s} broad)", "",
         "Matching uses only the words in the book's title (Crossref has no abstract or text for reviews), so books whose titles "
         "do not signal the topic are missed. **strong** = clear topic term in the title; **broad** = weaker or generic cue, check by hand. "
         "The review's author is the reviewer, not the book's author.", "",
         "## Table of contents", "", "| # | Tier | Reviewed in | Book (as cited) | Reviewer | Matched terms |", "|---|---|---|---|---|---|"]
    for r in recs:
        L.append(f"| [{r['id']}](#b{r['id']}) | {r['tier']} | {r['journal']} {r['year']} | {md_escape(r['citation'][:170])} | "
                 f"{md_escape(r['authors'])} | {md_escape(', '.join(r['topic_hits'][:4]))} |")
    L += ["", "## Entries", ""]
    for r in recs:
        vol = f"{r['volume']}" + (f"({r['issue']})" if r["issue"] else "")
        L += [f'<a id="b{r["id"]}"></a>', f"### {r['id']}. {r['citation']}", "",
              f"- **Reviewed in:** {r['journal']} {vol}, {r['year']}, pp. {r['page']}",
              f"- **Reviewer:** {r['authors'] or 'n/a'}",
              f"- **Review DOI:** [{r['doi']}](https://doi.org/{r['doi']})",
              f"- **Tier:** {r['tier']} · matched: {', '.join(r['topic_hits']) or '—'}", ""]
    (outdir / "book_reviews.md").write_text("\n".join(L), encoding="utf-8")
    (outdir / "book_reviews.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(outdir / "book_reviews.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, ["id", "tier", "journal", "year", "volume", "issue", "page", "citation", "authors", "doi", "topic_hits"], extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({**r, "topic_hits": "; ".join(r["topic_hits"])})


def run_book_reviews(outdir, y0, y1):
    cache = outdir / "raw_records.json"
    if not cache.exists():
        sys.exit("Run the main search first (it writes output/raw_records.json).")
    recs = json.loads(cache.read_text(encoding="utf-8"))
    hits = []
    for r in recs:
        if r.get("year") and y0 <= r["year"] <= y1:
            tier = classify_book_review(r)
            if tier:
                r["tier"] = tier
                hits.append(r)
    write_book_reviews(hits, outdir, y0, y1)
    print(f"Done: {len(hits)} book reviews -> {outdir / 'book_reviews.md'}", file=sys.stderr)


# -------------------------------------------------------------------- main
def run(outdir, y0, y1, reuse=False):
    cache = outdir / "raw_records.json"
    all_recs = []
    if reuse and cache.exists():
        all_recs = json.loads(cache.read_text(encoding="utf-8"))
    for name, issns in ([] if all_recs else JOURNALS.items()):
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

    outdir.mkdir(parents=True, exist_ok=True)

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
        if not r["abstract"] and not r.get("oa_done"):
            cands.append(r)
    api_key = os.environ.get("OPENALEX_API_KEY")
    if api_key:
        print(f"Back-filling abstracts for {len(cands)} items via OpenAlex ...", file=sys.stderr)
        got = oa_abstracts([r["doi"].lower() for r in cands if r["doi"]], api_key)
        for r in cands:
            r["abstract"] = got.get(r["doi"].lower(), "")
            r["oa_done"] = True
    else:
        print("OPENALEX_API_KEY not set: skipping OpenAlex abstract back-fill (Crossref abstracts only).", file=sys.stderr)

    cache.write_text(json.dumps(all_recs, ensure_ascii=False), encoding="utf-8")
    mark_clusters(all_recs)
    hits = []
    for r in all_recs:
        tier = classify(r)
        if tier:
            r["tier"] = tier
            hits.append(r)
    write_outputs(hits, outdir, y0, y1)
    print(f"Done: {len(hits)} candidates -> {outdir/'results.md'}", file=sys.stderr)


def selftest():
    mk = lambda **k: {"journal": "Isis", "type": "journal-article", "page": "100-130", "abstract": "", "doi": "x", **k}
    essay = "This essay surveys the historiography of popular science and suggests new categories."
    cases = [
        (mk(title="Popular Science in Britain: A Historiographical Review"), {"high"}),
        (mk(title="Rethinking the Vernacular in the History of Science", abstract=essay), {"high", "medium"}),
        (mk(title="Vernacular Knowledge: A Historiographical Survey"), {"high"}),
        (mk(title="Popular science and the Moon", abstract="This article examines the Moon lectures of 1850."), set()),
        (mk(title="The Chemistry of Dyes", page="1-30"), set()),
        (mk(title="Popular Astronomy", page="400-402", type="book-review"), set()),
        (mk(title="Front Matter", page="1-4"), set()),
        (mk(title="Introduction", journal="Osiris", volume_topic=3, abstract="popular science in the nineteenth century"), {"medium", "high"}),
        (mk(title="Afterword: Science popularization and democracy", page="430-435"), {"high"}),
        (mk(title="Trajectories in physics", doi="10.1177/007327531305100202", abstract=essay), set()),
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
    ap.add_argument("--book-reviews", action="store_true", help="list book reviews on the topic (needs a previous run's raw_records.json)")
    ap.add_argument("--reuse", action="store_true", help="reuse cached raw_records.json instead of refetching")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.book_reviews:
        run_book_reviews(Path(a.out), a.y0, a.y1)
    else:
        run(Path(a.out), a.y0, a.y1, a.reuse)
