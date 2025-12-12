#実行コード：python -m app.main
# サーバー起動ファイル、ルーティング定義
import os
import json
import requests
from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    jsonify,
)
from dotenv import load_dotenv
from app.core.mood_chain import QuoteManager
from .core.llm_connector import generate_options_from_csv
from typing import List, Dict

# .envファイルから環境変数を読み込む（ローカル開発用）
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret-key")
# CORS設定: フロントエンド（GitHub Pagesなど）からのアクセスを許可
from flask_cors import CORS
CORS(app) 

# --- グローバルな設定と初期化 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_FALLBACK_API_KEY")
QUOTE_MANAGER = QuoteManager()
GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# 作品ID → アイコンファイル名
WORK_ICON_MAP = {
    "hashire": "king_icon.jpg",    # 走れメロス
    "lemon": "lemon_icon.jpg",     # 檸檬
    "kokoro": "k_icon.jpg",        # こころ
    "chumon": "cat_icon.jpg",      # 注文の多い料理店
}

DEFAULT_ICON = "sun_icon.jpg"

# emotion 表示用の日本語ラベル
EMOTION_LABELS = {
    "neutral": "ふつう",
    "hope": "希望",
    "despair": "不安・絶望",
    # 必要に応じて増やしてOK
}


def attach_icons(options):
    """各 option に icon_filename キーを追加するヘルパー。"""
    for opt in options:
        work_id = opt.get("work_id")
        icon = WORK_ICON_MAP.get(work_id, DEFAULT_ICON)
        opt["icon_filename"] = icon
    return options



#--------------------------------------------------------------
#  index.html → play.html(1ターン目) → game.html(1ターン目) →・・・
#    → play.html(3ターン目) → game.html(3ターン目) → ending.html
#--------------------------------------------------------------

# タイトル画面（index.html)
@app.route("/")
def index():
    return render_template("index.html")


# ゲーム全体の初期化
# index.html の スタートbutton を押したときに呼ばれる
@app.route("/start")
def start_game():
    session.clear()
    session["turn"] = 1
    session["history"] = []
    session["current_mood"] = "neutral"
    return redirect(url_for("play"))

# play.html（メロスが走る画面）
@app.route("/play")
def play():
    turn = session.get("turn", 1)
    mood = session.get("current_mood", "neutral")
    return render_template("play.html", turn=turn, mood=mood)


# 選択肢が出る画面（game.html） ←【ファイル名わかりにくいから変えた方がいいかも】
@app.route("/game")
def game():
    turn = session.get("turn", 1)
    current_mood = session.get("current_mood", "neutral")

    # 現在の感情に応じて次の選択肢を生成
    options = generate_options_from_csv(current_mood)
    attach_icons(options)

    return render_template(
        "game.html",
        options=options,
        mood=current_mood,
        turn=turn,
    )


# 
"""
@app.route("/choose", methods=["POST"])
def choose():
    # フォームから選ばれた次の mood
    selected_mood = request.form.get("selected_mood", "neutral")

    turn = session.get("turn", 1)
    history = session.get("history", [])
    history.append(selected_mood)
    session["history"] = history
    session["current_mood"] = selected_mood

    # 3ターン目の選択で終了（ending.htmlへ）
    if turn >= 3:
        return redirect(url_for("ending"))
  
    # 続く場合はターンを進める？　【あとで確認】
    session["turn"] = turn + 1
    return redirect(url_for("play"))
"""
@app.post("/api/reset_story")
def reset_story():
    save_story({"story": []})
    return jsonify({"ok": True})

@app.route("/choose", methods=["POST"])
def choose():
    # game.html からのデータ
    chosen_text = request.form.get("chosen_text", "")
    chosen_mood = request.form.get("selected_mood", "neutral")
    next_theme = request.form.get("next_theme", "友情")
    current_work = request.form.get("current_work", "走れメロス")

    # 1. LLM に段落生成を依頼
    payload = {
        "chosen_text": chosen_text,
        "chosen_mood": chosen_mood,
        "next_theme": next_theme,
        "current_work": current_work
    }

    res = requests.post("http://127.0.0.1:5000/api/generate_scene_text", json=payload)

    if res.status_code != 200:
        print("LLM生成に失敗:", res.text)

    # 2. ゲーム進行の状態更新
    turn = session.get("turn", 1)
    history = session.get("history", [])
    history.append(chosen_mood)
    session["history"] = history
    session["current_mood"] = chosen_mood

    # 最終ターンで ending へ
    if turn >= 3:
        return redirect(url_for("ending"))

    # ターン経過
    session["turn"] = turn + 1

    # 3. play.html へ戻る（story.json が更新済み）
    return redirect(url_for("play"))


# エンディング画面（ending.html）
@app.route("/ending")
def ending():
    final_mood = session.get("current_mood", "neutral")
    final_label = EMOTION_LABELS.get(final_mood, final_mood)
    history = session.get("history", [])

    return render_template(
        "ending.html",
        final_mood=final_mood,    # hope・neutral など
        final_label=final_label,  # 希望・ふつう など
        history=history,          # 途中の mood 遷移 【あとで確認】
    )


# ----------------------------------------------------------------------------------
# APIエンドポイント 1: 感情連鎖による次の選択肢の取得
# ----------------------------------------------------------------------------------
@app.route('/api/choices', methods=['POST'])
def get_next_choices():
    """
    現在の感情（current_mood）に基づき、次のシーンのテーマと選択肢を提供する。
    """
    try:
        data = request.get_json()
        current_mood = data.get('current_mood', 'start')

        # ロジックを呼び出し: 次の主題、文脈、選択肢を取得
        next_theme, context_text, choices = QUOTE_MANAGER.get_next_scene_data(current_mood)
        
        if not choices:
            return jsonify({
                "error": "次の主題に合うセリフが見つかりませんでした。",
                "next_theme": next_theme
            }), 404

        return jsonify({
            "next_theme": next_theme,
            "context_text": context_text,
            "choices": choices
        })

    except Exception as e:
        app.logger.error(f"Error processing choices: {e}")
        return jsonify({"error": "次の選択肢の決定中に失敗しました。", "details": str(e)}), 500


# ----------------------------------------------------------------------------------
# APIエンドポイント 2: LLMによる場面の橋渡しテキスト生成
# ----------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORY_PATH = os.path.join(BASE_DIR, "static", "data", "story.json")

def load_story():
    if not os.path.exists(STORY_PATH):
        return {"story": []}
    with open(STORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_story(story_data):
    os.makedirs(os.path.dirname(STORY_PATH), exist_ok=True)
    with open(STORY_PATH, "w", encoding="utf-8") as f:
        json.dump(story_data, f, ensure_ascii=False, indent=2)

@app.route('/api/generate_scene_text', methods=['POST'])
def generate_scene_text():
    """
    プレイヤーの選択と次のテーマ、さらに story.json の履歴を踏まえて
    物語の続きを生成し、段落ごとに保存する
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_FALLBACK_API_KEY":
        return jsonify({"error": "Gemini API key is not configured on the server."}), 503

    try:
        data = request.get_json()
        chosen_text = data.get('chosen_text', '')
        chosen_mood = data.get('chosen_mood', 'calm')
        next_theme = data.get('next_theme', '友情')
        current_work = data.get('current_work', '走れメロス')

        ### 追加：これまでのストーリー読み込み
        story_data = load_story()
        previous_story = "\n".join(story_data["story"])  # LLM 用にまとめる

        system_instruction = (
            "あなたは物語の語り手です。"
            "以下はこれまでのストーリー全体です：\n"
            f"{previous_story}\n\n"
            "主人公メロスは、今「走れメロス」から離れて別作品の世界へ向かう。"
            f"直前のメロスの選択は「{chosen_text}」（作品：{current_work}, 感情：{chosen_mood}）である。"
            f"次の主題は「{next_theme}」である。\n"
            "この流れを自然につなぐ新しい段落を 150字以内で生成せよ。"
            "縦書きに向くように改行を含めてもよい。"
            "段落は1つだけ生成し、決して長編にしない。"
        )

        user_prompt = (
            f"メロスが「{chosen_text}」と言った。次の主題は「{next_theme}」。"
            "この場面転換をつなぐ新しい段落を生成してください。"
        )

        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]}
        }
        
        response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", json=payload)
        response.raise_for_status()

        result = response.json()
        scene_text = result['candidates'][0]['content']['parts'][0]['text']

        ### 追加：段落として JSON に追加
        new_paragraph = scene_text.strip()
        story_data["story"].append(new_paragraph)

        ### 追加：保存
        save_story(story_data)

        return jsonify({
            "scene_text": new_paragraph,
            "next_mood": chosen_mood
        })

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Gemini APIとの通信に失敗しました。", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "場面生成中に予期せぬエラー。", "details": str(e)}), 500


# ----------------------------------------------------------------------------------
# APIエンドポイント 3: LLMによるエンディングの生成 (省略)
# ----------------------------------------------------------------------------------
# ※ 前回のコードとロジックは同じため、ここでは省略する。

# サーバーの起動
if __name__ == '__main__':
    # 開発サーバー起動（本番環境では使用しない）
    app.run(debug=True, host='0.0.0.0', port=5000)