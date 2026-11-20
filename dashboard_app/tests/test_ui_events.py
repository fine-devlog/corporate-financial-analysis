"""ui_events.py のテスト。"""
import types

import ui_events as U


def test_clicked_table_row_from_cell_or_row():
    assert U.clicked_table_row({"selection": {"cells": [(3, "企業名")], "rows": []}}) == 3
    assert U.clicked_table_row({"selection": {"cells": [], "rows": [5]}}) == 5
    assert U.clicked_table_row({"selection": {"cells": [], "rows": []}}) is None
    assert U.clicked_table_row(None) is None
    # 属性でアクセスする形（Streamlit の戻り値）でも読める
    assert U.clicked_table_row(types.SimpleNamespace(selection={"cells": [(1, "決算期")]})) == 1


def test_clicked_chart_company():
    assert U.clicked_chart_company({"selection": {"pick": [{"企業名": "トヨタ自動車株式会社"}]}}) == "トヨタ自動車株式会社"
    assert U.clicked_chart_company({"selection": {"pick": {"企業名": "本田技研工業株式会社"}}}) == "本田技研工業株式会社"
    assert U.clicked_chart_company({"selection": {"pick": []}}) is None
    assert U.clicked_chart_company({"selection": {"hover": [{"企業名": "X"}]}}) is None  # カーソルを合わせただけでは選ばない
    assert U.clicked_chart_company(None) is None


def test_scroll_script_targets_element():
    js = U.scroll_to_element_js("company-search-anchor", "123")
    assert 'shikihoScrollToElement("company-search-anchor")' in js and "// 123" in js
