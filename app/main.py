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
    "hashire": "king_icon.png",    # 走れメロス
    "lemon": "lemon_icon.png",     # 檸檬
    "kokoro": "k_icon.png",        # こころ
    "chumon": "cat_icon.png",      # 注文の多い料理店
}

DEFAULT_ICON = "sun_icon.png"


# データベースの mood カラムの値に合わせて修正
EMOTION_LABELS = {
    "hopeful": "希望",
    "angry": "激怒",
    "melancholic": "憂鬱・哀愁",
    "anxious": "不安",
    "calm": "平静",
    "neutral": "ふつう"
}

PHASE_INSTRUCTIONS = {
    1: "物語の『承』です。状況が動き出し、登場人物の行動が意味を持ち始めます。",
    2: "物語の『転』です。不安や違和感が生まれ、物語の方向性が揺らぎます。",
    3: "物語の『落』です。結末に向かう決定的な心情や選択を描いてください。"
}

SERINENTIUS_RULE = (
    "【エンディング必須演出】\n"
    "- メロスはセリヌンティウスのもとへ向かい、辿り着く過程または瞬間を描くこと\n"
    "- 再会の成否は描写しても、描写しなくてもよい\n"
    "- 友情・信義・約束の重みが行動の理由として滲むように描写する\n"
    "- セリヌンティウスの名を明示的に一度以上記すこと\n\n"
)


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
            "title": "走れメロス、レモン、注文の多い料理店、こころ",
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
            どたっと倒れるだろうね。」
            私はその人を常に先生と呼んでいた。だからここでもただ先生と書くだけで本名は打ち明けない。
            これは世間を憚る遠慮というよりも、その方が私にとって自然だからである。
            私はその人の記憶を呼び起こすごとに、すぐ「先生」といいたくなる。筆を執っても
            心持は同じ事である。
            よそよそしい頭文字などはとても使う気にならない。「あなたは今、自由な、独立した、
            己れに充ちた現代の人間に生り切ろうとしている。しかしその反面には、
            孤独の寂しさを味わわなければならないのが、現代の人間が支払うべき報酬のようなものですよ。その代り自由な、
            独立した、己れに充ちた現代の人間は、愛に対して、またそれに応えるべきはずの
            犠牲を払わなければならなくなるのです」"""
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

    # 現在の感情に応じた選択肢を生成
    options = generate_options_from_csv(current_mood)
    
    # 【重要】optionsの中身が辞書(dict)であることを確認し、アイコンを付与
    options = attach_icons(options)

    return render_template(
        "game.html",
        options=options,  # 辞書のリストとして渡す
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
    # --- 1. フォームデータ取得 ---
    chosen_text = request.form.get("chosen_text", "")
    chosen_mood = request.form.get("selected_mood") or "neutral"
    next_theme = request.form.get("next_theme", "友情")
    current_work = request.form.get("current_work", "走れメロス")

    # --- 2. セッション更新 ---
    history = session.get("history", [])
    history.append(chosen_mood)
    session["history"] = history
    session["current_mood"] = chosen_mood

    turn = session.get("turn", 1)
    session["turn"] = turn + 1
    session.modified = True

    # --- 3. LLM による文章生成 ---
    try:
        story_data = load_story()
        previous_story = "\n".join(story_data.get("story", []))

        phase_instruction = PHASE_INSTRUCTIONS.get(turn, "")
        serinentius_instruction = ""
        if session["turn"] == 3:
            serinentius_instruction = SERINENTIUS_RULE
        
        # --- system instruction（物語ルール） ---
        system_instruction = (
            "あなたは文学作品の語り手です。\n"
            "この物語は『走れメロス』を軸に、他の文学作品の世界が交錯するクロスワールドです。\n\n"
            
            "【重要な世界観ルール】\n"
            "- メロスは常に走り続けている存在であり、立ち止まらない\n"
            "- 他の文学作品の人物・言葉・空間は、道中に『割り込む』『語りかける』『影のように現れる』\n"
            "- メロスと他作品は、完全に理解し合わなくてよい。すれ違いや違和感を大切にする\n\n"
            
            "【文章表現の制約】\n"
            "- 出力は地の文のみ（解説・説明は禁止）\n"
            "- 150字以内の一段落\n"
            "- 意味や印象の切れ目で改行を入れてよい\n"
            
            f"【物語フェーズ】\n{phase_instruction}\n\n"
            f"{serinentius_instruction}"
            f"【これまでの物語】\n{previous_story}\n"
        )

        # --- user prompt（今回の場面指示） ---
        user_prompt = (
            f"メロスは走りながら「{chosen_text}」と口にした。\n"
            f"その瞬間、彼の前に「{current_work}」の世界の気配が滲み出す。\n"
            f"彼の感情は「{chosen_mood}」。\n"
            f"物語は「{next_theme}」の兆しを帯びる。\n"
            "この交錯が、次の場面へ自然につながるよう描写せよ。"
        )


        payload = {
            "contents": [
                {"parts": [{"text": user_prompt}]}
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }

        res = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            json=payload,
            timeout=10
        )
        res.raise_for_status()

        scene_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        story_data["story"].append(scene_text)
        save_story(story_data)

    except Exception as e:
        print(f"LLM Generation Error: {e}")
        # フォールバック（物語が止まらないため）
        story_data = load_story()
        story_data["story"].append(
            f"メロスは{next_theme}の気配を胸に抱いたまま、歩みを止めなかった。"
        )
        save_story(story_data)

    # --- 4. 進行判定 ---
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
    initial_story = ["メロスは激怒した。",
                     "必ずや、かの邪智暴虐の王を除かなければならぬと決意した。",
                     "走り出した瞬間、彼はまだ知らなかった。この道が、ひとつの物語の内側だけでは終わらぬことを。"]
    
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
    return render_template("synopsis.html", titles=titles, background_text=bg_text,work_icons=WORK_ICON_MAP)

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
    icon = WORK_ICON_MAP.get(work_id)
    return render_template("synopsis_detail.html", content=content, background_text=bg_text,icon=icon)

# ----------------------------------------------------------------------------------
# APIエンドポイント 3: LLMによるエンディングの生成 (省略)
# ----------------------------------------------------------------------------------

# サーバーの起動
if __name__ == '__main__':
    # 開発サーバー起動
    app.run(debug=True, host='0.0.0.0', port=5000)