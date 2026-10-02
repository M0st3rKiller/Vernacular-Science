# Vernacular-Science

Searches Isis, Osiris, History of Science and BJHS (1980–2026) for review-type
articles on vernacular / popular / everyday science and technology.

```
pip install requests
python3 search_reviews.py            # fetch from Crossref, write output/results.{md,json,csv}
python3 search_reviews.py --reuse    # re-score cached output/raw_records.json (no refetch)
python3 search_reviews.py --selftest
```

Optional: `OPENALEX_API_KEY` (free, https://help.openalex.org/api/authentication/)
back-fills abstracts missing from Crossref. Without it only Crossref abstracts are used,
so Isis and Osiris (no abstracts in Crossref) are matched on titles, page counts and
themed-cluster heuristics only. Treat tiers as triage, not a final verdict.

## Watchlist of key scholars

```
python3 key_authors.py   # needs output/raw_records.json; writes output/key_authors.md
```

Lists 40 scholars with their topics, how they frame vernacular/popular/everyday science
(tagged `[data]` when taken from an abstract in the four journals, `[background]` when
summarised from general knowledge and to be verified), and their articles/reviews found by name match.

## Reading lists (MPIWG Dept. Daston, Science for the People)

```
python3 reading_lists.py   # reads data/reading_lists_sources.json + output/raw_records.json -> output/reading_lists.md
```

`data/reading_lists_sources.json` holds what was read from the two organisations' own websites
(with the fetch date); relevance labels in the output are judgements from titles only.
