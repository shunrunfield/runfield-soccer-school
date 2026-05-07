"""
せっかく掲示板 RSS取得スクリプト
毎日1回 GitHub Actions から実行され、data/announcements.json を更新します。
"""
import urllib.request
import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime, timezone

RSS_URL = "https://bbs6.sekkaku.net/bbs/soccer75/mode=rss"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'announcements.json')

def fetch_rss():
    # User-Agentを明示して1日1回の定期取得であることを示す
    req = urllib.request.Request(
        RSS_URL,
        headers={'User-Agent': 'ASC-RunField-Site/1.0 (daily scheduled fetch, 1x/day)'}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

def parse_rss(xml_data):
    root = ET.fromstring(xml_data)
    channel = root.find('channel')
    items = []
    for item in channel.findall('item'):
        title = item.findtext('title', '').strip()
        link = item.findtext('link', '').strip()
        description = item.findtext('description', '').strip()
        pub_date = item.findtext('pubDate', '').strip()
        items.append({
            'title': title,
            'link': link,
            'description': description,
            'pubDate': pub_date,
        })
    return items

def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    xml_data = fetch_rss()
    items = parse_rss(xml_data)
    output = {
        'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'items': items,
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(items)} 件取得")

if __name__ == '__main__':
    main()
