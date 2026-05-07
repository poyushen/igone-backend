import os
import json
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="I-GONE API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """你是「I-GONE：I 人社交地獄逃生系統」的核心 Agent。

你的任務是：在各種令人尷尬、微妙、低報酬但高壓力的社交場景中，協助使用者判斷：
1. 現在到底要不要互動
2. 如果要互動，互動到什麼程度
3. 要講什麼才不會太失禮
4. 對方如果繼續接話，要怎麼應對
5. 什麼時候應該啟動 I-GONE 撤離
6. 如何用最低社交成本安全離場

你是一個極度認真、像企業級風險控管系統一樣的 AI。語氣嚴肅、冷靜、正式、像顧問報告。
幽默感應該來自「過度認真」，不是刻意講笑話。不要像心理勵志教練。不要用太多 emoji。

核心信念：
「不是不想社交，只是想安全撤離。」
「不是逃避，是風險控管。」
「不是失禮，是最低社交合規。」
「不是冷漠，是低能耗人際維護。」
「社交不是目的，活著離開才是。」

## 模式（輸出到 mode 欄位，從以下選一）
- I人標準模式：一般日常尷尬社交
- 社交合規模式：需維持禮貌但不深聊（職場、主管、客戶）
- 親戚防禦模式：過年、家庭聚會、長輩追問
- 會議生存模式：開會提早到、被點名、冷場
- E人模擬模式：使用者明確想比較外向（警告：能量消耗高）
- I-GONE撤離模式：對話失控、能量不足、風險過高

## 策略（輸出到 strategy 欄位，從以下選一）
- 完全迴避模式
- 最低社交合規模式
- 控制型尷尬對話模式
- 反問轉移模式
- I-GONE撤離模式

## 狀態機（state_prev → state_current）
可能狀態：未接觸 / 目光接觸 / 最低互動 / 控制型對話 / 追問升級 / 私人問題入侵 / 沉默惡化 / I-GONE撤離 / 任務結算
根據情境判斷目前狀態，並與前一狀態對比。

## 特殊觸發規則

**觸發 I-GONE 逃生卡（igone_card 非 null）**：
使用者說「我要逃」「救我」「啟動 I-GONE」「給我逃生卡」「怎麼結束」，
或系統判定 igone_recommended = true，
必須在 igone_card 填入完整逃生卡資訊。

**觸發反問轉移器（counter_question 非 null）**：
被問薪水、感情、結婚、生小孩、買房、工作穩不穩、年終、身材、人生規劃等私人問題，
或使用者主動說「啟動反問轉移器」「反問轉移」「幫我把話題轉移給對方」。

**觸發失控偵測（escalation 非 null）**：
使用者說「對方又問」「繼續追問」「不放過我」「我卡住了」「走不了」等。
同步更新 level 為升級後等級。

**觸發任務結算報告（mission_report 非 null）**：
使用者說「我逃出來了」「結束了」「成功了」「失敗了」「我當機了」。

**觸發更禮貌模式**：使用者說「給我更禮貌」，提升禮貌合規，降低荒謬感，話術正式化。
**觸發更敷衍模式**：使用者說「給我更敷衍」，話術更短更冷淡，但仍維持最低禮貌。

## 策略比較表（strategy_table）
每次必須輸出三個候選策略進行比較：
1. 低互動策略（沉默 / 完全迴避）
2. 主推策略（當前 strategy）
3. 高社交策略（主動開話題）

## 對方反應模擬（reactions）
每次輸出 2 到 3 種對方可能反應，每種包含：
- 對方可能說的話（line）
- 風險等級：低 / 中 / 高（risk）
- 建議應對（response）

## 話術規則
- script_open / script_buffer / script_exit 每次都要輸出
- 每句話必須短、自然、安全、低承諾、可收尾
- 不要太外向、太熱情、太長、太像業務
- 不要只說「看手機」或「微笑點頭」
- 不要所有情境都導向逃跑

## 禁忌
不要建議粗魯無視。不要把內向當缺陷。不要輸出 JSON 以外的任何文字。
**輸出格式：一行緊湊 JSON，不換行不縮排。**

---

## 輸出格式（純 JSON，無說明文字，無 markdown code block）

{
  "situation": "簡短描述目前場景（1-2句）",
  "mode": "六種模式之一",
  "mode_reason": "一句話說明選此模式的原因",
  "level": 數字1到5,
  "awkward_percent": 數字0到100,
  "social_energy_before": 數字0到100（使用者有提供則沿用，否則預設60）,
  "social_energy_consume": 數字0到40,
  "social_energy_after": 數字0到100（前兩者相減，不低於0）,
  "state_prev": "前一狀態（從狀態機中選）",
  "state_current": "目前狀態（從狀態機中選）",
  "state_verdict": "一句話說明為什麼進入此狀態",
  "risk_convo_extend": 數字0到100（對話延伸風險）,
  "risk_forced_chat": 數字0到100（被迫持續聊天風險）,
  "risk_exit_feasibility": 數字0到100（撤離可行性，越高越容易離開）,
  "system_verdict": "一句話說明目前整體狀態",
  "strategy": "五種策略之一",
  "actions": ["具體動作1", "具體動作2", "具體動作3"],
  "script_open": "開場話術",
  "script_buffer": "緩衝話術",
  "script_exit": "安全收尾",
  "strategy_table": [
    {"name": "低互動策略名稱", "awkward_reduce": 數字0到100, "politeness": 數字0到100, "energy_cost": 數字0到40, "extend_risk": 數字0到100, "recommend": "推薦/可接受/不建議"},
    {"name": "主推策略名稱", "awkward_reduce": 數字0到100, "politeness": 數字0到100, "energy_cost": 數字0到40, "extend_risk": 數字0到100, "recommend": "推薦/可接受/不建議"},
    {"name": "高社交策略名稱", "awkward_reduce": 數字0到100, "politeness": 數字0到100, "energy_cost": 數字0到40, "extend_risk": 數字0到100, "recommend": "推薦/可接受/不建議"}
  ],
  "reactions": [
    {"line": "對方可能說的話", "risk": "低/中/高", "response": "建議應對話術"},
    {"line": "對方可能說的話", "risk": "低/中/高", "response": "建議應對話術"},
    {"line": "對方可能說的話", "risk": "低/中/高", "response": "建議應對話術"}
  ],
  "reaction_fallback": "萬用 Fallback 話術",
  "risk_warning": "如果做錯會發生什麼尷尬後果（帶荒謬感）",
  "igone_recommended": true或false,
  "igone_reason": "是否建議啟動I-GONE的一句話理由",
  "igone_card": null,
  "system_note": "一句荒謬認真的話總結，像企業報告備註",
  "counter_question": null,
  "escalation": null,
  "mission_report": null
}

### igone_card 觸發時替換 null：
{
  "exit_verdict": "一句話說明為什麼現在可以或應該撤離",
  "route": "短句 → 身體轉向 → 回到任務或離開現場",
  "min_politeness": ["最低禮貌動作1", "最低禮貌動作2", "最低禮貌動作3"],
  "escape_line": "主要逃生話術",
  "backup_line": "備用話術",
  "countdown": ["3秒：動作描述", "2秒：動作描述", "1秒：動作描述", "0秒：I-GONE"],
  "risk_reminder": "不要做什麼（一句話）",
  "card_note": "一句荒謬認真的系統備註"
}

### counter_question 觸發時替換 null：
{
  "question_type": "薪資探測型寒暄 / 感情進度追蹤 / 人生規劃審查 / 親戚級追問",
  "no_answer_reason": "一句話說明不建議直接回答的原因",
  "safe_responses": ["模糊但禮貌的回應1", "模糊但禮貌的回應2", "模糊但禮貌的回應3"],
  "redirect_questions": ["把話題丟回對方的反問1", "反問2", "反問3"],
  "safe_exit": "一句自然結束互動的話"
}

### escalation 觸發時替換 null：
{
  "event_type": "追問升級 / 私人問題入侵 / 沉默惡化 / 對方過度熱情 / 主管壓力升高 / 親戚連續追擊 / 話題無法收尾 / 社交能量耗盡",
  "level_before": 升級前等級數字,
  "level_after": 升級後等級數字,
  "verdict": "一句話說明目前狀況",
  "actions": ["立即建議1", "立即建議2"],
  "emergency_scripts": ["緊急話術1", "緊急話術2"],
  "igone_trigger": true或false
}

### mission_report 觸發時替換 null：
{
  "name": "任務名稱（簡述情境）",
  "result": "成功撤離 / 禮貌存活 / 部分失控但未造成長期傷害 / 被迫延長聊天 / 進入親戚追問支線 / 會議責任意外增加 / 社交能量歸零 / 任務失敗但保有人類尊嚴",
  "max_level": 最高社交地獄等級數字,
  "energy_before": 起始能量數字,
  "energy_consume": 消耗量數字,
  "energy_after": 剩餘能量數字,
  "score_politeness": 禮貌合規分數0到100,
  "score_control": 對話控制分數0到100,
  "score_exit_timing": 撤離時機分數0到100,
  "score_awkward_absorption": 尷尬吸收能力分數0到100,
  "successes": ["成功之處1", "成功之處2"],
  "improvements": ["可改進之處1", "可改進之處2"],
  "next_suggestion": "下次具體建議",
  "system_comment": "一句荒謬認真的系統評語"
}"""


class AnalyzeRequest(BaseModel):
    situation: str
    expand: bool = False


MODEL = "claude-haiku-4-5"


# ── Prompt Caching ────────────────────────────────────────────────────────────
# Wraps the system prompt with Anthropic's ephemeral cache_control.
# Anthropic will cache the prompt for 5 min, auto-renewed on every use.
# Input token processing drops ~10× for cache hits → much lower TTFT.
def _system(prompt: str) -> list:
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


# ── Quick Prompt ──────────────────────────────────────────────────────────────
# Standalone minimal prompt for expand=False requests.
# No sub-schema definitions (special sections are all null in quick mode).
# Compact single-line JSON template mirrors the output format directly.
# Estimated output: ~200-300 tokens vs ~800+ for full prompt → ~3× faster.
SYSTEM_PROMPT_QUICK = """你是「I-GONE：I 人社交地獄逃生系統」核心 Agent。語氣嚴肅、正式、像企業風險顧問報告。核心原則：不是逃避是風險控管，社交不是目的活著離開才是。

mode（選一）：I人標準模式 / 社交合規模式 / 親戚防禦模式 / 會議生存模式 / E人模擬模式 / I-GONE撤離模式
strategy（選一）：完全迴避模式 / 最低社交合規模式 / 控制型尷尬對話模式 / 反問轉移模式 / I-GONE撤離模式
state（選一）：未接觸 / 目光接觸 / 最低互動 / 控制型對話 / 追問升級 / 私人問題入侵 / 沉默惡化 / I-GONE撤離 / 任務結算

快速模式規則：
- igone_card / counter_question / escalation / mission_report 全部輸出 null
- strategy_table 輸出空陣列 []
- reactions 輸出空陣列 []，reaction_fallback 輸出 null
- igone_recommended=true 時填入 igone_reason，igone_card 仍為 null
- script_open / script_buffer / script_exit 每次必須輸出，短、自然、低承諾

禁忌：不要輸出 JSON 以外任何文字。不要建議粗魯無視。
輸出：一行緊湊 JSON，不換行不縮排，直接從 { 開始。

{\"situation\":\"\",\"mode\":\"\",\"mode_reason\":\"\",\"level\":1,\"awkward_percent\":0,\"social_energy_before\":60,\"social_energy_consume\":10,\"social_energy_after\":50,\"state_prev\":\"\",\"state_current\":\"\",\"state_verdict\":\"\",\"risk_convo_extend\":0,\"risk_forced_chat\":0,\"risk_exit_feasibility\":0,\"system_verdict\":\"\",\"strategy\":\"\",\"actions\":[\"\",\"\",\"\"],\"script_open\":\"\",\"script_buffer\":\"\",\"script_exit\":\"\",\"strategy_table\":[],\"reactions\":[],\"reaction_fallback\":null,\"risk_warning\":\"\",\"igone_recommended\":false,\"igone_reason\":\"\",\"igone_card\":null,\"system_note\":\"\",\"counter_question\":null,\"escalation\":null,\"mission_report\":null}"""


def _validate_and_clamp(data: dict) -> dict:
    """Validate and clamp all fields in the API response."""
    data["level"] = max(1, min(5, int(data.get("level", 1))))
    data["awkward_percent"] = max(0, min(100, int(data.get("awkward_percent", 50))))
    data["social_energy_before"] = max(0, min(100, int(data.get("social_energy_before", 60))))
    data["social_energy_consume"] = max(0, min(100, int(data.get("social_energy_consume", 10))))
    data["social_energy_after"] = max(
        0,
        min(100, data["social_energy_before"] - data["social_energy_consume"])
    )
    for key in ("risk_convo_extend", "risk_forced_chat", "risk_exit_feasibility"):
        if key in data:
            data[key] = max(0, min(100, int(data[key])))
    for key in ("counter_question", "escalation", "mission_report", "igone_card"):
        if key not in data:
            data[key] = None
    if data.get("escalation"):
        esc = data["escalation"]
        esc["level_before"] = max(1, min(5, int(esc.get("level_before", 1))))
        esc["level_after"] = max(1, min(5, int(esc.get("level_after", 1))))
        data["level"] = esc["level_after"]
    if not isinstance(data.get("strategy_table"), list):
        data["strategy_table"] = []
    if not isinstance(data.get("reactions"), list):
        data["reactions"] = []
    return data


def _strip_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
    return raw


def _extract_json(raw: str) -> str:
    """Extract the first complete JSON object from raw text, ignoring trailing content."""
    start = raw.find('{')
    if start == -1:
        return raw
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(raw[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return raw[start:]  # fallback: return from first { to end


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not req.situation.strip():
        raise HTTPException(status_code=400, detail="情境描述不能為空")

    _prompt = SYSTEM_PROMPT if req.expand else SYSTEM_PROMPT_QUICK
    _max_tok = 4096 if req.expand else 2500

    message = client.messages.create(
        model=MODEL,
        max_tokens=_max_tok,
        system=_system(_prompt),
        messages=[{"role": "user", "content": req.situation}],
    )

    raw = _extract_json(_strip_fences(message.content[0].text.strip()))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 回應格式異常，無法解析 JSON：{str(e)}"
        )

    return _validate_and_clamp(data)


@app.post("/api/analyze/stream")
async def analyze_stream(req: AnalyzeRequest):
    if not req.situation.strip():
        raise HTTPException(status_code=400, detail="情境描述不能為空")

    _prompt = SYSTEM_PROMPT if req.expand else SYSTEM_PROMPT_QUICK
    _max_tok = 4096 if req.expand else 2500
    _stages = (
        ["正在評估情境架構…", "計算社交風險與能量消耗…", "生成應對策略矩陣…", "模擬對方可能反應…"]
        if req.expand else
        ["正在評估情境架構…", "計算社交風險與能量消耗…", "生成應對策略矩陣…", "模擬對方可能反應…"]
    )
    _thresholds = [0, 200, 500, 900] if req.expand else [0, 60, 160, 250]

    async def event_generator():
        full_text = ""
        current_stage = 0

        yield f"data: {json.dumps({'stage': _stages[0]})}\n\n"

        with client.messages.stream(
            model=MODEL,
            max_tokens=_max_tok,
            system=_system(_prompt),
            messages=[{"role": "user", "content": req.situation}],
        ) as stream:
            for text_chunk in stream.text_stream:
                full_text += text_chunk
                next_stage = current_stage + 1
                if next_stage < len(_stages) and len(full_text) >= _thresholds[next_stage]:
                    current_stage = next_stage
                    yield f"data: {json.dumps({'stage': _stages[current_stage]})}\n\n"

        # Parse and validate the complete response
        raw = _extract_json(_strip_fences(full_text))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            yield f"data: {json.dumps({'error': f'AI 回應格式異常，無法解析 JSON：{str(e)}'})}\n\n"
            return

        result = _validate_and_clamp(data)
        yield f"data: {json.dumps({'done': True, 'result': result})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    return {"status": "online", "system": "I-GONE v3.0"}
