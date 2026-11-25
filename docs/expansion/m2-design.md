# M2 詳細設計: ゲーミフィケーション拡張

M1 (`m1-design.md`) の XP 台帳・クエスト基盤の上に積む。報酬は M1 と同じく、すべて `GamificationService.award()` (冪等キー) 経由で付与する。

## 1. スコープ

| 機能 | この PR | 備考 |
|---|---|---|
| バッジ / 実績 | ✅ | 15 種。獲得ごとに 🪙10 |
| ウィークリークエスト | ✅ | 3 種。週は月曜始まり (APP_TIMEZONE) |
| ステージマップ (スキルツリーの可視化) | ✅ | `/map` |
| 実力テストによる飛び級 | ✅ | |
| ボス戦 | ✅ | |
| ストリークフリーズ (コインで購入) | ✅ | 課金なし |
| オリジナルマスコット「ピコ」 | ✅ | SVG、5 つの表情 |
| ダークモード | ❌ 別 Issue | 全画面の配色を見直す作業になるため分離 |
| フレンド / リーグ | ❌ 別 Issue | 公開範囲・ブロック・通報などプライバシー設計が先に必要 |

## 2. DB (migration `0003_gamification_m2`)

```
user_stats          + streak_freezes int
user_badges         (user_id, badge_id) PK, earned_at
course_achievements (user_id, course_id, kind) PK, achieved_at
                    kind = placement_passed | boss_defeated
challenge_sessions  id, user_id, course_id, mode(placement|boss), question_ids JSONB,
                    status(open|passed|failed), correct_count, activity_date,
                    created_at, expires_at, completed_at
```

## 3. コースのクリア判定 (M1 からの変更点)

`is_cleared(course)` は、次のどちらかを満たすと真になる。

- 問題の 70% 以上に正解している (M1 と同じ)
- `placement_passed` を持っている

解放判定 (`is_unlocked`) は「前提コースがすべて `is_cleared`」で M1 と変わらない。判定ロジックは `catalog_service.ProgressView` に集約した。

## 4. チャレンジ (実力テスト / ボス戦)

| | 実力テスト | ボス戦 |
|---|---|---|
| 受験条件 | 未クリアのコース (ロック中でも可) | 解放済みかつクリア済み |
| 回数制限 | 同じコースは 1 日 1 回 | なし |
| 出題 | 自動採点できる問題 (text 以外) からランダムに最大 5 問 | 同じく最大 8 問 |
| 制限時間 | 1 問 90 秒 | 1 問 60 秒 |
| 合格 | 80% 以上 | 80% 以上 |
| 合格時 | 対象コースと全祖先コースに `placement_passed` を付ける。+30 XP (初回のみ) | `boss_defeated` (👑) を付ける。+50 XP +🪙20 (初回のみ) |

- 自動採点できる問題が 2 問未満のコースはチャレンジ対象外 (`can_take_placement` / `can_challenge_boss` が false)。
- 出題はサーバーが決めて保存し、提出時にその問題だけを採点する。正解は提出後にのみ返す。
- 時間切れ (`expires_at` + 猶予 15 秒) で提出した場合は不合格。答え合わせは返す。
- チャレンジ内の回答も `question_attempts` に記録する (解決済み判定・クエストに反映)。チャレンジ内の問題ごとの初回正解 XP は付与しない (二重取り防止)。
- ロック順: `user_stats` → `challenge_sessions` → `xp_events`。

## 5. ストリークフリーズ

- ショップで 🪙50。最大 2 個まで所持できる。購入は台帳に `reason=shop`、`coins=-50` として記録する。
- 休んだ日数 (= 最終学習日から今日までの空白日数) が所持数以下なら、次に学習したときにその数だけ消費してストリークを継続する。
- 表示上のストリークも、所持数で守れる間は継続中として扱う。

## 6. バッジ

`app/domain/gamification.py` の `BADGES` にコード定義する。学習行動の後 (`after_activity`) に「クエスト → バッジ」の順で判定する。

指標:
- 解いた問題数
- 現在のストリーク
- レベル
- 完走したコース数
- 倒したボスの数
- 実力テスト合格
- クエスト達成回数

## 7. API

| Method | Path | 説明 |
|---|---|---|
| POST | `/api/v1/challenges` | `{course_id, mode}` で開始し、問題を返す (正解なし) |
| GET | `/api/v1/challenges/{id}` | 受験中のチャレンジを取得 (リロード用) |
| POST | `/api/v1/challenges/{id}/submit` | `{answers: {question_id: AnswerRequest}}` で採点・報酬付与 |
| GET | `/api/v1/gamification/badges` | 全バッジと獲得日時 |
| POST | `/api/v1/gamification/shop/streak-freeze` | ストリークフリーズを購入 |

`GET /gamification/me` には `streak_freezes` と `weekly_quests` を追加した。回答・チャレンジの `reward` には `new_badges` を追加した。

## 8. フロントエンド

- `/map`: ステージマップ。前提コースからの最長距離で段を決め、同じ段の中は親の平均 x 座標順に並べる (`lib/stageMap.ts`)。ノードはキーボードで操作できる。
- `/achievements`: バッジ一覧とショップ。
- `/challenges/:id`: 受験画面 (タイマー・時間切れで自動提出)。結果画面にマスコット・解放されたコース・答え合わせを表示する。
- コース詳細: 「実力テストを受ける」「ボスに挑む」ボタン。ロック中でも飛び級できるコースはカードからたどれる。
- ダッシュボード: マスコットの一言、ウィークリークエスト、🧊 フリーズ数。
