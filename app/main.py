# サーバー起動ファイル、ルーティング定義
import os
import json
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from core.mood_chain import QuoteManager 
from typing import List, Dict

# .envファイルから環境変数を読み込む（ローカル開発用）
load_dotenv()

app = Flask(__name__)
# CORS設定: フロントエンド（GitHub Pagesなど）からのアクセスを許可
from flask_cors import CORS
CORS(app) 

# --- グローバルな設定と初期化 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_FALLBACK_API_KEY")
QUOTE_MANAGER = QuoteManager()
GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

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
@app.route('/api/generate_scene_text', methods=['POST'])
def generate_scene_text():
    """
    プレイヤーの選択と次のテーマに基づき、LLMが次の場面への物語の橋渡しテキストを生成する。
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_FALLBACK_API_KEY":
        return jsonify({"error": "Gemini API key is not configured on the server."}), 503

    try:
        data = request.get_json()
        chosen_text = data.get('chosen_text', '')
        chosen_mood = data.get('chosen_mood', 'calm')
        next_theme = data.get('next_theme', '友情')
        current_work = data.get('current_work', '走れメロス')

        system_instruction = (
            "あなたは物語の語り手である。主人公メロスは、今「走れメロス」から離れて、他の文学作品の世界へ引き込まれている。"
            f"直前のメロスの行動は、セリフ「{chosen_text}」（作品：{current_work}、感情：{chosen_mood}）を選んだことである。"
            f"この選択により、物語の主題は「{next_theme}」に急激に変化する。"
            "この急な変化を繋ぎ合わせる、自然で文学的な橋渡しのテキストを生成せよ。"
            "**縦書きの作文用紙に合うよう、一行あたりの文字数を少なくし、改行を多く用いること。**"
            "生成する文章は、**新たな場面への導入（150字程度）**に留めること。"
        )
        user_prompt = (
            f"メロスが「{chosen_text}」と発言した。彼の目の前に新たな情景が広がる。次の主題は「{next_theme}」である。この場面転換を描写せよ。"
        )

        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]}
        }
        
        response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", json=payload)
        response.raise_for_status() 
        
        result = response.json()
        scene_text = result['candidates'][0]['content']['parts'][0]['text']

        # LLM生成テキストと次の感情（選択されたもの）を返す
        return jsonify({
            "scene_text": scene_text,
            "next_mood": chosen_mood # 選んだセリフのMoodを次のターンの入力として使う
        })

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Gemini API Request Error: {e}")
        return jsonify({"error": "Gemini APIとの通信に失敗しました。", "details": str(e)}), 500
    except Exception as e:
        app.logger.error(f"Error generating scene text: {e}")
        return jsonify({"error": "場面生成中に予期せぬエラーが発生しました。", "details": str(e)}), 500


# ----------------------------------------------------------------------------------
# APIエンドポイント 3: LLMによるエンディングの生成 (省略)
# ----------------------------------------------------------------------------------
# ※ 前回のコードとロジックは同じため、ここでは省略する。

# サーバーの起動
if __name__ == '__main__':
    # 開発サーバー起動（本番環境では使用しない）
    app.run(debug=True, host='0.0.0.0', port=5000)