import argparse
import requests
import webbrowser
import os
import datetime
import time
import re
from typing import List, Dict, Set
from huggingface_hub import HfApi

# ==========================================
# 1. 検索カテゴリ (データ収集の入り口)
# ==========================================
SEARCH_CATEGORIES = {
    "1. Forecasting (予測)": {"gh": "time series forecasting", "hf": "time-series-forecasting"},
    "2. Anomaly Detection (異常検知)": {"gh": "time series anomaly detection", "hf": "anomaly-detection"},
    "3. Classification (分類)": {"gh": "time series classification", "hf": "time-series-classification"},
    "4. Foundation Models (基盤モデル)": {"gh": "time series foundation model OR large time series model", "hf": "time-series-foundation-model"},
    "5. Transformers": {"gh": "time series transformer", "hf": "transformer time-series"},
    "6. Generation (生成)": {"gh": "time series generation synthetic", "hf": "synthetic-time-series"},
    "7. Preprocessing (前処理)": {"gh": "time series preprocessing imputation", "hf": "imputation"},
    "8. Tools & Viz (ツール)": {"gh": "time series visualization automl", "hf": "visualization"},
    "9. Finance (金融)": {"gh": "financial time series quantitative", "hf": "financial-time-series"}
}

# ==========================================
# 2. 自動タグ付けルール (学習手法・モデル種別)
# ==========================================
# 検索結果のテキスト(説明文やトピック)に含まれるキーワードで自動分類します
TAG_RULES = {
    "Supervised": ["supervised", "forecasting", "classification", "regression", "label"],
    "Unsupervised": ["unsupervised", "anomaly detection", "clustering", "outlier", "self-supervised", "contrastive"],
    "RL": ["reinforcement learning", "rl", "gym", "agent", "reward", "policy"],
    "Deep Learning": ["deep learning", "neural network", "lstm", "rnn", "cnn", "transformer", "pytorch", "tensorflow", "keras", "diffusion"],
    "Foundation Model": ["foundation model", "pretrained", "large language model", "llm", "zero-shot", "few-shot", "generalist"],
    "Statistical/ML": ["arima", "ets", "prophet", "scikit-learn", "xgboost", "lightgbm", "statistical", "machine learning"]
}

DEFAULT_DAYS_BACK = 365
DEFAULT_LIMIT_PER_CAT = 30
OUTPUT_FILE = "ts_ultimate_report.html"

# ==========================================
# クラス定義
# ==========================================
class TrendItem:
    def __init__(self, source, title, url, stars, date, desc, author, topics):
        self.source = source
        self.title = title
        self.url = url
        self.stars = stars
        self.date = date
        self.desc = desc or ""
        self.author = author
        self.topics = topics or []
        self.derived_tags = self._analyze_tags()

    def _analyze_tags(self) -> Set[str]:
        """説明文とトピックから学習手法タグを自動判定"""
        text = (self.title + " " + self.desc + " " + " ".join(self.topics)).lower()
        tags = set()
        
        for label, keywords in TAG_RULES.items():
            for kw in keywords:
                # 単語境界を考慮した簡易チェック
                if kw in text:
                    tags.add(label)
                    break # 1つでもヒットすればそのタグを付与
        
        # GitHub/HFのソースごとのデフォルトタグ補完
        if "forecasting" in text: tags.add("Supervised")
        if "anomaly" in text: tags.add("Unsupervised")
        
        return tags

# ==========================================
# 検索エンジン
# ==========================================
class SearchEngine:
    def __init__(self, token=None):
        self.gh_headers = {"Accept": "application/vnd.github.v3+json"}
        if token: self.gh_headers["Authorization"] = f"token {token}"
        self.hf_api = HfApi()

    def search_github(self, query: str, limit: int, days_back: int) -> List[TrendItem]:
        since = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime('%Y-%m-%d')
        final_query = f"{query} created:>{since}"
        items = []
        try:
            params = {"q": final_query, "sort": "stars", "order": "desc", "per_page": min(limit, 100)}
            resp = requests.get("https://api.github.com/search/repositories", headers=self.gh_headers, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for repo in data.get("items", [])[:limit]:
                    items.append(TrendItem(
                        "GitHub", repo["full_name"], repo["html_url"], repo["stargazers_count"],
                        repo["created_at"][:10], repo["description"], repo["owner"]["login"], repo.get("topics", [])
                    ))
        except Exception as e:
            print(f"  [GH Error] {e}")
        return items

    def search_huggingface(self, query: str, limit: int) -> List[TrendItem]:
        items = []
        try:
            models = self.hf_api.list_models(search=query, sort="likes", direction=-1, limit=limit)
            for m in models:
                items.append(TrendItem(
                    "HF Model", m.modelId, f"https://huggingface.co/{m.modelId}", getattr(m, 'likes', 0),
                    "Recent", f"Tags: {', '.join(m.tags[:5] if m.tags else [])}", m.modelId.split('/')[0], m.tags
                ))
        except Exception as e:
            print(f"  [HF Error] {e}")
        return items

# ==========================================
# HTML生成 (フィルタ機能付き)
# ==========================================
def generate_html(data_map: Dict[str, List[TrendItem]], filename: str):
    
    # フィルタボタンの定義
    filter_buttons_html = """
    <div class="filter-bar">
        <span style="font-weight:bold; color:#555; margin-right:10px;"><i class="fas fa-filter"></i> Filter by Method:</span>
        <button class="filter-btn active" onclick="applyFilter('all')">All</button>
    """
    for tag_key in TAG_RULES.keys():
        # スペース除去してID化
        safe_tag = tag_key.replace(" ", "-")
        filter_buttons_html += f'<button class="filter-btn" onclick="applyFilter(\'{safe_tag}\')">{tag_key}</button>'
    filter_buttons_html += "</div>"

    # コンテンツ生成
    tabs_html = ""
    contents_html = ""
    
    for idx, (cat_name, items) in enumerate(data_map.items()):
        safe_id = re.sub(r'[^a-zA-Z0-9]', '', cat_name)
        active_class = "active" if idx == 0 else ""
        display_style = "block" if idx == 0 else "none"
        
        tabs_html += f'<div class="tab-item {active_class}" onclick="openTab(event, \'{safe_id}\')">{cat_name} <span class="badge">{len(items)}</span></div>'
        
        rows = ""
        for rank, item in enumerate(items, 1):
            icon = "fab fa-github" if "GitHub" in item.source else "fas fa-brain"
            color_class = "gh-color" if "GitHub" in item.source else "hf-color"
            
            # タグのHTML化
            tags_html = "".join([f'<span class="tag">{t}</span>' for t in item.derived_tags])
            
            # フィルタリング用のクラス文字列作成 (例: "Supervised Deep-Learning")
            filter_classes = " ".join([t.replace(" ", "-") for t in item.derived_tags])
            
            rows += f"""
            <tr class="item-row {filter_classes}">
                <td>{rank}</td>
                <td class="stars"><i class="fas fa-star" style="color:#f1c40f"></i> {item.stars}</td>
                <td class="date">{item.date}</td>
                <td>
                    <div class="title">
                        <i class="{icon} {color_class}"></i> 
                        <a href="{item.url}" target="_blank">{item.title}</a>
                    </div>
                    <div class="desc">{item.desc}</div>
                    <div class="tags-container">
                        <span class="method-label">Methods:</span> {tags_html}
                    </div>
                </td>
            </tr>
            """
            
        contents_html += f"""
        <div id="{safe_id}" class="tab-content" style="display: {display_style};">
            <h2 class="section-title">{cat_name}</h2>
            {filter_buttons_html}
            <table id="table-{safe_id}">
                <thead>
                    <tr><th width="50">#</th><th width="80">Stars</th><th width="100">Date</th><th>Details</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
            <div class="no-results" style="display:none; padding:20px; text-align:center; color:#999;">
                No items match the selected filter.
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Ultimate Time Series Analysis Trends</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f0f2f5; display: flex; height: 100vh; overflow: hidden; }}
            
            /* Sidebar */
            .sidebar {{ width: 260px; background: #2c3e50; color: #ecf0f1; display: flex; flex-direction: column; flex-shrink: 0; }}
            .sidebar-header {{ padding: 20px; background: #1a252f; text-align: center; border-bottom: 1px solid #34495e; }}
            .tab-list {{ overflow-y: auto; flex: 1; }}
            .tab-item {{ padding: 15px; cursor: pointer; border-bottom: 1px solid #34495e; transition: 0.2s; display: flex; justify-content: space-between; font-size: 0.9em; }}
            .tab-item:hover {{ background: #34495e; }}
            .tab-item.active {{ background: #3498db; color: white; border-left: 5px solid #2980b9; }}
            .badge {{ background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 10px; font-size: 0.8em; }}
            
            /* Main */
            .main {{ flex: 1; overflow-y: auto; padding: 20px; }}
            .tab-content {{ background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); padding: 20px; }}
            .section-title {{ margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 10px; color: #2c3e50; }}
            
            /* Filter Bar */
            .filter-bar {{ padding: 10px 0; border-bottom: 1px solid #eee; margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
            .filter-btn {{ background: #f8f9fa; border: 1px solid #ddd; padding: 6px 12px; border-radius: 20px; cursor: pointer; font-size: 0.85em; transition: 0.2s; color: #555; }}
            .filter-btn:hover {{ background: #e2e6ea; }}
            .filter-btn.active {{ background: #3498db; color: white; border-color: #3498db; box-shadow: 0 2px 5px rgba(52, 152, 219, 0.3); }}

            /* Table */
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #f8f9fa; color: #666; text-align: left; padding: 10px; }}
            td {{ padding: 12px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
            .stars {{ color: #f1c40f; font-weight: bold; }}
            .date {{ color: #999; font-size: 0.85em; }}
            .title a {{ text-decoration: none; color: #0366d6; font-weight: bold; font-size: 1.1em; }}
            .desc {{ font-size: 0.9em; color: #555; margin: 5px 0; }}
            .method-label {{ font-size: 0.75em; font-weight: bold; color: #888; text-transform: uppercase; margin-right: 5px; }}
            .tag {{ background: #e1ecf4; color: #0366d6; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; margin-right: 4px; display: inline-block; margin-bottom: 2px; }}
            
            .gh-color {{ color: #24292e; }}
            .hf-color {{ color: #ff9d00; }}
        </style>
        <script>
            // タブ切り替え
            function openTab(evt, tabId) {{
                var i, tabcontent, tablinks;
                tabcontent = document.getElementsByClassName("tab-content");
                for (i = 0; i < tabcontent.length; i++) {{ tabcontent[i].style.display = "none"; }}
                tablinks = document.getElementsByClassName("tab-item");
                for (i = 0; i < tablinks.length; i++) {{ tablinks[i].className = tablinks[i].className.replace(" active", ""); }}
                document.getElementById(tabId).style.display = "block";
                evt.currentTarget.className += " active";
                
                // タブ切り替え時にフィルタをAllにリセット
                resetFilters(tabId);
            }}

            // フィルタ適用
            function applyFilter(filterClass) {{
                // アクティブなタブ内の要素を取得
                var activeTab = document.querySelector('.tab-content[style*="block"]');
                if (!activeTab) return;
                
                // ボタンのアクティブ状態更新
                var buttons = activeTab.querySelectorAll('.filter-btn');
                buttons.forEach(btn => btn.classList.remove('active'));
                
                // クリックされたボタンをアクティブに(テキスト一致で判定)
                event.target.classList.add('active');

                var rows = activeTab.getElementsByClassName("item-row");
                var visibleCount = 0;

                for (var i = 0; i < rows.length; i++) {{
                    if (filterClass === 'all') {{
                        rows[i].style.display = "";
                        visibleCount++;
                    }} else {{
                        if (rows[i].classList.contains(filterClass)) {{
                            rows[i].style.display = "";
                            visibleCount++;
                        }} else {{
                            rows[i].style.display = "none";
                        }}
                    }}
                }}
                
                // 該当なしメッセージの表示制御
                var noResults = activeTab.querySelector('.no-results');
                if (visibleCount === 0) {{
                    noResults.style.display = "block";
                }} else {{
                    noResults.style.display = "none";
                }}
            }}
            
            function resetFilters(tabId) {{
                var tab = document.getElementById(tabId);
                var allBtn = tab.querySelector('.filter-btn'); // 最初のボタン(All)
                if(allBtn) allBtn.click();
            }}
        </script>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>TS Trend Ultimate</h3>
                <small>AI & Method Analysis</small>
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
    print(f"\n[Success] Report generated: {os.path.abspath(filename)}")

# ==========================================
# メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT_PER_CAT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK)
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()

    engine = SearchEngine(args.token)
    all_results = {}

    print(f"=== Starting Analysis (Last {args.days} days) ===")
    
    for cat_name, queries in SEARCH_CATEGORIES.items():
        print(f">> Scanning: {cat_name}")
        gh = engine.search_github(queries['gh'], args.limit, args.days)
        time.sleep(1)
        hf = engine.search_huggingface(queries['hf'], args.limit)
        
        # 結合してスター順にソート
        combined = sorted(gh + hf, key=lambda x: x.stars, reverse=True)
        all_results[cat_name] = combined
        print(f"   -> {len(combined)} items fetched.")

    generate_html(all_results, OUTPUT_FILE)
    webbrowser.open('file://' + os.path.realpath(OUTPUT_FILE))

if __name__ == "__main__":
    main()