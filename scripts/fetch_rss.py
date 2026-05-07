"""
せっかく掲示板 RSS取得スクリプト
毎日1回 GitHub Actions から実行され、data/announcements.json を更新します。
"""
import urllib.request
import xml.etree.ElementTree as ET
import json
import os
import re
import time
from datetime import datetime, timezone
from html import unescape

RSS_URL = "https://bbs6.sekkaku.net/bbs/soccer75/mode=rss"
BOARD_URL = "https://bbs6.sekkaku.net/bbs/soccer75/"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'announcements.json')
REQUEST_DELAY_SECONDS = 3
USER_AGENT = "ASC-RunField-Site/1.0 (daily scheduled fetch, contact: site maintainer)"


def fetch_url(url):
    # User-Agentを明示して定期取得の目的を示す
    req = urllib.request.Request(
        url,
        headers={'User-Agent': USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read(), response.headers.get_content_charset()


def decode_bytes(data, charset=None):
    if charset:
        try:
            return data.decode(charset)
        except UnicodeDecodeError:
            pass

    head = data[:2048].decode('ascii', errors='ignore')
    match = re.search(r'charset=["\']?([A-Za-z0-9_\-]+)', head, re.I)
    candidates = [match.group(1)] if match else []
    candidates.extend(['utf-8', 'cp932', 'euc_jp'])
    for enc in candidates:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode('utf-8', errors='replace')


def fetch_rss():
    data, _ = fetch_url(RSS_URL)
    return data

def parse_rss(xml_data):
    root = ET.fromstring(xml_data)
    channel = root.find('channel')
    items = []
    for item in channel.findall('item'):
        title = item.findtext('title', '').strip()
        link = item.findtext('link', '').strip()
        description = item.findtext('description', '').strip()
        pub_date = item.findtext('pubDate', '').strip()
        guid = item.findtext('guid', '').strip()
        parsed = {
            'title': title,
            'link': link,
            'description': description,
            'pubDate': pub_date,
        }
        if guid:
            parsed['guid'] = guid
        items.append(parsed)
    return items


def looks_truncated(text):
    plain = unescape(re.sub(r'<[^>]*>', '', text or '')).strip()
    return plain.endswith('...') or plain.endswith('…')


def normalize_text(text):
    text = unescape(text or '')
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]*>', '', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t\u3000]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def normalize_key(text):
    return re.sub(r'\s+', '', normalize_text(text))


def parse_board_posts(html_text):
    post_re = re.compile(
        r'\[\s*(?:No\.)?(?P<no>\d+)\s*\].*?'
        r'(?:題名|タイトル)[：:]\s*(?P<title>.*?)\s+名前[：:].*?'
        r'</p>\s*<blockquote[^>]*>\s*(?P<body>.*?)</blockquote>',
        re.I | re.S,
    )

    posts = []
    for match in post_re.finditer(html_text):
        title = normalize_text(match.group('title'))
        body = cleanup_board_body(match.group('body'))
        if not body:
            continue
        posts.append({
            'no': match.group('no'),
            'title': title,
            'body': body,
        })
    return posts


def cleanup_board_body(body):
    lines = []
    skip_prefixes = (
        'この掲示板をサポートする',
        'このページを通報する',
        '管理人へ連絡',
        'SYSTEM BY',
        'TOPに戻る',
    )
    for line in normalize_text(body).splitlines():
        line = line.strip()
        if not line or any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def enrich_truncated_items(items):
    if not any(looks_truncated(item.get('description', '')) for item in items):
        return items

    # 掲示板への負荷を抑えるため、RSS取得後にトップページを1回だけ取得して照合する。
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        html_data, charset = fetch_url(BOARD_URL)
        posts = parse_board_posts(decode_bytes(html_data, charset))
    except Exception as exc:
        print(f"WARN: 掲示板本文の追加取得に失敗したためRSS本文を使用します: {exc}")
        return items

    if not posts:
        print("WARN: 掲示板本文を抽出できなかったためRSS本文を使用します")
        return items

    posts_by_title = {normalize_key(post['title']): post for post in posts}
    for item in items:
        if not looks_truncated(item.get('description', '')):
            continue
        post = posts_by_title.get(normalize_key(item.get('title', '')))
        if not post:
            continue
        item['description'] = post['body']
        item['source'] = 'board'
    return items


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    xml_data = fetch_rss()
    items = parse_rss(xml_data)
    items = enrich_truncated_items(items)
    output = {
        'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'items': items,
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(items)} 件取得")

if __name__ == '__main__':
    main()
