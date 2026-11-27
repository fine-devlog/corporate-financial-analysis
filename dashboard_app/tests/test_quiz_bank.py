"""quiz_bank.py（四季報クイズの問題と出題の選び方）のテスト。"""
import random

import pytest

import quiz_bank as qb


def test_question_ids_are_unique_and_answers_valid():
    ids = [q["id"] for q in qb.QUESTIONS]
    assert len(ids) == len(set(ids))
    for q in qb.QUESTIONS:
        assert q["pattern"] in qb.PATTERNS
        assert q["explain"] and q["where"] and q["tag"]
        if q["type"] == "ox":
            assert isinstance(q["answer"], bool)
        elif q["type"] == "calc":
            assert isinstance(q["answer"], float)
        else:
            assert 0 <= q["answer"] < len(q["options"])


def test_every_pattern_has_enough_questions():
    for key in qb.PATTERNS:
        n = sum(1 for q in qb.QUESTIONS if q["pattern"] == key)
        assert n >= (8 if key == "H" else 6), key


def test_calc_answers_match_givens():
    """計算ドリルの答えが、問題の数字から本当に計算できること。"""
    def num(s):
        return float(s.replace(",", ""))

    for q in (q for q in qb.QUESTIONS if q["type"] == "calc"):
        a, b = (num(v) for _, v in q["givens"])
        if "成長率" in q["tag"]:
            expected = (a - b) / b * 100
        elif q["tag"] == "営業利益率":
            expected = b / a * 100
        else:  # 営業CFマージン：営業CF ÷ 売上高
            expected = a / b * 100
        assert round(expected, 1) == q["answer"], q["id"]


@pytest.mark.parametrize("answer, ok", [(8.0, True), (8.04, True), ("8", True), (7.8, False), (None, False), ("abc", False)])
def test_check_answer_calc(answer, ok):
    assert qb.check_answer(qb.BY_ID["F01"], answer) is ok


def test_check_answer_ox_and_choice():
    assert qb.check_answer(qb.BY_ID["D01"], False) and not qb.check_answer(qb.BY_ID["D01"], True)
    assert qb.check_answer(qb.BY_ID["A01"], 0) and not qb.check_answer(qb.BY_ID["A01"], 1)


def history(*pairs):
    return [{"question_id": i, "correct": c} for i, c in pairs]


def test_latest_result_wins():
    h = history(("A01", False), ("A01", True), ("A02", True), ("A02", False))
    assert qb.latest_results(h) == {"A01": True, "A02": False}
    assert qb.wrong_question_ids(h) == ["A02"]
    s = qb.summarize(h)
    assert (s["answered"], s["correct"], s["wrong"], s["attempts"]) == (2, 1, 1, 4)


def test_pick_prefers_unseen_then_wrong():
    a_ids = [q["id"] for q in qb.QUESTIONS if q["pattern"] == "A"]
    # 2問だけ残して解いた状態：1問は未解答、1問はまちがい、残りは正解
    h = history(*[(i, True) for i in a_ids[2:]], (a_ids[1], False))
    picked = qb.pick_questions(h, "A", n=3, rng=random.Random(0))
    assert picked[0] == a_ids[0]            # 未解答が最初
    assert picked[1] == a_ids[1]            # 次に、まちがえた問題
    assert picked[2] in a_ids[2:]


def test_pick_mixed_excludes_case_and_varies():
    picks = {tuple(qb.pick_questions([], qb.MIXED, n=5, rng=random.Random(seed))) for seed in range(5)}
    assert len(picks) > 1                                              # 毎回ちがう問題
    assert all(qb.BY_ID[i]["pattern"] != "H" for p in picks for i in p)


def test_pick_wrong_only():
    assert qb.pick_questions(history(("A01", True), ("D03", False)), qb.WRONG) == ["D03"]
    assert qb.pick_questions([], qb.WRONG) == []


def test_pick_case_keeps_order_and_rotates():
    first = qb.pick_questions([], "H", rng=random.Random(1))
    case = first[0].split("-")[0]
    assert first == [f"{case}-{i}" for i in range(1, 5)]
    # その社を解き終えたら、次はもう一方の社が出る
    second = qb.pick_questions(history(*[(i, True) for i in first]), "H", rng=random.Random(1))
    assert second[0].split("-")[0] != case
