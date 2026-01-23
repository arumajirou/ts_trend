これまでの開発内容および追加要望を整理し、**「時系列分析トレンド調査システム（TS-Trend-Hunter）」**としての詳細要件定義書を作成しました。

---

# 時系列分析トレンド調査システム 詳細要件定義書

**プロジェクト名:** TS-Trend-Hunter
**バージョン:** 1.0
**作成日:** 2026/01/22

## 1. はじめに

### 1.1 背景・目的

時系列データ分析（Time Series Analysis）の分野は、従来の統計的手法から深層学習、さらには大規模基盤モデル（Foundation Models）へと急速に進化している。最新の研究論文（ArXiv）、実装コード（GitHub）、学習済みモデル（Hugging Face）が日々公開されており、これらを人手で網羅的に調査することは困難である。
本システムは、これらの主要プラットフォームを横断的に自動検索・分析し、**「今、何が流行っているか（トレンド）」「どれが実用的か（環境・コード）」**を可視化するダッシュボードを生成することを目的とする。

### 1.2 対象ユーザー

* データサイエンティスト、機械学習エンジニア
* 最新のSOTA（State-of-the-Art）モデルを探している研究者
* 実務ですぐに使えるライブラリ（Docker/Pip対応）を探している開発者

---

## 2. システム概要

### 2.1 システム構成図

本システムはPythonベースのCLIツール群として動作し、外部APIから情報を取得、ローカルで解析・スコアリングを行い、HTMLレポートを出力する。

### 2.2 処理フロー

1. **検索（Search）**: ユーザー指定の条件および定義済みカテゴリに基づき、3大ソース（GitHub, HF, ArXiv）を検索。
2. **解析（Analyze）**: 取得したテキスト（アブストラクト、README、タグ）を解析し、特徴（SOTA、多変量対応など）を抽出。
3. **評価（Evaluate）**: スター数や更新頻度に基づき、独自の「Trend Score」を算出。
4. **出力（Report）**: フィルタリング・ソート可能なインタラクティブHTMLを生成。

---

## 3. 機能要件

### 3.1 データ収集・検索機能

以下の3つのプラットフォームに対し、APIを通じて検索を行う。

| ソース | 検索対象 | 検索手法 | 備考 |
| --- | --- | --- | --- |
| **GitHub** | リポジトリ | Search API | `created` フィルタによる期間指定、`topic` 検索対応 |
| **Hugging Face** | Models, Datasets | HfApi | `pipeline_tag`, `tags` によるフィルタリング |
| **ArXiv** | 論文 (Preprint) | arxiv API | `all` クエリによる全文検索、提出日順ソート |

#### 3.1.1 検索カテゴリの細分化

以下の専門カテゴリごとにクエリを最適化して実行すること。

1. **予測 (Forecasting)**: 一般的な時系列予測。
2. **確率的予測 (Probabilistic)**: 不確実性推定、分位点回帰。
3. **異常検知 (Anomaly Detection)**: 外れ値検知、故障予兆。
4. **基盤モデル (Foundation Models)**: 事前学習済み大規模モデル、Zero-shot。
5. **Transformers**: Temporal Attention、Transformer応用。
6. **GNN / 時空間 (Spatial-Temporal)**: グラフニューラルネット、交通流予測など。
7. **多変量・外生変数 (Multivariate)**: 複数系列、共変量（Covariates）対応。
8. **金融 (Finance)**: アルゴリズム取引、株価予測。
9. **カンファレンス (Conferences)**: NeurIPS, ICML, ICLR, ITISE, ISF などの主要国際会議。
10. **コンペティション (Competitions)**: Kaggle等の上位解法。

### 3.2 自動解析・タグ付け機能

取得したメタデータ（タイトル、説明文、要約）に対し、正規表現およびキーワードマッチングを用いて以下の属性を自動判定する。

* **学習手法分類**:
* Supervised (教師あり), Unsupervised (教師なし), Reinforcement Learning (強化学習)
* Deep Learning (深層学習), Statistical (統計的手法)


* **機能・環境特性**:
* **Docker対応**: `Dockerfile`, `docker-compose` の有無。
* **パッケージ管理**: `pip`, `requirements.txt`, `conda`, `setup.py` の有無。
* **データ型**: `Multivariate` (多変量), `Exogenous` (外生変数) の記述有無。
* **ハードウェア**: `GPU`, `CUDA` 対応。


* **SOTA判定**:
* "State-of-the-Art", "SOTA", "Outperform", "Benchmark" などの記述がある場合、SOTAバッジを付与。



### 3.3 評価・スコアリング機能 (Trend Score)

単純なスター数だけでなく、情報の鮮度と勢いを加味した独自のスコアを算出する。

* **算出式 (例)**: `(Base_Stars * 0.3 + Velocity * 0.7) * SOTA_Bonus`
* **Velocity**: `Stars / 経過日数` （期間あたりの注目度）
* **SOTA_Bonus**: SOTA判定がTrueの場合、スコアを1.2倍にする等の重み付け。



### 3.4 レポート出力・UI機能

検索結果を1つのHTMLファイルとして出力する。JavaScriptを含み、ブラウザ上で以下の操作が可能であること。

* **サイドバーナビゲーション**: カテゴリごとのタブ切り替え。件数バッジの表示。
* **インタラクティブ・フィルタ**:
* 環境: Dockerのみ、Pip対応のみ
* データ: 多変量のみ、外生変数対応のみ
* 特別: SOTA記述ありのみ


* **ソート機能**: Trend Score順、Star数順、日付順（最新順）への切り替え。
* **バッジ表示**: 解析結果（SOTA, Docker, Multi-Var）を視覚的なバッジとして表示。
* **自動起動**: 処理完了後、デフォルトブラウザでレポートを自動的に開く。

---

## 4. 非機能要件

### 4.1 パフォーマンス・API制限対策

* **レート制限回避**: GitHub API等の制限を回避するため、リクエスト間に適切な `sleep` (待機時間) を設ける。
* **認証トークン**: GitHub Personal Access Token を環境変数または引数で受け取り、認証付きリクエストを行う（制限緩和のため）。
* **ページネーション**: 指定された件数（Limit）まで再帰的にページを取得する。

### 4.2 拡張性・保守性

* **モジュール化**: 検索ロジック、解析ロジック、HTML生成ロジックをクラスや関数で分離する。
* **設定の外部化**: 検索キーワードや正規表現ルールを辞書形式で定義し、コード変更なしに調整可能にする（ソースコード内の定数定義による管理）。

### 4.3 動作環境

* **OS**: Windows, macOS, Linux (Dockerコンテナ内含む)
* **言語**: Python 3.8以上
* **依存ライブラリ**: `requests`, `arxiv`, `huggingface_hub`

---

## 5. ファイル・ディレクトリ構成

現在管理されているリポジトリ構成は以下の通りである。

```text
ts_trend/
├── README.md                   # プロジェクト説明書
├── trend.ipynb                 # 実行用Jupyter Notebook (各スクリプトのランチャー)
├── arxiv_trend.py              # [Basic] ArXiv検索・コード抽出
├── trend_hunter.py             # [Standard] GitHub/HFトレンド検索
├── ts_trend_master.py          # [Category] カテゴリ別網羅検索
├── ts_trend_ultimate.py        # [Filter] 手法別フィルタリング機能付き
├── ts_trend_arxiv_integrated.py # [Integrated] 3大ソース統合版
└── ts_trend_advanced.py        # [Advanced] SOTA/環境判定・独自スコア搭載 (推奨版)

```

### 推奨される利用フロー

1. **環境構築**: `pip install -r requirements.txt` (または各ライブラリ)
2. **設定**: `GITHUB_TOKEN` の設定。
3. **実行**: 通常は **`ts_trend_advanced.py`** を使用することで、全ての要件を満たしたレポートが得られる。
* コマンド: `python ts_trend_advanced.py --limit 20 --days 365`



---

## 6. 今後の拡張性 (Future Roadmap)

* **LLMによる要約**: 取得したアブストラクトをChatGPT API等に投げ、日本語で3行要約を生成する機能。
* **定期実行・通知**: GitHub Actions等で毎日実行し、SlackやDiscordに「今日のトレンド」を通知する機能。
* **被引用数・Impact Factor**: Semantic Scholar API等を連携させ、論文の信頼性をより厳密に評価する機能。