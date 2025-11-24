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
@app.route("/choose", methods=["POST"])
def choose():
    # フォームから選ばれた次の mood
    selected_mood = request.form.get("selected_mood", "neutral")

    turn = session.get("turn", 1)
    history = session.get("history", [])