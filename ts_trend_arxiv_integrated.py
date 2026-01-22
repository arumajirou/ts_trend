import argparse
import requests
import webbrowser
import os
import datetime
import time
import re
from typing import List, Dict, Set, Any
import arxiv
from huggingface_hub import HfApi

# ==========================================
# 1. 検索カテゴリ設定 (3つのソースに対応)
# ==========================================
SEARCH_CATEGORIES = {
    "1. Forecasting (予測)": {
        "gh": "time series forecasting", 
        "hf": "time-series-forecasting",
        "arxiv": 'all:"time series forecasting"'
    },
    "2. Anomaly Detection (異常検知)": {
        "gh": "time series anomaly detection", 
        "hf": "anomaly-detection",
        "arxiv": 'all:"time series anomaly detection"'
    },
    "3. Classification (分類)": {
        "gh": "time series classification", 
        "hf": "time-series-classification",
        "arxiv": 'all:"time series classification"'
    },
    "4. Foundation Models (基盤モデル)": {
        "gh": "time series foundation model OR large time series model", 
        "hf": "time-series-foundation-model",
        "arxiv": 'all:"time series" AND (all:"foundation model" OR all:"large language model" OR all:"pretrained")'
    },
    "5. Transformers": {
        "gh": "time series transformer", 
        "hf": "transformer time-series",
        "arxiv": 'all:"time series transformer"'
    },
    "6. Generation (生成)": {
        "gh": "time series generation synthetic", 
        "hf": "synthetic-time-series",
        "arxiv": 'all:"time series generation" OR all:"synthetic time series"'
    },
    "7. Preprocessing (前処理)": {
        "gh": "time series preprocessing imputation", 
        "hf": "imputation",
        "arxiv": 'all:"time series imputation" OR all:"missing value"'
    },
    "8. Finance (金融)": {
        "gh": "financial time series quantitative", 
        "hf": "financial-time-series",
        "arxiv": 'all:"financial time series" OR all:"quantitative trading"'
    }
}

# ==========================================
# 2. 自動タグ付けルール (共通)
# ==========================================
TAG_RULES = {
    "Supervised": ["supervised", "forecasting", "classification", "regression"],
    "Unsupervised": ["unsupervised", "anomaly detection", "clustering", "outlier", "self-supervised"],
    "RL": ["reinforcement learning", "rl", "gym", "agent", "reward"],
    "Deep Learning": ["deep learning", "neural network", "lstm", "rnn", "cnn", "transformer", "diffusion", "attention"],
    "Foundation Model": ["foundation model", "pretrained", "llm", "zero-shot", "few-shot", "generative"],
    "Statistical": ["arima", "ets", "prophet", "statistical", "bayesian", "stochastic"],
    "Code Available": ["github.com", "huggingface.co", "code available"] # 論文用
}

DEFAULT_DAYS_BACK = 365
DEFAULT_LIMIT_PER_CAT = 20
OUTPUT_FILE = "ts_trend_integrated_report.html"

# ==========================================
# データクラス
# ==========================================
class TrendItem:
    def __init__(self, source, title, url, score, date, desc, author, tags):
        self.source = source        # GitHub, HF Model, ArXiv
        self.title = title
        self.url = url
        self.score = score          # Stars, Likes, or 0 (ArXiv)
        self.date = date            # YYYY-MM-DD
        self.desc = desc or ""
        self.author = author
        self.tags = tags or []      # Original tags
        self.derived_tags = self._analyze_tags()

    def _analyze_tags(self) -> Set[str]:
        # 全テキストを結合して小文字化
        text = (str(self.title) + " " + str(self.desc) + " " + " ".join(self.tags)).lower()
        derived = set()
        
        for label, keywords in TAG_RULES.items():
            for kw in keywords:
                if kw in text:
                    derived.add(label)
                    break
        
        # ソース別のデフォルトタグ
        if self.source == "ArXiv" and "github.com" in text:
            derived.add("Code Available")
            
        return derived

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
        final_query = f"{query} created:>{since}"
        items = []
        try:
            params = {"q": final_query, "sort": "stars", "order": "desc", "per_page": min(limit, 100)}
            resp = requests.get("https://api.github.com/search/repositories", headers=self.gh_headers, params=params, timeout=10)
            if resp.status_code == 200:
                for repo in resp.json().get("items", [])[:limit]:
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
                    "Recent", f"Task: {m.pipeline_tag}", m.modelId.split('/')[0], m.tags
                ))
        except Exception as e:
            print(f"  [HF Error] {e}")
        return items

    def search_arxiv(self, query: str, limit: int) -> List[TrendItem]:
        items = []
        try:
            search = arxiv.Search(
                query=query,
                max_results=limit,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            for r in self.arxiv_client.results(search):
                # 要約の整形
                summary = r.summary.replace("\n", " ")
                # 論文は「Star」がないため、便宜上 0 とするが、最新順に並ぶ
                items.append(TrendItem(
                    "ArXiv", r.title, r.entry_id, 0,
                    r.published.strftime("%Y-%m-%d"), summary, 
                    ", ".join([a.name for a in r.authors[:2]]), []
                ))
        except Exception as e:
            print(f"  [ArXiv Error] {e}")
        return items

# ==========================================
# HTML生成
# ==========================================
def generate_html(data_map: Dict[str, List[TrendItem]], filename: str):
    
    # フィルタボタン定義
    filter_html = """
    <div class="filter-group">
        <span class="filter-label">Source:</span>
        <button class="filter-btn active" onclick="filterSource('all')">All</button>
        <button class="filter-btn" onclick="filterSource('GitHub')">GitHub</button>
        <button class="filter-btn" onclick="filterSource('HF')">HuggingFace</button>
        <button class="filter-btn" onclick="filterSource('ArXiv')">ArXiv</button>
    </div>
    <div class="filter-group" style="margin-top:10px;">
        <span class="filter-label">Method:</span>
        <button class="filter-btn active" onclick="filterTag('all')">All</button>
    """
    for tag in TAG_RULES.keys():
        safe_tag = tag.replace(" ", "-")
        filter_html += f'<button class="filter-btn" onclick="filterTag(\'{safe_tag}\')">{tag}</button>'
    filter_html += "</div>"

    tabs_html = ""
    contents_html = ""
    
    for idx, (cat_name, items) in enumerate(data_map.items()):
        safe_id = re.sub(r'[^a-zA-Z0-9]', '', cat_name)
        active_class = "active" if idx == 0 else ""
        display_style = "block" if idx == 0 else "none"
        
        tabs_html += f'<div class="tab-item {active_class}" onclick="openTab(event, \'{safe_id}\')">{cat_name} <span class="badge">{len(items)}</span></div>'
        
        rows = ""
        for rank, item in enumerate(items, 1):
            # アイコンと色設定
            if item.source == "GitHub":
                icon, color, source_cls = "fab fa-github", "#24292e", "src-GitHub"
                score_display = f'<i class="fas fa-star" style="color:#f1c40f"></i> {item.score}'
            elif "HF" in item.source:
                icon, color, source_cls = "fas fa-brain", "#ff9d00", "src-HF"
                score_display = f'<i class="fas fa-heart" style="color:#e74c3c"></i> {item.score}'
            else: # ArXiv
                icon, color, source_cls = "fas fa-graduation-cap", "#b31b1b", "src-ArXiv"
                score_display = '<span style="color:#777; font-size:0.8em;">Paper</span>'

            # タグ生成
            tags_html = "".join([f'<span class="tag">{t}</span>' for t in item.derived_tags])
            
            # クラス付与 (フィルタ用)
            tag_classes = " ".join([t.replace(" ", "-") for t in item.derived_tags])
            
            rows += f"""
            <tr class="item-row {source_cls} {tag_classes}">
                <td>{rank}</td>
                <td style="white-space:nowrap;">{score_display}</td>
                <td class="date">{item.date}</td>
                <td>
                    <div class="title">
                        <i class="{icon}" style="color:{color}"></i> 
                        <a href="{item.url}" target="_blank">{item.title}</a>
                    </div>
                    <div class="desc">{item.desc[:300]}...</div>
                    <div class="tags-container">{tags_html}</div>
                </td>
            </tr>
            """
            
        contents_html += f"""
        <div id="{safe_id}" class="tab-content" style="display: {display_style};">
            <h2 class="section-title">{cat_name}</h2>
            <div class="control-panel">{filter_html}</div>
            <table>
                <thead><tr><th width="40">#</th><th width="80">Score</th><th width="100">Date</th><th>Details</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            <div class="no-results" style="display:none; text-align:center; padding:20px; color:#999;">No matching items.</div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>TS Trend Integrated Report</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f0f2f5; display: flex; height: 100vh; overflow: hidden; }}
            .sidebar {{ width: 250px; background: #2c3e50; color: #ecf0f1; display: flex; flex-direction: column; flex-shrink: 0; }}
            .sidebar-header {{ padding: 20px; background: #1a252f; text-align: center; }}
            .tab-list {{ overflow-y: auto; flex: 1; }}
            .tab-item {{ padding: 15px; cursor: pointer; border-bottom: 1px solid #34495e; font-size: 0.9em; }}
            .tab-item.active {{ background: #3498db; border-left: 5px solid #2980b9; }}
            .badge {{ background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 10px; font-size: 0.8em; float: right; }}
            
            .main {{ flex: 1; overflow-y: auto; padding: 20px; }}
            .tab-content {{ background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); padding: 20px; }}
            .control-panel {{ background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px; border: 1px solid #eee; }}
            .filter-group {{ margin-bottom: 5px; }}
            .filter-label {{ font-weight: bold; font-size: 0.85em; color: #555; margin-right: 10px; min-width: 60px; display: inline-block; }}
            .filter-btn {{ background: white; border: 1px solid #ddd; padding: 4px 10px; border-radius: 15px; cursor: pointer; font-size: 0.8em; margin-right: 5px; color: #555; }}
            .filter-btn.active {{ background: #3498db; color: white; border-color: #3498db; }}
            
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #f1f2f6; padding: 10px; text-align: left; color: #777; font-size: 0.9em; }}
            td {{ padding: 12px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
            .title a {{ text-decoration: none; color: #2980b9; font-weight: bold; font-size: 1.05em; }}
            .desc {{ font-size: 0.9em; color: #555; margin: 5px 0; }}
            .tag {{ background: #eef2f7; color: #2980b9; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-right: 4px; display: inline-block; }}
            .date {{ font-size: 0.85em; color: #999; }}
        </style>
        <script>
            let currentSource = 'all';
            let currentTag = 'all';

            function openTab(evt, tabId) {{
                let tabs = document.getElementsByClassName("tab-content");
                for (let i = 0; i < tabs.length; i++) tabs[i].style.display = "none";
                let links = document.getElementsByClassName("tab-item");
                for (let i = 0; i < links.length; i++) links[i].className = links[i].className.replace(" active", "");
                document.getElementById(tabId).style.display = "block";
                evt.currentTarget.className += " active";
                applyFilters();
            }}

            function filterSource(source) {{
                currentSource = source;
                updateBtnState('filter-group', 0, source); // 簡易実装: インデックス0のグループ
                applyFilters();
            }}

            function filterTag(tag) {{
                currentTag = tag;
                updateBtnState('filter-group', 1, tag); // インデックス1のグループ
                applyFilters();
            }}
            
            function updateBtnState(groupClass, groupIndex, value) {{
                let groups = document.querySelectorAll('.' + groupClass);
                if (groups[groupIndex]) {{
                    let btns = groups[groupIndex].querySelectorAll('.filter-btn');
                    btns.forEach(btn => {{
                        if (btn.innerText.toLowerCase() === value.replace('-',' ').toLowerCase() || 
                           (value === 'HF' && btn.innerText === 'HuggingFace') ||
                           (value === 'all' && btn.innerText === 'All')) {{
                            btn.classList.add('active');
                        }} else {{
                            btn.classList.remove('active');
                        }}
                    }});
                }}
            }}

            function applyFilters() {{
                let activeTab = document.querySelector('.tab-content[style*="block"]');
                if (!activeTab) return;
                
                let rows = activeTab.getElementsByClassName("item-row");
                let visibleCount = 0;

                for (let row of rows) {{
                    let matchSource = (currentSource === 'all') || row.classList.contains('src-' + currentSource);
                    let matchTag = (currentTag === 'all') || row.classList.contains(currentTag);
                    
                    if (matchSource && matchTag) {{
                        row.style.display = "";
                        visibleCount++;
                    }} else {{
                        row.style.display = "none";
                    }}
                }}
                activeTab.querySelector('.no-results').style.display = visibleCount === 0 ? "block" : "none";
            }}
        </script>
    </head>
    <body>
        <div class="sidebar">
            <div class="sidebar-header">
                <h3><i class="fas fa-layer-group"></i> Trend Hunter</h3>
                <small>GitHub / HF / ArXiv</small>
            </div>
            <div class="tab-list">{tabs_html}</div>
        </div>
        <div class="main">{contents_html}</div>
    </body>
    </html>
    """
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[Success] Report generated: {os.path.abspath(filename)}")

# ==========================================
# メイン
# ==========================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT_PER_CAT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK)
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()

    engine = SearchEngine(args.token)
    all_results = {}

    print(f"=== TS Trend Hunter: Integrated Edition (Last {args.days} days) ===")
    
    for cat_name, queries in SEARCH_CATEGORIES.items():
        print(f"\n>> Scanning: {cat_name}")
        items = []
        
        # 1. GitHub
        gh = engine.search_github(queries['gh'], args.limit, args.days)
        print(f"   GitHub: {len(gh)}")
        items.extend(gh)
        time.sleep(0.5)
        
        # 2. Hugging Face
        hf = engine.search_huggingface(queries['hf'], args.limit)
        print(f"   HF:     {len(hf)}")
        items.extend(hf)
        
        # 3. ArXiv
        ax = engine.search_arxiv(queries['arxiv'], args.limit)
        print(f"   ArXiv:  {len(ax)}")
        items.extend(ax)
        
        # ソート: GitHubのStar数などを考慮しつつ、ArXivは新しいものなら上位に来るように調整も可能だが
        # シンプルに Star/Score 順で並べ、ArXiv(Score=0)は後方、またはフィルタで見る運用とする。
        # ただしArXiv論文に「Code Available」タグがついている場合はスコアを少し盛るなどの工夫も可能。
        
        all_results[cat_name] = sorted(items, key=lambda x: x.score, reverse=True)

    generate_html(all_results, OUTPUT_FILE)
    webbrowser.open('file://' + os.path.realpath(OUTPUT_FILE))

if __name__ == "__main__":
    main()