#実行コード：python -m app.main
# サーバー起動ファイル、ルーティング定義
import os
import json
import requests
import random
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


# データベースの mood カラムの値に合わせて修正
EMOTION_LABELS = {
    "hopeful": "希望",
    "angry": "激怒",
    "melancholic": "憂鬱・哀愁",
    "anxious": "不安",
    "calm": "平静",
    "neutral": "ふつう"
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

def get_literary_background():
    """
    APIを使わず、指定した文学テキストをランダムに取得する。
    """
    # ここに表示したい文章を自由に記述してください。
    # 三連引用符 (''' or """) を使うと、改行を含めた長い文章をそのまま書けます。
    library = [
        {
            "title": "走れメロス、レモン、注文の多い料理店",
            "content": """メロスは激怒した。必ず、かの邪智暴虐の王を除かなければならぬと決意した。
            メロスには政治がわからぬ。メロスは、村の牧人である。笛を吹き、羊と遊んで暮して来た。
            けれども邪悪に対しては、人一倍に敏感であった。きょう未明メロスは村を出発し、野を越え山越え、
            十里はなれた此のシラクスの市にやって来た。メロスには父も母も無い。女房も無い。
            十六の、内気な妹と二人暮しだ。この妹は、村の或る律気な一牧人を、近々、花婿として迎える事になっていた。"""
            """えたいの知れない不吉な塊が私の心を始終圧えつけていた。
            焦躁と言おうか、嫌悪と言おうか――酒を飲んだあとに二日酔いがあるように、酒を毎日飲んでいると
            二日酔いに相当した時期がやって来る。それが来たのだ。これはちょっといけなかった。
            結果した肺尖カタルや神経衰弱がいけないのではない。また、背を焼くような借金などがいけないのではない。
            いけないのはその不吉な塊だ。以前あんなに私をひきつけた丸善の棚の背表紙も、
            今ではただ不潔な、がらくたの集まりにしか見えない。"""
            """二人の若い紳士が、すっかりイギリスの兵隊のかたちをして、ぴかぴかする鉄砲をかついで、
            白熊のような犬を二匹つれて、だいぶ山奥の、木の葉のわさわさしたとこを、歩いておりました。
            「ぜんたい、ここらの山は怪しからんね。鳥も獣も一匹も居やがらん。なんでも構わないから、
            早くタンタアーンとやってみたいもんだなあ。」
            「鹿の黄いろな横っ腹なんぞに、二三発お見舞したら、ずいぶん愉快だろうね。くるくる廻って、
            どたっと倒れるだろうね。」"""
        }
    ]

    try:
        # リストからランダムに1つ選ぶ
        selected_book = random.choice(library)
        return selected_book["content"]
    except Exception as e:
        print(f"Text Selection Error: {e}")
        return "テキストの読み込みに失敗しました。"

# ----------------------------------------------------------------------------------
#  ルーティング
# ----------------------------------------------------------------------------------

# タイトル画面（index.html)
@app.route("/")
def index():
    # 背景用テキストを取得して HTML に渡す
    bg_text = get_literary_background()
    return render_template("index.html", background_text=bg_text)


# ゲーム全体の初期化
# index.html の スタートbutton を押したときに呼ばれる
@app.route("/start")
def start_game():
    session.clear()
    session["turn"] = 1
    session["history"] = []
    session["current_mood"] = "neutral"
    save_story({"story": []})
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
    # 1. フォームデータの取得（HTML側が ['mood'] でも .mood でも取れるようにする）
    chosen_text = request.form.get("chosen_text", "")
    chosen_mood = request.form.get("selected_mood") or "neutral"
    next_theme = request.form.get("next_theme", "友情")
    current_work = request.form.get("current_work", "走れメロス")

    print(f"--- ユーザーが選択した感情: {chosen_mood} ---")

    # 2. セッションの更新（ここをLLM生成より先に行う）
    history = session.get("history", [])
    history.append(chosen_mood)
    
    session["history"] = history
    session["current_mood"] = chosen_mood
    turn = session.get("turn", 1)
    session["turn"] = turn + 1
    session.modified = True

    # 3. LLMによる文章生成（内部のロジックを直接呼ぶ）
    # 外部への requests.post("http://127.0.0.1:5000/...") はデッドロックの原因になるので避ける
    try:
        # これまでのストーリーを読み込む
        story_data = load_story()
        previous_story = "\n".join(story_data.get("story", []))

        system_instruction = (
            "あなたは物語の語り手です。\n"
            f"これまでのあらすじ：{previous_story}\n"
            f"メロスの今の行動：{chosen_text} (作品：{current_work}, 感情：{chosen_mood})\n"
            f"次のテーマ：{next_theme}\n"
            "これらを踏まえ、次のシーンへ繋ぐ150字以内の文章を生成してください。"
        )

        payload = {
            "contents": [{"parts": [{"text": f"メロスは{chosen_text}と言い、{next_theme}の世界へ向かった。"}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]}
        }
        
        # 直接 Gemini API を叩く
        res = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", json=payload, timeout=10)
        res.raise_for_status()
        
        scene_text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        story_data["story"].append(scene_text)
        save_story(story_data)

    except Exception as e:
        print(f"LLM Generation Error: {e}")
        # 万が一生成に失敗しても、物語が止まらないよう仮の文章を入れる
        story_data = load_story()
        story_data["story"].append(f"メロスは{next_theme}の予感を感じながら先を急いだ。")
        save_story(story_data)

    # 4. 進行判定
    # 3回選択した後の4回目の文章生成が終わったらエンディングへ
    if session["turn"] > 4:
        return redirect(url_for("ending"))
    
    return redirect(url_for("play"))


# エンディング画面（ending.html）
@app.route("/ending")
def ending():
    # 1. その時点での最新の感情を取得（なければ neutral）
    final_mood = session.get("current_mood", "neutral")
    # 日本語ラベルに変換
    final_label = EMOTION_LABELS.get(final_mood, final_mood)
    
    # 2. 感情の履歴を取得
    raw_history = session.get("history", [])
    
    # 軌跡の作成：初期状態(neutral) + 選択してきた履歴
    full_history_raw = ["neutral"] + raw_history
    history_labels = [EMOTION_LABELS.get(m, m) for m in full_history_raw]

    # 3. これまで生成された文章をすべて読み込む
    story_data = load_story()
    generated_story = story_data.get("story", [])

    # 初期文章（固定）
    initial_story = ["メロスは激怒した。必ずや、かの邪智暴虐の王を除かなければならぬと決意した。"]
    
    # 全文章を結合
    full_story = initial_story + generated_story

    return render_template(
        "ending.html",
        final_label=final_label,
        history=history_labels, # 軌跡用（リスト）
        story_text=full_story
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
# ★ 新規追加部分：あらすじ機能
# ----------------------------------------------------------------------------------

# あらすじ選択画面（4つのタイトルを表示）
@app.route("/synopsis")
def synopsis():
    bg_text = get_literary_background()
    titles = [
        {"id": "hashire", "name": "走れメロス"},
        {"id": "lemon", "name": "檸檬"},
        {"id": "kokoro", "name": "こころ"},
        {"id": "chumon", "name": "注文の多い料理店"}
    ]
    return render_template("synopsis.html", titles=titles, background_text=bg_text)

# あらすじ詳細画面（選択したタイトルのあらすじを表示）
@app.route("/synopsis/<work_id>")
def synopsis_detail(work_id):
    bg_text = get_literary_background()
    # ★ ここに各作品のあらすじ文章を自由に記述してください
    synopsis_data = {
        "hashire": {
            "title": "走れメロス", 
            "text": """
                羊飼いのメロスは、暴君と噂される王に会うため都を訪れる。<br>
                王が人を疑い、無実の人々を処刑していることを知ったメロスは怒りをぶつけるが、逆に捕らえられ死刑を宣告される。<br><br>
                メロスは妹の結婚式を行うため三日間の猶予を願い出て、代わりに親友<b>セリヌンティウス</b>を人質として残す。<br><br>
                道中、川の氾濫や山賊などの困難に遭い、心が折れそうになりながらも、友への信頼と約束を守るため必死に走り続ける。<br><br>
                期限ぎりぎりで都に戻ったメロスの姿に王は心を打たれ、人を信じる気持ちを取り戻す。<br><br>
                <b>友情と信頼の尊さ</b>を描いた、太宰治の不朽の名作。
            """
        },
        "lemon": {
            "title": "檸檬", 
            "text": """
                心身の不調に悩む「私」は、重苦しい気分を抱えながら京都の町をさまよい歩く。<br>
                かつて心を躍らせた丸善の棚や音楽さえも、今の「私」にはただ不潔で退屈なものにしか見えない。<br><br>
                ある時、気晴らしに立ち寄った果物屋で、鮮やかな一個の<b>檸檬</b>を買い求める。<br>
                その冷たさ、強い色、そして爽やかな香りに、「私」は一時的な解放感を覚える。<br><br>
                その後、再び訪れた丸善の店内で、「私」は美術書の山の上にそっと檸檬を置く。<br>
                それを<b>黄金色の爆弾</b>に見立て、店を立ち去る「私」。<br><br>
                憂鬱な日常から一瞬だけ逃れるひそかな快感を描いた、梶井基次郎の代表作。
            """
        },
        "kokoro": {
            "title": "こころ", 
            "text": """
                鎌倉の海岸で「私」が出会ったのは、どこか世間を避けて生きる<b>「先生」</b>だった。<br>
                次第に親交を深めていくが、先生は時折、人付き合いを拒むような暗い影を見せる。<br><br>
                やがて、先生から「私」のもとに届いた一通の分厚い<b>遺書</b>。<br>
                そこには、若き日の先生が親友「K」と同じ女性を愛し、卑怯な裏切りによって<b>Kを自死へ追いやってしまった</b>という凄惨な過去が綴られていた。<br><br>
                長年、消えない罪悪感を抱え続けてきた先生は、明治の時代の終焉とともに、自ら命を絶つ道を選ぶ。<br><br>
                人間のエゴイズムと救いがたい孤独を深く掘り下げた、夏目漱石の最高傑作。
            """
        },
        "chumon": {
            "title": "注文の多い料理店", 
            "text": """
                山奥へ狩りにやってきた二人の若い紳士は、道に迷い、お腹を空かせていた。<br>
                そこへ突如として現れた、立派な西洋料理店<b>「山猫軒」</b>。<br><br>
                扉を開けるたびに「髪をとかしてください」「体に塩を塗り込んでください」といった奇妙な<b>『注文』</b>が次々に現れる。<br>
                二人はそれを「客へのサービス」だと都合よく解釈し、喜んで従っていくが……。<br><br>
                実はその店は、人間を食べるために山猫たちが仕掛けた恐ろしい罠だった。<br>
                あわや料理されそうになった瞬間、連れていた猟犬たちが飛び込み、間一髪で難を逃れる。<br><br>
                人間の傲慢さを皮肉り、自然の恐ろしさを幻想的に描いた、宮沢賢治の不朽の童話。
            """
        }
    }
    
    content = synopsis_data.get(work_id, {"title": "不明", "text": "内容が見つかりませんでした。"})
    return render_template("synopsis_detail.html", content=content, background_text=bg_text)

# ----------------------------------------------------------------------------------
# APIエンドポイント 3: LLMによるエンディングの生成 (省略)
# ----------------------------------------------------------------------------------

# サーバーの起動
if __name__ == '__main__':
    # 開発サーバー起動
    app.run(debug=True, host='0.0.0.0', port=5000)