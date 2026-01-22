import argparse
import requests
import webbrowser
import os
import datetime
from typing import List, Dict, Any
# 修正箇所: ModelFilter, DatasetFilter を削除し、HfApi のみにしました
from huggingface_hub import HfApi

# ==========================================
# 設定・定数
# ==========================================
DEFAULT_DAYS_BACK = 365  # 過去何日以内のプロジェクトを対象にするか
DEFAULT_LIMIT = 50       # 各ソースごとの取得件数
OUTPUT_FILE = "timeseries_trend_report.html"

# ==========================================
# 基底クラス・共通データ構造
# ==========================================
class TrendItem:
    def __init__(self, source, title, url, stars, date, desc, author, tags):
        self.source = source        # 'GitHub' or 'HuggingFace'
        self.title = title
        self.url = url
        self.stars = stars          # GitHub: Stars, HF: Likes
        self.date = date            # YYYY-MM-DD
        self.desc = desc or "No description provided."
        self.author = author
        self.tags = tags            # List of strings

    def to_dict(self):
        return self.__dict__

# ==========================================
# GitHub検索ロジック
# ==========================================
class GitHubSearcher:
    def __init__(self, token=None):
        self.api_url = "https://api.github.com/search/repositories"
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"

    def search(self, query: str, limit: int, days_back: int) -> List[TrendItem]:
        print(f"[{datetime.datetime.now()}] Searching GitHub for '{query}'...")
        
        since_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime('%Y-%m-%d')
        final_query = f"{query} created:>{since_date}"
        
        params = {
            "q": final_query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(limit, 100)
        }

        items = []
        try:
            page = 1
            while len(items) < limit:
                params["page"] = page
                response = requests.get(self.api_url, headers=self.headers, params=params, timeout=10)
                
                if response.status_code != 200:
                    print(f"GitHub API Error: {response.status_code}")
                    break
                
                data = response.json()
                if "items" not in data or not data["items"]:
                    break
                
                for repo in data["items"]:
                    desc = repo.get("description", "") or ""
                    item = TrendItem(
                        source="GitHub",
                        title=repo["full_name"],
                        url=repo["html_url"],
                        stars=repo["stargazers_count"],
                        date=repo["created_at"][:10],
                        desc=desc,
                        author=repo["owner"]["login"],
                        tags=[t for t in repo.get("topics", [])]
                    )
                    items.append(item)
                    if len(items) >= limit:
                        break
                page += 1
                
        except Exception as e:
            print(f"GitHub Search Failed: {e}")
            
        return items

# ==========================================
# Hugging Face検索ロジック
# ==========================================
class HuggingFaceSearcher:
    def __init__(self):
        self.api = HfApi()

    def search(self, limit: int, days_back: int) -> List[TrendItem]:
        print(f"[{datetime.datetime.now()}] Searching Hugging Face (Models & Datasets)...")
        
        items = []
        # 検索タグ（時系列関連）
        target_tags = ["time-series", "time-series-forecasting", "tabular-classification"]
        
        # --- Models Search ---
        try:
            # ModelFilterクラスを使わず、直接リストを渡す形式に変更
            models = self.api.list_models(
                filter=target_tags,
                sort="likes",
                direction=-1,
                limit=limit
            )
            
            for m in models:
                likes = getattr(m, 'likes', 0)
                
                # パイプラインタグの取得（安全策）
                pipeline = m.pipeline_tag if hasattr(m, 'pipeline_tag') else "unknown"
                tags = m.tags if hasattr(m, 'tags') else []
                author = m.author if hasattr(m, 'author') and m.author else m.modelId.split('/')[0]

                items.append(TrendItem(
                    source="HuggingFace (Model)",
                    title=m.modelId,
                    url=f"https://huggingface.co/{m.modelId}",
                    stars=likes,
                    date="Recent",
                    desc=f"Task: {pipeline}",
                    author=author,
                    tags=tags
                ))
        except Exception as e:
            print(f"HF Models Search Failed: {e}")

        # --- Datasets Search ---
        try:
            datasets = self.api.list_datasets(
                filter="time-series",
                sort="likes",
                direction=-1,
                limit=limit // 2
            )
            
            for d in datasets:
                likes = getattr(d, 'likes', 0)
                author = d.author if hasattr(d, 'author') and d.author else d.id.split('/')[0]
                tags = d.tags if hasattr(d, 'tags') else []

                items.append(TrendItem(
                    source="HuggingFace (Dataset)",
                    title=d.id,
                    url=f"https://huggingface.co/datasets/{d.id}",
                    stars=likes,
                    date="Recent",
                    desc="Time Series Dataset",
                    author=author,
                    tags=tags
                ))
        except Exception as e:
            print(f"HF Datasets Search Failed: {e}")

        return sorted(items, key=lambda x: x.stars, reverse=True)[:limit]

# ==========================================
# HTMLレポート生成
# ==========================================
def generate_html(gh_items: List[TrendItem], hf_items: List[TrendItem], filename: str):
    
    def create_table_rows(items):
        rows = ""
        for idx, item in enumerate(items, 1):
            tags_html = "".join([f'<span class="tag">{t}</span>' for t in item.tags[:5]])
            icon = "fab fa-github" if "GitHub" in item.source else "fas fa-brain"
            color_class = "gh-color" if "GitHub" in item.source else "hf-color"
            
            rows += f"""
            <tr>
                <td>{idx}</td>
                <td class="stars"><i class="fas fa-star" style="color:#e6ac00"></i> {item.stars}</td>
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
        return rows

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Time Series Analysis Trends</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; background: #f5f7fa; color: #333; }}
            header {{ background: #2b3137; color: white; padding: 20px; text-align: center; }}
            h1 {{ margin: 0; font-size: 1.8rem; }}
            .container {{ max-width: 1200px; margin: 20px auto; padding: 0 20px; }}
            .tabs {{ display: flex; cursor: pointer; background: white; border-radius: 8px 8px 0 0; overflow: hidden; margin-top: 20px; }}
            .tab {{ flex: 1; padding: 15px; text-align: center; font-weight: bold; background: #eee; border-bottom: 3px solid transparent; transition: 0.3s; }}
            .tab:hover {{ background: #e1e4e8; }}
            .tab.active {{ background: white; border-bottom: 3px solid #0366d6; color: #0366d6; }}
            .content {{ display: none; background: white; padding: 20px; border-radius: 0 0 8px 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
            .content.active {{ display: block; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }}
            th {{ background-color: #f8f9fa; color: #666; font-size: 0.9em; }}
            tr:hover {{ background-color: #fcfcfc; }}
            .title a {{ text-decoration: none; color: #0366d6; font-weight: bold; font-size: 1.1em; }}
            .desc {{ font-size: 0.9em; color: #555; margin-top: 5px; max-width: 800px; }}
            .stars {{ font-weight: bold; width: 80px; }}
            .date {{ color: #888; font-size: 0.85em; width: 100px; }}
            .tags-container {{ margin-top: 8px; }}
            .tag {{ background: #eff3f6; color: #0366d6; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; margin-right: 5px; display: inline-block; }}
            .gh-color {{ color: #24292e; }}
            .hf-color {{ color: #ff9d00; }}
        </style>
        <script>
            function openTab(tabName) {{
                var i;
                var x = document.getElementsByClassName("content");
                for (i = 0; i < x.length; i++) {{ x[i].style.display = "none"; }}
                var tabs = document.getElementsByClassName("tab");
                for (i = 0; i < tabs.length; i++) {{ tabs[i].classList.remove("active"); }}
                document.getElementById(tabName).style.display = "block";
                document.getElementById("btn-" + tabName).classList.add("active");
            }}
        </script>
    </head>
    <body>
        <header>
            <h1><i class="fas fa-chart-line"></i> Time Series Analysis Trends</h1>
            <p style="font-size: 0.9em; opacity: 0.8;">Latest & Trending Resources from GitHub & Hugging Face</p>
        </header>

        <div class="container">
            <div class="tabs">
                <div id="btn-github" class="tab active" onclick="openTab('github')"><i class="fab fa-github"></i> GitHub Repositories ({len(gh_items)})</div>
                <div id="btn-hf" class="tab" onclick="openTab('hf')"><i class="fas fa-brain"></i> Hugging Face Models ({len(hf_items)})</div>
            </div>

            <div id="github" class="content active">
                <table>
                    <thead>
                        <tr>
                            <th width="50">#</th>
                            <th>Stars</th>
                            <th>Created</th>
                            <th>Repository Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {create_table_rows(gh_items)}
                    </tbody>
                </table>
            </div>

            <div id="hf" class="content">
                <table>
                    <thead>
                        <tr>
                            <th width="50">#</th>
                            <th>Likes</th>
                            <th>Date</th>
                            <th>Model / Dataset Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {create_table_rows(hf_items)}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[Success] Report generated: {os.path.abspath(filename)}")

# ==========================================
# メイン実行関数
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="時系列データ分析トレンド検索ツール (GitHub & Hugging Face)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="各ソースの検索上限数")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help="検索対象とする期間（過去N日以内）")
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"), help="GitHub API Token")
    parser.add_argument("--query", type=str, default="time series", help="GitHub検索用キーワード")
    
    args = parser.parse_args()
    
    print("=== Time Series Trend Hunter ===")
    
    gh_searcher = GitHubSearcher(token=args.token)
    gh_results = gh_searcher.search(query=args.query, limit=args.limit, days_back=args.days)
    
    hf_searcher = HuggingFaceSearcher()
    hf_results = hf_searcher.search(limit=args.limit, days_back=args.days)
    
    generate_html(gh_results, hf_results, OUTPUT_FILE)
    
    webbrowser.open('file://' + os.path.realpath(OUTPUT_FILE))

if __name__ == "__main__":
    main()