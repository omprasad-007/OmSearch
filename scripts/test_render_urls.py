import urllib.request
import urllib.parse
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

import sys

base_host = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
queries = ['fastapi', 'react', 'machine learning', 'quantum', 'docker', 'database', 'artificial intelligence', 'python']
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for q in queries:
    search_url = f'{base_host}/api/v1/search?q={urllib.parse.quote(q)}'
    req = urllib.request.Request(search_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error querying {q}: {e}")
        continue

    results = data.get('results', [])
    print(f"\n=== Query: {q} ({len(results)} results) ===")
    for r in results[:4]:
        url = r.get('url', '')
        # Check HTTP status of target URL
        status_code = None
        try:
            head_req = urllib.request.Request(url, headers=headers, method='HEAD')
            with urllib.request.urlopen(head_req, timeout=5, context=ctx) as head_resp:
                status_code = head_resp.status
        except urllib.error.HTTPError as he:
            status_code = he.code
        except Exception as e:
            status_code = str(e)[:30]

        print(f"  [{status_code}] {r.get('title')}", flush=True)
        print(f"       URL: {url}", flush=True)
