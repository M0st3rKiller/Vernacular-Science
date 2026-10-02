#!/usr/bin/env python3
"""Build output/key_authors.md: a watchlist of 40 scholars (topics, how each frames
"vernacular"/"popular"/"everyday" science) plus their traces in Isis, Osiris,
History of Science and BJHS, taken from output/raw_records.json (run search_reviews.py first).

Basis tags in the output:
  [data]       the framing is taken from an abstract in the four journals
  [background] the framing is a summary from general knowledge of the author's work; verify before citing
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from search_reviews import NON_BOOK_TITLE, clean_citation, md_escape, page_count  # noqa: E402

D, B = "[data]", "[background]"

# name, regex alternatives (on normalised lowercase text), topics, stance on vernacular/popular/everyday, basis
PEOPLE = [
    ("Bernard Lightman", [r"bernard\s+lightman"], "維多利亞時期科學普及者（Tyndall、Huxley 等）、科學與宗教、視覺文化",
     "把普及者看作有自己立場、為特定讀者「設計自然」的作者，而不是被動的傳聲筒；批評單向的擴散模型。", B),
    ("Aileen Fyfe", [r"aileen\s+fyfe"], "十九世紀英國科學出版：福音派出版社、廉價印刷品、讀者；皇家學會期刊",
     "把 popular science 當作一門出版業和宗教事業來研究，重點是出版機構、市場與讀者，而不是「科學家向公眾解釋」。", B),
    ("Ralph O'Connor", [r"ralph\s+o'?connor"], "地質學與化石的大眾文化、普及科學的文學體裁與詩學；新近還寫過年輕地球創世論的史學",
     "主張更系統地引入文學史與體裁研究，把科學看作一套傳播實踐；反對把 popular science、popularization 這類範疇從學術語彙裡清除，稱它們是有用的「統稱標籤」。", D),
    ("Jonathan R. Topham", [r"jonathan\s+(?:r\.?\s+)?topham"], "科學印刷與期刊文化、閱讀史；Bridgewater Treatises 的生產與閱讀；Isis 2009 Focus 組的導言作者",
     "在導言中把問題定為：放棄對 popular science 的本質主義定義，改為考察它作為「行動者範疇」在近兩個世紀裡的複雜歷史，並強調跨國與跨學科視角。", D),
    ("Roger Cooter", [r"roger\s+cooter"], "骨相學作為大眾科學、醫學與身體的文化史",
     "《The Cultural Meaning of Popular Science》把大眾科學放在階級與社會共識的脈絡裡，看作社會力量的一部分。與 Pumfrey 合寫 1994 年的 History of Science 論文，反思「科學普及」與「大眾文化中的科學」的研究。", B),
    ("Stephen Pumfrey", [r"stephen\s+pumfrey"], "早期近代英國自然哲學、磁學、科學文化",
     "與 Cooter 合寫 1994 年 History of Science 論文 'Separate Spheres and Public Places'，質疑把精英科學與大眾科學截然分成兩個領域。", B),
    ("Katherine Pandora", [r"katherine\s+pandora"], "美國大眾文化中的科學、內戰前（antebellum）時期的普及科學、Luther Burbank",
     "主張內戰前美國是理解 popular science 的關鍵時期，因為它在不同政治背景下歷史上多變多樣；與 Rader 一起論證各種「公眾」應被算進更大的科學共同體。", D),
    ("Karen A. Rader", [r"karen\s+(?:a\.?\s+)?rader"], "二十世紀美國科學博物館、科學與公眾、實驗動物史",
     "與 Pandora 合寫 'Science in the Everyday World'（Isis 2008）：博物館等場所是傳達科學觀念與科學實踐觀念的重要陣地。", D),
    ("Peter J. Bowler", [r"peter\s+(?:j\.?\s+)?bowler"], "二十世紀初英國科學普及、進化論與宗教、科學與大眾",
     "《Science for All》把普及作為二十世紀初大眾接受科學的主要途徑，包括作者、出版與媒體；BJHS 2006 主席演講討論專家與出版商如何寫 popular science。", B),
    ("Andreas W. Daum", [r"andreas\s+(?:w\.?\s+)?daum"], "十九世紀德國科學普及與市民社會、公共知識",
     "主張把各種 popular science 放進更大的「公共知識」過程：不同時空、文化裡生成與轉化公共知識的過程、實踐與行動者；要去本質化、歷史化 popularization，並關注「科學」以外的知識形式。", D),
    ("Bernadette Bensaude-Vincent", [r"bernadette\s+bensaude"], "化學史、科學與公眾輿論、納米技術與公共領域",
     "主張對稱地看問題：不僅科學及其公共面貌是社會建構的，「外行公眾」本身也是被科學實踐建構出來的；研究重點應放在科學與其他知識形式之間的劃界機制；並提到從缺失模型轉向參與模型。", D),
    ("Agustí Nieto-Galan", [r"agust[ií]\s+nieto", r"august[ií]\s+nieto"], "加泰羅尼亞與西班牙的科學普及、染料工匠與化學、公共領域中的外行知識與專業知識",
     "把科學放在公共領域裡看外行知識與專家知識的互動；與 Florensa 在 History of Science 2022 專號導言中，透過獨裁政權下的普及來重新檢視 'popular science' 與 'public sphere' 的定義。", D),
    ("Sigrid Schmalzer", [r"sigrid\s+schmalzer"], "毛時代中國的大眾科學、農業中的「群眾科學」、北京人化石的公共歷史、美國的 Science for the People 運動",
     "《The People's Peking Man》把 popular science 與政治動員、身份認同連在一起，普通人不是知識的被動接收者，而是科學生產的參與者。", B),
    ("Peter Broks", [r"peter\s+broks"], "媒體研究視角下的 popular science、科學傳播",
     "《Understanding Popular Science》把 popular science 看作一種文化形式與傳播現象，從媒體與文化研究的角度分析，而不只是科學的簡化版本。", B),
    ("Michael R. Lynn", [r"michael\s+(?:r\.?\s+)?lynn"], "啟蒙時代法國的公共科學、沙龍、咖啡館、氣球與公開演示",
     "《Popular Science and Public Opinion in Eighteenth-Century France》把科學普及與公共輿論的形成連在一起。", B),
    ("Maurice Crosland", [r"maurice\s+crosland"], "科學語言、化學命名法、從方言到專門術語",
     "《The Language of Science: From the Vernacular to the Technical》：vernacular 取語言學意義，即日常語言與專門術語之間的關係。", B),
    ("John C. Burnham", [r"john\s+(?:c\.?\s+)?burnham"], "美國的科學與健康普及",
     "《How Superstition Won and Science Lost》是普及史的早期代表作，認為普及並沒有真正傳播科學精神。Isis 2019 有三篇專門評論他的文章。", B),
    ("Rebecca Onion", [r"rebecca\s+onion"], "美國兒童與大眾科學文化：科學博物館、玩具、書籍",
     "《Innocent Experiments》把兒童當作大眾科學的核心受眾與參與者，popular science 是一種以童年為中心的文化實踐。", B),
    ("Helen Tilley", [r"helen\s+tilley"], "非洲殖民地科學、「地方／原住民知識」的編碼、全球科學史",
     "在 Isis 2010 年的文章中，把「口傳的原住民知識」被研究和編碼，看作科學全球化、人類學專業化、殖民國家建設這幾個過程的副產品；vernacular science 在這裡指被殖民邊緣的地方知識。", D),
    ("Eugenia Lean", [r"eugenia\s+lean"], "近代中國的地方創新與被翻譯的技術、化妝品與化工",
     "《Vernacular Industrialism in China》用 vernacular 指在地行動者把全球技術翻譯、轉化成本地可用形式的過程（我的理解，請核對原書的定義）。", B),
    ("James A. Secord", [r"james\s+(?:a\.?\s+)?secord", r"jim\s+secord"], "維多利亞時期科學閱讀與流通：《Vestiges》、Lyell、Visions of Science",
     "提出「流通中的知識」（knowledge in transit）：與其把 popular science 看作從專家向公眾的擴散，不如研究知識如何在閱讀、傳播中被轉化；並建議放棄 popular science 作為中性描述詞，因為它帶有「擴散論包袱」（Topham 導言轉述）。", D),
    ("Larry Stewart", [r"larry\s+stewart"], "十八世紀英國的公共科學、牛頓主義公開講演、儀器與商業",
     "《The Rise of Public Science》把科學講演看作商業化的公共活動，與技術、工業利益聯繫在一起。", B),
    ("Pamela H. Smith", [r"pamela\s+(?:h\.?\s+)?smith"], "工匠知識、鍊金術、「making and knowing」",
     "《The Body of the Artisan》把工匠的身體實踐與知識看作自然知識的來源，挑戰把理論與手藝分開的敘述。", B),
    ("David Edgerton", [r"david\s+edgerton"], "技術史、技術在使用中的歷史、二十世紀英國",
     "《The Shock of the Old》主張從「使用中的技術」而不是創新出發寫技術史，這和 everyday technology 的取向最接近。", B),
    ("Adrian Johns", [r"adrian\s+johns"], "印刷文化與知識的可信性、盜版與知識產權",
     "《The Nature of the Book》主張書本的可靠性不是印刷本身賦予的，而是取決於具體的實踐和信任關係，這對理解「大眾讀物」很有用。", B),
    ("William Eamon", [r"william\s+eamon"], "文藝復興的秘籍書（books of secrets）、方言科學寫作",
     "《Science and the Secrets of Nature》研究用方言寫作的秘籍書如何傳播自然知識，是早期近代 vernacular science 的經典個案。", B),
    ("Ruth Schwartz Cowan", [r"ruth\s+schwartz\s+cowan"], "家庭技術史、家務勞動、技術與性別",
     "《More Work for Mother》研究家庭技術如何改變家務：日常技術並不一定省力，反而改變了期望和分工。", B),
    ("Ronald R. Kline", [r"ronald\s+(?:r\.?\s+)?kline"], "農村電氣化、技術使用者、美國技術史",
     "《Consumers in the Country》把使用者看作技術變遷的主動參與者。", B),
    ("Susan Sheets-Pyenson", [r"sheets-?pyenson"], "殖民地與邊緣地區的自然史博物館、地方科學文化",
     "《Cathedrals of Science》研究十九世紀殖民地自然史博物館，關注科學的邊緣與地方形態。", B),
    ("Ann B. Shteir", [r"ann\s+(?:b\.?\s+)?shteir"], "英國的女性與植物學、植物學的普及與性別",
     "《Cultivating Women, Cultivating Science》研究植物學如何成為女性可以參與的知識領域；與 Lightman 合編《Figuring It Out》，討論科學、性別與視覺文化。", B),
    ("Alison Winter", [r"alison\s+winter"], "維多利亞時期的催眠術、公共實踐與科學權威、記憶史",
     "《Mesmerized》研究催眠術在公共表演與日常實踐中的流行，說明科學權威如何在公眾面前被確立。", B),
    ("Lynn K. Nyhart", [r"lynn\s+(?:k\.?\s+)?nyhart"], "德國的大眾博物學、博物館、生物學的學院化",
     "《Modern Nature》研究十九世紀德國大眾自然史與學院生物學之間的關係。", B),
    ("Peter Burke", [r"peter\s+burke"], "知識社會史、早期近代歐洲的文化史",
     "《A Social History of Knowledge》把知識看作多元的、有社會層次的，並區分不同類型的知識（含大眾、地方知識）。", B),
    ("Kapil Raj", [r"kapil\s+raj"], "南亞與歐洲之間的科學流通、翻譯與地方知識",
     "《Relocating Modern Science》把現代科學看作在南亞和歐洲之間流通、協商的結果，地方行動者是知識生產的共同參與者。", B),
    ("Deborah Harkness", [r"deborah\s+(?:e\.?\s+)?harkness"], "伊麗莎白時代倫敦的工匠、醫生與自然知識實踐者",
     "《The Jewel House》主張倫敦的實踐者共同體是科學革命的重要場所，非學院的人群在其中起了作用。", B),
    ("Pamela O. Long", [r"pamela\s+(?:o\.?\s+)?long"], "工匠與技術寫作、文藝復興時期技術知識的書寫與公開",
     "《Openness, Secrecy, Authorship》研究技術知識如何從手藝傳統走向寫作與公開。", B),
    ("Elaine Leong", [r"elaine\s+leong"], "早期近代英國的家庭醫藥配方、日常知識與女性實踐者",
     "與 Alisha Rankin 合編《Secrets and Knowledge in Medicine and Science》，研究家庭配方、秘方和日常知識的傳遞。", B),
    ("Iwan Rhys Morus", [r"iwan\s+(?:rhys\s+)?morus"], "維多利亞時期倫敦的電學表演、公共展覽與科學",
     "《Frankenstein's Children》研究電學在公開展示和表演中的意義，說明公共展示本身是科學實踐的一部分。", B),
    ("Gowan Dawson", [r"gowan\s+dawson"], "維多利亞時期的科學與文學、期刊、科學自然主義",
     "《Darwin, Literature and Victorian Respectability》與《Victorian Scientific Naturalism》（與 Lightman 合編）研究維多利亞期刊與科學寫作。", B),
    ("Marcel C. LaFollette", [r"marcel\s+(?:c\.?\s+|chotkowski\s+)?lafollette"], "二十世紀美國媒體中的科學形象：雜誌、廣播、電視",
     "《Making Science Our Own》與《Science on the Air》把大眾媒體塑造的科學形象和科學普及者作為研究對象。", B),
]

# Definitions section: (label, journal, year, title prefix, one-line gloss)
DEF_SOURCES = {
    "topham": ("Isis", 2009, "Introduction"),
    "bensaude": ("Isis", 2009, "A Historical Perspective on Science and Its"),
    "pandora": ("Isis", 2008, "Science in the Everyday World"),
    "tilley": ("Isis", 2010, "Global Histories, Vernacular Science"),
    "gurevitch": ("History of Science", 2020, "The uses of useful knowledge"),
    "meade": ("History of Science", 2023, "Science across the Meiji divide"),
    "bill": ("BJHS", 2018, "Imperial vernacular"),
    "fransen": ("Isis", 2017, "Latin in a Time of Change"),
    "schafer": ("Isis", 2017, "Thinking in Many Tongues"),
    "oconnor": ("Isis", 2009, "Reflections on Popular Science in Britain"),
    "daum": ("Isis", 2009, "Varieties of Popular Science"),
    "florensa": ("History of Science", 2022, "Introduction: Science popularization"),
}


# Book titles that identify a review when the citation omits the author's name.
KEY_TITLES = {
    "Bernard Lightman": r"victorian popularizers of science", "Aileen Fyfe": r"science and salvation",
    "Ralph O'Connor": r"earth on show", "Roger Cooter": r"cultural meaning of popular science",
    "Peter J. Bowler": r"science for all: the popularization", "Rebecca Onion": r"innocent experiments",
    "Eugenia Lean": r"vernacular industrialism", "James A. Secord": r"victorian sensation|visions of science",
    "Larry Stewart": r"rise of public science", "Pamela H. Smith": r"body of the artisan|business of alchemy",
    "David Edgerton": r"shock of the old", "Adrian Johns": r"nature of the book", "William Eamon": r"science and the secrets of nature",
    "Ruth Schwartz Cowan": r"more work for mother", "Ronald R. Kline": r"consumers in the country",
    "Susan Sheets-Pyenson": r"cathedrals of science", "Ann B. Shteir": r"cultivating women, cultivating science",
    "Alison Winter": r"mesmerized: powers of mind", "Lynn K. Nyhart": r"modern nature: the rise of the biological",
    "Peter Burke": r"social history of knowledge", "Kapil Raj": r"relocating modern science",
    "Deborah Harkness": r"the jewel house", "Pamela O. Long": r"openness, secrecy, authorship",
    "Iwan Rhys Morus": r"frankenstein.s children", "Marcel C. LaFollette": r"making science our own|science on the air",
    "Michael R. Lynn": r"popular science and public opinion", "Maurice Crosland": r"language of science: from the vernacular",
    "Sigrid Schmalzer": r"people.s peking man", "Peter Broks": r"understanding popular science",
    "John C. Burnham": r"how superstition won and science lost",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[‐-―−]", "-", s)
    return re.sub(r"\s+", " ", s).lower()


def find_rec(recs, journal, year, prefix):
    for r in recs:
        if r["journal"] == journal and r["year"] == year and r["title"].startswith(prefix) and r.get("abstract"):
            return r
    return None


def link(r, text):
    return f"[{text}](https://doi.org/{r['doi']})" if r.get("doi") else text


def line(r, text):
    vol = f"{r['volume']}" + (f"({r['issue']})" if r["issue"] else "")
    return f"- {r['year']} · {r['journal']} {vol}, pp. {r['page']} · {link(r, md_escape(text[:150]))}"


def person_records(recs, patterns, title_rx=None):
    rx = re.compile("|".join(patterns))
    trx = re.compile(title_rx) if title_rx else None
    arts, reviewed, reviewing = [], [], []
    for r in recs:
        if not r.get("year") or not (1980 <= r["year"] <= 2026) or NON_BOOK_TITLE.search(r["title"]):
            continue
        pc = page_count(r["page"])
        in_auth = bool(rx.search(norm(r.get("authors", ""))))
        cit = clean_citation(r["title"])
        in_cit = bool(rx.search(norm(cit))) or bool(trx and trx.search(norm(cit)))
        if pc is not None and pc <= 6:
            if in_cit and not in_auth:
                reviewed.append((r, cit))
            elif in_auth:
                reviewing.append((r, cit))
        elif in_auth and pc is not None:
            arts.append((r, r["title"]))
    key = lambda t: (t[0]["year"], t[0]["journal"])
    return sorted(arts, key=key), sorted(reviewed, key=key), sorted(reviewing, key=key)


def main(outdir="output"):
    outdir = Path(outdir)
    cache = outdir / "raw_records.json"
    if not cache.exists():
        sys.exit("Run search_reviews.py first (it writes output/raw_records.json).")
    recs = json.loads(cache.read_text(encoding="utf-8"))
    D_ = {k: find_rec(recs, *v) for k, v in DEF_SOURCES.items()}

    def ref(k, label):
        r = D_.get(k)
        return f"[{label}]({'https://doi.org/' + r['doi']})" if r else label

    L = ["# 關注作者表：vernacular／popular／everyday science 的 40 位學者", "",
         f"生成於 {time.strftime('%Y-%m-%d')} · 數據來自 Isis、Osiris、History of Science、BJHS 1980–2026（Crossref + OpenAlex）", "",
         "**怎麼讀這份文件**", "",
         "- 每位學者的「研究題目」和「對 vernacular／popular／everyday 的取向」旁邊有依據標記：`[data]` = 來自這四本刊的摘要；`[background]` = 我根據對其著作的一般了解寫的概括，**沒有在數據裡核實，引用前請核對原書**。",
         "- 「在四刊中的記錄」是按姓名在 Crossref 條目裡匹配出來的：他們寫的文章、他們的書被評的書評、他們自己寫的書評。姓名匹配可能把同名的人混進來，也可能因為書評格式不一致而漏掉。",
         "- 名單是我挑選的，不是「引用最多」的客觀排序。", "",
         "---", "", "## 一、「vernacular」到底指什麼：目前結果裡能看到的五種用法", "",
         "這個領域沒有公認的定義，同一個詞在不同作者那裡指不同的東西。下面按這四本刊裡的文章整理，**引文都來自摘要**。", ""]
    def quote(k, n=380):
        r = D_.get(k)
        return (r["abstract"][:n].rsplit(" ", 1)[0] + " …") if r else ""

    L += ["### 1. 語言意義：方言／本地語言 vs. 拉丁語或學術語言", "",
          f"- {ref('fransen', 'Fransen, Isis 2017')}：伽利略、笛卡爾、Van Helmont 在拉丁語仍是學術語言的時候，有時選擇用母語寫作，這些選擇「是社會的、政治的，並且總是非常重要的」。",
          f"- {ref('schafer', 'Schäfer, Isis 2017')}：晚期帝制中國的科學常被想成只用一種語言，但多語實踐可能才是常態。",
          f"- {ref('gurevitch', 'Gurevitch, History of Science 2020')}：十一世紀南印度學者用 New Kannada 寫「對世人有用的世間科學」，把本地語境當作優點。",
          "- Crosland 的《The Language of Science: From the Vernacular to the Technical》（Isis 2007、BJHS 2008 有書評）是這一用法的書名級例子。", "",
          "### 2. 社會意義：非精英、非學院、口傳或實踐中的知識", "",
          f"- {ref('pandora', 'Pandora & Rader, Isis 2008')}：主張各種現代「公眾」都應算進更大的科學共同體，並說自然知識的生產發生在「vernacular contexts」裡，舉了維多利亞的 popular science 出版、美國科學博物館、大眾媒體中的科學家形象三例。",
          f"- {ref('tilley', 'Tilley, Isis 2010')}：討論「原始」或「原住民」知識，尤其是口傳知識，如何被編碼、研究，是科學全球化、人類學專業化、殖民國家建設等因素的副產品。",
          "- 工匠與實踐者方向（Smith、Long、Harkness 等）屬於同一傳統，但他們不一定用 vernacular 這個詞。", "",
          "### 3. 文類意義：用本地體裁寫成、被現代科學史忽略的科學作品", "",
          f"- {ref('meade', 'Meade, History of Science 2023')}：日本明治時期的 kyūri 書等 vernacular 體裁被貼上「前現代」標籤，結果恰好是大多數人接觸科學的作品被邊緣化；文章問，如果把它們當作科學書本身來看會怎樣。",
          f"- {ref('bill', 'Bill, BJHS 2018')}：「Imperial vernacular」——原住民植物名在 Humboldt 之後被當作語文學材料，而普遍適用的是拉丁名；這是把 vernacular 放在殖民權力關係中看。", "",
          "### 4. 公眾意義：popular science / popularization / 公共知識（爭論最集中）", "",
          f"- {ref('topham', 'Topham 導言，Isis 2009')}：引述 Secord 的建議，認為 popular science 帶有「擴散論包袱」，不宜再當中性描述詞，應改看它作為「行動者範疇」的歷史。",
          f"- {ref('oconnor', 'O’Connor, Isis 2009')}：反對把這些範疇清除，認為處理得當時它們是跨學科、與更廣泛公眾溝通的「統稱標籤」；並建議引入文學體裁研究。",
          f"- {ref('daum', 'Daum, Isis 2009')}：把 popular science 放進更大的「公共知識」生成過程，要去本質化、歷史化，也要關注科學以外的知識形式。",
          f"- {ref('bensaude', 'Bensaude-Vincent, Isis 2009')}：從缺失模型到參與模型的轉變意味著，「外行公眾」也是被科學實踐建構出來的，應關注科學與其他知識形式之間的劃界。",
          f"- {ref('florensa', 'Florensa & Nieto-Galan, History of Science 2022')}：從獨裁政權下的普及重新審視 popular science 與 public sphere 兩個範疇。", "",
          "### 5. 日常與使用意義：everyday science / everyday technology", "",
          "- Pandora & Rader（見上）的標題就是 'Science in the Everyday World'。",
          "- 技術史方向：Edgerton（使用中的技術）、Cowan（家庭技術）、Kline（農村使用者）；Isis 2014 評過 Arnold 的《Everyday Technology》，BJHS 2016 評過 Josephson 的《Fish Sticks, Sports Bras, and Aluminum Cans》。",
          "- Lean 的《Vernacular Industrialism in China》（Isis 2021 書評）把 vernacular 用於技術的在地化與翻譯。", "",
          "### 我的小結（供你定義研究範圍時參考，不是定論）", "",
          "1. **這個領域至少有三條互相交叉但並不重合的線**：語言／文類（第 1、3 種）、非精英知識（第 2 種）、公眾與普及（第 4 種）；日常技術（第 5 種）是另一條平行的線。",
          "2. **如果你要做文獻綜述，建議先固定一個操作性定義**，例如：「用非學術語言、由非學院行動者、或在本地／日常情境中生產與傳播的科學與技術知識」。這個定義我是自己概括的，不是從文獻裡引來的，需要你根據研究目的調整。",
          "3. **popular science 與 vernacular science 不是同義詞**。Isis 2009 的那組論爭，說明 popular science 這個詞本身就有爭議；而 vernacular 更強調語言與地方性。",
          "", "---", "", "## 二、40 位學者目錄", "",
          "| # | 學者 | 主要題目 | 依據 | 他們的文章 | 其書被評 | 自己寫書評 |", "|---|---|---|---|---|---|---|"]

    body = ["", "---", "", "## 三、逐人條目", ""]
    for i, (name, pats, topics, stance, basis) in enumerate(PEOPLE, 1):
        arts, reviewed, reviewing = person_records(recs, pats, KEY_TITLES.get(name))
        L.append(f"| {i} | [{name}](#p{i}) | {md_escape(topics[:60])}… | {basis} | {len(arts)} | {len(reviewed)} | {len(reviewing)} |")
        body += [f'<a id="p{i}"></a>', f"### {i}. {name}", "",
                 f"- **研究題目：** {topics}", f"- **對 vernacular／popular／everyday 的取向：** {stance} `{basis}`", ""]
        for title, lst in (("在四刊發表的文章（含評論文章）", arts), ("其著作在四刊中被評的書評", reviewed), ("他／她為四刊寫的書評", reviewing)):
            body.append(f"**{title}**（{len(lst)}）")
            body.append("")
            if lst:
                body += [line(r, t) for r, t in lst[:40]]
                if len(lst) > 40:
                    body.append(f"- … 另有 {len(lst) - 40} 條，見 results 原始數據")
            else:
                body.append("- 未在匹配中找到")
            body.append("")
    (outdir / "key_authors.md").write_text("\n".join(L + body), encoding="utf-8")
    print(f"Done: {len(PEOPLE)} people -> {outdir / 'key_authors.md'}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "output")
