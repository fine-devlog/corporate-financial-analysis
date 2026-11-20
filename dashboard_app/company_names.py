"""企業名のゆれ（略称・英語名・読み仮名）を吸収して企業を探す。LLMは使わない。

EDINET のコードリスト（無料・キー不要）にある「英語名」「読み仮名」を使う。
  - 英語名の頭文字    : Nomura Research Institute → NRI
  - 英語名            : nomura, toyota, sony …
  - 読み仮名          : のむら、ノムラソウゴウ …
  - 略称（文字の順番） : 野村総研 → 野村総合研究所、日テレ → 日本テレビ
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile

import pandas as pd
import requests

CODELIST_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"

# 一致の強さ（小さいほど上に表示）
EXACT, PREFIX, CONTAINS, ALIAS, ABBREVIATION = range(5)

_CORP_WORDS_JA = ("株式会社", "(株)", "有限会社", "合同会社")
_CORP_KANA = ("カブシキガイシャ", "カブシキカイシャ", "ユウゲンガイシャ", "ゴウドウガイシャ")
# 頭文字に含めない英単語（会社の種類や「グループ」など）
_ACRONYM_STOPWORDS = {"co", "ltd", "inc", "corp", "corporation", "company", "limited", "the", "and", "of",
                      "kk", "k", "plc", "group", "holdings", "holding", "hd", "hds"}


def normalize_name(name) -> str:
    """「株式会社」や空白・記号の違いをなくした比較用の社名。"""
    s = unicodedata.normalize("NFKC", str(name or ""))  # ㈱ → (株)、全角英数 → 半角
    for token in _CORP_WORDS_JA:
        s = s.replace(token, "")
    s = re.sub(r"[\s・･\-‐ー－,，.．'’&＆]", "", s) if not _is_kana(s) else re.sub(r"[\s・･]", "", s)
    return s.lower()


def _is_kana(s: str) -> bool:
    return bool(s) and all("぀" <= ch <= "ヿ" or ch in "ー・ 　" for ch in s)


def to_katakana(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch for ch in s)


def normalize_kana(s) -> str:
    s = to_katakana(str(s or "")).replace(" ", "").replace("　", "").replace("・", "")
    for word in _CORP_KANA:
        s = s.replace(word, "")
    return s


def english_key(name_en) -> str:
    """英語名を小文字・英数字だけにする（Co.,Ltd. などは除く）。"""
    words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", str(name_en or "")).lower())
    return "".join(w for w in words if w not in _ACRONYM_STOPWORDS)


def acronym(name_en) -> str:
    """英語名の頭文字。Nomura Research Institute,Ltd. → nri"""
    words = re.findall(r"[A-Za-z]+", unicodedata.normalize("NFKC", str(name_en or "")))
    letters = [w[0].lower() for w in words if w.lower() not in _ACRONYM_STOPWORDS]
    return "".join(letters) if len(letters) >= 2 else ""


def is_subsequence(query: str, text: str) -> bool:
    """query の文字が text の中に同じ順番で現れるか（略称の判定）。"""
    it = iter(text)
    return all(ch in it for ch in query)


def match_rank(query: str, name: str, name_en=None, name_kana=None):
    """一致の強さを返す（一致しなければ None）。"""
    q = normalize_name(query)
    if not q:
        return None
    n = normalize_name(name)
    if q == n:
        return EXACT
    if n.startswith(q):
        return PREFIX
    if q in n:
        return CONTAINS
    q_ascii = re.sub(r"[^a-z0-9]", "", q)
    if q_ascii and q_ascii == q:  # 英数字だけの入力 → 英語名・頭文字
        en = english_key(name_en)
        if len(q_ascii) >= 3 and q_ascii == acronym(name_en):
            return ALIAS
        if len(q_ascii) >= 3 and en and (en.startswith(q_ascii) or q_ascii == en):
            return ALIAS
    if _is_kana(query.strip()):  # かな・カナ → 読み仮名
        qk = normalize_kana(query)
        if len(qk) >= 2 and qk in normalize_kana(name_kana):
            return ALIAS
    # 略称：日本語で2文字以上、先頭の文字が同じ、かつ全文字が順番どおりに含まれる（野村総研・日テレ）
    # 英字の入力（NTT など）には使わない（無関係な社名に当たりやすいため）
    if len(q) >= 2 and not q_ascii == q and n and q[0] == n[0] and is_subsequence(q, n):
        return ABBREVIATION
    return None


def load_name_table(path: str | None = None) -> pd.DataFrame:
    """EDINET コードリストから、上場企業の社名・英語名・読み仮名の表を作る。"""
    if path:
        raw = open(path, "rb").read()
    else:
        r = requests.get(CODELIST_URL, timeout=60)
        r.raise_for_status()
        raw = r.content
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(next(n for n in z.namelist() if n.lower().endswith(".csv")))
    df = pd.read_csv(io.BytesIO(raw), encoding="cp932", skiprows=1, dtype=str)
    df.columns = [unicodedata.normalize("NFKC", c) for c in df.columns]
    df = df[df["上場区分"] == "上場"]
    return pd.DataFrame({
        "edinet_code": df["EDINETコード"],
        "name": df["提出者名"],
        "name_en": df["提出者名(英字)"],
        "name_kana": df["提出者名(ヨミ)"],
        "sec_code": df["証券コード"].fillna("").str[:4],
    }).reset_index(drop=True)


def search_names(query: str, table: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """表全体から候補を探し、一致の強い順に返す（列 rank 付き）。"""
    q = unicodedata.normalize("NFKC", query or "").strip()
    if not q:
        return table.iloc[0:0].assign(rank=[])
    ranks = []
    for name, en, kana, code in zip(table["name"], table["name_en"], table["name_kana"], table["sec_code"]):
        ranks.append(EXACT if q == code else match_rank(q, name, en, kana))
    out = table.assign(rank=ranks).dropna(subset=["rank"])
    return out.sort_values(["rank", "name"]).head(limit)
