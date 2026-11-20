"""company_names.py のテスト（ネットワーク不要）。"""
import pytest

import company_names as C

NRI = ("株式会社野村総合研究所", "Nomura Research Institute,Ltd.", "カブシキガイシャノムラソウゴウケンキュウショ")
NTV = ("日本テレビホールディングス株式会社", "Nippon Television Holdings,Inc.", "ニッポンテレビホールディングスカブシキガイシャ")


@pytest.mark.parametrize("query,company,rank", [
    ("野村総合研究所", NRI, C.EXACT),
    ("野村総合", NRI, C.PREFIX),
    ("総合研究所", NRI, C.CONTAINS),
    ("NRI", NRI, C.ALIAS),           # 英語名の頭文字
    ("nri", NRI, C.ALIAS),
    ("nomura", NRI, C.ALIAS),        # 英語名
    ("のむらそうごう", NRI, C.ALIAS),  # 読み仮名（ひらがな）
    ("ノムラ", NRI, C.ALIAS),          # 読み仮名（カタカナ）
    ("野村総研", NRI, C.ABBREVIATION),  # 略称
    ("日テレ", NTV, C.ABBREVIATION),
    ("NR", NRI, None),               # 2文字の英字は誤爆しやすいので使わない
    ("XYZ", NRI, None),
    ("総研", NRI, None),               # 略称は先頭の文字が一致するものだけ
])
def test_match_rank(query, company, rank):
    assert C.match_rank(query, *company) == rank


def test_acronym_skips_company_words():
    assert C.acronym("Nomura Research Institute,Ltd.") == "nri"
    assert C.acronym("SONY GROUP CORPORATION") == ""  # 頭文字が1文字しか残らない
    assert C.acronym("Nippon Telegraph and Telephone Corporation") == "ntt"


def test_normalize_kana_removes_company_type():
    assert C.normalize_kana("かぶしきがいしゃメルカリ") == "メルカリ"
