import argparse
import requests
import webbrowser
import os
import datetime
import time
import re
import math
from typing import List, Dict, Set, Any
import arxiv
from huggingface_hub import HfApi

# ==========================================
# 1. 詳細カテゴリ設定
# ==========================================
SEARCH_CATEGORIES = {
    # --- 主要タスク ---
    "1. Forecasting (General)": {
        "gh": "time series forecasting", 
        "hf": "time-series-forecasting",
        "arxiv": 'all:"time series forecasting"'
    },
    "2. Probabilistic Forecasting (確率的予測)": {
        "gh": "probabilistic time series forecasting OR quantile regression",
        "hf": "probabilistic-forecasting",
        "arxiv": 'all:"probabilistic time series" OR all:"uncertainty estimation"'
    },
    "3. Anomaly Detection (異常検知)": {
        "gh": "time series anomaly detection",
        "hf": "anomaly-detection",
        "arxiv": 'all:"time series anomaly detection"'
    },
    
    # --- モデルアーキテクチャ別 ---
    "4. Foundation Models (基盤モデル)": {
        "gh": "time series foundation model OR large time series model OR zero-shot forecasting",
        "hf": "time-series-foundation-model",
        "arxiv": 'all:"time series" AND (all:"foundation model" OR all:"large language model")'
    },
    "5. Transformers & Attention": {
        "gh": "time series transformer OR temporal attention",
        "hf": "transformer",
        "arxiv": 'all:"time series transformer" OR all:"temporal attention"'
    },
    "6. GNN / Spatial-Temporal (グラフ・時空間)": {
        "gh": "spatiotemporal time series OR graph neural network time series",
        "hf": "graph-machine-learning",
        "arxiv": 'all:"spatiotemporal" OR all:"graph neural network" AND all:"time series"'
    },

    # --- データ特性・ドメイン ---
    "7. Multivariate & Exogenous (多変量・外生)": {
        "gh": "multivariate time series forecasting OR exogenous variables",
        "hf": "multivariate",
        "arxiv": 'all:"multivariate time series" OR all:"covariates"'
    },
    "8. Finance & Trading (金融)": {
        "gh": "financial time series OR algorithmic trading reinforcement learning",
        "hf": "financial-time-series",
        "arxiv": 'all:"financial time series" OR all:"stock prediction"'
    },

    # --- カンファレンス・コンペ・SOTA ---
    "9. Conferences (NeurIPS/ICML/ITISE)": {
        "gh": "topic:neurips-2024 OR topic:icml-2024 OR topic:time-series-conference",
        "hf": "arxiv", # HFはタグ検索が弱いため汎用
        "arxiv": 'all:"time series" AND (all:"NeurIPS" OR all:"ICML" OR all:"ICLR" OR all:"ITISE" OR all:"ISF")'
    },
    "10. Competition Solutions (Kaggle etc.)": {
        "gh": "topic:kaggle-solution OR topic:time-series-competition",
        "hf": "competition",
        "arxiv": 'all:"time series competition" OR all:"forecasting competition"'
    }
}

# ==========================================
# 2. 解析・正規表現ルール
# ==========================================
REGEX_RULES = {
    # 環境・ツール
    "docker": r"(docker|container|dockerfile|docker-compose)",
    "pip": r"(pip install|requirements\.txt|setup\.py)",
    "conda": r"(conda install|environment\.yml)",
    
    # データ型対応
    "multivariate": r"(multivariate|multi-variate|mts|multiple series)",
    "univariate": r"(univariate|single series)",
    "exogenous": r"(exogenous|covariates|external variables|control variables|forcing)",
    
    # 評価・SOTA
    "sota": r"(state-of-the-art|sota|state of the art|outperform|beats|benchmark)",
    "gpu": r"(gpu|cuda|accelerator)",
}

DEFAULT_DAYS_BACK = 365
DEFAULT_LIMIT = 15
OUTPUT_FILE = "ts_trend_advanced_report.html"

# ==========================================
# データクラス & 評価ロジック
# ==========================================
class TrendItem:
    def __init__(self, source, title, url, stars, date, desc, author, raw_text=""):
        self.source = source
        self.title = title
        self.url = url
        self.stars = int(stars)
        self.date = date # YYYY-MM-DD
        self.desc = desc or ""
        self.author = author
        self.raw_text = (str(title) + " " + str(desc) + " " + str(raw_text)).lower()
        
        # 解析実行
        self.features = self._analyze_features()
        self.trend_score = self._calculate_trend_score()

    def _analyze_features(self) -> Dict[str, bool]:
        """テキスト解析による機能・環境の自動判定"""
        feats = {}
        for key, pattern in REGEX_RULES.items():
            feats[key] = bool(re.search(pattern, self.raw_text))
        return feats

    def _calculate_trend_score(self) -> float:
        """
        独自評価指標: Trend Score
        - スター数が多いほど高い
        - 新しいほど高い（期間あたりの注目度）
        - SOTAへの言及があるとボーナス
        """
        try:
            date_obj = datetime.datetime.strptime(self.date, "%Y-%m-%d")
            days_old = (datetime.datetime.now() - date_obj).days
            days_old = max(days_old, 1) # 0除算防止
        except:
            days_old = 365

        # 基本スコア: スター数
        base_score = self.stars
        
        # 勢い補正: (スター数 / 経過日数) * 係数
        velocity = (self.stars / days_old) * 100
        
        # SOTAボーナス
        sota_bonus = 1.2 if self.features.get("sota") else 1.0
        
        # ArXivなどのスターがないものは、新しさを重視
        if self.source == "ArXiv":
            base_score = 50 # 基礎点
            velocity = (1000 / days_old) # 新しいほど高得点
        
        # 最終スコア算出 (対数スケールなどを組み合わせる)
        final_score = (base_score * 0.3 + velocity * 0.7) * sota_bonus
        return round(final_score, 1)

# ==========================================
# 検索エンジン
# ==========================================
class SearchEngine:
    def __init__(self, token=None):
        self.gh_headers = {"Accept": "application/vnd.github.v3+json"}
        if token: self.gh_headers["Authorization"] = f"token {token}"
        self.hf_api = HfApi()
        self.arxiv_client = arxiv.Client()

    def search_github(self, query: str, limit: int, days_back: int) -> List[TrendItem]:
        since = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime('%Y-%m-%d')
        # READMEも検索したいがAPI制限がきついため、descriptionとtopicsで判断
        final_query = f"{query} created:>{since}"
        items = []
        try:
            params = {"q": final_query, "sort": "stars", "order": "desc", "per_page": min(limit, 100)}
            resp = requests.get("https://api.github.com/search/repositories", headers=self.gh_headers, params=params, timeout=10)
            if resp.status_code == 200:
                for repo in resp.json().get("items", [])[:limit]:
                    # 追加情報の取得（Topicsなど）
                    extra_text = " ".join(repo.get("topics", []))
                    
                    # READMEを取得するとAPI制限にかかりやすいため、今回はdesc+topicsで判定
                    # 本番運用ならここで readme API を叩く
                    
                    items.append(TrendItem(
                        "GitHub", repo["full_name"], repo["html_url"], repo["stargazers_count"],
                        repo["created_at"][:10], repo["description"], repo["owner"]["login"], 
                        raw_text=extra_text
                    ))
        except Exception as e:
            print(f"  [GH Error] {e}")
        return items

    def search_huggingface(self, query: str, limit: int) -> List[TrendItem]:
        items = []
        try:
            # API仕様変更への対応
            models = self.hf_api.list_models(search=query, sort="likes", direction=-1, limit=limit)
            for m in models:
                raw_info = f"{m.pipeline_tag} {' '.join(m.tags if m.tags else [])}"
                items.append(TrendItem(
                    "HF", m.modelId, f"https://huggingface.co/{m.modelId}", getattr(m, 'likes', 0),
                    "Recent", f"Task: {m.pipeline_tag}", m.modelId.split('/')[0],
                    raw_text=raw_info
                ))
        except Exception as e:
            print(f"  [HF Error] {e}")
        return items

    def search_arxiv(self, query: str, limit: int) -> List[TrendItem]:
        items = []
        try:
            search = arxiv.Search(
                query=query, max_results=limit,
                sort_by=arxiv.SortCriterion.SubmittedDate, sort_order=arxiv.SortOrder.Descending
            )
            for r in self.arxiv_client.results(search):
                summary = r.summary.replace("\n", " ")
                items.append(TrendItem(
                    "ArXiv", r.title, r.entry_id, 0,
                    r.published.strftime("%Y-%m-%d"), summary, 
                    ", ".join([a.name for a in r.authors[:2]]),
                    raw_text=summary # アブストラクトを全文解析対象にする
                ))
        except Exception as e:
            print(f"  [ArXiv Error] {e}")
        return items

# ==========================================
# HTML生成 (高度なUI)
# ==========================================
def generate_html(data_map: Dict[str, List[TrendItem]], filename: str):
    
    # バッジ生成ヘルパー
    def get_badges(item):
        badges = []
        if item.features['sota']: badges.append('<span class="badge badge-sota">SOTA?</span>')
        if item.features['docker']: badges.append('<span class="badge badge-env"><i class="fab fa-docker"></i> Docker</span>')
        if item.features['pip'] or item.features['conda']: badges.append('<span class="badge badge-env"><i class="fab fa-python"></i> Py/Conda</span>')
        if item.features['multivariate']: badges.append('<span class="badge badge-data">Multi-Var</span>')
        if item.features['exogenous']: badges.append('<span class="badge badge-data">Exogenous</span>')
        return " ".join(badges)

    # フィルタUI HTML
    filter_html = """
    <div class="dashboard-panel">
        <div class="filter-row">
            <strong><i class="fas fa-layer-group"></i> Environment:</strong>
            <label><input type="checkbox" onchange="applyFilters()" value="docker" class="feat-filter"> Docker</label>
            <label><input type="checkbox" onchange="applyFilters()" value="pip" class="feat-filter"> Pip/Conda</label>
            <label><input type="checkbox" onchange="applyFilters()" value="gpu" class="feat-filter"> GPU Support</label>
        </div>
        <div class="filter-row">
            <strong><i class="fas fa-database"></i> Data Capabilities:</strong>
            <label><input type="checkbox" onchange="applyFilters()" value="multivariate" class="feat-filter"> Multivariate</label>
            <label><input type="checkbox" onchange="applyFilters()" value="exogenous" class="feat-filter"> Exogenous Vars</label>
        </div>
        <div class="filter-row">
            <strong><i class="fas fa-trophy"></i> Special:</strong>
            <label><input type="checkbox" onchange="applyFilters()" value="sota" class="feat-filter"> SOTA Mentioned</label>
        </div>
        <div class="filter-row">
            <strong><i class="fas fa-sort"></i> Sort By:</strong>
            <select id="sortOrder" onchange="sortItems()">
                <option value="trend">Trend Score (High Velocity)</option>
                <option value="stars">Stars / Likes</option>
                <option value="date">Date (Newest)</option>
            </select>
        </div>
    </div>
    """

    tabs_html = ""
    contents_html = ""
    
    for idx, (cat_name, items) in enumerate(data_map.items()):
        safe_id = re.sub(r'[^a-zA-Z0-9]', '', cat_name)
        active_class = "active" if idx == 0 else ""
        display_style = "block" if idx == 0 else "none"
        
        tabs_html += f'<div class="tab-item {active_class}" onclick="openTab(event, \'{safe_id}\')">{cat_name} <span class="count-badge">{len(items)}</span></div>'
        
        rows = ""
        for item in items:
            # ソース別アイコン
            if item.source == "GitHub": icon, col = "fab fa-github", "#24292e"
            elif item.source == "HF": icon, col = "fas fa-brain", "#ff9d00"
            else: icon, col = "fas fa-graduation-cap", "#b31b1b"
            
            # データ属性（JSフィルタ用）
            data_attrs = f'data-stars="{item.stars}" data-trend="{item.trend_score}" data-date="{item.date}"'
            for k, v in item.features.items():
                if v: data_attrs += f' data-{k}="1"'

            rows += f"""
            <tr class="item-row" {data_attrs}>
                <td class="score-cell">
                    <div class="trend-score">{item.trend_score}</div>
                    <div class="sub-score"><i class="fas fa-star"></i> {item.stars}</div>
                </td>
                <td class="date-cell">{item.date}</td>
                <td>
                    <div class="title">
                        <i class="{icon}" style="color:{col}"></i> 
                        <a href="{item.url}" target="_blank">{item.title}</a>
                        {get_badges(item)}
                    </div>
                    <div class="desc">{item.desc[:250]}...</div>
                    <div class="meta-info">
                        Author: {item.author} | Source: {item.source}
                    </div>
                </td>
            </tr>
            """
            
        contents_html += f"""
        <div id="{safe_id}" class="tab-content" style="display: {display_style};">
            <h2 class="section-title">{cat_name}</h2>
            {filter_html}
            <table class="data-table">
                <thead><tr><th width="80">Score</th><th width="100">Date</th><th>Details</th></tr></thead>
                <tbody id="tbody-{safe_id}">{rows}</tbody>
            </table>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Advanced TS Trend Report</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            :root {{ --primary: #2c3e50; --accent: #3498db; --bg: #f4f7f6; }}
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; display: flex; height: 100vh; background: var(--bg); color: #333; }}
            
            /* Sidebar */
            .sidebar {{ width: 280px; background: var(--primary); color: white; display: flex; flex-direction: column; }}
            .sidebar-header {{ padding: 20px; background: #1a252f; text-align: center; border-bottom: 1px solid #455a64; }}
            .tab-list {{ overflow-y: auto; flex: 1; }}
            .tab-item {{ padding: 15px 20px; cursor: pointer; border-bottom: 1px solid #34495e; transition: 0.2s; font-size: 0.9em; display: flex; justify-content: space-between; }}
            .tab-item:hover {{ background: #34495e; }}
            .tab-item.active {{ background: var(--accent); border-left: 5px solid #2980b9; }}
            .count-badge {{ background: rgba(0,0,0,0.3); padding: 2px 8px; border-radius: 10px; font-size: 0.8em; }}

            /* Main */
            .main {{ flex: 1; overflow-y: auto; padding: 20px; }}
            .tab-content {{ background: white; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); padding: 25px; animation: fadeIn 0.3s; }}
            
            /* Dashboard Panel */
            .dashboard-panel {{ background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 15px; margin-bottom: 20px; }}
            .filter-row {{ margin-bottom: 10px; display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }}
            .filter-row strong {{ min-width: 120px; color: #555; font-size: 0.9em; }}
            label {{ font-size: 0.9em; cursor: pointer; display: flex; align-items: center; gap: 5px; }}
            select {{ padding: 4px; border-radius: 4px; border: 1px solid #ccc; }}

            /* Table */
            .data-table {{ width: 100%; border-collapse: collapse; }}
            th {{ text-align: left; padding: 12px; background: #eef2f7; color: #555; font-weight: 600; }}
            td {{ padding: 15px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
            
            /* Items */
            .score-cell {{ text-align: center; }}
            .trend-score {{ font-size: 1.4em; font-weight: bold; color: var(--accent); }}
            .sub-score {{ font-size: 0.8em; color: #7f8c8d; }}
            .date-cell {{ color: #95a5a6; font-size: 0.9em; }}
            .title {{ font-size: 1.1em; font-weight: bold; margin-bottom: 8px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
            .title a {{ text-decoration: none; color: #2c3e50; transition: color 0.2s; }}
            .title a:hover {{ color: var(--accent); }}
            .desc {{ font-size: 0.95em; color: #555; line-height: 1.5; margin-bottom: 8px; }}
            .meta-info {{ font-size: 0.85em; color: #999; }}

            /* Badges */
            .badge {{ font-size: 0.75em; padding: 3px 8px; border-radius: 4px; font-weight: normal; display: inline-flex; align-items: center; gap: 4px; }}
            .badge-sota {{ background: #e74c3c; color: white; font-weight: bold; }}
            .badge-env {{ background: #34495e; color: white; }}
            .badge-data {{ background: #27ae60; color: white; }}
            
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        </style>
        <script>
            function openTab(evt, tabId) {{
                let contents = document.getElementsByClassName("tab-content");
                for (let c of contents) c.style.display = "none";
                let items = document.getElementsByClassName("tab-item");
                for (let i of items) i.className = i.className.replace(" active", "");
                document.getElementById(tabId).style.display = "block";
                evt.currentTarget.className += " active";
                
                // タブ切り替え時にソート・フィルタ再適用
                applyFilters();
            }}

            function applyFilters() {{
                let activeTab = document.querySelector('.tab-content[style*="block"]');
                if (!activeTab) return;
                
                // チェックされているフィルタを取得
                let checkboxes = activeTab.querySelectorAll('.feat-filter:checked');
                let requiredFeats = Array.from(checkboxes).map(cb => cb.value);
                
                let rows = activeTab.querySelectorAll('.item-row');
                for (let row of rows) {{
                    let show = true;
                    // 全てのチェック条件を満たすか確認 (AND条件)
                    for (let feat of requiredFeats) {{
                        if (feat === 'pip' || feat === 'conda') {{
                            // pipまたはcondaどちらかあればOKとする場合などはここで調整可能
                            // ここでは単純に data-pip="1" があるかを見る
                        }}
                        if (!row.getAttribute('data-' + feat)) {{
                            show = false;
                            break;
                        }}
                    }}
                    row.style.display = show ? "" : "none";
                }}
                
                // ソート適用
                sortItems();
            }}

            function sortItems() {{
                let activeTab = document.querySelector('.tab-content[style*="block"]');
                if (!activeTab) return;
                
                let sortKey = activeTab.querySelector('#sortOrder').value;
                let tbody = activeTab.querySelector('tbody');
                let rows = Array.from(tbody.querySelectorAll('.item-row'));
                
                rows.sort((a, b) => {{
                    let valA, valB;
                    if (sortKey === 'date') {{
                        valA = new Date(a.getAttribute('data-date'));
                        valB = new Date(b.getAttribute('data-date'));
                    }} else if (sortKey === 'stars') {{
                        valA = parseInt(a.getAttribute('data-stars'));
                        valB = parseInt(b.getAttribute('data-stars'));
                    }} else {{ // trend
                        valA = parseFloat(a.getAttribute('data-trend'));
                        valB = parseFloat(b.getAttribute('data-trend'));
                    }}
                    return valB - valA; // 降順
                }});
                
                rows.forEach(row => tbody.appendChild(row));
            }}
        </script>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>TS Trend Advanced</h3>
                <small>Metrics & SOTA & Env</small>
            </div>
            <div class="tab-list">
                {tabs_html}
            </div>
        </div>
        <div class="main">
            {contents_html}
        </div>
    </body>
    </html>
    """
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[Success] Generated Report: {os.path.abspath(filename)}")

# ==========================================
# メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK)
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()

    engine = SearchEngine(args.token)
    all_results = {}

    print(f"=== TS Trend Advanced Scan (Last {args.days} days) ===")
    
    for cat_name, queries in SEARCH_CATEGORIES.items():
        print(f"\n>> Scanning: {cat_name}")
        items = []
        
        # 3ソース検索
        items.extend(engine.search_github(queries['gh'], args.limit, args.days))
        time.sleep(1) # API制限考慮
        items.extend(engine.search_huggingface(queries['hf'], args.limit))
        items.extend(engine.search_arxiv(queries['arxiv'], args.limit))
        
        # Trend Score順で初期ソート
        all_results[cat_name] = sorted(items, key=lambda x: x.trend_score, reverse=True)
        print(f"   -> Fetched {len(items)} items")

    generate_html(all_results, OUTPUT_FILE)
    webbrowser.open('file://' + os.path.realpath(OUTPUT_FILE))

if __name__ == "__main__":
    main()