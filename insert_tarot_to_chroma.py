"""把 resources/tarot/tarot-basic.docx（塔罗知识库）解析并写入 Chroma 向量库。

用法：
    python insert_tarot_to_chroma.py            # 解析 + 入库（需本地 Ollama 已运行并已拉取 bge-m3）
    python insert_tarot_to_chroma.py --dry-run  # 只解析，打印统计与样例，不写库

产出：
    - 78 张牌文档（每张牌一条，正文自包含：牌名+关键词+对应+牌面意象+正位+逆位）
    - 19 条通用知识文档（结构/花色/宫廷/历史/大阿卡纳详表/旬星/占星速查/伪史/关于占卜/来源）
    集合名 tarot_knowledge，独立于风水集合 local_documents。
"""
import argparse
import os
import re
import zipfile

from lxml import etree

from models import get_ollama_embeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

DOCX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "tarot", "tarot-basic.docx")
PERSIST_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "tarot_knowledge"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 花色 → (英文, 元素)
SUITS = {"权杖": ("Wands", "火"), "圣杯": ("Cups", "水"), "宝剑": ("Swords", "风"), "星币": ("Pentacles", "土")}
RANKS = {"侍从": "Page", "骑士": "Knight", "王后": "Queen", "国王": "King"}
CN_NUM = {"二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}

# 章节序号 → 章节 key
CN_ORD = {
    "一": "structure", "二": "suits", "三": "court", "四": "history",
    "五": "major_table", "六": "decan", "七": "astro", "八": "cards",
    "九": "pseudohistory", "十": "about_divination", "十一": "sources",
}
SECTION_LABEL = {
    "structure": "结构", "suits": "四花色", "court": "宫廷牌元素", "history": "历史源流",
    "major_table": "大阿卡纳详表", "decan": "旬星对应", "astro": "占星速查",
    "cards": "牌义图鉴", "pseudohistory": "伪史澄清", "about_divination": "关于占卜", "sources": "来源依据",
}
# 通用知识章节（cards 章节单独处理为 78 张牌）
GENERAL_SECTIONS = {k for k in CN_ORD.values() if k != "cards"}

_STYLE_H1 = "00000a"
_STYLE_H2 = "000008"
_STYLE_H3 = "000009"
_STYLE_TOC = "000006"


def p_text(p):
    """段落内所有 w:t 文本（忽略域代码，TOC 已按样式跳过）。"""
    return "".join(t.text or "" for t in p.iter(W + "t"))


def p_style(p):
    pPr = p.find(W + "pPr")
    if pPr is None:
        return ""
    ps = pPr.find(W + "pStyle")
    return ps.get(W + "val") if ps is not None else ""


def table_rows(tbl):
    rows = []
    for tr in tbl.findall(W + "tr"):
        cells = ["".join(t.text or "" for t in tc.iter(W + "t")).strip()
                 for tc in tr.findall(W + "tc")]
        rows.append(cells)
    return rows


def section_key(heading_text):
    """由标题序号（一/二/…/十一）得到章节 key。"""
    m = re.match(r"^([一二三四五六七八九十]+)、", heading_text)
    return CN_ORD.get(m.group(1)) if m else None


def parse_card_heading(heading):
    """解析卡牌标题，如「0 · 愚者（The Fool）」「权杖侍从（Page of Wands）」。返回元数据字典或 None。"""
    m = re.match(r"^\s*(.*?)\s*（([^（）]+)）\s*$", heading)
    if not m:
        return None
    cn_full, en = m.group(1).strip(), m.group(2).strip()
    mm = re.match(r"^(0|[IVX]+)\s*·\s*(.+)$", cn_full)
    if mm:
        return {
            "card": mm.group(2).strip(), "card_en": en, "arcana": "major",
            "number": mm.group(1).strip(), "suit": "", "suit_en": "",
            "element": "", "rank": "", "keywords": "",
        }
    for scn, (se, el) in SUITS.items():
        if cn_full.startswith(scn):
            suit_cn, suit_en, element = scn, se, el
            break
    else:
        return None
    rest = cn_full[len(suit_cn):]
    rank = number = ""
    if rest in RANKS:
        rank = rest
    elif rest == "首牌":
        number = "Ace"
    elif rest in CN_NUM:
        number = CN_NUM[rest]
    return {
        "card": cn_full, "card_en": en, "arcana": "minor",
        "number": number, "suit": suit_cn, "suit_en": suit_en,
        "element": element, "rank": rank, "keywords": "",
    }


def build_card(heading, rows):
    meta = parse_card_heading(heading)
    if meta is None:
        return None
    if meta["arcana"] == "major":
        title = f"{meta['card']}（{meta['card_en']}）｜大阿卡纳 {meta['number']}"
    elif meta["rank"]:
        title = f"{meta['card']}（{meta['card_en']}）｜小阿卡纳·宫廷牌·{meta['suit']}"
    else:
        title = f"{meta['card']}（{meta['card_en']}）｜小阿卡纳·数字牌·{meta['suit']}"
    lines = [title]
    for row in rows:
        key = row[0].strip()
        if key == "来源":
            continue
        val = " | ".join(c.strip() for c in row[1:] if c.strip())
        if not val or val in ("undefined", "None"):
            continue
        if key == "关键词":
            meta["keywords"] = val
        lines.append(f"{key}：{val}")
    meta["doc_type"] = "card"
    meta["section"] = "牌义图鉴"
    doc_id = f"card:{meta['card_en'].replace(' ', '_')}"
    return Document(page_content="\n".join(lines), metadata=meta, id=doc_id)


def render_lines(blocks):
    lines = []
    for kind, payload in blocks:
        if kind == "h2":
            lines.append(f"【{payload}】")
        elif kind == "para":
            lines.append(payload)
        else:  # table
            for row in payload:
                lines.append(" | ".join(row))
    return lines


def build_general_docs(blocks):
    docs = []
    for key, blks in blocks.items():
        if key == "suits":
            suit_table = None
            note_lines = []
            for kind, payload in blks:
                if kind == "table" and payload and payload[0][0].strip() == "花色":
                    suit_table = payload
                elif kind == "table":
                    note_lines.extend(" | ".join(row) for row in payload)
                else:
                    note_lines.append(payload)
            note = "\n".join(note_lines)
            for row in suit_table[1:]:
                suit_cn = row[0].strip()
                suit_en, element = SUITS[suit_cn]
                content = (f"{suit_cn}（{suit_en}）｜塔罗花色与元素\n"
                           f"元素：{element}\n"
                           f"主题领域：{row[3].strip()}\n"
                           f"宫廷牌阶位：{row[4].strip()}")
                if note and suit_cn == "权杖":
                    content += "\n" + note
                meta = {"doc_type": "general", "section": "四花色",
                        "suit": suit_cn, "suit_en": suit_en, "element": element}
                docs.append(Document(page_content=content, metadata=meta,
                                     id=f"general:suits:{suit_cn}"))
        elif key == "pseudohistory":
            n = 0
            for kind, payload in blks:
                n += 1
                content = ("\n".join(" | ".join(row) for row in payload)
                           if kind == "table" else payload)
                meta = {"doc_type": "general", "section": "伪史澄清"}
                docs.append(Document(page_content=content, metadata=meta,
                                     id=f"general:pseudohistory:{n}"))
        else:
            content = "\n".join(render_lines(blks))
            meta = {"doc_type": "general", "section": SECTION_LABEL[key]}
            docs.append(Document(page_content=content, metadata=meta, id=f"general:{key}"))
    return docs


def build_documents():
    """解析 docx，返回 (cards, generals)。"""
    with zipfile.ZipFile(DOCX_PATH) as z:
        xml = z.read("word/document.xml")
    root = etree.fromstring(xml)
    body = root.find(W + "body")

    cards = []
    blocks = {}          # section key -> list[(kind, payload)]
    current_sec = None   # 当前章节 key
    prev_style = None    # 最近一个段落的样式（用于卡牌表判定）
    pending_card = None  # 待配对的卡牌标题（heading 3）

    for el in body:
        tag = etree.QName(el).localname
        if tag == "p":
            style = p_style(el)
            text = p_text(el).strip()
            if style == _STYLE_TOC or not text:
                prev_style = style
                continue
            if style == _STYLE_H1:
                current_sec = section_key(text)
                pending_card = None
            elif style == _STYLE_H2:
                if current_sec in GENERAL_SECTIONS:
                    blocks.setdefault(current_sec, []).append(("h2", text))
                pending_card = None
            elif style == _STYLE_H3:
                pending_card = text
            else:  # 普通段落
                if current_sec in GENERAL_SECTIONS:
                    blocks.setdefault(current_sec, []).append(("para", text))
                pending_card = None
            prev_style = style
        elif tag == "tbl":
            rows = table_rows(el)
            is_card = (prev_style == _STYLE_H3 and pending_card
                       and rows and rows[0][0].strip() == "关键词"
                       and len(rows) in (6, 7))
            if is_card:
                doc = build_card(pending_card, rows)
                if doc is not None:
                    cards.append(doc)
                pending_card = None
            elif current_sec in GENERAL_SECTIONS:
                blocks.setdefault(current_sec, []).append(("table", rows))
            prev_style = None

    generals = build_general_docs(blocks)
    return cards, generals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只解析并打印统计/样例，不写库")
    args = parser.parse_args()

    cards, generals = build_documents()
    assert len(cards) == 78, f"期望 78 张牌，实际 {len(cards)}"
    print(f"解析完成：78 张牌文档 + {len(generals)} 条通用文档 = {len(cards) + len(generals)} 条")

    if args.dry_run:
        print("\n--- 样例：大阿卡纳（愚者）---")
        print(cards[0].page_content)
        print("\n--- 样例：小阿卡纳数字牌（权杖二）---")
        wands_two = next(d for d in cards if d.metadata.get("card_en") == "Two of Wands")
        print(wands_two.page_content)
        print("\n--- 通用文档样例 ---")
        for g in generals[:2]:
            print(f"[{g.metadata['section']}] {g.page_content[:80]}…")
        return

    docs = cards + generals
    embedding = get_ollama_embeddings()
    vectordb = Chroma(persist_directory=PERSIST_DIRECTORY,
                      embedding_function=embedding,
                      collection_name=COLLECTION_NAME)
    vectordb.reset_collection()   # 清空重建，保证可重复运行
    vectordb.add_documents(docs)  # upsert，用 Document.id 确定性去重
    print(f"已写入集合 {COLLECTION_NAME}，共 {len(docs)} 条（含 78 张牌 + {len(generals)} 条通用知识）。")
    print("向量库目录：", PERSIST_DIRECTORY)


if __name__ == "__main__":
    main()
