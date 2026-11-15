from langchain_core.prompts import ChatPromptTemplate
from langchain_community.utilities import SerpAPIWrapper
from langchain_core.tools import tool
from langchain_chroma import Chroma
import requests
import json
import os
import re
import random
from loguru import logger
from models import get_ollama_embeddings, get_model_client
from dotenv import load_dotenv

load_dotenv()

YUANFENJU_API_KEY = os.getenv("YUANFENJU_API_KEY")
os.environ["SERPAPI_API_KEY"] = os.getenv("SERPAPI_API_KEY", "")

YUANFENJU_BASE = "https://api.yuanfenju.com/index.php/v1"

# 星座名称 → 缘份居运势接口的 0~11 编号
ZODIAC_IDS = ["白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座", "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座"]

# ====================== 周易六爻 ======================
# 八卦三爻（自下而上：初爻→中爻→上爻，阳=1 阴=0）→ 卦名
_TRIGRAM_BY_BITS = {
    "111": "乾", "110": "兑", "101": "离", "100": "震",
    "011": "巽", "010": "坎", "001": "艮", "000": "坤",
}
_YAO_POS_NAMES = {1: "初", 2: "二", 3: "三", 4: "四", 5: "五", 6: "上"}
_ZHOUYI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "zhouyi")
_yijing_cache = None


def _load_yijing():
    """解析 resources/zhouyi/Gua.txt，返回 {by_trigrams, text, xiang}。"""
    global _yijing_cache
    if _yijing_cache is not None:
        return _yijing_cache
    xiang = {}
    try:
        with open(os.path.join(_ZHOUYI_DIR, "GuaName.json"), encoding="utf-8") as f:
            xiang = json.load(f)
    except Exception:
        pass
    by_trigrams, text_map = {}, {}
    try:
        with open(os.path.join(_ZHOUYI_DIR, "Gua.txt"), encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"周易卦辞读取失败: {e}")
        return None
    for sec in re.split(r"(?m)^(?=\d{2})", content):
        sec = sec.strip()
        if not sec:
            continue
        head = sec.split("\n", 1)[0]
        head_fixed = re.sub(r"^(\d{2})\s*卦\s+", r"\1 ", head)  # 修正「14卦」这类编号粘连
        m = re.match(r"^\d+\s+(\S+)", head_fixed)
        mm = re.search(r"(\S)上(\S)下\s*$", head_fixed)
        if not m or not mm:
            continue
        name, upper, lower = m.group(1), mm.group(1), mm.group(2)
        by_trigrams[(upper, lower)] = name
        text_map[name] = sec.replace(head, head_fixed, 1)
    _yijing_cache = {"by_trigrams": by_trigrams, "text": text_map, "xiang": xiang}
    return _yijing_cache


def _yao_prefix(pos: int, yang: bool) -> str:
    """爻名，如初九/六二/九五/上六。"""
    jiu_liu = "九" if yang else "六"
    if pos == 1:
        return "初" + jiu_liu
    if pos == 6:
        return "上" + jiu_liu
    return jiu_liu + _YAO_POS_NAMES[pos]


def _yaogua():
    """六爻摇卦。返回 (本卦位串, 变卦位串, 动爻位置[1-6])。位串自初爻到上爻，阳=1 阴=0。"""
    lines = []  # (是否阳, 是否动)
    for _ in range(6):
        s = sum(random.randint(2, 3) for _ in range(3))  # 6老阴 7少阳 8少阴 9老阳
        lines.append((s in (7, 9), s in (6, 9)))
    ben = "".join("1" if y else "0" for y, _ in lines)
    dong = [i + 1 for i, (_, d) in enumerate(lines) if d]
    bian = list(ben)
    for i, (_, d) in enumerate(lines):
        if d:
            bian[i] = "0" if bian[i] == "1" else "1"
    return ben, "".join(bian), dong


def _gua_of_bits(bits: str, data):
    """由 6 爻位串查卦名。"""
    upper = _TRIGRAM_BY_BITS.get(bits[3:6])
    lower = _TRIGRAM_BY_BITS.get(bits[0:3])
    if not upper or not lower:
        return None
    return data["by_trigrams"].get((upper, lower))


def _gua_summary(text: str) -> str:
    """截取卦辞/彖/象（到第一条爻辞之前）。"""
    m = re.search(r"(?m)^(初九|初六)[：:]", text)
    return text[:m.start()].strip() if m else text


def _truncate(text, limit=3000):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…（内容过长已截断）"
  

def _extract_orientation(text: str, upright: bool) -> str:
    """从牌义正文里取出「正位」或「逆位」那一行的内容。"""
    key = "正位" if upright else "逆位"
    m = re.search(rf"(?m)^{key}：(.*)$", text)
    return m.group(1).strip() if m else ""


def _post_yuanfenju(path, data):
    """调用缘份居接口，返回 (data, error)。"""
    try:
        res = requests.post(YUANFENJU_BASE + path, data=data, timeout=30)
    except Exception as e:
        logger.error(f"缘份居请求异常 {path}: {e}")
        return None, "接口请求超时或网络异常"
    try:
        j = res.json()
    except Exception:
        return None, f"接口返回异常（HTTP {res.status_code}）"
    if res.status_code == 200 and j.get("errcode") in (0, "0"):
        return j.get("data"), None
    return None, j.get("errmsg") or f"请求失败（HTTP {res.status_code}）"


@tool
def serp_search(query: str):
    """当不知道答案、需要查实时资讯、新闻、定义、未知知识时使用。"""
    try:
        serp = SerpAPIWrapper()
        result = serp.run(query)
        if isinstance(result, (list, dict)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return "搜索暂时不可用。"


@tool
def get_info_from_local_db(query: str):
    """专门查「风水」「办公室风水」「风水常识」相关内容。"""
    try:
        vector_store = Chroma(
            persist_directory="./chroma_db",
            embedding_function=get_ollama_embeddings(),
            collection_name="local_documents"
        )
        retriever = vector_store.as_retriever(search_kwargs={"k": 4})
        docs = retriever.invoke(query)
        if not docs:
            return "本地知识库里暂时没查到相关内容。"
        return "\n".join([f"- {d.page_content}" for d in docs])
    except Exception as e:
        logger.error(f"向量库查询失败: {e}")
        return "本地知识库暂时不可用。"


@tool
def bazi_cesuan(name: str, sex: int, year: int, month: int, day: int, hours: int, minute: int = 0, type: int = 1) -> str:
    """用户要算八字、排八字、论命时使用。sex：0男1女；type：1公历0农历。需要姓名和出生年月日时。"""
    if not YUANFENJU_API_KEY:
        return "八字服务暂时不可用。"
    data, err = _post_yuanfenju("/Bazi/cesuan", {
        "api_key": YUANFENJU_API_KEY, "name": name, "sex": sex, "type": type,
        "year": year, "month": month, "day": day, "hours": hours, "minute": minute,
    })
    if err:
        return f"八字排盘失败：{err}"
    return "八字排盘结果：" + _truncate(json.dumps(data, ensure_ascii=False))


@tool
def ziwei_paipan(name: str, sex: int, year: int, month: int, day: int, hours: int, minute: int = 0, type: int = 1) -> str:
    """用户要排紫微斗数、看紫微星盘时使用。sex：0男1女；type：1公历0农历。需要姓名和出生年月日时。"""
    if not YUANFENJU_API_KEY:
        return "紫微斗数服务暂时不可用。"
    data, err = _post_yuanfenju("/Bazi/zwpan", {
        "api_key": YUANFENJU_API_KEY, "name": name, "sex": sex, "type": type,
        "year": year, "month": month, "day": day, "hours": hours, "minute": minute,
    })
    if err:
        return f"紫微排盘失败：{err}"
    return "紫微斗数排盘结果：" + _truncate(json.dumps(data, ensure_ascii=False))


@tool
def xingzuo_yunshi(sign: str) -> str:
    """用户问星座运势、星座性格时使用。sign 为星座名，如「天蝎座」「白羊座」。"""
    if not YUANFENJU_API_KEY:
        return "星座服务暂时不可用。"
    sign_clean = (sign or "").replace("座", "").strip()
    idx = None
    for i, z in enumerate(ZODIAC_IDS):
        if sign_clean and (sign_clean in z or z.replace("座", "") == sign_clean):
            idx = i
            break
    if idx is None:
        return f"没识别出星座「{sign}」，请告诉我具体是哪个星座（如天蝎座、白羊座）。"
    data, err = _post_yuanfenju("/Zhanbu/yunshi", {
        "api_key": YUANFENJU_API_KEY, "type": 0, "title_yunshi": idx,
    })
    if err:
        return f"星座运势查询失败：{err}"
    return f"{ZODIAC_IDS[idx]}运势：" + _truncate(json.dumps(data, ensure_ascii=False))


@tool
def taluo_zhanbu(question: str) -> str:
    """用户想占塔罗、抽塔罗牌、问塔罗指引时使用。question 为用户想问的问题。
    本地抽牌：随机抽 3 张牌（过去-现在-未来），牌义取自本地塔罗知识库，不依赖外部占卜 API。"""
    try:
        vector_store = Chroma(
            persist_directory="./chroma_db",
            embedding_function=get_ollama_embeddings(),
            collection_name="tarot_knowledge",
        )
        res = vector_store.get(where={"doc_type": "card"})
        metas = res.get("metadatas") or []
        documents = res.get("documents") or []
        if len(metas) < 3:
            return "塔罗牌库尚未初始化，请先运行 python insert_tarot_to_chroma.py。"
        idxs = random.sample(range(len(metas)), 3)
        lines = ["【塔罗占卜·三张牌阵（过去 · 现在 · 未来）】", f"你的问题：{question}", ""]
        for pos, i in zip(("过去", "现在", "未来"), idxs):
            meta = metas[i]
            upright = random.choice([True, False])
            orient = "正位" if upright else "逆位"
            meaning = _extract_orientation(documents[i], orient)
            lines.append(f"{pos}：{meta.get('card', '')}（{meta.get('card_en', '')}）· {orient}")
            lines.append(f"关键词：{meta.get('keywords', '')}")
            if meaning:
                lines.append(f"含义：{meaning}")
            lines.append("")
        return "\n".join(lines).strip()
    except Exception as e:
        logger.error(f"塔罗抽牌失败: {e}")
        return "塔罗抽牌暂时不可用。"


@tool
def get_tarot_info_from_db(query: str):
    """用户询问塔罗牌义、某张牌的正逆位含义、关键词、对应体系（占星/希伯来字母/元素）、
    花色结构、塔罗历史或塔罗伪史澄清等塔罗知识时使用。抽牌占卜请用 taluo_zhanbu，不要用本工具。"""
    try:
        vector_store = Chroma(
            persist_directory="./chroma_db",
            embedding_function=get_ollama_embeddings(),
            collection_name="tarot_knowledge",
        )
        retriever = vector_store.as_retriever(search_kwargs={"k": 6})
        docs = retriever.invoke(query)
        if not docs:
            return "塔罗知识库里暂时没查到相关内容。"
        return "\n".join([f"- {d.page_content}" for d in docs])
    except Exception as e:
        logger.error(f"塔罗知识库查询失败: {e}")
        return "塔罗知识库暂时不可用。"


@tool
def jiemeng(query: str):
    """用户做梦、想解梦、询问梦境含义时使用。"""
    url = YUANFENJU_BASE + "/Gongju/zhougong"
    llm = get_model_client(streaming=False)

    # 用 LLM 提取 1~3 个关键词
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个关键词提取器。从用户输入中提取 1~3 个核心关键词（名词），只输出关键词，用英文逗号分隔，不要输出其他文字。"),
            ("human", "{query}"),
        ])
        kw_str = (prompt | llm).invoke({"query": query}).content.strip()
    except Exception as e:
        logger.error(f"关键词提取失败: {e}")
        kw_str = ""
    keywords = [k.strip() for k in kw_str.split(",") if k.strip()]
    if not keywords:
        keywords = re.findall(r'[一-龥]{2,}', query)[:3] or [query.strip()]

    candidates = []
    full = re.sub(r'[，,。.！!？?、\s]+', '', query)
    if full and full not in candidates:
        candidates.append(full)
    for kw in keywords:
        if kw and kw not in candidates:
            candidates.append(kw)

    for kw in candidates:
        try:
            res = requests.post(url, data={"api_key": YUANFENJU_API_KEY, "title_zhougong": kw}, timeout=30)
            j = res.json()
            if res.status_code == 200 and j.get("errcode") in (0, "0") and j.get("data"):
                data = j["data"]
                result = None
                if isinstance(data, list) and data:
                    result = data[0].get("message")
                elif isinstance(data, dict):
                    result = data.get("content") or data.get("message")
                if result:
                    return result
        except Exception as e:
            logger.error(f"关键词 '{kw}' 查询异常: {e}")
            continue
    return "没有查到该梦境的解梦内容，可以换种说法再描述一下～"


@tool
def zhouyi_qigua(question: str) -> str:
    """用户想算卦、占卜、摇卦、问周易吉凶时使用。question 为用户想问的事。"""
    data = _load_yijing()
    if not data:
        return "周易卦辞暂时不可用。"
    ben, bian, dong = _yaogua()
    ben_name = _gua_of_bits(ben, data)
    bian_name = _gua_of_bits(bian, data)
    if not ben_name or not bian_name:
        return "起卦失败，请稍后再试。"

    ben_xiang = data["xiang"].get(ben_name, ben_name)
    bian_xiang = data["xiang"].get(bian_name, bian_name)
    ben_text = data["text"].get(ben_name, "")
    bian_text = data["text"].get(bian_name, "")

    dong_lines = []
    for p in dong:
        yang = ben[p - 1] == "1"
        prefix = _yao_prefix(p, yang)
        m = re.search(rf"^{prefix}[：:](.+)$", ben_text, re.M)
        dong_lines.append(m.group(0).strip() if m else f"{prefix}：见卦辞。")

    out = [
        "【起卦结果】",
        f"本卦：{ben_xiang}（{ben_name}）",
        f"变卦：{bian_xiang}（{bian_name}）",
        f"动爻：{'、'.join(_yao_prefix(p, ben[p - 1] == '1') for p in dong) if dong else '无'}",
        "",
        "【本卦·卦辞/彖/象】",
        _gua_summary(ben_text),
        "",
        "【变卦·卦辞/彖/象】",
        _gua_summary(bian_text),
        "",
        "【动爻爻辞】",
        "\n".join(dong_lines) if dong_lines else "无动爻",
    ]
    return _truncate("\n".join(out))
