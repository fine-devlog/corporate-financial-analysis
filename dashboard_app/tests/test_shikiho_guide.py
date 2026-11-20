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
