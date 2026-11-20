"""shikiho_guide.py の内容の整合性テスト。"""
import shikiho_guide as G


def test_referenced_items_exist():
    names = {x["item"] for x in G.SHIKIHO_LOCATIONS}
    for item in G.LOCATIONS_FOR_MANUAL_INPUT + G.LOCATIONS_FOR_HEADLINE:
        assert item in names, item


def test_every_guide_entry_is_complete():
    for g in G.METRIC_GUIDE:
        for key in ("metric", "meaning", "high", "low", "tips", "caution"):
            assert g[key], (g["metric"], key)


def test_tenure_is_not_claimed_to_be_in_kaisha_shikiho():
    """平均勤続年数は会社四季報には載っていない（有報・就職四季報）。誤った案内をしない。"""
    tenure = G.locations(["平均勤続年数"])[0]
    assert "載っていない" in tenure["where"]


import pytest


@pytest.mark.parametrize("ua,mobile", [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1", True),
    ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36", True),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", False),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15", False),  # Mac・iPad
    ("Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", False),  # Androidタブレット
    ("", False),  # 分からなければパソコン扱い
])
def test_is_mobile_user_agent(ua, mobile):
    assert G.is_mobile_user_agent(ua) is mobile
