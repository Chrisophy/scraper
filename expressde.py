# -*- coding: utf-8 -*-
# Tube8 
# IT('s) Possible 
# 2026.10.28
import json
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlparse

from resources.lib import log, multiquest

try:
    from resources.lib import htmlscrape
except Exception:
    htmlscrape = None

SITE_ID       = 'expressde'
SITE_NAME     = 'EXPRESS.de News'
SITE_DOMAIN   = 'www.express.de'
TYPE          = 'news'
GLOBAL_SEARCH = False
ACTIVE        = True

BASE_URL = 'https://www.express.de'
PER_PAGE = 32
API_LIMIT = 88
FRONT_CHECK_HASH = '021a356684d118a91b7a076a8ade63ea8f04d583'
VIDEO_TOKENS = {'1': 'GbzYiHVN', '2': 'VhRaNvXL', '3': 'mwMUstde', '4': 'XHwP4VTw'}

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
_HEADERS = {
    'User-Agent': _UA,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.7',
    'Origin': BASE_URL,
    'Referer': BASE_URL + '/',
}

CATEGORIES = [
    ('Startseite', BASE_URL + '/', 'Die wichtigsten Nachrichten und Top-Themen des Tages auf EXPRESS.de.'),
    ('Aktuelle Videos', 'videos', 'Alle aktuellen Video-Beiträge und Streams von EXPRESS.de gebündelt in einer Liste.'),
    ('1. FC Köln', BASE_URL + '/sport/fussball/1-fc-koeln', 'Alles rund um den 1. FC Köln: News, Transfers, Spielberichte und Hintergründe.'),
    ('Köln', BASE_URL + '/koeln', 'Lokale Nachrichten, Veedels-Geschichten und Aktuelles aus Köln und Umgebung.'),
    ('Sport', BASE_URL + '/sport', 'Sportnachrichten, Fußball, Handball, Eishockey und mehr aus der Region und der Welt.'),
    ('Promi & Show', BASE_URL + '/promi-und-show', 'Stars, Sternchen, Klatsch, TV-Formate und Unterhaltung aus der Promiwelt.'),
    ('NRW', BASE_URL + '/nrw', 'Aktuelle Nachrichten und Blaulicht-Meldungen aus Nordrhein-Westfalen.'),
    ('Politik & Wirtschaft', BASE_URL + '/politik-und-wirtschaft', 'Hintergründe, Analysen und News aus Politik, Wirtschaft und Gesellschaft.'),
    ('Panorama', BASE_URL + '/panorama', 'Spannende, kuriose und weltweite Geschichten im Panorama.'),
]

_BLOCKED = ['stimmen zum spiel', 'spieltagstipp', 'kommentare', 'startseite', 'mehr anzeigen',
            'impressum', 'datenschutz', 'kontakt', 'aktuelle meldungen', 'verkehr']
_TEXT_SELECTORS = ['article p', '.article-body p', '.content p', "div[data-component='ArticleBody'] p", '.paragraph p']
_STREAM_RE = re.compile(r'https://[^\s"\'<>\\]*?\.(?:mp4|m3u8)[^\s"\'<>\\]*')
_IMG_RE = re.compile(r'https://[^\s"\'<>\\]*?\.(?:jpe?g|png|webp)(?:\?[^\s"\'<>\\]*)?', re.I)


# ----------------------------------------------------------------------------- Hilfen

def _get(url, timeout=20):
    try:
        r = multiquest.get(url, headers=_HEADERS, timeout=timeout)
        if r.status_code >= 400:
            log.log('[EXPRESS] HTTP %s: %s' % (r.status_code, url), log.LOGWARNING)
            return ''
        return r.text or ''
    except Exception as e:
        log.log('[EXPRESS] Fehler beim Laden %s: %s' % (url, e), log.LOGWARNING)
        return ''


def _abs(url):
    url = unescape(str(url or '').strip())
    if not url:
        return ''
    if url.startswith('//'):
        return 'https:' + url
    return urljoin(BASE_URL + '/', url)


def _clean(value):
    return re.sub(r'\s+', ' ', unescape(str(value or ''))).strip()


def _date(raw):
    if not raw:
        return ''
    try:
        dt = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime('%d.%m.%Y, %H:%M Uhr')
    except Exception:
        return re.sub(r'(\.\d+)?([+-]\d{2}:\d{2}|Z)$', '', raw).replace('T', ' ')


def _date_key(raw):
    try:
        return datetime.fromisoformat((raw or '').replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0


def _is_valid_article(url, title):
    if not url or not title or not re.search(r'-(\d+)$', urlparse(url).path):
        return False
    if len(title) < 12 or len(title) > 140 or re.match(r'^\d+\s+[A-Za-zÄÖÜäöüß]+', title):
        return False
    low = title.lower()
    return not any(t in low for t in _BLOCKED)


def _best_stream(streams):
    def score(u):
        u = u.lower()
        s = 15 if '.m3u8' in u else 0
        if any(k in u for k in ('hd', '1080', '720', 'hq', 'high')):
            s += 10
        if any(k in u for k in ('sd', '480', '360', 'lq', 'low')):
            s -= 10
        return s
    return sorted(streams, key=score, reverse=True)[0] if streams else None


def _page_item(label, url, plot):
    return {'title': label, 'url': url, 'plot': plot, 'is_playable': False, 'next_func': 'showEntries'}


def _text_row(text):
    return {'title': text, 'url': 'lesen', 'no_cache': True, 'is_playable': False, 'next_func': 'nothing'}


# ----------------------------------------------------------------------------- Artikel-Listen

def parse_articles(html, cat_url):
    """Artikel-Links einer Rubrikseite (wie im Kodi-Addon)."""
    if htmlscrape is None:
        return []
    root = htmlscrape.parse(html)
    main = (htmlscrape.select(root, 'main') or [root])[0]
    noise = set()
    for n in main.iter():
        if n.tag in ('nav', 'header', 'footer', 'aside'):
            noise.add(id(n))

    def in_noise(n):
        p = n
        while p is not None:
            if id(p) in noise:
                return True
            p = p.parent
        return False

    cat_path = urlparse(cat_url).path.rstrip('/').lower()
    is_front = cat_path in ('', '/')
    out, seen = [], set()
    for a in main.iter():
        if a.tag != 'a' or not a.attrs.get('href') or '#' in a.attrs['href'] or in_noise(a):
            continue
        url = _abs(a.attrs['href'])
        if not url.startswith(BASE_URL):
            continue
        path = urlparse(url).path.lower()
        if not is_front and cat_path and not path.startswith(cat_path):
            continue
        heads = [n for n in a.iter() if n.tag in ('h2', 'h3', 'h4')]
        if heads:
            title = _clean(heads[0].text())
        else:
            raw = _clean(a.text())
            half = len(raw) // 2
            title = raw[:half].strip() if len(raw) > 20 and len(raw) % 2 == 0 and raw[:half] == raw[half:] else raw
        if not _is_valid_article(url, title) or path in seen:
            continue
        seen.add(path)
        thumb = ''
        imgs = [n for n in a.iter() if n.tag == 'img']
        if not imgs and a.parent is not None:
            imgs = [n for n in a.parent.iter() if n.tag == 'img']
        for img in imgs[:1]:
            for attr in ('src', 'data-src', 'data-original', 'data-lazy-src'):
                v = img.attrs.get(attr)
                if v and not v.startswith('data:'):
                    thumb = _abs(v)
                    break
        plot = 'Artikel auf EXPRESS: %s' % title
        box = a.parent
        while box is not None and box.tag not in ('article', 'div', 'li', '#root'):
            box = box.parent
        if box is not None and box.tag != '#root':
            ps = [n for n in box.iter() if n.tag == 'p']
            if ps and len(_clean(ps[0].text())) > 20:
                plot = _clean(ps[0].text())
        m = re.search(r'-(\d+)$', path)
        out.append({'title': title, 'url': url, 'thumb': thumb, 'plot': plot, 'id': int(m.group(1)) if m else 0})
    if is_front:
        out.sort(key=lambda x: x['id'], reverse=True)
    return out


def _list_articles(cat_url, page):
    arts = parse_articles(_get(cat_url), cat_url)
    start = (page - 1) * PER_PAGE
    items = [{
        'title':       a['title'],
        'url':         a['url'],
        'plot':        a['plot'],
        'poster':      a['thumb'],
        'fanart':      a['thumb'],
        'live':        True,           
        'is_playable': False,
        'next_func':   'showArticle',
    } for a in arts[start:start + PER_PAGE]]
    if len(arts) > start + PER_PAGE:
        items.append(_page_item('Nächste Seite >>', 'list:%d:%s' % (page + 1, cat_url), 'Weitere Artikel in dieser Rubrik laden.'))
    log.log('[EXPRESS] %s Seite %d: %d Artikel' % (cat_url, page, len(items)))
    return items


# ----------------------------------------------------------------------------- Videos (greenvideo-Mixe)

def _mix_hash_and_tokens():
    html = _get(BASE_URL, timeout=8)
    m = re.search(r'mixes/([a-fA-F0-9]{40})/', html)
    mix = m.group(1) if m else FRONT_CHECK_HASH
    tokens = dict(VIDEO_TOKENS)
    for t in re.findall(r'mixes/[a-zA-Z0-9_-]+/([a-zA-Z0-9]{8})', html):
        if not t.islower() and t not in tokens.values():
            tokens['Mix_%s' % t] = t
    return mix, tokens


def _json_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ('items', 'results', 'videos', 'data', 'payload', 'mixes'):
            if isinstance(data.get(k), list):
                return data[k]
        for v in data.values():
            if isinstance(v, list) and v:
                return v
        return [data]
    return []


def _first(item, keys):
    for k in keys:
        v = item.get(k)
        if v:
            return str(v).strip()
    return ''


def _list_videos(page):
    start = (page - 1) * PER_PAGE
    offset = (start // API_LIMIT) * API_LIMIT
    mix, tokens = _mix_hash_and_tokens()
    videos, seen_ids, seen_base = [], set(), set()
    for name, token in tokens.items():
        url = ('https://media-api-prod.greenvideo.io/api/v1/mixes/%s/%s?ncr=1&resolve=true&limit=%d&offset=%d'
               % (mix, token, API_LIMIT, offset))
        try:
            data = json.loads(_get(url, timeout=15) or 'null')
        except Exception:
            continue
        for it in _json_items(data):
            if not isinstance(it, dict):
                continue
            vid = _first(it, ('id', 'videoId', 'uuid', 'guid'))
            if vid and vid in seen_ids:
                continue
            blob = json.dumps(it)
            streams = [s for s in set(_STREAM_RE.findall(blob)) if 'video-websearch-indexing.mes.glomex.cloud' not in s]
            best = _best_stream(streams)
            if not best:
                continue
            base = re.sub(r'(_(hd|sd|hq|lq)|\b(1080|720|480|360)p?)\b', '', best, flags=re.I)
            if base in seen_base:
                continue
            seen_base.add(base)
            if vid:
                seen_ids.add(vid)
            image = _first(it, ('thumbnail', 'thumbnailUrl', 'poster', 'image', 'imageUrl', 'preview'))
            if not image.startswith('http'):
                imgs = _IMG_RE.findall(blob)
                image = imgs[0] if imgs else ''
            published = _first(it, ('publishedAt', 'published', 'date', 'createdAt', 'pubDate'))
            videos.append({'title': _first(it, ('title', 'headline', 'name', 'caption')) or 'Video',
                           'published': published, 'stream': best, 'image': image,
                           'plot': _clean(_first(it, ('description', 'teaser', 'summary')))})
    videos.sort(key=lambda v: _date_key(v['published']), reverse=True)
    local = start % API_LIMIT
    items = []
    for v in videos[local:local + PER_PAGE]:
        when = _date(v['published'])
        items.append({
            'title':       v['title'],
            'url':         v['stream'],
            'plot':        '\n\n'.join(x for x in ('Veröffentlicht am: %s' % when if when else '', v['plot'] or v['title']) if x),
            'poster':      v['image'],
            'fanart':      v['image'],
            'live':        True,
            'mediatype':   'video',
            'is_playable': True,
            'next_func':   'get_hosters',
        })
    if len(videos) > local + PER_PAGE or len(items) == PER_PAGE:
        items.append(_page_item('Nächste Seite >>', 'videos:%d' % (page + 1), 'Weitere Videos laden.'))
    log.log('[EXPRESS] Videos Seite %d: %d' % (page, len(items)))
    return items


# ----------------------------------------------------------------------------- Artikelseite

def _meta(html, prop):
    for pat in (r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)',
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']'):
        m = re.search(pat % re.escape(prop), html or '', re.I)
        if m:
            return unescape(m.group(1)).strip()
    return ''


def article_parts(html):
    """-> (datum, absätze, streams)"""
    date = ''
    m = re.search(r'<time\b[^>]*>(.*?)</time>', html or '', re.S | re.I)
    if m:
        date = _clean(re.sub(r'<[^>]+>', ' ', m.group(1)))
    if not date:
        date = _date(_meta(html, 'article:published_time') or _meta(html, 'pubdate'))
    paras = []
    if htmlscrape is not None:
        root = htmlscrape.parse(html)
        for sel in _TEXT_SELECTORS:
            found = []
            for n in htmlscrape.select(root, sel):
                t = _clean(n.text())
                if len(t) > 30 and t not in found:
                    found.append(t)
            if found:
                paras = found
                break
    streams = []
    for s in _STREAM_RE.findall((html or '').replace('\\/', '/')):
        if 'video-websearch-indexing.mes.glomex.cloud' not in s and s not in streams:
            streams.append(s)
    return date, paras, streams


# ----------------------------------------------------------------------------- Menüs (MovieScout)

def load(url='', params=None):
    return [{'title': name, 'url': u, 'plot': plot, 'is_playable': False, 'next_func': 'showEntries'}
            for name, u, plot in CATEGORIES]


def showEntries(url='', params=None):
    if not url:
        return load()
    if url == 'videos' or url.startswith('videos:'):
        page = int(url.split(':', 1)[1]) if ':' in url else 1
        return _list_videos(page)
    page = 1
    if url.startswith('list:'):
        _, p, url = url.split(':', 2)
        page = int(p)
    return _list_articles(url, page)


def showArticle(url='', params=None):
    """Artikel als Liste: zuerst Videos (abspielbar), dann Datum und Text Absatz für Absatz."""
    html = _get(url)
    if not html:
        return [_text_row('Artikel konnte nicht geladen werden.')]
    date, paras, streams = article_parts(html)
    image = _meta(html, 'og:image')
    items = []
    for i, s in enumerate(streams, 1):
        items.append({
            'title':       '▶ Video öffnen' if len(streams) == 1 else '▶ Video %d öffnen' % i,
            'url':         s,
            'plot':        _meta(html, 'og:title'),
            'poster':      _abs(image) if image else '',
            'is_playable': True,
            'next_func':   'get_hosters',
        })
    if date:
        items.append(_text_row('Veröffentlicht am: %s' % date))
    items.extend(_text_row(p) for p in (paras or ['Kein Artikeltext gefunden.']))
    return items


def nothing(url='', params=None):
    return []


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    if not url:
        return []
    if not re.search(r'\.(m3u8|mp4)', url, re.I):                
        streams = article_parts(_get(url))[2]
        if not streams:
            return []
        url = _best_stream(streams)
    quality = 'HD' if re.search(r'\.m3u8|hd|1080|720', url, re.I) else ''
    return [('EXPRESS Video', url, True, quality, 'de')]
