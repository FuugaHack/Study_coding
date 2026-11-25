"""ランナーの起動。UNIX ソケットを自前で作り、権限を絞ってから uvicorn に渡す。

ソケットは 0660・所有グループ RUNNER_SOCKET_GID (backend 側のプロセスのグループ)。
ユーザーコードを実行するスロット uid は所有者でもグループでもないため、接続できない。
"""
import os
import socket

import uvicorn

SOCKET_PATH = os.environ.get("RUNNER_SOCKET", "/sock/runner.sock")
SOCKET_GID = int(os.environ.get("RUNNER_SOCKET_GID", "0"))


def main() -> None:
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)  # 作成時点から 0600 (chmod までの隙をなくす)
    try:
        sock.bind(SOCKET_PATH)
    finally:
        os.umask(old)
    os.chown(SOCKET_PATH, 0, SOCKET_GID)
    os.chmod(SOCKET_PATH, 0o660)
    sock.listen(64)
    uvicorn.run("runner.app:app", fd=sock.fileno(), log_level="info")


if __name__ == "__main__":
    main()
