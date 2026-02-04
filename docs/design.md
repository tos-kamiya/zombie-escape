# Zombie Escape 設計メモ

この文書は、`zombie-escape` の主要な構造・データ・関数の関係を素早く把握するための設計メモです。
実装詳細は各モジュールのコメントや関数本体を参照してください。

## 1. モジュール構成の概要

- `src/zombie_escape/zombie_escape.py`
  - エントリポイント。CLI引数の解析、`pygame`（pygame-ce）初期化、画面遷移ループを担当。
- `src/zombie_escape/screens/*.py`
  - `title`, `settings`, `gameplay`, `game_over` の各画面。
  - `screens/__init__.py` に画面遷移と表示ユーティリティ。
- `src/zombie_escape/gameplay/*.py`
  - ゲームロジックの分割モジュール。初期化、スポーン、移動、当たり判定、勝敗条件など。
- `src/zombie_escape/entities.py`, `src/zombie_escape/world_grid.py`
  - `pygame.sprite.Sprite` を使ったゲーム内エンティティ定義と衝突判定補助（pygame-ce を利用）。
- `src/zombie_escape/models.py`
  - 進行状態やステージ情報のデータ構造（`dataclass`）。
- `src/zombie_escape/stage_constants.py`
  - ステージ構成とデフォルト設定の一覧。
- `src/zombie_escape/render/`
  - 描画パイプラインの分割モジュール群。
  - `render/core.py`: 床/壁/霧/足跡/HUD呼び出し/ヒント矢印などの中心描画。
  - `render/hud.py`: HUD描画（目的/アイコン/ステータスバー/タイマー/ヒント矢印など）。
  - `render/shadows.py`: 壁影/エンティティ影の生成と描画。
  - `render/overview.py`: ゲームオーバー用縮小図、デバッグ用全体表示。
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
- ゲームオーバー画面用: `scaled_overview`, `overview_created`
- 進行演出: `footprints`, `last_footprint_pos`, `footprint_visible_toggle`, `elapsed_play_ms`
- アイテム状態: `has_fuel`, `flashlight_count`, `shoes_count`
- ヒント/メッセージ: `hint_expires_at`, `hint_target_type`, `fuel_message_until`, `survivor_messages`,
  `timed_message`, `timed_message_until`, `timed_message_clear_on_input`
- ステージ特殊処理: `buddy_rescued`, `buddy_onboard`, `survivors_onboard`, `survivors_rescued`, `survivor_capacity`
- 相棒の壁ターゲット: `player_wall_target_cell`, `player_wall_target_ttl`（壁接触後7フレームで失効）
- サバイバル用: `endurance_elapsed_ms`, `endurance_goal_ms`, `dawn_ready`, `dawn_prompt_at`, `dawn_carbonized`
- 乱数/デバッグ: `seed`, `debug_mode`, `time_accel_active`
- 落下スポーン: `falling_zombies`
- 落下スポーン補助: `falling_spawn_carry`（落下スポーン位置が見つからない場合に繰り越すカウント）
- スポーンタイミング: `last_zombie_spawn_time`
- 演出: `dust_rings`

### 3.2 ゲーム状態 (models.GameData)

- `state`: `ProgressState`
- `groups`: `Groups`（Sprite Groupの集合）
- `camera`: `Camera`
- `layout`: `LevelLayout`（外周/内側/外側セルなど）
- `fog`: 霧描画用のキャッシュ辞書
- `stage`: `Stage`（ステージ定義）
- `cell_size`, `level_width`, `level_height`: ステージ別のタイルサイズに応じたワールド寸法
- `fuel`, `flashlights`, `shoes`, `player`, `car`, `waiting_cars` など
- ログ補助: `last_logged_waiting_cars`

### 3.3 ステージ定義 (models.Stage)

`Stage` はステージ属性を保持する `dataclass`。

- プレイ特性: `requires_fuel`, `buddy_required_count`, `rescue_stage`, `endurance_stage`, `intro_key`
- スポーン/難易度: `spawn_interval_ms`, `initial_interior_spawn_rate`, `survivor_spawn_rate`
- 内外/落下スポーン比率: `exterior_spawn_weight`, `interior_spawn_weight`, `interior_fall_spawn_weight`（重みを分け合う）
- サバイバル設定: `endurance_goal_ms`, `fuel_spawn_count`
- 初期アイテム: `initial_flashlight_count`, `initial_shoes_count`
- 待機車両: `waiting_car_target_count`（ステージ別の待機車両数の目安）
- 変種移動ルーチン: `zombie_normal_ratio`（通常移動の出現率）
- 変種移動ルーチン: `zombie_tracker_ratio`（足跡追跡型の出現率）
- 変種移動ルーチン: `zombie_wall_hugging_ratio`（壁沿い巡回型の出現率）
- エイジング速度: `zombie_aging_duration_frames`（値が大きいほど老化が遅い）
- 壁生成アルゴリズム: `wall_algorithm` ("default", "empty", "grid_wire")
- 瓦礫壁の割合: `wall_rubble_ratio`（内部壁のうち、瓦礫外観に差し替える比率）
- 落とし穴の出現率: `pitfall_density` (0.0〜1.0)
- 落とし穴の固定配置: `pitfall_zones`（矩形指定で落とし穴セルを確定配置）
- 落下スポーン領域: `fall_spawn_zones`, `fall_spawn_floor_ratio`
- ステージ公開: `available`
- セルサイズ: `cell_size`（ステージごとのワールド縮尺）
- グリッドサイズ: `grid_cols`, `grid_rows`（タイル数。デフォルトは `level_constants.py` の値）

### 3.4 レベルレイアウト (models.LevelLayout)

- `field_rect`: プレイフィールド全体の `Rect`。
- `outside_cells`: 外周（`O`）領域のセル座標。
- `walkable_cells`: 歩行可能床セルの座標（アイテム・スポーン候補。落とし穴は含まない）。
- `outer_wall_cells`: 外周壁（`B`）セルの座標。
- `wall_cells`: 壁セル（外周壁＋内部壁）の座標。
- `pitfall_cells`: 落とし穴セルの座標。
- `fall_spawn_cells`: 落下ゾンビの候補セル。
- `bevel_corners`: 壁描画の角丸／面取り情報。
- 命名規則: `*_cells` はセル座標の集合（`list`/`set`）。

### 3.5 スプライト群 (models.Groups)

- `all_sprites` (`LayeredUpdates`) と `wall_group`, `zombie_group`, `survivor_group` を保持。

### 3.6 エンティティ (entities.py)

- `Wall`: 内壁。体力を持ち、破壊時に `on_destroy` を発火。
- `RubbleWall`: 内壁と同じ当たり判定/耐久を持ち、見た目だけを瓦礫風に差し替えた壁。
- `SteelBeam`: 簡易な強化障害物。
- `Camera`: 画面スクロール用の矩形管理。
- `Player`, `Zombie`, `Car`, `Survivor`（`is_buddy` フラグで相棒を表現）
- `FuelCan`, `Flashlight`, `Shoes`（収集アイテム）

相棒 (`is_buddy=True`) は一定距離内で追従を開始し、車に乗った数と脱出時の救出数で管理する。
一般 `Survivor` は画面外でゾンビに接触した場合はリスポーンする。
プレイヤー/相棒/生存者は、進行方向に落とし穴があっても、その先に安全な床（`walkable_cells`）があれば自動的に**ジャンプ（跳躍）**して回避する。
ジャンプ中はスプライトが一時的に拡大し、影が本体から切り離されて描画されることで滞空感を表現する。
プレイヤー/相棒は「本体＋手（小円2つ）」の簡易シルエットを使い、移動方向に合わせて手の角度が回転する。
生存者/ゾンビも同じ人型シルエットを使うが、両手は描かない。
方向は16分割（22.5度刻み）で更新し、停止時は直前の方向を維持する。生存者/ゾンビは移動ベクトルから16方向へ丸めて向きを更新する。
プレイヤー/相棒/生存者/ゾンビ/車は 16 方向（22.5度刻み）の画像を使う。人型（プレイヤー/相棒/生存者/ゾンビ）の 16 方向画像は条件（半径/色/手の有無）ごとに共有キャッシュされ、インスタンスごとに再生成しない。車は事前生成した 16 方向画像を描画時に選択し、毎フレーム回転はしない（回転用に拡大した元画像を使って超解像度回転→縮小）。
相棒は内部壁/鉄筋に衝突すると、プレイヤーの70%のダメージを与える。

### 3.6.1 足跡 (models.Footprint)

- `pos` は `tuple[int, int]`（ピクセル座標）。
- `visible` で描画の有無を制御（追跡は可視/不可視を問わず参照）。
- 記録密度は従来の2倍、表示は1つおき（`footprint_visible_toggle`）で見た目密度を維持。

## 3.7 ゾンビ移動戦略

ゾンビの移動は `MovementStrategy`（`entities.py` 内の関数群）として切り出し、`Zombie.update()` から呼び出す。
個体ごとの戦略は `Zombie.movement_strategy` に保持され、生成時に `tracker` フラグに応じて設定される。

- 通常移動 (`zombie_normal_movement`)
  - 視界範囲 `ZOMBIE_SIGHT_RANGE` でプレイヤーを検知したら直進追尾。
  - 視界外は `zombie_wander_move` で徘徊移動。
- 追跡移動 (`zombie_tracker_movement`)
  - 視界範囲 `ZOMBIE_TRACKER_SIGHT_RANGE` でプレイヤーを検知したら直進追尾。
  - 視界外は足跡 (`footprints`) を追跡する。
    - 足跡探索は約30フレームに1回だけ実施。
    - 探索半径は `ZOMBIE_TRACKER_SCENT_RADIUS` / `ZOMBIE_TRACKER_FAR_SCENT_RADIUS` の2段階。
    - 半径内の足跡から候補を集め、ゾンビから近すぎる足跡（`FOOTPRINT_STEP_DISTANCE * 0.5` 以内）は除外。
    - `SCENT_RADIUS` のときは「前回ターゲットより新しい足跡のうち一番古いもの」を優先し、
      ただし `ZOMBIE_TRACKER_NEWER_FOOTPRINT_MS` 以上新しい足跡があれば最新側を優先する。
    - `FAR_SCENT_RADIUS` のときは新しい順に候補（最大3件）を評価する。
    - 候補の中で「壁がない直線経路」が成立する足跡をターゲットにする。
    - ターゲットが見つからない場合は、(a) 現在ターゲット上にいなければ維持、(b) 現在ターゲット上なら次に新しい足跡へ更新。
- 壁沿い移動 (`zombie_wall_hug_movement`)
  - 視界範囲 `ZOMBIE_TRACKER_SIGHT_RANGE` でプレイヤーを検知したら直進追尾。
  - 視界外は前方と±45度のプローブで壁までの距離を測り、目標ギャップ(約4px)を維持するよう旋回する。
  - 壁が遠い場合は壁側へ寄り、近すぎる場合は離れる方向へ補正する。
  - 一定時間壁を検知できなければ徘徊に切り替える。右手/左手の選択は個体ごとにランダム。

補助要素:

- `zombie_wander_move` はランダム角度・壁際の回避挙動で歩行を維持。
  - 角度更新時、外周セルで外向きベクトルを引いた場合は 50% の確率で反転。
  - 外周セルにいる場合、`outer_wall_cells` を参照して内側のセルが外周でなければ内側へ誘導。
  - `outer_wall_cells` がない場合でも、壁衝突を避けられるなら内側へ 1 ステップ押し戻す。
- `Zombie.update()` 側で壁衝突・近接回避・外周逸脱時の補正を処理。
- 落とし穴（`pitfall_cells`）に中心座標が入った場合、ゾンビは即座に消滅し、縮小しながら穴へ吸い込まれる落下アニメーション（`mode="pitfall"`）が再生される。
- wander中は落とし穴を避ける（次セルが落とし穴なら反転して回避し、回避不能ならそのフレームは停止）。追跡/直進時は落下し得る。
- `create_zombie()` で `stage.zombie_tracker_ratio` を参照し追跡型の出現率を決定。

### 3.7.1 追跡ゾンビの行列対策（設計案）

追跡ゾンビが足跡へ過度に集中しないように、混雑検知と再ロック制限を導入する。

- 追跡 -> wandering 移行条件:
  - 自身の進行方向は直前の移動方向から決める（8方向程度）。
  - 進行方向に対して前方に帯を置く（後方は見ない）。
  - 帯の起点はゾンビ中心からオフセット 0px。
  - 帯のサイズは 50px x 50px の長方形（幅 x 長さ）。
  - 帯の中に追跡ゾンビが 5 体以上いる場合、wandering 行動へ移行する。
- wandering -> 追跡 復帰条件（再ロック制限）:
  - wandering 移行時点で最後に追跡していた足跡の timestamp + 3 秒より新しい足跡のみ追跡対象にできる。

## 3.8 落とし穴とジャンプの挙動

落とし穴は床の一部に配置される即死（ゾンビ用）または通行不能（プレイヤー・車用）のトラップ。

- **プレイヤー / 車**:
  - 原則として「壊せない壁」として扱い、進入を阻止する。
  - 落とし穴に接触しても車へのダメージは発生しない。
- **人間（プレイヤー・生存者・相棒）**:
  - 移動ベクトルに基づいた先読み判定を行い、穴の先に安全な床がある場合はジャンプを開始する。
  - ジャンプ中は滞空演出（拡大＋影のオフセット）を行い、穴の判定を無視して通行する。
- **ゾンビ**:
  - 穴を回避せず、進入した瞬間に落下・消滅する。

## 4. ゲームロジックの主要関数 (gameplay/*.py)

### 初期化・生成

- `initialize_game_state(config, stage)` (`gameplay/state.py`)
  - `GameData` の基本セットアップ。
- `generate_level_from_blueprint(game_data, config)` (`gameplay/layout.py`)
  - `level_blueprints` から壁・歩行セル・外部セル・落とし穴を作成。
  - 連結性検証の結果得られた「車で到達可能なタイル（`car_walkable_cells`）」を保持。
  - 予約記号（`f`, `l`, `s` 等）を解釈し、アイテムの確定配置地点を決定。
  - 内部壁の一部は `wall_rubble_ratio` に応じて `RubbleWall` に差し替える（見た目のみ、シード再現性には依存しない）。
- `setup_player_and_cars(game_data, layout_data, car_count)` (`gameplay/spawn.py`)
  - プレイヤーと待機車両を配置。車は必ず「車で到達可能なエリア」に配置される。
- `spawn_initial_zombies(game_data, player, layout_data, config)` (`gameplay/spawn.py`)
  - 初期ゾンビを内側エリア中心に配置。

### スポーン

- `spawn_exterior_zombie`, `spawn_weighted_zombie` (`gameplay/spawn.py`)
  - 外周スポーン/重み付けスポーン。
- `find_exterior_spawn_position`, `find_interior_spawn_positions`, `find_nearby_offscreen_spawn_position` (`gameplay/spawn.py`)
  - スポーン候補位置の探索。
- `update_falling_zombies` (`gameplay/spawn.py`)
  - 落下中オブジェクト（出現または穴への落下）を管理。
  - `mode="spawn"`: 上空から拡大しながら登場。着地時にゾンビを生成しホコリリングを発生。
  - `mode="pitfall"`: 穴の中心へ吸い込まれながら縮小・消滅。
  - 位置が見つからない場合は落下スポーンを行わず、`falling_spawn_carry` を加算して次回へ繰り越す。
- `spawn_survivors` / `place_buddies` / `place_fuel_can` / `place_flashlights` / `place_shoes` (`gameplay/spawn.py`)
  - ステージ別のアイテムやNPCを配置。ブループリントの予約地点を優先使用する。
- `spawn_waiting_car` / `place_new_car` / `maintain_waiting_car_supply` (`gameplay/spawn.py`)
  - 待機車両の補充と再配置。**車で到達可能なタイル（`car_walkable_cells`）からのみ選択**され、孤立を防止する。
- `respawn_buddies_near_player` / `nearest_waiting_car` (`gameplay/spawn.py`)
  - 相棒の再配置や最寄り車両の検索。

### 更新

- `process_player_input(keys, player, car)` (`gameplay/movement.py`)
  - プレイヤー/車両の入力速度を決定。
- `update_entities(game_data, player_dx, player_dy, car_dx, car_dy, config)` (`gameplay/movement.py`)
  - 移動、カメラ更新、ゾンビAI、サバイバー移動など。
  - 人間キャラクターのジャンプ判定と、ゾンビの穴落下判定を実施。
  - 壁セルに隣接するタイル端に近い場合、移動ベクトルをタイル中心へ3%だけ補正する（全キャラ共通）。
- `check_interactions(game_data, config)` (`gameplay/interactions.py`)
  - アイテム収集、車両/救助/敗北判定などの相互作用。
- `update_survivors(game_data, config)` (`gameplay/survivors.py`)
  - サバイバー/相棒の移動と追従。
  - 落とし穴を壁と同様の障害物として避ける。
  - 相棒は追従中、プレイヤーが内部壁/鉄筋に接触している間だけ同じセル中心を追う。
  - 相棒は移動方向に合わせて描画用の向き（16方向）を更新する（壁接触時は隣方向へ揺らす）。
- `handle_survivor_zombie_collisions(game_data, config)` (`gameplay/survivors.py`)
  - サバイバーとゾンビの接触処理。
- `add_survivor_message`, `cleanup_survivor_messages`, `random_survivor_conversion_line` (`gameplay/survivors.py`)
  - サバイバーのメッセージ表示と文言選択。
- `update_footprints(game_data, config)` (`gameplay/footprints.py`)
  - 足跡を記録し寿命で削除（表示は設定で制御し、記録は常時行う）。
- `get_shrunk_sprite(sprite, scale)` (`gameplay/footprints.py`)
  - 足跡描画用の縮小スプライトを生成/キャッシュ。
- `update_endurance_timer(game_data, dt_ms)` (`gameplay/state.py`)
  - サバイバル用の時間管理と夜明け切り替え。
- `carbonize_outdoor_zombies(game_data)` (`gameplay/state.py`)
  - 夜明け時の屋外ゾンビ炭化処理。
- `sync_ambient_palette_with_flashlights(game_data, force=False)` (`gameplay/ambient.py`)
  - 懐中電灯数に合わせて環境パレットを同期。
 - ステージ導入セリフ
   - `Stage.intro_key` にローカライズキーを設定。
   - `initialize_game_state()` で導入セリフを timed_message として設定。
   - `screens/gameplay.py` で移動入力があれば導入セリフを即スキップ。

### 速度/容量補助

- `calculate_car_speed_for_passengers`, `apply_passenger_speed_penalty`
  - 乗車人数に応じた速度低下。
- `increase_survivor_capacity`, `drop_survivors_from_car` など

### 補助ユーティリティ

- `_handle_pitfall_detection(x, y, ...)` (`gameplay/movement.py`)
  - 座標が落とし穴にあるか判定し、中心への吸い込みターゲット座標を計算。

## 5. 描画パイプライン (render/core.py)

- `draw(...)` が描画の中心。
  1. 環境色で背景塗りつぶし
  2. プレイ領域・床パターン描画
  3. 落とし穴の描画: 奈落の暗色、左右の滑らかなグラデーション影、および上端の金属的な断面（断面には斜め縞模様のテクスチャ）を描画。
  4. 影レイヤー（壁影・エンティティ影）を生成して合成
     - ジャンプ中のエンティティの影は、本体から下にオフセットして描画。
  5. 足跡のフェード描画
  6. Sprite 群を `Camera` でオフセットして描画
  7. 追跡型/壁沿いゾンビには識別用の装飾を追加（追跡は鼻ライン、壁沿いは壁側の手）
  8. ヒント矢印 (`_draw_hint_arrow`)
  9. 霧 (`fog_surfaces` + `FOG_RINGS`)
  10. HUD: 目的/メッセージ/ステータスバー

- 影は `shadow_layer` に壁影とエンティティ影を描き、光源（プレイヤーまたは車）基準でずらして合成する。
  - 屋外セル（`outside_cells`）上のエンティティは影を描かない。

- `_draw_status_bar()`
  - 設定フラグやステージ番号、シード値を表示。
- 導入セリフ/短時間メッセージ (`_draw_timed_message` in `render/hud.py`)
  - 画面上部のプレイヤー位置付近に、タイプライター表示（1文字ずつ）。
  - 半透明帯の上に LIGHT_GRAY で描画。

- `draw_level_overview()` (`render/overview.py`)
  - `game_over` 画面用のレベル縮小図（落下ゾンビ床も表示）。
- `draw_debug_overview()` (`render/overview.py`)
  - デバッグ用の全体表示（ゾンビ位置＋カメラ枠）。

## 5.1 ウィンドウ/フルスクリーン

- トグル操作: F キーでフルスクリーン/ウィンドウを切り替える（起動時は常にウィンドウ）。
- フルスクリーン切替: SDL2 Window 経由で現在ウィンドウ位置からディスプレイ番号を推定し、取得できない場合は `get_display_index()`、それも失敗すれば `set_mode(FULLSCREEN)` へフォールバックする。
- ウィンドウ復帰: 解除時は直前のウィンドウ位置へ戻す（Wayland 等では位置指定が無視される場合がある）。
- 論理解像度の基本: 400x300 を基準に OS のウィンドウサイズへ拡大描画する。
- 画面別論理解像度: ゲームプレイ/ゲームオーバーは 400x300 のサーフェイス、タイトル/設定は 800x600 のサーフェイスを生成し、ウィンドウへ拡大・縮小して表示する。
- ウィンドウ再作成の理由: `pygame.display.set_mode()` で OS ウィンドウのサイズ・フルスクリーン状態・`pygame.SCALED` の論理解像度を反映するため。
- 論理解像度の切替: `set_scaled_logical_size()` が 400x300 ⇄ 800x600 を切り替え、ウィンドウサイズを維持したい場合は `preserve_window_size=True` で復元する。
- 再作成が発生する操作: フルスクリーン切替、ウィンドウ倍率変更（`apply_window_scale` / `nudge_menu_window_scale`）、論理解像度変更時に `set_mode()` が呼ばれる。
- サーフェイス切替: 起動時に 400x300 (`logical_screen`) と 800x600 (`menu_screen`) を生成し、画面遷移で使い分ける。
- 表示パス: `set_scaled_logical_size()` / `adjust_menu_logical_size()` で論理解像度を整えたうえで、`present()` が現在のウィンドウへスケーリング描画する。
- `pygame.SCALED` の扱い: 利用可能な環境ではウィンドウ側で拡大し、利用できない場合は `present()` がアスペクト比を保つレターボックス描画を行う。

## 6. レベル生成 (level_blueprints.py)

- グリッド凡例
  - `O`: 外周（勝利判定エリア / outside area, victory zone）
  - `B`: 外周壁（outer wall band）
  - `E`: 出口（exit）
  - `1`: 内部壁（interior wall）
  - `.`: 空床（walkable floor）
  - `P`: プレイヤー候補（player spawn candidate）
  - `C`: 車候補（car spawn candidate）
  - `x`: 落とし穴（pitfall trap）
  - `f`: 燃料候補（fuel candidate）
  - `l`: 懐中電灯候補（flashlight candidate）
  - `s`: 靴候補（shoes candidate）

- `generate_random_blueprint(wall_algo)`
  - 外周 -> 出口 -> スポーン・アイテム候補（P/C/f/l/s）予約 -> 落とし穴 -> 壁 -> 鉄筋候補 の順に生成。
  - 予約地点（`reserved_cells`）には壁や落とし穴が生成されないよう保護される。
  - `wall_algo` により壁配置戦略を切り替え可能。
    - `"default"`: ランダムな長さの直線をランダム配置。
    - `"empty"`: 内部壁なし。
    - `"grid_wire"`: 縦横を独立グリッドで生成しマージ。平行な壁の隣接（2x2ブロック）を禁止する。
    - `"sparse_moore"`: 低密度の点在壁を配置（上下左右＋斜めの隣接禁止）。
    - `"sparse_moore.<int>%"`: 点在壁の密度を 0〜100 の整数％で指定。
    - `"sparse_ortho"`: 低密度の点在壁を配置（上下左右のみ隣接禁止）。
    - `"sparse_ortho.<int>%"`: 点在壁の密度を 0〜100 の整数％で指定。
  - ステージ内のアイテム配置（燃料/懐中電灯/靴など）は、レイアウト生成後に `walkable_cells` を使って行う。

- 落下ゾンビ用タイル
  - `fall_spawn_zones`（ステージ定義の矩形群）をセル集合に展開し、`fall_spawn_cells` として保持。
  - `fall_spawn_floor_ratio` が有効なら、内部セルから一定割合を落下候補セルに追加。
  - `fall_spawn_cells` は落下スポーン位置の候補として利用される（床のハイライトにも使用）。
  - `draw_level_overview()` でも暗色で可視化される。

- 落とし穴ゾーン
  - `pitfall_zones`（ステージ定義の矩形群）をセル集合に展開し、対象セルを落とし穴に設定。
  - 出口周辺セルは落とし穴対象から除外される。

### 6.1 連結性保証とリトライロジック

生成されたブループリント（ステージの初期配置データ）は、以下の2段階の検証（BFS）を経て、不合格の場合はリトライされる。

1. **車用連結性チェック (`validate_car_connectivity`)**:
   - 車 (`C`) から開始し、**4方向移動**で少なくとも一つの出口 (`E`) に到達可能かを確認。
   - 脱出可能なパスが繋がっているタイル集合（`car_reachable_cells`）を返し、ブループリントに保持される。
   - 生成後は `GameData.blueprint` に保存され、`car_walkable_cells` としてスポーン候補に利用される。
2. **人間用連結性チェック (`validate_humanoid_connectivity`)**:
   - プレイヤー (`P`) から開始し、斜め移動を含む**8方向移動**で、ブループリント上のすべての通行可能タイル（アイテム・相棒地点含む）に到達可能かを確認。

**リトライロジック**:
- 上記の検証に失敗した場合、 `base_seed + attempt_count` によってシード値を更新し、最大20回まで再生成を試みる。
- これにより、特定のシード値に対して常に決定論的に同一の「合格したマップ」が生成される。
- 20回失敗した場合は `MapGenerationError` を投げ、タイトル画面へ安全に復帰する。

## 7. 設定と進行データ

- `config.py`
  - `DEFAULT_CONFIG` を基準に `load_config()` でユーザ設定を統合。
  - 保存先: `platformdirs.user_config_dir(APP_NAME, APP_NAME)`
  - 視覚設定: `visual.shadows.enabled` で壁影/エンティティ影の描画を切替。

- `progress.py`
  - ステージクリア回数を `user_data_dir()` 配下へ保存。

## 7.1 相棒ステージの勝利条件（追加仕様）

相棒ステージ（`buddy_required_count > 0`）の勝利判定は以下のAND条件。

- **脱出条件**:
  - 車があるステージ: プレイヤーが車に乗って外周へ到達
  - 車がないステージ: endurance の時間達成（既存判定）
- **相棒条件**:
  - `buddy_onboard` と「プレイヤーから 30px 以内かつ追尾中」の人数の合算が
    `buddy_required_count` を満たすこと。
  - HUD では人数に応じて「相棒/同僚と合流する（合流済: X/Y人）」を表示する。

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
