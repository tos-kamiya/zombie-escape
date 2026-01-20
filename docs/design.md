# Zombie Escape 設計メモ

この文書は、`zombie-escape` の主要な構造・データ・関数の関係を素早く把握するための設計メモです。
実装詳細は各モジュールのコメントや関数本体を参照してください。

## 1. モジュール構成の概要

- `src/zombie_escape/zombie_escape.py`
  - エントリポイント。CLI引数の解析、`pygame` 初期化、画面遷移ループを担当。
- `src/zombie_escape/screens/*.py`
  - `title`, `settings`, `gameplay`, `game_over` の各画面。
  - `screens/__init__.py` に画面遷移と表示ユーティリティ。
- `src/zombie_escape/gameplay/*.py`
  - ゲームロジックの分割モジュール。初期化、スポーン、移動、当たり判定、勝敗条件など。
- `src/zombie_escape/entities.py`
  - `pygame.sprite.Sprite` を使ったゲーム内エンティティ定義と衝突判定補助。
- `src/zombie_escape/models.py`
  - 進行状態やステージ情報のデータ構造（`dataclass`）。
- `src/zombie_escape/stage_constants.py`
  - ステージ構成とデフォルト設定の一覧。
- `src/zombie_escape/render.py`
  - 描画パイプライン（床/壁/霧/足跡/HUD/ヒント矢印など）。
- `src/zombie_escape/level_blueprints.py`
  - マップのセル配置生成（外周・出口・内部壁・スポーン候補）。
- `src/zombie_escape/config.py`
  - 設定のデフォルト値、保存/読込。
- `src/zombie_escape/progress.py`
  - ステージクリア回数の保存/読込。
- `src/zombie_escape/rng.py`
  - 再現性のある乱数生成（MT19937）。
- `src/zombie_escape/colors.py`
  - 環境パレットと基本色定義。
- `src/zombie_escape/render_assets.py`, `render_constants.py`
  - 描画系アセットと定数の集約（`render_constants.py` にレンダリング用定数/データ構造、`render_assets.py` に描画関数）。
- `src/zombie_escape/level_constants.py`, `screen_constants.py`, `gameplay_constants.py`
  - マップ・画面・ゲームプレイの各種パラメータ。

## 2. 画面遷移とゲームループ

- `ScreenID` は `TITLE`, `SETTINGS`, `GAMEPLAY`, `GAME_OVER`, `EXIT` の5種。
- `zombie_escape.main()` が `ScreenTransition` を受け取りながら画面遷移を管理。
- ゲームプレイ本体は `screens/gameplay.py:gameplay_screen()`。
  - ここで `gameplay/state.py:initialize_game_state()` -> `gameplay/layout.py:generate_level_from_blueprint()` -> 各種スポーン -> メインループへ。

## 3. 主要データ構造

### 3.1 進行状態 (models.ProgressState)

`ProgressState` はプレイ中の状態変数を集約する `dataclass`。

- 勝敗・ゲーム終了関連: `game_over`, `game_won`, `game_over_message`, `game_over_at`
- 進行演出: `footprints`, `last_footprint_pos`, `elapsed_play_ms`
- アイテム状態: `has_fuel`, `flashlight_count`
- ヒント/メッセージ: `hint_expires_at`, `hint_target_type`, `fuel_message_until`, `survivor_messages`
- ステージ特殊処理: `buddy_rescued`, `buddy_onboard`, `survivors_onboard`, `survivors_rescued`, `survivor_capacity`
- サバイバル用: `survival_elapsed_ms`, `survival_goal_ms`, `dawn_ready`, `dawn_prompt_at`, `dawn_carbonized`
- 乱数/デバッグ: `seed`, `debug_mode`, `time_accel_active`

### 3.2 ゲーム状態 (models.GameData)

- `state`: `ProgressState`
- `groups`: `Groups`（Sprite Groupの集合）
- `camera`: `Camera`
- `layout`: `LevelLayout`（外周/内側/外側セルなど）
- `fog`: 霧描画用のキャッシュ辞書
- `stage`: `Stage`（ステージ定義）
- `cell_size`, `level_width`, `level_height`: ステージ別のタイルサイズに応じたワールド寸法
- `fuel`, `flashlights`, `player`, `car`, `waiting_cars` など

### 3.3 ステージ定義 (models.Stage)

`Stage` はステージ属性を保持する `dataclass`。

- プレイ特性: `requires_fuel`, `buddy_required_count`, `rescue_stage`, `survival_stage`
- スポーン/難易度: `spawn_interval_ms`, `initial_interior_spawn_rate`
- 内外スポーン比率: `exterior_spawn_weight`, `interior_spawn_weight`
- サバイバル設定: `survival_goal_ms`, `fuel_spawn_count`
- 待機車両: `waiting_car_target_count`（ステージ別の待機車両数の目安）
- 変種移動ルーチン: `zombie_normal_ratio`（通常移動の出現率）
- 変種移動ルーチン: `zombie_tracker_ratio`（足跡追跡型の出現率）
- 変種移動ルーチン: `zombie_wall_follower_ratio`（壁沿い巡回型の出現率）
- エイジング速度: `zombie_aging_duration_frames`（値が大きいほど老化が遅い）
- 壁生成アルゴリズム: `wall_algorithm` ("default", "empty", "grid_wire")
- タイルサイズ: `tile_size`（ステージごとのワールド縮尺）
- グリッドサイズ: `grid_cols`, `grid_rows`（タイル数。デフォルトは `level_constants.py` の値）

### 3.4 レベルレイアウト (models.LevelLayout)

- `outer_rect`, `inner_rect`, `outside_rects`, `walkable_cells`, `outer_wall_cells` を保持。

### 3.5 スプライト群 (models.Groups)

- `all_sprites` (`LayeredUpdates`) と `wall_group`, `zombie_group`, `survivor_group` を保持。

### 3.6 エンティティ (entities.py)

- `Wall`: 内壁。体力を持ち、破壊時に `on_destroy` を発火。
- `SteelBeam`: 簡易な強化障害物。
- `Camera`: 画面スクロール用の矩形管理。
- `Player`, `Zombie`, `Car`, `Survivor`（`is_buddy` フラグで相棒を表現）
- `FuelCan`, `Flashlight`（収集アイテム）

相棒 (`is_buddy=True`) は一定距離内で追従を開始し、車に乗った数と脱出時の救出数で管理する。
一般 `Survivor` は画面外でゾンビに接触した場合はリスポーンする。

補助関数:

- `circle_rect_collision`, `circle_polygon_collision`, `rect_polygon_collision`
- `spritecollide_walls`, `spritecollideany_walls` など

## 3.7 ゾンビ移動戦略

ゾンビの移動は `MovementStrategy`（`entities.py` 内の関数群）として切り出し、`Zombie.update()` から呼び出す。
個体ごとの戦略は `Zombie.movement_strategy` に保持され、生成時に `tracker` フラグに応じて設定される。

- 通常移動 (`zombie_normal_movement`)
  - 視界範囲 `ZOMBIE_SIGHT_RANGE` でプレイヤーを検知したら直進追尾。
  - 視界外は `zombie_wander_move` で徘徊移動。
- 追跡移動 (`zombie_tracker_movement`)
  - 視界範囲 `ZOMBIE_TRACKER_SIGHT_RANGE` でプレイヤーを検知したら直進追尾。
  - 視界外は足跡 (`footprints`) から `ZOMBIE_TRACKER_SCENT_RADIUS` 内の最新位置を追跡し、見つからない場合は徘徊。
- 壁沿い移動 (`zombie_wall_follow_movement`)
  - 視界範囲 `ZOMBIE_TRACKER_SIGHT_RANGE` でプレイヤーを検知したら直進追尾。
  - 視界外は前方と±45度のプローブで壁までの距離を測り、目標ギャップ(約4px)を維持するよう旋回する。
  - 壁が遠い場合は壁側へ寄り、近すぎる場合は離れる方向へ補正する。
  - 一定時間壁を検知できなければ徘徊に切り替える。右手/左手の選択は個体ごとにランダム。

補助要素:

- `zombie_wander_move` はランダム角度・壁際の回避挙動で歩行を維持。
- `Zombie.update()` 側で壁衝突・近接回避・外周逸脱時の補正を処理。
- `create_zombie()` で `stage.zombie_tracker_ratio` を参照し追跡型の出現率を決定。

## 4. ゲームロジックの主要関数 (gameplay/*.py)

### 初期化・生成

- `initialize_game_state(config, stage)` (`gameplay/state.py`)
  - `GameData` の基本セットアップ。
- `generate_level_from_blueprint(game_data, config)` (`gameplay/layout.py`)
  - `level_blueprints` から壁・歩行セル・外部セルを作成。
- `setup_player_and_cars(game_data, layout_data, car_count)` (`gameplay/spawn.py`)
  - プレイヤーと待機車両を配置。
- `spawn_initial_zombies(game_data, player, layout_data, config)` (`gameplay/spawn.py`)
  - 初期ゾンビを内側エリア中心に配置。

### スポーン

- `spawn_nearby_zombie`, `spawn_exterior_zombie`, `spawn_weighted_zombie` (`gameplay/spawn.py`)
  - 画面外スポーン/外周スポーン/重み付けスポーン。
- `spawn_survivors` / `place_buddies` / `place_fuel_can` / `place_flashlights` (`gameplay/spawn.py`)
  - ステージ別のアイテムやNPCを配置。

### 更新

- `process_player_input(keys, player, car)` (`gameplay/movement.py`)
  - プレイヤー/車両の入力速度を決定。
- `update_entities(game_data, player_dx, player_dy, car_dx, car_dy, config)` (`gameplay/movement.py`)
  - 移動、カメラ更新、ゾンビAI、サバイバー移動など。
  - 壁セルに隣接するタイル端に近い場合、移動ベクトルをタイル中心へ3%だけ補正する（全キャラ共通）。
- `check_interactions(game_data, config)` (`gameplay/interactions.py`)
  - アイテム収集、車両/救助/敗北判定などの相互作用。
- `update_footprints(game_data, config)` (`gameplay/footprints.py`)
  - 足跡を記録し寿命で削除（表示は設定で制御し、記録は常時行う）。
- `update_survival_timer(game_data, dt_ms)` (`gameplay/state.py`)
  - サバイバル用の時間管理と夜明け切り替え。

### 速度/容量補助

- `calculate_car_speed_for_passengers`, `apply_passenger_speed_penalty`
  - 乗車人数に応じた速度低下。
- `increase_survivor_capacity`, `drop_survivors_from_car` など

## 5. 描画パイプライン (render.py)

- `draw(...)` が描画の中心。
  1. 環境色で背景塗りつぶし
  2. プレイ領域・床パターン描画
  3. 足跡のフェード描画
  4. Sprite 群を `Camera` でオフセットして描画
  4.5 追跡型/壁沿いゾンビには常時識別用の輪郭を描画
  5. ヒント矢印 (`_draw_hint_arrow`)
  6. 霧 (`fog_surfaces` + `FOG_RINGS`)
  7. HUD: 目的/メッセージ/ステータスバー

- `draw_status_bar()`
  - 設定フラグやステージ番号、シード値を表示。

- `draw_level_overview()`
  - `game_over` 画面用のレベル縮小図。

## 5.1 ウィンドウ/最大化

- F キーでウィンドウの最大化/復帰をトグル（起動時は常にウィンドウ）。
- 論理解像度は 400x300 のまま、OSの最大化サイズに合わせて拡大描画する。

## 6. レベル生成 (level_blueprints.py)

- グリッド凡例
  - `O`: 外周（勝利判定エリア）
  - `B`: 外周壁
  - `E`: 出口
  - `1`: 内部壁
  - `.`: 空床
  - `P`: プレイヤー候補
  - `C`: 車候補
  - `Z`: ゾンビ候補

- `generate_random_blueprint(wall_algo)`
  - 外周 -> 出口 -> 壁 -> スポーン候補 の順に生成。
  - `wall_algo` により壁配置戦略を切り替え可能。
    - `"default"`: ランダムな長さの直線をランダム配置。
    - `"empty"`: 内部壁なし。
    - `"grid_wire"`: 縦横を独立グリッドで生成しマージ。平行な壁の隣接（2x2ブロック）を禁止する。

## 7. 設定と進行データ

- `config.py`
  - `DEFAULT_CONFIG` を基準に `load_config()` でユーザ設定を統合。
  - 保存先: `platformdirs.user_config_dir(APP_NAME, APP_NAME)`

- `progress.py`
  - ステージクリア回数を `user_data_dir()` 配下へ保存。

## 8. 乱数とシード

- `rng.py` で MT19937 を自前実装。
- `seed_rng(seed)` で全体RNGを初期化。
- `screens/title.py` でシード入力/自動生成を受け付け。

## 9. ローカライズ

- `localization.py` が `python-i18n` をラップ。
- `locales/ui.*.json` を読み込み、`translate()` で文字列取得。
- フォント指定やスケールもロケール別に制御。

## 10. 重要な定数

- `screen_constants.py`: 400x300 の論理解像度、`DEFAULT_WINDOW_SCALE=2.0`。
- `level_constants.py`: グリッドのデフォルト値（48x30）。
- `gameplay_constants.py`: 速度、判定半径、スポーンレートなど。
- `render_constants.py`: 霧や足跡の描画パラメータ。

---

必要に応じて、この文書に「テスト観点」「拡張ポイント」「既知の制約」などを追加してください。
