 # 過去の行動履歴(R)やアイテムデータの管理
from pathlib import Path
from functools import lru_cache
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
QUOTES_CSV = DATA_DIR / "quotes.csv"


@lru_cache(maxsize=1)
def load_quotes() -> pd.DataFrame:
  """quotes.csv を 1 回だけ読み込んでキャッシュする。"""
  return pd.read_csv(QUOTES_CSV)