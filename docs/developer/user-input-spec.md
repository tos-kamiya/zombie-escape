# ユーザー操作仕様（入力正規化・リファクタリング設計）

この文書は、`zombie-escape` におけるユーザー操作入力を一元管理するための仕様を定義する。
対象はキーボードおよびジョイパッド（コントローラー/ジョイスティック）であり、既存挙動を維持しつつ、画面ごとの分岐重複を減らすことを目的とする。

## 1. 目的

- 画面ごとに分散している `KEYDOWN` / `JOYBUTTONDOWN` / `JOYHATMOTION` 分岐を統合する。
- 「デバイス依存の入力」ではなく「ゲーム内アクション」で判定できるようにする。
- 既存操作（キーマップ・ゲーム体験）を維持したまま、拡張容易性と保守性を上げる。

## 2. 入力分類

入力は次の3カテゴリに分類する。

### 2.1 KeyboardOnly

キーボード専用で扱う入力。ゲーム進行の共通操作ではなく、UI/ユーティリティ操作・文字入力を含む。

- 例:
  - タイトルのシード入力（`0-9`, `Backspace`）
  - ウィンドウ操作（`[`, `]`, `F`）
  - 設定リセット（`R`）

### 2.2 AnalogVectorOnly

アナログスティック由来の連続ベクトル入力。

- 対象:
  - 左スティック（`x`, `y`）
- 非対象:
  - D-pad / HAT（これらは離散方向入力として CommonAction に正規化する）

### 2.3 CommonAction

キーボード・ジョイパッドの差異を吸収し、共通キーとして扱う離散操作。

- `confirm`（決定）
- `back`（戻る）
- `start`（開始/ポーズ）
- `up`, `down`, `left`, `right`（離散方向）
- `accel`（時間加速）

注: 画面ごとの意味付け（例: `start` が「再挑戦」か「ポーズ」か）は各画面で決める。入力層は意味付けしない。

## 3. 正規化ヘルパの責務

`InputHelper`（名称は実装時に調整可）を導入し、以下を責務とする。

- デバイス接続管理
  - controller/joystick の初期化
  - デバイス追加/削除イベント反映
- フレーム入力収集
  - イベント列と `pygame.key.get_pressed()` を受け取り、正規化状態を作る
- 入力状態提供
  - `pressed`（このフレームで押下）
  - `released`（このフレームで離した）
  - `held`（押下継続中）
- ベクトル入力提供
  - `analog_vector`（左スティック）
  - `move_vector`（必要時のみ: analog + dpad/hat の合成）

## 4. 推奨データモデル

```python
from dataclasses import dataclass
from enum import Enum, auto

class CommonAction(Enum):
    CONFIRM = auto()
    BACK = auto()
    START = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    ACCEL = auto()

@dataclass(frozen=True)
class ActionState:
    pressed: bool
    released: bool
    held: bool

@dataclass(frozen=True)
class InputSnapshot:
    actions: dict[CommonAction, ActionState]
    analog_vector: tuple[float, float]   # left stick only
    move_vector: tuple[float, float]     # analog + dpad/hat (gameplay用)
    text_input: str                       # KEYDOWN.unicode の連結
    keyboard_only_keys_pressed: set[int]  # このフレームで押されたキー
```

## 5. マッピング仕様

### 5.1 CommonAction の標準マップ

- `CONFIRM`
  - Keyboard: `Enter`, `Space`
  - Gamepad: `South (A)`
- `BACK`
  - Keyboard: `Escape`（画面により `Backspace` 追加可）
  - Gamepad: `Select/Back`
- `START`
  - Keyboard: `P`（画面により `R` は KeyboardOnly）
  - Gamepad: `Start`
- `UP/DOWN/LEFT/RIGHT`
  - Keyboard: `Arrow`, `WASD`
  - Gamepad: D-pad, HAT
- `ACCEL`
  - Keyboard: `LShift`, `RShift`
  - Gamepad: `R1` または `Right Trigger > deadzone`

### 5.2 AnalogVectorOnly の標準マップ

- `analog_vector`
  - Controller API: `LEFTX`, `LEFTY`（deadzone 適用）
  - Joystick API: axis `0`, `1`（deadzone 適用）

### 5.3 KeyboardOnly の扱い

`InputSnapshot.keyboard_only_keys_pressed` と `text_input` を使って処理する。

- タイトル画面
  - シード数字入力（`text_input`）
  - `Backspace` で自動シードへ戻す
- 全画面共通
  - `[`/`]`/`F` によるウィンドウ管理
- 設定画面
  - `R` デフォルト復帰

## 6. 画面側の利用契約

各 `screens/*.py` は原則として次の順で入力処理する。

1. `snapshot = input_helper.poll(events, keys)` を取得
2. KeyboardOnly を処理
3. CommonAction を処理
4. Gameplay では `snapshot.move_vector` を `process_player_input()` に渡す

禁止事項:

- 画面側で `JOYBUTTONDOWN`/`JOYHATMOTION` の個別分岐を再実装しない
- 画面側で controller/joystick の生 API を直接読まない

## 7. 既存挙動との互換要件

- 必須互換:
  - タイトル/設定/ゲームプレイ/ゲームオーバーの操作体験を維持
  - スタートアップ画面の「confirm 長押し解除待ち」を維持
  - デバイス hotplug（追加/削除）を維持
- 許容差分:
  - 内部実装の分岐場所
  - 入力ヘルパのクラス名/ファイル配置

## 8. 実装方針（段階移行）

1. `input_utils.py` に `InputHelper` と `InputSnapshot` を追加
2. 既存関数（`is_confirm_event` 等）は互換レイヤとして残す
3. `title.py` と `settings.py` を先行移行（分岐削減効果が大きい）
4. `game_over.py` と `startup_check.py` を移行
5. `gameplay.py` を移行し、`read_gamepad_move()` 呼び出しを `snapshot.move_vector` に置換
6. 旧分岐の削除と最終整理

## 9. 検証項目

- キーボードのみで全画面遷移可能
- ジョイパッドのみで全画面遷移可能（KeyboardOnly 操作を除く）
- アナログスティックと D-pad/HAT の競合時に移動ベクトルが破綻しない
- `ACCEL`（Shift/R1/RT）動作が現行どおり
- デバイス抜き差し中にクラッシュしない

## 10. 非目標（この仕様で扱わない）

- キーコンフィグUIの追加
- 複数コントローラー同時プレイ
- 入力遅延補正・リプレイ入力記録

---

運用ルール:

- 入力仕様変更時は、この文書と `docs/design.md` の該当節を同時更新する。
- 画面固有の新規キー追加は、必ず「KeyboardOnly / CommonAction / AnalogVectorOnly」のいずれかに分類して記述する。
