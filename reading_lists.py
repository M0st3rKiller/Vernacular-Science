#!/usr/bin/env python3
"""Build output/reading_lists.md: two reading lists, one for the MPIWG Department II (Daston)
and one for Science for the People (SftP).

Inputs:
  data/reading_lists_sources.json  items read from the two organisations' own websites (see "fetched" date inside)
  output/raw_records.json          Crossref records of the four journals (from search_reviews.py), used to
                                   show where each item was reviewed or discussed in Isis/Osiris/HoS/BJHS.

Relevance labels are my judgement from titles only (nothing here was read in full).
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from search_reviews import NON_BOOK_TITLE, clean_citation, md_escape, page_count  # noqa: E402

HERE = Path(__file__).parent

# regex on lowercase citation text -> identifies a book/issue in the four journals' review titles
WG_REVIEW_RX = {
    "Working with Paper": r"working with paper", "Entangled Itineraries": r"entangled itineraries",
    "Science in the Archives": r"science in the archives", "Before Copernicus": r"before copernicus",
    "Documenting the World": r"documenting the world", "Canonical Texts and Scholarly Practices": r"canonical texts",
    "Endangerment, biodiversity": r"endangerment, biodiversity", "How Reason Almost Lost": r"how reason almost lost",
    "Histories of Scientific Observation": r"histories of scientific observation", "Natural Law and Laws of Nature": r"natural law and laws of nature",
    "Thinking with Animals": r"thinking with animals", "Historia": r"historia: empiricism", "Things that Talk": r"things that talk",
    "The Moral Authority of Nature": r"moral authority of nature", "Biographies of Scientific Objects": r"biographies of scientific objects",
}
# (regex on the citation, level, reason) - relevance to vernacular / popular / everyday science, from the title only
WG_RELEVANCE = [
    (r"beyond the academy", "高", "標題直接講學院之外的知識，與非學院行動者的主題最近"),
    (r"working with paper", "中", "紙張工作中的性別化實踐，偏日常與手頭知識"),
    (r"entangled itineraries", "中", "物質、實踐與知識的跨歐亞流動，涉及手藝與地方"),
    (r"things that talk", "中", "從物件、藝術與科學出發，偏物質文化"),
    (r"histories of scientific observation", "中", "把觀察當作一種實踐來寫，包含非專業的觀察"),
    (r"historia", "中", "早期近代經驗主義與博學，談的是實用與記錄的知識"),
    (r"testing drugs", "中", "試藥與試療的實踐，偏經驗與實用"),
    (r"experiencing the global environment|endangerment|documenting the world", "低-中", "與地方、環境、文化或記錄有關，但不是主題核心"),
]
SFTP_RELEVANT = {  # article-title regex -> why (my judgement)
    r"popular science magazines": "直接評論大眾科學雜誌",
    r"deficit model": "批評科學傳播的「缺失模型」，與 Isis 2009 的爭論相通",
    r"communicating knowledge otherwise": "科學傳播的另一種方式",
    r"us and them": "專家與公眾的分界",
    r"fiction can improve": "用小說做科學傳播",
    r"reclaiming epistemic diversity": "知識多樣性，與地方知識有關",
    r"on kinship: indigenous": "原住民知識",
    r"malitan: preserving seeds": "種子保存與生活方式，屬地方實踐知識",
    r"sowing ancestral futures": "祖傳農業知識",
    r"chinese medicine": "傳統醫學與療癒",
    r"people-centered science": "以人民為中心的科學",
    r"science journalism we need": "科學新聞",
    r"pubs, bathtubs": "科學在酒吧、浴缸等非學院場所",
    r"introduction|commentary on science for the people|reflections on the 19": "對 1970 年代訪華代表團的重讀，連著毛時代大眾科學",
}


def load_sources():
    return json.loads((HERE / "data" / "reading_lists_sources.json").read_text(encoding="utf-8"))


def find_reviews(recs, rx):
    pat = re.compile(rx, re.I)
    out = []
    for r in recs:
        if not r.get("year") or not (1980 <= r["year"] <= 2026) or NON_BOOK_TITLE.search(r["title"]):
            continue
        pc = page_count(r["page"])
        if pc is not None and pc <= 8 and pat.search(clean_citation(r["title"])):
            out.append(r)
    return sorted(out, key=lambda r: (r["year"], r["journal"]))


def review_links(rs):
    return "；".join(f"[{r['journal']} {r['year']}](https://doi.org/{r['doi']})" for r in rs) or "—"


def link(url, text):
    return f"[{md_escape(text)}]({url})"


def first_match(text, pairs):
    for rx, *rest in pairs:
        if re.search(rx, text, re.I):
            return rest
    return None


def daston_section(src, recs):
    d = src["daston"]
    L = ["## 一、MPIWG Department II（Daston）書單", "",
         f"來源：[{d['department_title']}]({d['page']})（部門頁面）、[Working Group Books]({d['wg_books_page']})。網站內容抓取於 {src['fetched']}。", "",
         "- **數量說明：** 部門頁面介紹說有 22 卷 Working Group 書，但 Working Group Books 頁面實際只列出 20 條，下表是頁面上列出的全部。",
         "- **「相關度」是我只憑書名做的判斷，沒有讀過這些書。** 部門本身是研究理性的歷史，大部分書不是專門寫 vernacular 或 popular science 的。",
         "- **「四刊書評」一欄**是在 Isis、Osiris、History of Science、BJHS 的 Crossref 記錄里按書名找到的書評；查不到不代表沒有被評過。", "",
         "### 1.1 Working Group Books", "",
         "| # | 年份 | 書／專號 | 相關度（我的判斷） | 四刊書評 |", "|---|---|---|---|---|"]
    entries = []
    for i, b in enumerate(d["working_group_books"], 1):
        cit = b["citation"]
        rel = first_match(cit, WG_RELEVANCE)
        rx = next((v for k, v in WG_REVIEW_RX.items() if k.lower() in cit.lower()), None)
        rv = find_reviews(recs, rx) if rx else []
        extra = ""
        if re.search(r"Data Histories", cit):  # an Osiris special issue: list its Osiris contents
            osr = [r for r in recs if r["journal"] == "Osiris" and r["year"] == 2017 and str(r.get("volume")) == "32"]
            extra = f"Osiris 32 本身，共 {len(osr)} 條記錄（見 results 原始數據）"
        entries.append((i, b, rel, rv, extra))
        label = f"{rel[0]}：{rel[1]}" if rel else "低（按書名）"
        L.append(f"| {i} | {b['year']} | {md_escape(cit[:170])} | {md_escape(label)} | {review_links(rv) if rv else (extra or '—')} |")
    L += ["", "### 1.2 部門的研究項目（官方標題）", "",
          "項目頁面的描述我沒有逐頁摘錄；標題是各項目頁 `<title>` 里的原文。下表「對應的書」是我按標題對上的，不是網站明說的。", "",
          "| 項目 | 可能對應的書（我的對應） |", "|---|---|"]
    mapping = {"Scientific Objects": "Biographies of Scientific Objects（2000）", "Historia": "Historia: Empiricism and Erudition（2005）",
               "Scientific Observation": "Histories of Scientific Observation（2011）", "Sciences of the Archive": "Science in the Archives（2017）",
               "Cold War Rationality": "How Reason Almost Lost its Mind（2013）", "Gender Studies": "Working with Paper（2019）；Beyond the Academy（2013）"}
    for p in d["projects"]:
        m = next((v for k, v in mapping.items() if k.lower() in p["title"].lower()), "未對應")
        L.append(f"| {link(p['url'], p['title'])} | {m} |")
    L += ["", "### 1.3 逐書條目", ""]
    for i, b, rel, rv, extra in entries:
        L += [f"**{i}.** {b['citation']}", f"- 相關度：{rel[0] + '，' + rel[1] if rel else '低（按書名）'}", f"- 四刊書評：{review_links(rv) if rv else (extra or '未找到')}", ""]
    return L


def sftp_section(src, recs):
    s = src["sftp"]
    L = ["## 二、Science for the People（SftP）書單", "",
         f"來源：[{s['site']}]({s['site']})、[Resources]({s['resources']})、期刊網站 magazine.scienceforthepeople.org、歷史檔案 archive.scienceforthepeople.org。網站內容抓取於 {src['fetched']}。", "",
         "- 這裡的「書單」其實是**書、小冊子、期刊專號和專輯**的混合清單，因為 SftP 網站上列出的主要是這些。",
         "- 「相關度」同樣是我的判斷，且對期刊文章是看標題。", "",
         "### 2.1 書與小冊子（網站 Resources 頁）", "", "| # | 條目 | 四刊書評 |", "|---|---|---|"]
    doc_rv = find_reviews(recs, r"science for the people: documents")
    for i, it in enumerate(s["resource_items"], 1):
        rv = doc_rv if "Documents from America" in it["title"] else []
        extra = f"（[在線閱讀]({it['extra']})）" if it.get("extra") else ""
        note = ""
        if rv:
            note = review_links(rv) + "；Schmalzer 為合編者（見 Isis 的書目引用）"
        L.append(f"| {i} | {link(it['url'], it['title'])}{extra} | {note or '—'} |")
    L += ["", "### 2.2 與 Schmalzer 研究方向的連接（四刊數據）", ""]
    for rx, name in ((r"people.s peking man", "The People's Peking Man"), (r"science for the people: documents", "Science for the People: Documents（合編）")):
        L.append(f"- *{name}*：{review_links(find_reviews(recs, rx))}")
    L += ["", "### 2.3 期刊專號（2018 年起新版）", "", "| 專號 | 與你主題的相關度（我的判斷） |", "|---|---|"]
    hi = {"Rethinking Science Communication": "高：科學傳播、缺失模型、大眾科學雜誌", "Ways of Knowing": "高：原住民與地方知識、認識論多樣性",
          "Envisioning and Enacting": "中：「以人民為中心的科學」", "Return of Radical Science": "中：運動復興的背景"}
    for t, u in s["issues"]:
        rel = next((v for k, v in hi.items() if k in t), "—")
        L.append(f"| {link(u, t)} | {rel} |")
    L += ["", "### 2.4 專輯（Specials）", "", "| 專輯 | 說明 |", "|---|---|"]
    sp_note = {"China": "對 1970 年代《China: Science Walks on Two Legs》的重讀，**最直接連著 Schmalzer 的研究方向（毛時代中國的大眾科學）**——關聯是我的判斷"}
    for t, u in s["specials"]:
        L.append(f"| {link(u, t)} | {next((v for k, v in sp_note.items() if k in t), '—')} |")
    L += ["", "### 2.5 與主題最相關的幾期里的文章（標題取自專號頁面）", ""]
    for issue, arts in s["articles"].items():
        L += [f"**{issue}**", ""]
        for a in arts:
            if a["title"] == "The Magazine":
                continue
            why = next((v for k, v in SFTP_RELEVANT.items() if re.search(k, a["title"], re.I)), "")
            L.append(f"- {link(a['url'], a['title'])}" + (f" ——{why}（我的判斷）" if why else ""))
        L.append("")
    L += ["### 2.6 歷史刊物檔案（1969–1989）", "", s["archive"]["note"], "",
          f"- 檔案首頁：{s['archive']['index']}"]
    L += [f"- {link(u, t)}" for t, u in s["archive"]["volumes"]]
    L += ["", "**局限：** 歷史各卷我只拿到卷號和網址，沒有逐篇列出，所以這部分不能直接當書單用。要按主題找文章，需要到檔案網站搜索。", ""]
    return L


def main(outdir="output"):
    outdir = Path(outdir)
    cache = outdir / "raw_records.json"
    if not cache.exists():
        sys.exit("Run search_reviews.py first (it writes output/raw_records.json).")
    recs = json.loads(cache.read_text(encoding="utf-8"))
    src = load_sources()
    L = ["# 書單：MPIWG Daston 部門 與 Science for the People", "",
         f"生成於 {time.strftime('%Y-%m-%d')}。兩份清單的條目都取自這兩個組織自己的網站（抓取於 {src['fetched']}），"
         "再與 Isis、Osiris、History of Science、BJHS 的書評記錄交叉核對。", "",
         "**怎麼讀：** 條目本身是網站上有的；「相關度」「對應」「原因」是我的判斷，已逐處標明；我沒有讀過這些書。", "",
         "- [一、MPIWG Department II（Daston）書單](#一mpiwg-department-iidaston書單)",
         "- [二、Science for the People（SftP）書單](#二science-for-the-peoplesftp書單)", "", "---", ""]
    L += daston_section(src, recs) + ["---", ""] + sftp_section(src, recs)
    (outdir / "reading_lists.md").write_text("\n".join(L), encoding="utf-8")
    print(f"Done -> {outdir / 'reading_lists.md'}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "output")
