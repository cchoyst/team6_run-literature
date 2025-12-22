# LLM APIとの通信 (Gemini APIなど)
# 【応答が遅いから変える】
import os
import json
import re
from typing import Any
import google.generativeai as genai
from dotenv import load_dotenv
from .data_manager import load_quotes

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("Missing GEMINI_API_KEY")

genai.configure(api_key=api_key)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

# モデルを作る
model = genai.GenerativeModel(MODEL_NAME)

# LLM に渡す引用の最大数（多いほど遅くなるので絞る）
MAX_QUOTES_PER_CALL = 12


SYSTEM_MSG = """
あなたは日本文学を題材にしたマルチエンディングゲームのシナリオ生成AIです。
与えられた引用リストと現在の mood をもとに、
プレイヤーに提示する「次の選択肢 3 個」を JSON 形式で返してください。

各選択肢は、引用の雰囲気を活かした短いセリフにしてください。
また、各選択肢ごとに次の mood を "next_mood" として指定してください。

【指定可能な next_mood】
"hopeful", "angry", "melancholic", "anxious", "calm", "neutral"

出力は必ず次の形式の JSON **だけ** にしてください。
各 options[i] の "work_id" には、引用に対応する work_id を 1 つ入れてください。

{
  "options": [
    {"id": 1, "text": "選択肢1のセリフ", "next_mood": "hope",   "work_id": "hashire"},
    {"id": 2, "text": "選択肢2のセリフ", "next_mood": "despair","work_id": "kokoro"},
    {"id": 3, "text": "選択肢3のセリフ", "next_mood": "neutral","work_id": "lemon"}
  ]
}
""".strip()


def _extract_text(response: Any) -> str:
    """Gemini 応答からテキストだけを取り出す"""
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise RuntimeError("Gemini 応答に candidates がありません")

    cand = candidates[0]
    finish_reason = getattr(cand, "finish_reason", None)
    if finish_reason and str(finish_reason) not in (
        "FINISH_REASON_STOP",
        "STOP",
        "None",
    ):
        raise RuntimeError(f"Gemini 応答が正常終了していません: {finish_reason}")

    content = getattr(cand, "content", None)
    parts = getattr(content, "parts", None) or getattr(cand, "parts", None) or []
    pieces = [getattr(p, "text", "") for p in parts if getattr(p, "text", None)]

    if not pieces:
        raise RuntimeError("Gemini 応答からテキストを取得できませんでした")

    return "".join(pieces).strip()


def generate_options_from_csv(current_mood: str):
    """
    現在の mood と CSV の引用データから、
    次の選択肢候補3つを生成して返す。
    """
    df = load_quotes()

    # mood 列があれば優先してフィルタ
    if "mood" in df.columns:
        df_mood = df[df["mood"] == current_mood]
        if df_mood.empty:
            df_mood = df  # 該当が無ければ全体から
    else:
        df_mood = df

    # LLM に渡す行数を絞る（多いとその分トークン数が増えて遅くなる）
    if len(df_mood) > MAX_QUOTES_PER_CALL:
        df_mood = df_mood.sample(MAX_QUOTES_PER_CALL, random_state=None)

    quotes_list = df_mood.to_dict(orient="records")

    user_msg = f"""
現在の mood: {current_mood}

以下はゲームで利用できる引用データの一部です。
この mood に近いものを優先して参考にしながら、
プレイヤーに提示する「次の選択肢 3 個」を考えてください。

CSV データ (JSON 形式):
{json.dumps(quotes_list, ensure_ascii=False)}
""".strip()

    contents = [
        {"role": "user", "parts": [{"text": SYSTEM_MSG}]},
        {"role": "user", "parts": [{"text": user_msg}]},
    ]

    rsp = model.generate_content(contents=contents)
    raw = _extract_text(rsp)

    # 応答から JSON 部分だけ抜き出す
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        raise ValueError("Gemini から JSON を抽出できませんでした:\n" + raw)

    data = json.loads(json_match.group(0))

    options = data.get("options")
    if not isinstance(options, list):
        raise ValueError(
            "Gemini 応答 JSON に 'options' 配列がありません:\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
        )

    return options
