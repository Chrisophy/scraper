# -*- coding: utf-8 -*-
import json
import re
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree as ET

from resources.lib import log, multiquest

try:
    from resources.lib import htmlscrape            
except Exception:
    htmlscrape = None

SITE_ID       = 'bildde'
SITE_NAME     = 'BILD.de News'
SITE_DOMAIN   = 'www.bild.de'
TYPE          = 'news'
GLOBAL_SEARCH = False
ACTIVE        = True

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_HEADERS = {'User-Agent': _UA, 'Accept-Language': 'de-DE,de;q=0.9'}

CATEGORIES = [
    ('Top-News',     'https://www.bild.de/feed/alles.xml'),
    ('Politik',      'https://www.bild.de/rss-feeds/rss-16725492,feed=politik.bild.html'),
    ('News',         'https://www.bild.de/rss-feeds/rss-16725492,feed=news.bild.html'),
    ('Sport',        'https://www.bild.de/rss-feeds/rss-16725492,feed=sport.bild.html'),
    ('Unterhaltung', 'https://www.bild.de/rss-feeds/rss-16725492,feed=unterhaltung.bild.html'),
    ('Lifestyle',    'https://www.bild.de/rss-feeds/rss-16725492,feed=lifestyle.bild.html'),
    ('Auto',         'https://www.bild.de/rss-feeds/rss-16725492,feed=auto.bild.html'),
    ('Ratgeber',     'https://www.bild.de/rss-feeds/rss-16725492,feed=ratgeber.bild.html'),
]

_SELECTORS = ['article p', '.article-body p', '.txt p', '.post-content p', '[data-key=article] p']
_ARTICLE_TYPES = {'newsarticle', 'article', 'reportagenewsarticle', 'analysisnewsarticle',
                  'opinionnewsarticle', 'backgroundnewsarticle', 'blogposting', 'liveblogposting'}


# ----------------------------------------------------------------------------- Hilfen

def _get(url, raw=False):
    try:
        r = multiquest.get(url, headers=_HEADERS, timeout=15)
        if r.status_code >= 400:
            log.log('[BILD] HTTP %s: %s' % (r.status_code, url), log.LOGWARNING)
            return b'' if raw else ''
        return (r.content or b'') if raw else (r.text or '')
    except Exception as e:
        log.log('[BILD] Fehler beim Laden %s: %s' % (url, e), log.LOGWARNING)
        return b'' if raw else ''


def _plain(html):
    t = re.sub(r'<(br|/p|/div|/li)\b[^>]*>', '\n', html or '', flags=re.I)
    t = unescape(re.sub(r'<[^>]+>', ' ', t))
    t = re.sub(r'[ \t\r\f\v\xa0]+', ' ', t)
    t = re.sub(r' +([.,;:!?)])', r'\1', t)
    return re.sub(r'\s*\n\s*', '\n', t).strip()


def _tag(el):
    return el.tag.rsplit('}', 1)[-1].lower() if isinstance(el.tag, str) else ''


def _date(value):
    try:
        dt = parsedate_to_datetime((value or '').strip())
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime('%d.%m.%Y, %H:%M Uhr')
    except Exception:
        return ''


def _is_image(url, mime=''):
    if not url:
        return False
    if mime:
        return mime.lower().startswith('image')
    return bool(re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', url, re.I))


# ----------------------------------------------------------------------------- RSS

def parse_feed(data):
    """RSS -> [{'title','link','summary','image','date'}]"""
    if isinstance(data, str):
        data = data.encode('utf-8', 'replace')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    out = []
    for it in root.iter():
        if _tag(it) not in ('item', 'entry'):
            continue
        d = {'title': '', 'link': '', 'summary': '', 'image': '', 'date': ''}
        desc = ''
        for ch in it.iter():
            if ch is it:
                continue
            t, text = _tag(ch), (ch.text or '').strip()
            if t == 'title' and not d['title']:
                d['title'] = _plain(text)
            elif t == 'link' and not d['link']:
                d['link'] = text or (ch.get('href') or '').strip()
            elif t == 'guid' and not d['link'] and text.startswith('http'):
                d['link'] = text
            elif t in ('description', 'summary') and not desc:
                desc = ch.text or ''
            elif t in ('pubdate', 'published', 'updated', 'date') and not d['date']:
                d['date'] = text
            elif t == 'enclosure' and not d['image'] and _is_image(ch.get('url'), ch.get('type') or ''):
                d['image'] = ch.get('url')
            elif t in ('content', 'thumbnail') and not d['image'] and ch.get('url'):
                if (ch.get('medium') or '').lower() == 'image' or _is_image(ch.get('url'), ch.get('type') or ''):
                    d['image'] = ch.get('url')
        if not d['image']:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)', desc, re.I)
            if m:
                d['image'] = unescape(m.group(1))
        d['summary'] = _plain(desc)
        if d['title'] and d['link']:
            out.append(d)
    return out


# ----------------------------------------------------------------------------- Artikelseite

def _ld_objects(html):
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html or '', re.S | re.I):
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            o = stack.pop()
            if isinstance(o, list):
                stack.extend(o)
            elif isinstance(o, dict):
                yield o
                for k in ('@graph', 'video', 'associatedMedia'):
                    if isinstance(o.get(k), (list, dict)):
                        stack.append(o[k])


def _types(o):
    t = o.get('@type')
    return [str(x).lower() for x in ([t] if isinstance(t, str) else (t or []))]


def _meta(html, prop):
    for pat in (r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)',
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']'):
        m = re.search(pat % re.escape(prop), html or '', re.I)
        if m:
            return unescape(m.group(1)).strip()
    return ''


def article_text(html, url=''):
    """-> Liste von Absätzen. Bei BILDplus nur der freie Anriss (keine Umgehung der Bezahlschranke)."""
    paid = 'bild-plus' in (url or '').lower() or 'bildplus' in (url or '').lower()
    body = ''
    for o in _ld_objects(html):
        if not any(t in _ARTICLE_TYPES for t in _types(o)):
            continue
        free = o.get('isAccessibleForFree')
        if free is False or str(free).lower() == 'false':
            paid = True
        if not body and isinstance(o.get('articleBody'), str):
            body = o['articleBody']
    teaser = _meta(html, 'og:description') or _meta(html, 'description')
    if paid:
        return [teaser or 'Dieser Artikel ist nur mit BILDplus lesbar.',
                'BILDplus: Der vollständige Artikel ist kostenpflichtig und nur auf bild.de lesbar.']
    paras = []
    if body:
        paras = [p.strip() for p in re.split(r'\n\s*\n', unescape(body)) if p.strip()]
    if not paras and htmlscrape is not None:
        root = htmlscrape.parse(html)
        for sel in _SELECTORS:
            found = [re.sub(r'\s+', ' ', n.text()).strip() for n in htmlscrape.select(root, sel)]
            found = [t for t in found if len(t) > 40]
            if found:
                paras = found
                break
    if not paras:
        m = re.search(r'<article\b.*?</article>', html or '', re.S | re.I)
        found = [_plain(p).replace('\n', ' ') for p in re.findall(r'<p\b[^>]*>(.*?)</p>', m.group(0) if m else html or '', re.S | re.I)]
        paras = [t for t in found if len(t) > 40]
    out = []
    for p in paras:
        if p not in out:
            out.append(p)
    return out or [teaser or 'Kein Artikeltext gefunden.']


def article_videos(html):
    """Videos der Seite: [(titel, stream_url)] – aus den Seitendaten (VideoObject) oder direkten .m3u8/.mp4-Links."""
    found, seen = [], set()

    def add(title, u):
        u = (u or '').replace('\\/', '/').strip()
        if u.startswith('//'):
            u = 'https:' + u
        if u.startswith('http') and re.search(r'\.(m3u8|mp4)(\?|$)', u, re.I) and u not in seen:
            seen.add(u)
            found.append((title or 'Video', u))

    for o in _ld_objects(html):
        if 'videoobject' in _types(o):
            add(o.get('name') or o.get('headline'), o.get('contentUrl'))
    for m in re.finditer(r'https?:(?:\\?/){2}[^"\'\s<>]+?\.(?:m3u8|mp4)(?:\?[^"\'\s<>]*)?', html or ''):
        add('', m.group(0))
    return found


# ----------------------------------------------------------------------------- Menüs (MovieScout)

def load(url='', params=None):
    return [{'title': name, 'url': feed, 'plot': 'Aktuelle Artikel: %s' % name,
             'is_playable': False, 'next_func': 'showEntries'} for name, feed in CATEGORIES]


def showEntries(url='', params=None):
    if not url:
        return load()
    items = []
    for e in parse_feed(_get(url, raw=True)):
        items.append({
            'title':       e['title'],
            'url':         e['link'],
            'plot':        '\n\n'.join(x for x in (_date(e['date']), e['summary']) if x),
            'poster':      e['image'],
            'fanart':      e['image'],
            'live':        True,           
            'is_playable': False,
            'next_func':   'showArticle',
        })
    log.log('[BILD] %s: %d Artikel' % (url, len(items)))
    return items


def showArticle(url='', params=None):
    """Artikel als Liste: zuerst Videos (abspielbar), dann der Text Absatz für Absatz."""
    html = _get(url)
    if not html:
        return [{'title': 'Artikel konnte nicht geladen werden.', 'url': 'lesen', 'no_cache': True,
                 'is_playable': False, 'next_func': 'nothing'}]
    items = []
    for i, (title, stream) in enumerate(article_videos(html), 1):
        items.append({
            'title':       '▶ Video abspielen' + (': %s' % title if title and title != 'Video' else (' %d' % i if i > 1 else '')),
            'url':         stream,
            'plot':        _meta(html, 'og:title'),
            'is_playable': True,
            'next_func':   'get_hosters',
        })
    for p in article_text(html, url):
        items.append({'title': p, 'url': 'lesen', 'no_cache': True, 'is_playable': False, 'next_func': 'nothing'})
    return items


def nothing(url='', params=None):
    return []


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    if not url:
        return []
    if not re.search(r'\.(m3u8|mp4)(\?|$)', url, re.I):           
        vids = article_videos(_get(url))
        if not vids:
            return []
        url = vids[0][1]
    quality = 'HD' if '.m3u8' in url.lower() else ''
    stream = url + '|Referer=https://www.bild.de/&User-Agent=' + _UA.replace(' ', '%20')
    return [('BILD Video', stream, True, quality, 'de')]
