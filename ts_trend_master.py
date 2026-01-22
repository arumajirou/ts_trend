import argparse
import requests
import webbrowser
import os
import datetime
import time
import re
from typing import List, Dict
from huggingface_hub import HfApi

# ==========================================
# 1. 検索カテゴリ定義 (カスタマイズ可能)
# ==========================================
# カテゴリ名: { "gh": GitHub検索クエリ, "hf": HF検索キーワード }
SEARCH_CATEGORIES = {
    # --- タスク別 ---
    "1. Forecasting (予測)": {
        "gh": "time series forecasting", 
        "hf": "time-series-forecasting"
    },
    "2. Anomaly Detection (異常検知)": {
        "gh": "time series anomaly detection", 
        "hf": "anomaly-detection"
    },
    "3. Classification (分類)": {
        "gh": "time series classification", 
        "hf": "time-series-classification"
    },
    
    # --- トレンド・モデル ---
    "4. Foundation Models (基盤モデル)": {
        "gh": "time series foundation model OR large time series model", 
        "hf": "time-series-foundation-model"
    },
    "5. Transformers (Transformer系)": {
        "gh": "time series transformer", 
        "hf": "transformer time-series"
    },

    # --- データエンジニアリング ---
    "6. Generation & Augmentation (生成・拡張)": {
        "gh": "time series generation OR synthetic time series OR data augmentation", 
        "hf": "synthetic-time-series"
    },
    "7. Preprocessing (前処理・欠損補完)": {
        "gh": "time series preprocessing OR time series imputation", 
        "hf": "imputation"
    },

    # --- 評価・実運用 ---
    "8. Evaluation & Backtesting (評価・検証)": {
        "gh": "time series backtesting OR forecasting metrics OR evaluation", 
        "hf": "metrics" # HFはmetricが少ないためヒットしない可能性あり
    },
    "9. Tools & Viz (可視化・便利ツール)": {
        "gh": "time series visualization OR time series toolbox OR automl", 
        "hf": "visualization"
    },
    
    # --- ドメイン ---
    "10. Finance (金融)": {
        "gh": "financial time series OR quantitative trading", 
        "hf": "financial-time-series"
    }
}

# ==========================================
# 設定・データ構造
# ==========================================
DEFAULT_DAYS_BACK = 365
DEFAULT_LIMIT_PER_CAT = 30 # カテゴリごとの取得数
OUTPUT_FILE = "ts_comprehensive_report.html"

class TrendItem:
    def __init__(self, source, title, url, stars, date, desc, author, tags):
        self.source = source
        self.title = title
        self.url = url
        self.stars = stars
        self.date = date
        self.desc = desc or "No description."
        self.author = author
        self.tags = tags

# ==========================================
# 検索エンジンクラス
# ==========================================
class SearchEngine:
    def __init__(self, token=None):
        self.gh_token = token
        self.hf_api = HfApi()
        self.gh_headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.gh_headers["Authorization"] = f"token {token}"

    def search_github(self, query: str, limit: int, days_back: int) -> List[TrendItem]:
        since_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime('%Y-%m-%d')
        # クエリに作成日フィルタを追加
        final_query = f"{query} created:>{since_date}"
        api_url = "https://api.github.com/search/repositories"
        
        items = []
        params = {"q": final_query, "sort": "stars", "order": "desc", "per_page": min(limit, 100)}
        
        try:
            # ページネーション対応（limitまで）
            while len(items) < limit:
                params["page"] = (len(items) // 100) + 1
                resp = requests.get(api_url, headers=self.gh_headers, params=params, timeout=10)
                if resp.status_code != 200: break
                
                data = resp.json()
                if not data.get("items"): break
                
                for repo in data["items"]:
                    items.append(TrendItem(
                        source="GitHub",
                        title=repo["full_name"],
                        url=repo["html_url"],
                        stars=repo["stargazers_count"],
                        date=repo["created_at"][:10],
                        desc=repo.get("description", ""),
                        author=repo["owner"]["login"],
                        tags=repo.get("topics", [])
                    ))
                    if len(items) >= limit: break
        except Exception as e:
            print(f"  [GH Error] {e}")
        return items

    def search_huggingface(self, query: str, limit: int) -> List[TrendItem]:
        items = []
        try:
            # HFはsearchパラメータで検索
            models = self.hf_api.list_models(
                search=query,
                sort="likes",
                direction=-1,
                limit=limit
            )
            for m in models:
                likes = getattr(m, 'likes', 0)
                items.append(TrendItem(
                    source="HF Model",
                    title=m.modelId,
                    url=f"https://huggingface.co/{m.modelId}",
                    stars=likes,
                    date="Recent",
                    desc=f"Tags: {', '.join(m.tags[:3] if m.tags else [])}",
                    author=m.modelId.split('/')[0],
                    tags=m.tags or []
                ))
        except Exception as e:
            print(f"  [HF Error] {e}")
        return items

# ==========================================
# HTML生成
# ==========================================
def generate_html(data_map: Dict[str, List[TrendItem]], filename: str):
    # カテゴリごとのデータ処理
    tabs_html = ""
    contents_html = ""
    
    # サイドバー用カテゴリリスト生成
    for idx, (cat_name, items) in enumerate(data_map.items()):
        # ID生成（スペース除去）
        safe_id = re.sub(r'[^a-zA-Z0-9]', '', cat_name)
        active_class = "active" if idx == 0 else ""
        display_style = "block" if idx == 0 else "none"
        
        # タブボタン
        tabs_html += f"""
        <div class="tab-item {active_class}" onclick="openTab(event, '{safe_id}')">
            {cat_name} <span class="badge">{len(items)}</span>
        </div>
        """
        
        # テーブル行生成
        rows = ""
        if not items:
            rows = "<tr><td colspan='4' style='text-align:center; padding:20px;'>No items found in this period.</td></tr>"
        else:
            for rank, item in enumerate(items, 1):
                icon = "fab fa-github" if "GitHub" in item.source else "fas fa-brain"
                color_class = "gh-color" if "GitHub" in item.source else "hf-color"
                tags_html = "".join([f'<span class="tag">{t}</span>' for t in item.tags[:4]])
                
                rows += f"""
                <tr>
                    <td>{rank}</td>
                    <td class="stars"><i class="fas fa-star" style="color:#f1c40f"></i> {item.stars}</td>
                    <td class="date">{item.date}</td>
                    <td>
                        <div class="title">
                            <i class="{icon} {color_class}"></i> 
                            <a href="{item.url}" target="_blank">{item.title}</a>
                        </div>
                        <div class="desc">{item.desc}</div>
                        <div class="tags-container">{tags_html}</div>
                    </td>
                </tr>
                """

        # コンテンツエリア
        contents_html += f"""
        <div id="{safe_id}" class="tab-content" style="display: {display_style};">
            <h2 class="section-title">{cat_name}</h2>
            <table>
                <thead>
                    <tr>
                        <th width="50">#</th>
                        <th width="80">Stars</th>
                        <th width="100">Date</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Comprehensive Time Series Trends</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f4f6f8; display: flex; height: 100vh; overflow: hidden; }}
            
            /* Sidebar */
            .sidebar {{ width: 280px; background: #2c3e50; color: #ecf0f1; display: flex; flex-direction: column; flex-shrink: 0; }}
            .sidebar-header {{ padding: 20px; background: #1a252f; text-align: center; border-bottom: 1px solid #34495e; }}
            .sidebar-header h1 {{ font-size: 1.2rem; margin: 0; }}
            .tab-list {{ overflow-y: auto; flex: 1; }}
            .tab-item {{ padding: 15px 20px; cursor: pointer; border-bottom: 1px solid #34495e; transition: 0.2s; display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; }}
            .tab-item:hover {{ background: #34495e; }}
            .tab-item.active {{ background: #3498db; color: white; border-left: 5px solid #2980b9; }}
            .badge {{ background: rgba(0,0,0,0.2); padding: 2px 8px; border-radius: 10px; font-size: 0.8em; }}
            
            /* Main Content */
            .main {{ flex: 1; overflow-y: auto; padding: 20px; background: #ecf0f1; }}
            .tab-content {{ background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); padding: 20px; animation: fadeIn 0.3s; }}
            .section-title {{ border-bottom: 2px solid #3498db; padding-bottom: 10px; color: #2c3e50; margin-top: 0; }}
            
            /* Table */
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background: #f8f9fa; color: #7f8c8d; font-weight: 600; text-align: left; padding: 12px; border-bottom: 2px solid #eee; }}
            td {{ padding: 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
            tr:hover {{ background: #fdfdfd; }}
            
            .title {{ font-size: 1.1em; font-weight: bold; margin-bottom: 5px; }}
            .title a {{ text-decoration: none; color: #2980b9; }}
            .desc {{ font-size: 0.9em; color: #666; margin-bottom: 8px; line-height: 1.4; }}
            .stars {{ font-weight: bold; color: #7f8c8d; }}
            .date {{ color: #95a5a6; font-size: 0.85em; }}
            
            .tag {{ display: inline-block; background: #eef2f7; color: #2980b9; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; margin-right: 5px; margin-bottom: 2px; }}
            
            .gh-color {{ color: #333; }}
            .hf-color {{ color: #f39c12; }}

            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        </style>
        <script>
            function openTab(evt, tabId) {{
                var i, tabcontent, tablinks;
                tabcontent = document.getElementsByClassName("tab-content");
                for (i = 0; i < tabcontent.length; i++) {{
                    tabcontent[i].style.display = "none";
                }}
                tablinks = document.getElementsByClassName("tab-item");
                for (i = 0; i < tablinks.length; i++) {{
                    tablinks[i].className = tablinks[i].className.replace(" active", "");
                }}
                document.getElementById(tabId).style.display = "block";
                evt.currentTarget.className += " active";
            }}
        </script>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <h1><i class="fas fa-chart-line"></i> TS Trend Hunter</h1>
                <div style="font-size:0.7em; opacity:0.7; margin-top:5px;">Comprehensive Report</div>
            </div>
            <div class="tab-list">
                {tabs_html}
            </div>
            <div style="padding:15px; font-size:0.8em; text-align:center; color:#95a5a6;">
                Generated: {datetime.datetime.now().strftime('%Y-%m-%d')}
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
    print(f"\n[Done] Report saved: {os.path.abspath(filename)}")

# ==========================================
# メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="時系列分析 総合トレンド収集ツール")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT_PER_CAT, help="1カテゴリあたりの取得数")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help="過去N日以内")
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"), help="GitHub Token")
    args = parser.parse_args()

    print(f"=== Time Series Comprehensive Scan (Last {args.days} days) ===")
    
    engine = SearchEngine(args.token)
    all_results = {}

    # カテゴリごとにループ処理
    for cat_name, queries in SEARCH_CATEGORIES.items():
        print(f"\n>> Scanning Category: {cat_name}")
        
        # 1. GitHub Search
        print(f"   - GitHub Query: '{queries['gh']}'")
        gh_items = engine.search_github(queries['gh'], args.limit, args.days)
        time.sleep(1) # API制限回避のための待機
        
        # 2. HF Search
        print(f"   - HF Query: '{queries['hf']}'")
        hf_items = engine.search_huggingface(queries['hf'], args.limit)
        
        # 統合
        combined = sorted(gh_items + hf_items, key=lambda x: x.stars, reverse=True)
        all_results[cat_name] = combined
        
        print(f"   -> Found {len(combined)} items.")

    # HTML生成
    generate_html(all_results, OUTPUT_FILE)
    webbrowser.open('file://' + os.path.realpath(OUTPUT_FILE))

if __name__ == "__main__":
    main()