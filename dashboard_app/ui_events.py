"""画面操作（表・グラフのクリック、スクロール）の補助。Streamlit に依存しない部分だけを置く（テストしやすくするため）。"""
from __future__ import annotations

CHART_PICK_PARAM = "pick"    # グラフの棒をクリックしたときの選択の名前
CHART_HOVER_PARAM = "hover"  # カーソルを合わせた棒の色を変えるための選択の名前


def clicked_table_row(state) -> int | None:
    """企業データ一覧でクリックされた行の位置（セル選択でも行選択でも）。"""
    selection = _selection(state)
    cells = selection.get("cells") or []
    if cells:
        return int(cells[0][0])
    rows = selection.get("rows") or []
    return int(rows[0]) if rows else None


def clicked_chart_company(state, field: str = "企業名") -> str | None:
    """指標比較グラフでクリックされた棒の企業名。"""
    picked = _selection(state).get(CHART_PICK_PARAM) or []
    if isinstance(picked, dict):  # 念のため（バージョンによって形が違っても読めるように）
        picked = [picked]
    for point in picked:
        name = point.get(field) if isinstance(point, dict) else None
        if name:
            return str(name)
    return None


def _selection(state) -> dict:
    if not state:
        return {}
    try:
        selection = state.selection
    except AttributeError:
        selection = state.get("selection", {}) if isinstance(state, dict) else {}
    try:
        return dict(selection or {})
    except (TypeError, ValueError):
        return {}


# --------------------------------------------------------------------------
# スクロール（ページの中で使う JavaScript）
# --------------------------------------------------------------------------
# 【修正】ブラウザ標準の smooth スクロールは速すぎて「ページが動いた」ことが分かりにくいため、
# 距離に応じて 0.7〜1.4 秒かけて、ゆっくり動き出してゆっくり止まる（ease-in-out）動きにした。
# 「動きを減らす」設定（prefers-reduced-motion）の利用者には、アニメーションせずに移動する。
SCROLL_HELPERS_JS = """
(function () {
  if (window.shikihoScrollToElement) return;
  const candidates = () => [
    document.querySelector('[data-testid="stMain"]'),
    document.querySelector('[data-testid="stAppViewContainer"]'),
    document.scrollingElement,
  ].filter(Boolean);
  window.shikihoScroller = () => {
    for (const el of candidates()) {
      const style = el === document.scrollingElement ? null : getComputedStyle(el);
      const scrollable = el.scrollHeight > el.clientHeight + 1 &&
        (!style || ["auto", "scroll"].includes(style.overflowY));
      if (scrollable) return el;
    }
    return document.scrollingElement;
  };
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  window.shikihoSmoothScrollTo = (targetY) => {
    const el = window.shikihoScroller();
    const startY = el.scrollTop;
    const distance = Math.max(0, targetY) - startY;
    if (Math.abs(distance) < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { el.scrollTop = startY + distance; return; }
    const duration = Math.min(1400, Math.max(700, 500 + Math.abs(distance) * 0.35));
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      el.scrollTop = startY + distance * ease(t);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  window.shikihoScrollToElement = (id) => {
    const target = document.getElementById(id);
    if (!target) return false;
    const el = window.shikihoScroller();
    const top = el === document.scrollingElement ? 0 : el.getBoundingClientRect().top;
    window.shikihoSmoothScrollTo(el.scrollTop + target.getBoundingClientRect().top - top - 16);
    return true;
  };
})();
"""

BACK_TO_TOP_JS = """
(function () {
  if (document.getElementById("shikiho-to-top")) return;
  const btn = document.createElement("button");
  btn.id = "shikiho-to-top";
  btn.type = "button";
  btn.textContent = "↑";
  btn.title = "ページの一番上へ";
  btn.setAttribute("aria-label", "ページの一番上へ");
  Object.assign(btn.style, {
    position: "fixed", right: "20px", bottom: "24px", zIndex: "999999",
    width: "48px", height: "48px", borderRadius: "50%", border: "none",
    background: "#4C72B0", color: "#ffffff", fontSize: "22px", cursor: "pointer",
    boxShadow: "0 2px 8px rgba(0,0,0,0.3)", display: "none",
  });
  btn.addEventListener("click", () => window.shikihoSmoothScrollTo(0));
  document.body.appendChild(btn);
  setInterval(() => {
    const el = window.shikihoScroller && window.shikihoScroller();
    btn.style.display = el && el.scrollTop > 400 ? "block" : "none";
  }, 300);
})();
"""


def scroll_to_element_js(element_id: str, nonce: str) -> str:
    """その要素までゆっくりスクロールするスクリプト（nonce は毎回違う値にして確実に実行させる）。"""
    return f"""
// {nonce}
(function () {{
  let tries = 0;
  const go = () => {{
    if (window.shikihoScrollToElement && window.shikihoScrollToElement("{element_id}")) return;
    if (tries++ < 30) setTimeout(go, 100);
  }};
  // 比較結果などが描かれてページの高さが落ち着いてから動かす（途中でカクッと跳ねないように）
  setTimeout(go, 400);
}})();
"""
