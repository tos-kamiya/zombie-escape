# ゾンビ・エスケープ

街はゾンビで埋め尽くされた！
君は追っ手を振り切り、工場の廃墟へと逃げ込んだ。

入り組んだ迷路のような内部。これならヤツらもすぐには入れまい。
だが、武器はない。外は夜。停電で工場内も真っ暗だ。

頼りは一本の懐中電灯のみ。
どこかにあるはずの車……それが唯一の希望。

闇を照らし、車を探し出せ！
そして、この悪夢の街から脱出するのだ！

## 概要

このゲームは、ゾンビが徘徊する広大な建物の中から、車を見つけて脱出することを目指す、シンプルな2Dトップダウンビューのアクションゲームです。プレイヤーはゾンビから逃げ回り、壁を破壊しながら活路を見つけ出し、車に乗って建物の外へ脱出します。

<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot1-ja.png" width="400">
<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot2.png" width="400">
<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot3.png" width="400">
<img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/screenshot4.png" width="400">

## 操作方法

**キーボード・ジョイパッド**

-   **プレイヤー/車の移動:** `W` / `↑` (上), `A` / `←` (左), `S` / `↓` (下), `D` / `→` (右)
-   **車への乗車:** プレイヤーを車に重ねる
-   **ポーズ:** `P`/Start または `ESC`/Select
-   **ゲーム終了:** `ESC`/Select（ポーズ画面から）
-   **リスタート:** (ゲームオーバー/クリア画面で) `R` キー
-   **ウィンドウ拡大縮小/フルスクリーン:** `[` で1段階縮小（400x300）、 `]` で1段階拡大、 `F` でフルスクリーン切替
    -   これらの操作を行った直後、入力/フォーカス状態を明確にするためゲームは必ずポーズ状態になります。
-   **時間加速:** `Shift` キーまたは `R1` を押し続けると、ゲーム全体が4倍速で進み、離すと元の速度に戻ります。

**マウス**

-   **ゲーム画面** 左ボタンを押している間、プレイヤーはカーソル方向へ移動。
    -   プレイヤーキャラクターの上で左ボタンを押し続けると、押している間はゲーム全体が4倍速で進みます。
    -   画面四隅のホットスポット三角へカーソルを持っていくとポーズ。
    -   マウス操作でウィンドウサイズを変更した場合も、ゲームは必ずポーズになります。
-   **タイトル画面・設定画面など** 左ボタンを離す操作で選択

## タイトル画面

### ステージ選択

タイトル画面で以下のステージを選択できます：

- **Stage 1: Find the Car** — 車を見つけて脱出する。
- **Stage 2: Fuel Run** — 燃料を持っていない状態で始まる。まず燃料缶を見つけて拾い、その後車を見つけて脱出する。
- **Stage 3: Rescue Buddy** — 同様に燃料を探しつつ、迷子の相棒を見つけて車で回収し、一緒に脱出する。
- **Stage 4: Evacuate Survivors** — 車を見つけて生存者を集め、ゾンビに追いつかれる前に脱出する。ステージ内には複数の待機車があり、運転中にぶつかると定員も5人分ずつ増える。
- **Stage 5: 持久戦** — 車は利用できないので、四方から押し寄せるゾンビをかわしつつ夜明けまで生き延びる。夜が明けたら、既存の外周壁の開口部から徒歩で外に出ればクリア。

ステージページは段階的に解放されます。  

- ステージ1〜5は常に選択可能。
- ステージ6〜15は、ステージ1〜5をすべてクリアすると解放。
- ステージ16〜25は、ステージ6〜15のページで5ステージ以上クリアすると解放。
- 以降も同様に、「現在ページで5ステージ以上クリア」で次ページが解放されます。

（1ページ目を除き）現在ページで5未満しかクリアしていない場合、次ページには進めません。タイトル画面で左右キーを使って、解放済みページを切り替えられます。  

**ステージ名は未クリアだと赤** で表示され、1回でもクリアすると白になります。クリアしたステージ名の後ろには、ステージ内で登場するキャラクタ等がアイコンで表示されます。

プレイ中、画面左上に現在の目的が表示されます。

### 勝利・敗北条件

-   **勝利条件:** 車に乗った状態で、ステージ（レベル）の境界線の外に出る。
    - Stage 1 / Stage 4 は基本ルール通りで、車で建物を出ればクリアです。
    - Stage 2 では、燃料缶を取得していることが必須です。
    - Stage 3 では、相棒と合流し、車で建物を出ることが条件です。
    - Stage 5 では車が役に立たないため、夜明けまで生存し、外周壁の開口部から徒歩で屋外に出ればクリアです。
-   **敗北条件:**
    -   プレイヤーが車に乗っていない状態でゾンビに接触する。
    -   Stage 3 では、相棒がゾンビに捕まるとゲームオーバーになります。
    -   (注: 現在の実装では、車が破壊されても即ゲームオーバーにはなりません。新しい車を探して脱出を目指します。)

### シード値を共有して同じステージを遊ぶ

タイトル画面では、数字キーで **シード値** を入力することもできます（またはコマンドラインで `--seed <数字>` を指定）。シード値はステージの構造、壁の配置、アイテム配置などを完全に固定するため、たとえば遠く離れたプレイヤー同士でも同じシード値を共有すれば、まったく同じステージ構成で遊べます。シードはタイトル画面とゲーム中・ゲームオーバー画面の右下に表示され、Backspaceキーで自動生成値に戻せます。

## 設定画面

タイトル画面の **Settings** から次の項目をON/OFFできます：

-   **足跡:** 暗闇でも戻り道を思い出せるよう、足跡を残します。
-   **高速ゾンビ:** 高速ゾンビを出現させます（各ゾンビが通常〜高速の間で個別に速度を振り分け）。
-   **車のヒント:** 一定時間後に、燃料（Stage 2未取得時）や車の方向を示す三角マーカーを表示します。
-   **鉄筋:** 単マスの硬い障害物を5%程度の密度で追加します。

## ルール

### キャラクター/アイテム

#### キャラクター

<table>
  <colgroup>
    <col style="width:20%">
    <col>
    <col>
  </colgroup>
  <thead>
    <tr>
      <th>名前</th>
      <th>画像</th>
      <th>メモ</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>プレイヤー</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/player.png" width="64"></td>
      <td>手が付いた青い丸。WASDキー/矢印キーで操作。燃料所持中は右下に小さな黄色の四角が表示されます。</td>
    </tr>
    <tr>
      <td>ゾンビ</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/zombie-normal.png" width="64"></td>
      <td>プレイヤー（または車）を発見すると追跡。視界外では一定時間ごとに移動モードが切り替わります。</td>
    </tr>
    <tr>
      <td>車</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/car.png" width="64"></td>
      <td>接触で乗車。耐久力は壁衝突や轢きで減少し、0で破壊。定員は5人。運転中に待機車へぶつかると耐久力が回復し、定員+5。約5分後、目的地を示す三角マーカーが表示されます。</td>
    </tr>
    <tr>
      <td>相棒 (Stage 3)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/buddy.png" width="64"></td>
      <td>青緑寄りの相棒。画面内のときだけゾンビに狙われ、画面外で触れられても別地点に再出現。徒歩で触れると追尾（約70%速度）、車で触れると回収。壁や鉄筋を叩くと寄って削ってくれます。</td>
    </tr>
    <tr>
      <td>生存者 (Stage 4)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/survivor.png" width="64"></td>
      <td>近づくと約1/3の速度で追従。画面内でゾンビに触れられると即変異する。定員を超えて車に乗車すると車が損傷し、全員降車します。</td>
    </tr>
  </tbody>
</table>

#### アイテム

<table>
  <colgroup>
    <col style="width:20%">
    <col>
    <col>
  </colgroup>
  <thead>
    <tr>
      <th>名前</th>
      <th>画像</th>
      <th>メモ</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>懐中電灯</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/flashlight.png" width="64"></td>
      <td>拾うたびに視界が約20%ずつ拡大。</td>
    </tr>
    <tr>
      <td>燃料缶 (Stage 2/3)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/fuel.png" width="64"></td>
      <td>燃料なしで始まるステージのみ出現。拾うと車に乗れるようになります。</td>
    </tr>
    <tr>
      <td>鉄筋 (オプション)</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/steel-beam.png" width="64"></td>
      <td>斜線入りの障害物。内部壁と同じく通行不可で、耐久力は内部壁の1.5倍。内部壁破壊後にも出現することがあります。</td>
    </tr>
  </tbody>
</table>

#### 環境

<table>
  <colgroup>
    <col style="width:20%">
    <col>
    <col>
  </colgroup>
  <thead>
    <tr>
      <th>名前</th>
      <th>画像</th>
      <th>メモ</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>外周壁</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/wall-outer.png" width="64"></td>
      <td>グレーの外周壁。破壊不能に近く、各辺に1つの開口部（出口）があります。</td>
    </tr>
    <tr>
      <td>内部壁</td>
      <td><img src="https://raw.githubusercontent.com/tos-kamiya/zombie-escape/main/imgs/exports/wall-inner.png" width="64"></td>
      <td>ベージュの内部壁。耐久力を持ち、プレイヤーは繰り返し接触して破壊できます。ゾンビもゆっくりと削れます。車では破壊できません。</td>
    </tr>
  </tbody>
</table>

## 実行方法

**（必要環境: Python 3.10 以上）**

pipxでインストールしてください。

```sh
pipx install zombie-escape
```

あるいは、仮想環境を用意した上でpipでもインストールできます。

```sh
pip install zombie-escape
```

次のコマンドラインにより起動します。

```sh
zombie-escape
```

起動オプション:

- `--show-fps`: FPS表示を有効化します。
- `--debug`: デバッグ補助を有効化します（`--show-fps` を含みます）。
  - `--debug` 実行時は、ポーズ中に画面上部へ `-- paused --` と小さく表示されます。

## ライセンス

このプロジェクトは MIT License の下で公開されています。詳細は[LICENSEファイル](LICENSE.txt)をご覧ください。

本プロジェクトは pygame-ce に依存しています（リポジトリ: `https://github.com/pygame-community/pygame-ce`）。pygame-ce のライセンスは GNU LGPL version 2.1 です。

同梱している Silkscreen-Regular.ttf フォントのライセンスについては配布元に従います。
https://fonts.google.com/specimen/Silkscreen

同梱している misaki_gothic.ttf（美咲フォント、作者: 門真なむ） のライセンスについては Little Limit の配布元に従います。
https://littlelimit.net/misaki.htm

## 謝辞

このゲームの開発において、Python/Pygameによるコード生成、ルール調整の提案、デバッグ支援、そしてこのREADMEの作成に至るまで、技術的な実装とドキュメンテーションの多くの部分で Google の大規模言語モデル Gemini (開発時アクセスモデル) と OpenAI の GPT-5 から多大な協力を得ました。その迅速なコーディング能力と問題解決への貢献に深く感謝いたします。

ゲーム内で使用しているドットフォント Silkscreen-Regular.ttf の作者である Jason Kottke さんに感謝いたします。
Little Limit にて配布されている美咲フォント（misaki_gothic.ttf）の作者である 門真なむ さんに感謝いたします。
