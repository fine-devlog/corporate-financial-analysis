# 企業の財務データ分析プログラム（就活生向け）

## 概要

上場企業の有価証券報告書（EDINET）から取得した実データと、会社四季報の記者コメント見出しをもとに、
企業の傾向を「同じ業界の中央値」と比べて確認できる Streamlit アプリです。

> ⚠️ 本ツールの評価スコアは機械的な計算結果であり、企業の優劣や入社の可否を判断するものではありません。

```
EDINET API ──(edinet_ingest.py：毎日 GitHub Actions)──▶ Supabase (PostgreSQL)
                                                            │  companies / company_texts / results
                                                            ▼
                                       analysis02.py（Streamlit アプリ・ログイン必須）
                                                            │（任意）
                                                            ▼
                                             ai_summary.py → Claude / OpenAI
```

| ファイル | 内容 |
|---|---|
| `analysis02.py` | Streamlit アプリ本体 |
| `edinet_ingest.py` | EDINET API から有価証券報告書（XBRL→CSV）を取得し、指標と文章を Supabase に保存 |
| `ai_summary.py` | 有報の文章の AI 要約（Claude / OpenAI 切り替え） |
| `supabase_schema.sql` | テーブル・行レベルセキュリティ（RLS）・権限の定義 |
| `tests/` | pytest によるテスト（ネットワーク不要） |

## 使い方

1. ログイン（初回は「新規登録」）
2. 利用上の注意に同意し、業界を選ぶ
3. 企業名の一部（例「トヨタ」）か証券コード（例「7203」）で検索し、業界と比較する
4. （任意）四季報の記者コメント見出しと、市場全体の見出しランキングを入力する
5. 総合評価を確認し、保存する

## 機能

- **業界内比較**：16業界ごとに、平均年収・平均年齢・平均勤続年数・営業利益率・売上高成長率・営業利益成長率・営業CFマージンを業界の中央値と比較
- **企業検索**：社名の一部・証券コードに加えて、略称（野村総研）・英語名の頭文字（NRI）・英語名（nomura）・読み仮名（のむら）でも検索できる。選んだ業界に無い企業は、どの業界のデータにあるかを案内する（EDINET のコードリストを利用。LLMは使っていない）
- **複数業界への表示**：売上の3割以上を占める事業がある企業は、その業界にも「兼業」として表示する（有報のセグメント情報から判定）
- **四季報ミニガイド**：必要な情報が会社四季報のどの欄に書いてあるかを、どの画面からでも確認できる。パソコンではサイドバー、スマホでは画面右上のボタン（小窓）で表示し、入力欄の横にも小窓を置いた
- **指標の見方**：各指標が高い・低いと何が言えるか、就活でどう使うかをヘルプにまとめた
- **四季報の見出し分析**：記者コメントの見出し語（133語の辞書）と、市場全体の見出しランキングから相対的な強さを評価
  - 見出し語と出現数は [会社四季報オンライン（東洋経済新報社）の見出し語一覧](https://shikiho.toyokeizai.net/headwords) を参考にした。スコア（-5〜+5）とカテゴリ等は生成AIの補助を受けて独自に付けたもので、同サイトの見解ではない
- **手入力**：EDINETにない企業も、四季報の数値を入力して比較できる（異常値チェック付き）
- **管理者ページ**：保存された評価結果の確認・修正・Excel出力
- **AI要約（任意・未検証）**：有報の「事業の内容」「経営方針・課題」「事業等のリスク」を就活生向けに要約（APIキーを設定した場合のみ表示）

## こだわり

- **実データを使う**：架空のサンプルではなく、金融庁 EDINET の有価証券報告書を自動で取り込む。日次で更新
- **業界の「中央値」と比べる**：急成長・赤字転落などの極端な企業に業界の基準が引っ張られないようにした。比べる企業が3社未満の指標は評価しない
- **数字の比べ方を指標ごとに変える**：年収などは「何％高いか」、利益率・成長率などは「何ポイント差か」で比べる（業界がマイナス成長のときに判定が逆転しないように）
- **年齢を「高い＝良い」としない**：平均年齢そのものは点数にせず、創業年とあわせた定着度の手がかりだけを使う
- **データを混ぜない**：業界の基準値には EDINET のデータだけを使い、利用者の手入力やサンプルは混ぜない
- **安全性**：Supabase の行レベルセキュリティで、未ログインでは読めない・一般ユーザーは EDINET データを変更できないようにした。APIキーはログに出さない

## データについて

- 出典：金融庁 EDINET の有価証券報告書（XBRL）。直近1年分を取り込み、企業ごとに最新の決算期を使用
- 業界は EDINET の「提出者業種」を16業界に対応づけ（「その他製品」等は対象外）
  - 「情報・通信業」は IT と通信が混在するため、セグメント売上と有報の「事業の内容」の文章で IT／通信を判定
  - セグメント名（英語のID）に含まれる語から各事業の業界を推定し、売上の3割以上なら兼業として表示。語による推定なので誤りが残る可能性がある
- 主力セグメント利益集中度は、有報のセグメント別営業利益から計算（セグメントが1つの企業は空欄）
- 取得できない項目：海外売上比率・創業年・来期成長率予想（四季報で確認）
- 注意：平均年収・年齢・勤続年数は提出会社（単体）の値のため、持株会社は高めに出ることがある。銀行・保険は売上の項目が特殊で空欄になりやすい
- 平均年収は、提出書類の単位の誤り（桁が10の累乗ずれているもの）を取り込み時に補正している

## セットアップ（このフォルダで作業）

### 1. Supabase
1. プロジェクトを作成し、SQL Editor で `supabase_schema.sql` を実行
2. Project Settings → API Keys で次の値を控える
   - Project URL
   - **Publishable key**（`sb_publishable_...`）：アプリ用
   - **Secret key**（`sb_secret_...`）：取り込みスクリプト専用。アプリや Git には絶対に入れない
3. （公開する場合）Authentication → URL Configuration の Site URL を公開したアプリのURLにする
4. **新規登録のメール確認**：Supabase 標準のメール送信は、プロジェクトのチームメンバー宛てにしか送れない（1時間に2通まで）。
   - 確認メールなしで運用する：Authentication → Sign In / Providers → Email の「Confirm email」をオフ（登録後すぐログインできる）
   - 確認メールを使う：Authentication → Emails → SMTP Settings で独自のメールサーバーを設定する

### 2. EDINET API キー
[EDINET API キー発行画面](https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1) から取得（ブラウザのポップアップ許可が必要）

### 3. 設定ファイル（どちらも Git には入らない）
```bash
cd dashboard_app
cp .env.example .env                                         # EDINET_API_KEY / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # SUPABASE_URL / SUPABASE_KEY / ADMIN_PASSCODE
```

### 4. 実行
```bash
pip install -r requirements.txt

# お試し（DBに書かない）
python edinet_ingest.py --start 2026-06-26 --end 2026-06-26 --dry-run --limit 5
# 直近1年分を取り込む（2時間程度）
python edinet_ingest.py --start 2025-11-18 --end 2026-11-18
# アプリ起動
streamlit run analysis02.py
```

`edinet_ingest.py` のオプション：`--force`（取り込み済みも再取得）、`--inspect 書類ID`（XBRLの要素と抽出結果を表示）

## 自動取り込み（GitHub Actions）

リポジトリ直下の `.github/workflows/dashboard_app-edinet-ingest.yml` が毎日 7:00（日本時間）に直近14日分を取り込みます。
リポジトリの Settings → Secrets and variables → Actions に `EDINET_API_KEY` / `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` を登録してください（未登録の間は何もせず終了します）。

## 公開（Streamlit Community Cloud）

メインファイルに `dashboard_app/analysis02.py` を指定し、Secrets に `.streamlit/secrets.toml` と同じ内容を設定します。
日本語フォントはリポジトリ直下の `packages.txt` で入れています。

## Docker で動かす

`Dockerfile` と `compose.yaml` を用意しています。キー（`.env`・`secrets.toml`）はイメージに入れず、起動時に渡します。

```bash
docker compose up -d --build                  # http://localhost:8502 で起動
docker compose run --rm ingest --dry-run --limit 2   # 取り込みスクリプトを1回だけ実行
docker compose down
```

仕組みを体験しながら学ぶ手順は [DOCKER_HANDSON.md](DOCKER_HANDSON.md) にまとめています。

## テスト

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

EDINET API・Supabase・AI API はすべて偽物に差し替えてテストしています。`dashboard_app/` を変更して push すると GitHub Actions でも実行されます。

## 開発状況

| 項目 | 状態 |
|---|---|
| EDINET 取り込み・業界比較・検索・ログイン・結果保存 | 実データ（Supabase）で動作確認済み |
| 行レベルセキュリティ | テストユーザーで動作確認済み |
| AI要約 | 実装済み・実際のAPIキーでの要約は未検証（任意機能） |
| 上場していない企業の実在確認（gBizINFO） | 未実装 |
| ヘルプの解説動画 | 未作成 |

## 参考資料・出典

**データ**
- [EDINET（金融庁）](https://disclosure2.edinet-fsa.go.jp/)：有価証券報告書のデータ
  - [EDINET API 仕様書（Version 2）](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf)
  - [EDINET コードリスト](https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip)：上場区分・業種・英語名・読み仮名（企業検索の別名に利用）
  - [EDINET タクソノミ（jpcrp_cor）](https://disclosure2.edinet-fsa.go.jp/taxonomy/jpcrp/2025-11-01/jpcrp_cor_2025-11-01.xsd)：取り込みに使う XBRL の要素名の確認
- [会社四季報オンライン（東洋経済新報社）の見出し語一覧](https://shikiho.toyokeizai.net/headwords)：見出し辞書の見出し語と出現数（スコア・カテゴリは独自に付与）

**四季報の欄の名前・書かれ方（ミニガイド・ヘルプの内容）**
- [会社四季報の見方（auカブコム証券）](https://kabu.com/investment/market/quarterly/guide.html)
- [会社四季報の読み方（マネックス証券）](https://info.monex.co.jp/help/insight/shikihou02.html)

**開発に使った主な技術のドキュメント**
- [Streamlit](https://docs.streamlit.io/)、[Supabase](https://supabase.com/docs)（認証・行レベルセキュリティ）、[Streamlit Community Cloud の依存ファイル](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)

※ 指標の見方（ヘルプ）の文章は、上記の資料と一般的な財務指標の考え方をもとに、就活生向けに書いたもので、特定の資料からの引用ではありません。
