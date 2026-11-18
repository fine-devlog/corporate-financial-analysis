"""analysis02.py（Streamlitアプリ）のテスト。Supabase は偽物に差し替える。"""
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "analysis02.py")
USER = types.SimpleNamespace(email="test@example.com", app_metadata={})


def edinet_row(i, name, code, income, margin, growth):
    return {
        "id": i, "company_name": name, "sec_code": code, "source": "edinet", "edinet_code": f"E{i:05d}",
        "period_end": "2026-03-31", "income": income, "age": 41.0, "operating_margin": margin,
        "revenue_growth": growth, "operating_profit_growth": None, "avg_tenure": 15.0, "operating_cf_margin": 10.0,
        "overseas_ratio": None, "founding_year": None, "next_year_growth_forecast": None, "segment_concentration": None,
    }


COMPANIES = [
    edinet_row(1, "トヨタ自動車株式会社", "7203", 900, 10.0, -2.0),
    edinet_row(2, "本田技研工業株式会社", "7267", 850, 6.0, -3.0),
    edinet_row(3, "株式会社デンソー", "6902", 800, 5.0, -1.0),
    edinet_row(4, "スズキ株式会社", "7269", 700, 8.0, 500.0),  # 外れ値
    edinet_row(5, "トヨタ紡織株式会社", "3116", 650, 3.0, -2.5),
    {"id": 99, "company_name": "手入力社", "source": "user", "income": 5000},  # 業界基準には使わない
]
TEXTS = {"doc_id": "S100TEST", "period_end": "2026-03-31", "business_description": "自動車を作る。",
         "management_policy": None, "business_risks": "為替リスク。"}


class FakeQuery:
    def __init__(self, table, fail):
        self.table, self.fail, self.rng = table, fail, (0, 999)

    def __getattr__(self, _):
        return lambda *a, **k: self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def execute(self):
        if self.fail:
            raise ConnectionError("DB down")
        data = COMPANIES if self.table == "companies" else [TEXTS] if self.table == "company_texts" else []
        return types.SimpleNamespace(data=data[self.rng[0]: self.rng[1] + 1])


@pytest.fixture
def make_app(monkeypatch):
    def _make(page, db_fail=False, secrets=None, **state):
        import supabase

        monkeypatch.setattr(supabase, "create_client",
                            lambda *a, **k: types.SimpleNamespace(table=lambda n: FakeQuery(n, db_fail)))
        at = AppTest.from_file(APP, default_timeout=60)
        at.secrets["SUPABASE_URL"] = "https://example.supabase.co"
        at.secrets["SUPABASE_KEY"] = "sb_publishable_test"
        for k, v in (secrets or {}).items():
            at.secrets[k] = v
        at.session_state["auth_user"] = USER
        at.session_state["page"] = page
        for k, v in state.items():
            at.session_state[k] = v
        return at.run()

    return _make


def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def test_login_page_without_session():
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["SUPABASE_URL"] = "https://example.supabase.co"
    at.secrets["SUPABASE_KEY"] = "sb_publishable_test"
    at.run()
    assert not at.exception
    assert at.title[0].value.startswith("🔐")


def login_page_with_auth(monkeypatch, sign_up=None, sign_in=None):
    import supabase

    auth = types.SimpleNamespace(sign_up=sign_up, sign_in_with_password=sign_in)
    monkeypatch.setattr(supabase, "create_client",
                        lambda *a, **k: types.SimpleNamespace(auth=auth, table=lambda n: FakeQuery(n, False)))
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["SUPABASE_URL"] = "https://example.supabase.co"
    at.secrets["SUPABASE_KEY"] = "sb_publishable_test"
    return at.run()


def fill_signup(at):
    at.text_input(key="signup_email").input("new@example.com")
    at.text_input(key="signup_password").input("password1234")
    return click(at, "登録する")


def test_signup_without_email_confirmation_logs_in(monkeypatch):
    at = login_page_with_auth(monkeypatch, sign_up=lambda creds: types.SimpleNamespace(session=object(), user=USER))
    fill_signup(at)
    assert not at.exception
    assert at.session_state["auth_user"] is USER


def test_signup_with_email_confirmation(monkeypatch):
    at = login_page_with_auth(monkeypatch, sign_up=lambda creds: types.SimpleNamespace(session=None, user=USER))
    fill_signup(at)
    assert any("確認メールを送信しました" in s.value for s in at.success)
    assert at.session_state["auth_user"] is None


def test_signup_email_not_authorized(monkeypatch):
    def refuse(creds):
        raise RuntimeError("Email address not authorized")

    at = login_page_with_auth(monkeypatch, sign_up=refuse)
    fill_signup(at)
    assert any("確認メールを送れなかった" in e.value for e in at.error)


def test_login_email_not_confirmed(monkeypatch):
    def refuse(creds):
        raise RuntimeError("Email not confirmed")

    at = login_page_with_auth(monkeypatch, sign_in=refuse)
    at.text_input(key="login_email").input("new@example.com")
    at.text_input(key="login_password").input("password1234")
    click(at, "ログイン")
    assert any("確認が済んでいません" in e.value for e in at.error)


@pytest.mark.parametrize("page", ["title", "disclaimer", "industry_select", "help"])
def test_simple_pages_render(make_app, page):
    assert not make_app(page).exception


def test_db_failure_falls_back_to_sample(make_app):
    at = make_app("company_data", db_fail=True, selected_industry="1.電機・電子機器")
    assert not at.exception
    assert any("サンプル（架空）" in w.value for w in at.warning)


def test_edinet_search_and_median(make_app):
    at = make_app("company_data", selected_industry="9.輸送用機器")
    assert not at.exception
    # 手入力社(5000万)は中央値に入らない／中央値なので外れ値に引っ張られない
    assert any("平均年収 800.0万円" in c.value for c in at.caption)
    at.text_input(key="company_search_input").input("トヨタ").run()
    click(at, "検索")
    assert at.selectbox(key="candidate_select").options == [
        "トヨタ自動車株式会社［7203］（EDINET）", "トヨタ紡織株式会社［3116］（EDINET）"]
    click(at, "この企業を業界と比較する")
    result = at.session_state["comparison_result"]
    assert result["平均年収（万）"]["judgement"].startswith("業界中央値より高い")
    assert result["売上高成長率（％）"]["judgement"].startswith("業界中央値並み")
    assert result["平均年齢（歳）"]["score"] is None  # 創業年が不明ならスコア対象外
    assert at.session_state["selected_edinet_code"] == "E00001"


def test_result_page_ai_disabled_with_placeholder_key(make_app):
    at = make_app("result", secrets={"ANTHROPIC_API_KEY": "sk-ant-..."}, selected_industry="9.輸送用機器",
                  selected_company="トヨタ自動車株式会社", selected_edinet_code="E00001")
    assert not at.exception
    assert any("AI要約は、管理者が" in c.value for c in at.caption)
    assert not any("要約する" in b.label for b in at.button)


def test_result_page_ai_summary(make_app, monkeypatch):
    import ai_summary

    calls = []
    monkeypatch.setattr(ai_summary, "summarize", lambda p, prompt, key, model: calls.append(p) or f"{p}の要約")
    at = make_app("result", secrets={"OPENAI_API_KEY": "real-looking-key", "OPENAI_MODEL": "gpt-x"},
                  selected_industry="9.輸送用機器", selected_company="トヨタ自動車株式会社",
                  selected_edinet_code="E00001")
    button = next(b for b in at.button if "要約する" in b.label)
    button.click().run()
    assert not at.exception
    assert calls == ["openai"] and at.session_state["ai_calls"] == 1
    assert any("openaiの要約" in m.value for m in at.markdown)
