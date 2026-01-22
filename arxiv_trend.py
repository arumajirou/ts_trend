import argparse
import arxiv
import requests
import re
import webbrowser
import os
import datetime
import time
import sys
from typing import List, Dict, Set, Optional

# ==========================================
# デフォルト設定 (引数で上書き可能)
# ==========================================
DEFAULT_QUERY = 'all:"time series" OR all:"time-series" OR all:"forecasting" OR all:"temporal"'
DEFAULT_LIMIT = 500
DEFAULT_OUTPUT = "arxiv_trending_timeseries.html"

# ==========================================
# クラス: GitHub API分析
# ==========================================
class GitHubAnalyzer:
    def __init__(self, token: Optional[str] = None):
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        self.token = token or os.environ.get("GITHUB_TOKEN")
        
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
            # トークンの一部を隠して表示
            masked_token = self.token[:4] + "..." + self.token[-4:] if len(self.token) > 8 else "***"
            print(f"INFO: GitHub API Token set ({masked_token}). Rate limit is 5000 req/hr.")
        else:
            print("WARNING: No GitHub Token set. Using unauthenticated requests.")
            print("         Rate limit is strict (60 req/hr). Stars might be displayed as N/A (-1).")

    def get_repo_details(self, url: str) -> Dict:
        """
        URLからリポジトリ情報を取得する
        戻り値: {'stars': int, 'desc': str, 'valid': bool}
        """
        pattern = r'github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)'
        match = re.search(pattern, url)
        
        if not match:
            return {'stars': 0, 'valid': False}

        owner, repo = match.groups()
        repo = repo.replace('.git', '').rstrip('.')
        
        # 誤検知除外リスト
        if repo.lower() in ['orgs', 'topics', 'site', 'blog', 'about']:
            return {'stars': 0, 'valid': False}

        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        
        try:
            response = requests.get(api_url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'stars': data.get('stargazers_count', 0),
                    'desc': data.get('description', ''),
                    'valid': True,
                    'api_url': api_url
                }
            elif response.status_code == 404:
                return {'stars': 0, 'valid': False}
            elif response.status_code == 403:
                # レート制限などで取得できない場合
                print(f"WARN: API limit hit for {url}")
                return {'stars': -1, 'valid': True} # 有効だがスター数不明
            else:
                return {'stars': 0, 'valid': False}
        except Exception as e:
            # ネットワークエラー等はスキップ
            return {'stars': 0, 'valid': False}

# ==========================================
# 関数: リンク抽出・HTML生成
# ==========================================
def extract_links(text: str) -> Set[str]:
    """テキストからGitHub/HuggingFaceのリンクを抽出"""
    if not text:
        return set()
    
    links = set()
    # GitHub
    gh_matches = re.findall(r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)', text)
    for m in gh_matches:
        user, repo = m
        repo = repo.rstrip('.,;)]}') 
        links.add(f"https://github.com/{user}/{repo}")

    # Hugging Face
    hf_matches = re.findall(r'(?:https?://)?huggingface\.co/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)', text)
    for m in hf_matches:
        user, repo = m
        repo = repo.rstrip('.,;)]}')
        links.add(f"https://huggingface.co/{user}/{repo}")
        
    return links

def generate_html(papers: List[Dict], filename: str, query: str, limit: int):
    """HTMLレポートを作成"""
    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>ArXiv Trends: {query}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f4f7f6; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
            h1 {{ border-bottom: 3px solid #007bff; padding-bottom: 10px; color: #2c3e50; font-size: 1.8em; }}
            .meta-info {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 25px; font-size: 0.9em; }}
            .card {{ border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; margin-bottom: 20px; background: #fff; transition: all 0.2s ease; }}
            .card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); border-color: #007bff; }}
            .header-row {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
            .title {{ font-size: 1.3em; font-weight: bold; margin: 0 0 5px 0; color: #34495e; }}
            .title a {{ text-decoration: none; color: inherit; }}
            .title a:hover {{ color: #007bff; }}
            .authors {{ color: #666; font-size: 0.9em; margin-bottom: 10px; }}
            .badges {{ display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }}
            .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
            .date-badge {{ background: #e2e6ea; color: #495057; }}
            .star-badge {{ background: #fff3cd; color: #856404; border: 1px solid #ffeeba; display: flex; align-items: center; gap: 5px; }}
            .summary {{ font-size: 0.95em; line-height: 1.6; color: #555; background: #f8f9fa; padding: 10px; border-radius: 4px; border-left: 4px solid #dee2e6; }}
            .actions {{ margin-top: 15px; display: flex; gap: 10px; }}
            .btn {{ text-decoration: none; padding: 8px 16px; border-radius: 5px; font-size: 0.9em; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; transition: background 0.2s; }}
            .btn-arxiv {{ background-color: #b31b1b; color: white; }}
            .btn-arxiv:hover {{ background-color: #8e1616; }}
            .btn-code {{ background-color: #24292e; color: white; }}
            .btn-code:hover {{ background-color: #1b1f23; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1><i class="fas fa-search"></i> ArXiv Trend Report</h1>
            <div class="meta-info">
                <strong>Query:</strong> {query}<br>
                <strong>Scanned:</strong> Latest {limit} papers<br>
                <strong>Generated:</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
    """

    if not papers:
        html += "<p style='text-align:center; padding:50px; color:#777;'>条件に一致するコード付きの論文は見つかりませんでした。</p>"
    else:
        for rank, paper in enumerate(papers, 1):
            star_display = f"{paper['stars']}" if paper['stars'] >= 0 else "N/A"
            icon = "fab fa-github" if paper['repo_type'] == 'GitHub' else "fas fa-laptop-code"
            
            html += f"""
            <div class="card">
                <div class="header-row">
                    <div style="flex: 1;">
                        <div class="badges">
                            <span class="badge date-badge"><i class="far fa-calendar-alt"></i> {paper['date']}</span>
                            <span style="color:#888; font-size:0.9em;">Rank #{rank}</span>
                        </div>
                        <h2 class="title"><a href="{paper['arxiv_url']}" target="_blank">{paper['title']}</a></h2>
                        <div class="authors">{paper['authors']}</div>
                    </div>
                    <div class="badge star-badge">
                        <i class="fas fa-star"></i> {star_display}
                    </div>
                </div>
                <div class="summary">
                    {paper['summary']}
                </div>
                <div class="actions">
                    <a href="{paper['arxiv_url']}" target="_blank" class="btn btn-arxiv"><i class="fas fa-file-pdf"></i> ArXiv</a>
                    <a href="{paper['code_url']}" target="_blank" class="btn btn-code"><i class="{icon}"></i> Code</a>
                </div>
            </div>
            """

    html += """
        </div>
    </body>
    </html>
    """
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n[Done] Report saved to: {os.path.abspath(filename)}")

# ==========================================
# メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser(
        description='ArXivからコード付きの最新トレンド論文を検索・分析するツール'
    )
    
    parser.add_argument('-q', '--query', type=str, default=DEFAULT_QUERY,
                        help=f'検索クエリ (default: "{DEFAULT_QUERY}")')
    
    parser.add_argument('-n', '--limit', type=int, default=DEFAULT_LIMIT,
                        help=f'検索する論文の最大数 (default: {DEFAULT_LIMIT})')
    
    parser.add_argument('-o', '--output', type=str, default=DEFAULT_OUTPUT,
                        help=f'出力HTMLファイル名 (default: "{DEFAULT_OUTPUT}")')
    
    parser.add_argument('--token', type=str, default=None,
                        help='GitHub API Token (環境変数 GITHUB_TOKEN も使用可能)')
    
    parser.add_argument('--no-browser', action='store_true',
                        help='処理完了後にブラウザを自動で開かない')

    args = parser.parse_args()

    # --- 処理開始 ---
    print(f"[{datetime.datetime.now()}] Starting ArXiv Scan")
    print(f"Query: {args.query}")
    print(f"Limit: {args.limit} papers")

    # APIクライアント初期化
    arxiv_client = arxiv.Client()
    gh_analyzer = GitHubAnalyzer(args.token)
    
    # 検索設定
    search = arxiv.Search(
        query=args.query,
        max_results=args.limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    
    results = arxiv_client.results(search)
    
    papers_with_code = []
    checked_urls = set()
    count = 0
    
    try:
        for result in results:
            count += 1
            if count % 50 == 0:
                print(f"Scanning... {count}/{args.limit}")

            # タイトル+要約+コメントから検索
            text_to_scan = f"{result.title} {result.summary} {result.comment or ''}"
            found_links = extract_links(text_to_scan)
            
            if not found_links:
                continue

            # ベストなリンクを選定
            best_link = None
            max_stars = -1
            
            for link in found_links:
                if link in checked_urls: continue
                checked_urls.add(link)

                if "github.com" in link:
                    # トークンなしの場合は少しwaitを入れる
                    if not gh_analyzer.token: time.sleep(0.5)
                    
                    repo = gh_analyzer.get_repo_details(link)
                    if repo['valid']:
                        stars = repo['stars']
                        # 比較用スコア（エラーの場合は0扱い）
                        score = stars if stars >= 0 else 0
                        
                        if score > max_stars:
                            max_stars = score
                            best_link = {'url': link, 'stars': stars, 'type': 'GitHub'}
                
                elif "huggingface.co" in link:
                    # GitHubが見つかってない場合のみHFを採用
                    if max_stars < 0:
                        max_stars = 0
                        best_link = {'url': link, 'stars': 0, 'type': 'HuggingFace'}

            if best_link:
                papers_with_code.append({
                    'title': result.title,
                    'date': result.published.strftime("%Y-%m-%d"),
                    'authors': ", ".join([a.name for a in result.authors[:3]]),
                    'summary': result.summary,
                    'arxiv_url': result.entry_id,
                    'code_url': best_link['url'],
                    'stars': best_link['stars'],
                    'repo_type': best_link['type']
                })
                # 短くログ出力
                sys.stdout.write(f"\rFound: {len(papers_with_code)} papers (Latest: {result.title[:20]}...)")
                sys.stdout.flush()

    except Exception as e:
        print(f"\nError occurred: {e}")
    except KeyboardInterrupt:
        print("\nInterrupted by user. Generating report with current data...")

    print(f"\n\nTotal papers with code found: {len(papers_with_code)}")
    
    # ソート: スター数(降順) -> 日付(降順)
    sorted_papers = sorted(papers_with_code, key=lambda x: (x['stars'], x['date']), reverse=True)
    
    # HTML生成
    generate_html(sorted_papers, args.output, args.query, args.limit)
    
    # ブラウザ起動
    if not args.no_browser:
        webbrowser.open('file://' + os.path.realpath(args.output))

if __name__ == "__main__":
    main()