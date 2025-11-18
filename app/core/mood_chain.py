# 感情連鎖（MOOD_TO_THEME_LOGIC）のルール定義

import csv
import random
import os
from typing import List, Dict, Optional, Tuple

# --- ファイルパスの定義 ---
# 現在のファイル（app/core/mood_chain.py）からの相対パスでdata/literary_quotes.csvを参照
# 階層構造: app/core/ -> app/ -> data/literary_quotes.csv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE_PATH = os.path.join(BASE_DIR, '..', '..', 'data', 'quotes.csv')

# --- 感情連鎖ロジック（テーマ連動） ---
# ここはデータファイルから分離されたロジックであるため、そのまま維持する。

MOOD_CHAIN_LOGIC: Dict[str, List[str]] = {
    'start': ['友情', '希望'],      # 初期テーマは「友情」または「希望」
    'hopeful': ['不安', '芸術', '孤独'], 
    'angry': ['calm', '友情', '希望'],   
    'anxious': ['希望', 'calm', '友情'],  
    'melancholic': ['希望', '芸術', 'calm'],
    'calm': ['孤独', '芸術', '不安'],    
}

# テーマに合わせた物語の文脈（場面）を定義
THEME_CONTEXT: Dict[str, str] = {
    '友情': "メロスは、友との絆という原点に立ち返る。彼の心は、太宰治の原点にある。",
    '希望': "絶望の淵から、メロスは再び立ち上がる。友を救う使命と、自己の信念が、新たな力を生み出す。",
    '不安': "メロスは、希望の裏側にある、何かがおかしいという不吉な予感に襲われた。周囲には、宮沢賢治の『注文の多い料理店』のような奇妙な空気が漂っている。",
    '孤独': "激しい感情が去り、メロスの心には夏目漱石の『こころ』のような静かな孤独が広がる。友への信頼は揺らぎつつ、人間の罪深さに内省を始める。",
    '芸術': "走る道中で、メロスは梶井基次郎の『檸檬』のような、日常に潜む一瞬の美と破壊衝動に気づく。彼の目には、世界が美しくも不安定に映る。",
}

class QuoteManager:
    """文学作品の引用データ管理と抽出ロジックを扱うクラス。"""
    
    def __init__(self):
        self.quotes: List[Dict[str, str]] = self._load_quotes()

    def _load_quotes(self) -> List[Dict[str, str]]:
        """外部CSVファイルから引用データを辞書リストとして読み込む。"""
        quotes_list = []
        try:
            # CSV_FILE_PATHからファイルを読み込む
            with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    quotes_list.append(row)
        except FileNotFoundError:
            print(f"Error: CSVファイルが見つかりません。パスを確認してください: {CSV_FILE_PATH}")
            # ファイルが見つからない場合、空のリストを返す
            return []
        except Exception as e:
            print(f"CSVファイルの読み込み中にエラーが発生しました: {e}")
            return []
            
        return quotes_list

    def get_next_scene_data(self, current_mood: str) -> Tuple[str, str, List[Dict[str, str]]]:
        """
        現在の感情（Mood）に基づき、次のシーンの主題（Theme）、文脈テキスト、および選択肢を決定する。
        """
        
        # 1. 感情連鎖ロジックに基づき、次に遷移すべきテーマ（主題）を決定
        next_theme_candidates = MOOD_CHAIN_LOGIC.get(current_mood, ['友情', '希望'])
        next_theme = random.choice(next_theme_candidates)
        
        # 2. 決定されたテーマに合わせた、物語の状況説明文を取得
        context_text = THEME_CONTEXT.get(next_theme, f"メロスは荒野を駆ける。現在のテーマは「{next_theme}」である。")
        
        # 3. 決定されたテーマに基づき、データベースから3つのセリフを選択肢として抽出
        
        # 該当テーマを持つセリフをフィルタリング (theme_tagsに合致するもの)
        theme_quotes = [
            q for q in self.quotes 
            if q.get('theme_tags') == next_theme and q.get('allow_use') == 'True'
        ]
        
        choices: List[Dict[str, str]] = []
        used_work_ids: set[str] = set()

        # 3つの異なる作品のセリフが揃うまで試行する
        # このロジックは、同じ作品IDのセリフが選択肢に混ざらないようにする
        quotes_pool = list(theme_quotes) # プールを作成

        while len(choices) < 3 and quotes_pool:
            candidate = random.choice(quotes_pool)
            work_id = candidate['work_id']
            
            if work_id not in used_work_ids:
                choices.append({
                    'text': candidate['text'],
                    'work_title': candidate['work_title'],
                    'mood': candidate['mood'],
                    'work_id': work_id
                })
                used_work_ids.add(work_id)
                quotes_pool.remove(candidate) # 選んだものはプールから削除
            else:
                # 同じ作品IDの候補を一時的に除外
                quotes_pool.remove(candidate)
            
            # プールが空になっても3つ揃わなかった場合、ループを終了
            if not quotes_pool and len(choices) < 3:
                 break 
            
        return next_theme, context_text, choices