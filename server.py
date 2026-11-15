import os
import uuid
import json
import time
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage
from mytools import (
    serp_search,
    get_info_from_local_db,
    bazi_cesuan,
    ziwei_paipan,
    xingzuo_yunshi,
    taluo_zhanbu,
    get_tarot_info_from_db,
    jiemeng,
    zhouyi_qigua,
)
from models import get_model_client
from loguru import logger
import redis
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Vite 打包产物目录（前端构建输出）
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

# ---------- 配置 ----------
REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/6')

# ---------- Redis 辅助函数 ----------
# 每次操作实时创建短连接，用完即释放。避免顶层共享连接对象因网络抖动进入错误态导致全站静默丢数据。

def _make_redis():
    """创建新的 Redis 连接（短连接，2 秒超时）。"""
    return redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2,
                          health_check_interval=0)


def _rget(key):
    try:
        r = _make_redis()
        return r.get(key)
    except Exception:
        return None


def _rset(key, val, ex):
    try:
        r = _make_redis()
        r.set(key, val, ex=ex)
    except Exception:
        pass


def _r_zadd(key, mapping):
    try:
        r = _make_redis()
        r.zadd(key, mapping)
    except Exception:
        pass


def _r_zrevrange(key, start, stop):
    try:
        r = _make_redis()
        return r.zrevrange(key, start, stop)
    except Exception:
        return []


def _r_expire(key, ex):
    try:
        r = _make_redis()
        r.expire(key, ex)
    except Exception:
        pass


# ---------- 模块配置 ----------
BASE_PERSONA = (
    "你是「星语」，一位温柔友善的命理助手。"
    "永远用简体中文回答，语气亲切自然，像贴心的朋友，多用「呀」「呢」「～」，结尾常带 🌙。"
    "不故弄玄虚、不制造焦虑，把结果讲得温暖、清楚、好懂。"
)

MODULES = {
    "taluo": {
        "name": "塔罗",
        "prompt": BASE_PERSONA + "\n你负责塔罗。用户想抽牌占卜时调用 taluo_zhanbu 抽牌并解读；用户询问某张牌的含义、正逆位、关键词、对应体系（占星/希伯来字母/元素）、花色结构、塔罗历史或伪史澄清等知识时，先调用 get_tarot_info_from_db 查知识库，再温暖地解读。给出正向、具体的指引，不制造焦虑。",
        "tools": [taluo_zhanbu, get_tarot_info_from_db, serp_search],
    },
    "bazi": {
        "name": "八字",
        "prompt": BASE_PERSONA + "\n你负责八字命理。用户给出姓名、性别、出生年月日时后，调用 bazi_cesuan 排盘，再用温暖易懂的话解读命盘、五行与大运。信息不全时温柔地请用户补充。",
        "tools": [bazi_cesuan, serp_search],
    },
    "ziwei": {
        "name": "紫薇斗数",
        "prompt": BASE_PERSONA + "\n你负责紫微斗数。用户给出姓名、性别、出生年月日时后，调用 ziwei_paipan 起盘，再解读十二宫与星曜。信息不全时温柔地请用户补充。",
        "tools": [ziwei_paipan, serp_search],
    },
    "xingzuo": {
        "name": "星座",
        "prompt": BASE_PERSONA + "\n你负责西方星座运势。根据用户的星座（或出生日期）调用 xingzuo_yunshi 查询运势，再结合星座性格温柔地解读。",
        "tools": [xingzuo_yunshi, serp_search],
    },
    "fengshui": {
        "name": "风水",
        "prompt": BASE_PERSONA + "\n你负责风水。调用 get_info_from_local_db 查询风水常识，给出实用、温和的布局建议，不制造恐慌。",
        "tools": [get_info_from_local_db, serp_search],
    },
    "mbti": {
        "name": "MBTI",
        "prompt": BASE_PERSONA + "\n你负责 MBTI 性格分析。通过轻松的生活化提问，从四个维度（E/I、S/N、T/F、J/P）判断用户类型，再温暖地解读性格特质。不要直接抛术语，用生活化的场景提问。",
        "tools": [serp_search],
    },
    "jiemeng": {
        "name": "解梦",
        "prompt": BASE_PERSONA + "\n你负责解梦。调用 jiemeng 查询梦境含义，温柔地解读并安抚情绪。",
        "tools": [jiemeng, serp_search],
    },
    "zhouyi": {
        "name": "周易",
        "prompt": BASE_PERSONA + "\n你负责周易六爻算卦。用户想算卦时，调用 zhouyi_qigua 起卦，再结合用户所问之事解卦：先简要列出本卦、变卦、动爻，再重点解读动爻爻辞的含义，结合卦辞给出温暖、正向、具体的指引。不故弄玄虚、不制造焦虑。",
        "tools": [zhouyi_qigua, serp_search],
    },
}

TOOL_LABELS = {
    "bazi_cesuan": "正在为你排八字…",
    "ziwei_paipan": "正在为你排紫微星盘…",
    "xingzuo_yunshi": "正在查看星座运势…",
    "get_info_from_local_db": "正在查阅风水资料…",
    "jiemeng": "正在翻阅解梦典籍…",
    "taluo_zhanbu": "正在为你抽塔罗牌…",
    "get_tarot_info_from_db": "正在翻阅塔罗知识库…",
    "zhouyi_qigua": "正在为你摇卦起卦…",
    "serp_search": "正在查找相关资料…",
}

# 每个模块创建一个 agent（流式模型）
agents = {
    mid: create_agent(
        model=get_model_client(streaming=True),
        tools=cfg["tools"],
        system_prompt=cfg["prompt"],
    )
    for mid, cfg in MODULES.items()
}

SESSIONS_KEY = "chat_sessions"
HISTORY_TTL = 86400       # 聊天记录 1 天
META_TTL = 86400 * 7      # 会话列表 meta 7 天（比历史长，保证列表里点进去还有内容）


# ---------- 会话操作 ----------

def get_session_history(session_id: str) -> list:
    """加载会话消息。"""
    data = _rget(f"chat_history:{session_id}")
    if not data:
        return []
    try:
        msgs = json.loads(data)
        out = []
        for m in msgs:
            if m.get("role") == "assistant":
                out.append(AIMessage(content=m.get("content", "")))
            else:
                out.append(HumanMessage(content=m.get("content", "")))
        return out
    except Exception:
        return []


def save_session_history(session_id: str, messages: list):
    """保存会话消息（最多 50 条），并续期 TTL。"""
    serializable = []
    for m in messages:
        role = "assistant" if isinstance(m, AIMessage) else "human"
        content = getattr(m, "content", "")
        if not content:
            continue
        serializable.append({"role": role, "content": content})
    if len(serializable) > 50:
        serializable = serializable[-50:]
    _rset(f"chat_history:{session_id}", json.dumps(serializable, ensure_ascii=False), HISTORY_TTL)


def record_session(session_id: str, title: str, module: str):
    """登记/更新会话到列表。"""
    now = time.time()
    _r_zadd(SESSIONS_KEY, {session_id: now})
    _rset(f"session_meta:{session_id}",
          json.dumps({"title": title, "module": module, "updated_at": now}, ensure_ascii=False),
          META_TTL)
    _r_expire(SESSIONS_KEY, META_TTL)


def ensure_title(session_id: str, query: str, module: str) -> str:
    """首条消息生成标题；已有标题保留但刷新时间戳。"""
    existing = _rget(f"session_meta:{session_id}")
    title = ""
    if existing:
        try:
            title = json.loads(existing).get("title", "")
        except Exception:
            title = ""
    if not title:
        title = f"{MODULES[module]['name']} · {query[:18]}"
    record_session(session_id, title, module)
    return title


# ---------- SSE ----------

def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _extract_text(chunk) -> str:
    c = getattr(chunk, "content", "")
    if isinstance(c, list):
        parts = []
        for b in c:
            if isinstance(b, dict):
                parts.append(b.get("text", ""))
            else:
                parts.append(str(b))
        return "".join(parts)
    return c or ""


# ---------- 路由 ----------

@app.get("/")
async def read_root():
    index_file = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"detail": "前端尚未构建，请运行: cd frontend && npm run build"}


@app.get("/sessions")
async def list_sessions():
    ids = _r_zrevrange(SESSIONS_KEY, 0, -1)
    result = []
    for sid in ids:
        sid = sid.decode() if isinstance(sid, bytes) else sid
        meta = _rget(f"session_meta:{sid}")
        if not meta:
            continue
        try:
            m = json.loads(meta)
            result.append({
                "session_id": sid,
                "title": m.get("title", ""),
                "module": m.get("module", "bazi"),
                "updated_at": m.get("updated_at", 0),
            })
        except Exception:
            continue
    return {"sessions": result}


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    history = get_session_history(session_id)
    return {
        "messages": [
            {"role": "assistant" if isinstance(m, AIMessage) else "user", "content": m.content}
            for m in history
        ]
    }


@app.post("/chat/stream")
async def chat_stream(request: Request):
    try:
        data = await request.json()
    except Exception:
        return StreamingResponse(iter([sse({"type": "error", "text": "请求格式有误"})]), media_type="text/event-stream")

    query = (data.get("query") or "").strip()
    if not query:
        return StreamingResponse(iter([sse({"type": "error", "text": "请输入内容"})]), media_type="text/event-stream")

    session_id = data.get("session_id") or uuid.uuid4().hex
    module = data.get("module") if data.get("module") in MODULES else "bazi"
    agent = agents[module]

    history = get_session_history(session_id)
    messages = history + [HumanMessage(content=query)]

    async def gen():
        final_text = ""
        fallback = ""
        try:
            async for event in agent.astream_events({"messages": messages}, version="v2"):
                kind = event.get("event")
                if kind == "on_chat_model_stream":
                    text = _extract_text(event["data"]["chunk"])
                    if text:
                        final_text += text
                        yield sse({"type": "token", "content": text})
                elif kind == "on_tool_start":
                    label = TOOL_LABELS.get(event.get("name", ""))
                    if label:
                        yield sse({"type": "status", "text": label})
                elif kind == "on_chat_model_end":
                    out = event["data"].get("output")
                    if out is not None and not getattr(out, "tool_calls", None):
                        fc = _extract_text(out)
                        if fc:
                            fallback = fc
        except Exception as e:
            logger.error(f"流式生成异常: {e}")
            yield sse({"type": "token", "content": "哎呀，我这边走神了一下，稍后再试一次好吗？🌙"})

        answer = final_text.strip() or fallback.strip()
        if answer:
            # 兜底：若模型没有逐字流式输出，则一次性补发完整回答
            if not final_text.strip():
                yield sse({"type": "token", "content": answer})
            save_session_history(session_id, history + [HumanMessage(content=query), AIMessage(content=answer)])
        title = ensure_title(session_id, query, module)
        yield sse({"type": "done", "session_id": session_id, "title": title})

    return StreamingResponse(gen(), media_type="text/event-stream")


# 生产环境：将 Vite 打包产物挂载到根路径
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST), name="frontend")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)