# 四季報ツールで Docker を体験する（ハンズオン）

自分で作った四季報ツールを Docker で動かしながら、Docker の仕組みをなんとなくつかむための手順です。
所要時間は30分ほど。コマンドはすべて **PowerShell** で打ちます。

---

## 0. まず言葉だけ覚える

| 言葉 | たとえ | このツールでは |
|---|---|---|
| **Dockerfile** | 料理のレシピ | `Dockerfile`（Python を入れて、ライブラリを入れて、コードを入れて…という手順書） |
| **イメージ** | レシピどおりに作った「冷凍食品」。何個でも同じものを温められる | `shikiho-tool:latest`（アプリ一式が入った箱の型） |
| **コンテナ** | 冷凍食品を温めて、実際に食べている状態 | 実際に動いているアプリ（止めたり消したりできる） |
| **ポート** | 箱の窓口の番号 | 箱の中の 8501番 を、自分のPCの 8502番 につなぐ |
| **ボリューム** | 箱の外から物を貸し出す | `secrets.toml` を「読み取り専用」で貸す（箱には入れない） |
| **Compose** | 複数の箱の起動方法をまとめたメモ | `compose.yaml`（アプリ本体と取り込みスクリプトの2つ） |

**なぜ Docker を使うの？**
「自分のPCでは動くのに、他の人のPCやサーバーでは動かない」をなくすため。
Python のバージョンやライブラリまで含めて箱ごと渡すので、どこでも同じように動きます。
（Streamlit Community Cloud も、裏側では似たような仕組みでアプリを動かしています）

---

## 1. 準備
1. **Docker Desktop** を起動する（タスクバーにクジラのアイコンが出ればOK）
2. PowerShell で、このリポジトリの `dashboard_app` フォルダに移動する
   ```powershell
   cd "（リポジトリを置いた場所）\corporate-financial-analysis\dashboard_app"
   ```
   （エクスプローラーで `dashboard_app` を開き、アドレスバーに `powershell` と打って Enter でも開ける）

---

## 2. イメージを作る（レシピから冷凍食品を作る）
```powershell
docker compose build
```
- `Dockerfile` の手順が上から順に実行されます。1行ごとの結果は **レイヤー** として保存されます。
- 作ったイメージを確認：
  ```powershell
  docker image ls shikiho-tool
  ```
  サイズは約1.2GB（Python・ライブラリ・日本語フォントの分）。

### 🔍 実験：キャッシュ（作り置き）を体験する
1. `analysis02.py` のどこかにコメント行（`# テスト`）を1行足して保存
2. もう一度 `docker compose build`
3. ライブラリを入れる重い手順に **`CACHED`** と出て、一瞬で終わるはず

→ `Dockerfile` で「ライブラリを入れる手順」を「コードを入れる手順」より前に書いているから。
コードを変えても、その前の手順は作り置きをそのまま使える。**順番が速さを決める**。
（終わったら足したコメント行は消しておく）

---

## 3. コンテナを起動する（冷凍食品を温める）
```powershell
docker compose up -d
```
- `-d` は「裏で動かしておく」という意味
- ブラウザで **http://localhost:8502** を開くと、いつもの四季報ツールが出る

### 🔍 動いている箱を見てみる
```powershell
docker compose ps          # 動いている箱の一覧（STATUS に healthy と出れば元気）
docker compose logs -f app # アプリのログを流し見る（止めるのは Ctrl + C）
```

---

## 4. 箱の中に入ってみる
```powershell
docker compose exec app sh
```
箱の中のコマンド画面に入ります。次を打ってみてください。
```sh
whoami           # appuser と出る（管理者ではない一般ユーザーで動かしている）
ls -A            # アプリのファイル。.env は無い
ls .streamlit    # secrets.toml は「貸している」だけなので見える
cat /etc/os-release   # 中身は Windows ではなく Linux（Debian）
exit             # 箱から出る
```

**ポイント：キーはイメージに入っていない**
- `.dockerignore` で `.env` と `secrets.toml` をイメージに入れないようにしている
- イメージは人に渡したり公開したりできるので、中にキーがあると漏れてしまう
- キーは **起動するときに外から渡す**（`compose.yaml` の `volumes:` と `env_file:`）

---

## 5. 止める・消す・また起動する
```powershell
docker compose stop    # 止める（http://localhost:8502 が開けなくなる）
docker compose start   # また動かす
docker compose down    # 箱を消す（イメージは残るので、up ですぐ作り直せる）
```
→ 箱（コンテナ）は気軽に作って捨てるもの。イメージさえあれば何度でも同じ状態で起動できる。

---

## 6. 1回だけ動いて終わる箱：取り込みスクリプト
同じイメージを使って、EDINET の取り込みスクリプトも動かせます（DBには書かない `--dry-run`）。
```powershell
docker compose run --rm ingest --start 2026-06-26 --end 2026-06-26 --dry-run --limit 2
```
- `run` は「その場で箱を作って1回だけ実行」、`--rm` は「終わったら箱を自動で消す」
- アプリ本体と取り込みスクリプトが **同じイメージ（同じ環境）** で動いている

---

## 7. 片付け（ディスクを空けたいとき）
```powershell
docker compose down
docker image rm shikiho-tool
```

---

## 今回わかったこと（まとめ）
- **Dockerfile → イメージ → コンテナ** の順に作る
- イメージは **レイヤーの積み重ね**。変わりにくいものを先に書くと、作り直しが速い
- コンテナは使い捨て。**同じイメージからなら、どこでも同じように動く**
- **キーはイメージに入れず、起動時に外から渡す**
- 1つのイメージで、アプリ（ずっと動く）とスクリプト（1回で終わる）の両方を動かせる

## 関係するファイル
| ファイル | 役割 |
|---|---|
| `Dockerfile` | イメージの作り方（各行にコメントで説明あり） |
| `.dockerignore` | イメージに入れないもの（キー・テストなど） |
| `compose.yaml` | 起動のしかた（ポート・キーの渡し方・サービスの一覧） |
