# 四季報ツールを Docker で動かすための「設計図」（Dockerfile）
# この設計図から「イメージ」（アプリ入りの箱の型）を作り、イメージから「コンテナ」（実際に動く箱）を起動する。
# 上から順に1行ずつ実行され、各行の結果は「レイヤー」として保存・再利用（キャッシュ）される。

# 1. 土台：Python 3.12 が入った小さな Linux（Debian）。これを公式の置き場（Docker Hub）から取ってくる
FROM python:3.12-slim

# 2. 日本語フォント（ヘルプの図の日本語用。Streamlit Cloud の packages.txt と同じ役割）
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 3. 箱の中の作業フォルダ
WORKDIR /app

# 4. 先にライブラリだけ入れる。
#    requirements.txt が変わらない限り、次回以降はこの重い手順をキャッシュから一瞬で済ませられる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. アプリのコードを入れる（.dockerignore に書いたもの＝キーや一時ファイルは入らない）
COPY . .

# 6. 管理者（root）ではなく一般ユーザーで動かす（万一乗っ取られても被害を小さくするため）
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# 7. この箱は 8501 番の窓口（ポート）でアプリを提供する、という目印
EXPOSE 8501

# 8. 箱が元気かどうかを Docker が定期的に確認する方法
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# 9. 箱を起動したときに実行するコマンド
CMD ["streamlit", "run", "analysis02.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
