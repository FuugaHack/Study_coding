# コード実行ランナー。docker-compose.yml の runner サービスの隔離設定と組み合わせて使う。
FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

# サーバー用の依存は venv に入れる (ユーザーコードは /usr/bin/python3 -I で実行し、venv を見せない)
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "pytest>=8" "httpx>=0.27"

WORKDIR /srv
COPY runner ./runner
COPY tests ./tests
COPY pytest.ini ./

ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1

# サーバーは root で起動するが、ユーザーコードは実行ごとに専用 uid へ setuid する
# (必要なケーパビリティは compose 側で SETUID/SETGID/CHOWN/KILL/DAC_OVERRIDE/FOWNER のみに絞る)
# ソケットの権限は runner/main.py で絞る (0660・グループは RUNNER_SOCKET_GID)
CMD ["python", "-m", "runner.main"]
