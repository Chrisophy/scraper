# -*- coding: utf-8 -*-
# Bild.de News
# IT('s) Possible
# 2026.11.08
import json
import re
import time
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, quote, unquote
from xml.etree import ElementTree as ET

from resources.lib import log, multiquest

try:
    import requests
except Exception:
    requests = None

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
       '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
# Gleiche Header wie im Kodi-Addon, das die Videos zuverlässig abspielt
_HEADERS = {
    'User-Agent':      _UA,
    'Accept':          '*/*',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.7',
    'Referer':         'https://www.bild.de/',
    'Origin':          'https://www.bild.de',
}
_TIMEOUT = 15
_MAX_VIDEOS = 3
_CHUNK = 2000          # Sicherheitsgrenze: ein Feld fasst höchstens so viele Zeichen

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

_STREAM_EXT = re.compile(r'\.(?:m3u8|mp4|m4v|mov)(?:\?|$)', re.I)
_M3U8 = re.compile(r'https?://[^\s<>"\'\\]+?\.m3u8[^\s<>"\'\\]*')
_MEDIA = re.compile(r'https?://[^"\'\s<>\\]+?\.(?:mp4|m4v|mov)(?:\?[^"\'\s<>\\]*)?')
_VIDEO_HINT = re.compile(r'(?:glomex|jwplatform|jwpcdn|brightcove|akamaihd|cloudfront|vod\.|video\.|stream\.|cdn\.)[^"\'\s<>\\]{0,80}', re.I)
# Vorschaubilder und Werbe-Server sind keine Artikelvideos
_BAD_URL = re.compile(r'(?:thumb|preview|poster|sprite|doubleclick|imasdk|adition|adserver|googlesyndication|'
                      r'smartadserver|teads)', re.I)
# BILD-Token-Stream: die 24-stellige Video-ID steht auf der Seite oder am Ende der Artikel-URL
_TOKEN_HOST = re.compile(r'https?://hds\.ak\.token\.bild\.de/([a-f0-9]{24})')
_URL_ID = re.compile(r'-([a-f0-9]{24})(?:\.bild\.html)?$')


# ----------------------------------------------------------------------------- Hilfen

_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None and requests is not None:
        _SESSION = requests.Session()
        _SESSION.headers.update(_HEADERS)
    return _SESSION


def _get(url, raw=False):
    """Seite laden. Zuerst direkt per requests (wie das Kodi-Addon), sonst über multiquest."""
    t0 = time.time()
    empty = b'' if raw else ''
    for how in ('requests', 'multiquest'):
        try:
            if how == 'requests':
                s = _session()
                if s is None:
                    continue
                r = s.get(url, timeout=_TIMEOUT, allow_redirects=True)
            else:
                r = multiquest.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code >= 400:
                log.log('[BILD] HTTP %s (%s) nach %.1fs: %s' % (r.status_code, how, time.time() - t0, url), log.LOGWARNING)
                continue
            content = r.content or b''
            data = content if raw else content.decode('utf-8', 'replace')
            log.log('[BILD] geladen (%s) in %.1fs (%d Zeichen): %s' % (how, time.time() - t0, len(data), url[:100]))
            return data
        except Exception as e:
            log.log('[BILD] Fehler (%s) beim Laden %s nach %.1fs: %s' % (how, url, time.time() - t0, e), log.LOGWARNING)
    return empty


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


def _chunks(paras, limit=_CHUNK):
    """Absätze zu möglichst wenigen großen Textblöcken zusammenfassen (Absatzgrenzen bleiben erhalten)."""
    out, cur = [], ''
    for p in paras:
        while len(p) > limit:                      # extrem langen Absatz am Satzende teilen
            cut = p.rfind('. ', 0, limit)
            cut = cut + 1 if cut > limit // 2 else limit
            if cur:
                out.append(cur)
                cur = ''
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if cur and len(cur) + len(p) + 2 > limit:
            out.append(cur)
            cur = ''
        cur = (cur + '\n\n' + p) if cur else p
    if cur:
        out.append(cur)
    return out


# ----------------------------------------------------------------------------- RSS

def parse_feed(data):
    """RSS -> [{'title','link','summary','image','date','video'}]"""
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
        d = {'title': '', 'link': '', 'summary': '', 'image': '', 'date': '', 'video': ''}
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
            elif t in ('enclosure', 'content') and not d['video'] and ch.get('url') and (
                    (ch.get('type') or '').lower().startswith('video') or _STREAM_EXT.search(ch.get('url') or '')):
                d['video'] = ch.get('url')
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
    """Alle JSON-LD-Objekte der Seite als Liste (einmal parsen, dann weiterreichen)."""
    out = []
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
                out.append(o)
                for k in ('@graph', 'video', 'associatedMedia'):
                    if isinstance(o.get(k), (list, dict)):
                        stack.append(o[k])
    return out


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


def article_text(html, url='', ld=None):
    """-> Liste von Absätzen. Bei BILDplus nur der freie Anriss (keine Umgehung der Bezahlschranke)."""
    if ld is None:
        ld = _ld_objects(html)
    paid = 'bild-plus' in (url or '').lower() or 'bildplus' in (url or '').lower()
    body = ''
    for o in ld:
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
    # schneller Weg zuerst: Absätze per Regex aus dem <article>-Block
    if not paras:
        m = re.search(r'<article\b.*?</article>', html or '', re.S | re.I)
        if m:
            found = [_plain(p).replace('\n', ' ') for p in re.findall(r'<p\b[^>]*>(.*?)</p>', m.group(0), re.S | re.I)]
            paras = [t for t in found if len(t) > 40]
    # der langsame HTML-Parser nur als Notnagel
    if not paras and htmlscrape is not None:
        root = htmlscrape.parse(html)
        for sel in _SELECTORS:
            found = [re.sub(r'\s+', ' ', n.text()).strip() for n in htmlscrape.select(root, sel)]
            found = [t for t in found if len(t) > 40]
            if found:
                paras = found
                break
    if not paras:
        found = [_plain(p).replace('\n', ' ') for p in re.findall(r'<p\b[^>]*>(.*?)</p>', html or '', re.S | re.I)]
        paras = [t for t in found if len(t) > 40]
    out = []
    for p in paras:
        if p not in out:
            out.append(p)
    return out or [teaser or 'Kein Artikeltext gefunden.']


def _unescape_js(text):
    """Seitentext für die Videosuche: JSON-/JS-Masken (\\/, \\u002F, \\u0026, &amp;) auflösen."""
    t = text or ''
    for a, b in (('\\u002F', '/'), ('\\u002f', '/'), ('\\u0026', '&'), ('\\/', '/'), ('&amp;', '&')):
        t = t.replace(a, b)
    return t


def _token_stream(token_id):
    return 'https://hds.ak.token.bild.de/%s,delivery=hls.m3u8' % token_id


def article_videos(html, ld=None, feed_video='', article_url='', limit=_MAX_VIDEOS):
    """Videos der Seite: [(titel, stream_url)], höchstens _MAX_VIDEOS.

    Reihenfolge wie im funktionierenden Kodi-Addon: HLS-Links (.m3u8) im Seitentext zuerst, dann VideoObject,
    og:video, <video>/<source>, mp4-Links, der BILD-Token-Stream, das Video aus dem RSS-Feed und zuletzt
    der Token-Stream aus der 24-stelligen ID am Ende der Artikel-URL.
    Vorschaubilder und Werbe-Server werden aussortiert, doppelte Streams (gleicher Pfad) ebenfalls.
    """
    if ld is None:
        ld = _ld_objects(html)
    found, seen = [], set()
    text = _unescape_js(html)

    def add(title, u, loose=False):
        u = (u or '').strip()
        if u.startswith('//'):
            u = 'https:' + u
        if not u.startswith('http') or _BAD_URL.search(u):
            return
        key = u.split('?', 1)[0]
        if key in seen:
            return
        if _STREAM_EXT.search(u) or loose or 'token.bild.de' in u:
            seen.add(key)
            found.append((title or 'Video', u))

    names = [o.get('name') or o.get('headline') for o in ld if 'videoobject' in _types(o)]
    names = [n for n in names if n]

    for m in _M3U8.finditer(text):
        add('', m.group(0))
    for o in ld:
        if 'videoobject' in _types(o):
            add(o.get('name') or o.get('headline'), _unescape_js(str(o.get('contentUrl') or '')), loose=True)
    for prop in ('og:video', 'og:video:url', 'og:video:secure_url', 'twitter:player:stream'):
        add('', _unescape_js(_meta(html, prop)))
    for m in re.finditer(r'<(?:video|source)\b[^>]+\bsrc=["\']([^"\']+)', text, re.I):
        add('', unescape(m.group(1)))
    for m in _MEDIA.finditer(text):
        add('', m.group(0))
    m = _TOKEN_HOST.search(text)
    if m:
        add('', _token_stream(m.group(1)))
    if feed_video:
        add('', feed_video)
    if not found and article_url:
        m = _URL_ID.search(article_url.split('#', 1)[0].split('?', 1)[0])
        if m:
            add('', _token_stream(m.group(1)))

    # Gibt es HLS-Streams, sind mp4-Links meist dasselbe Video in anderem Format: nur HLS behalten
    hls = [f for f in found if '.m3u8' in f[1].lower() or 'token.bild.de' in f[1]]
    if hls:
        found = hls

    # Titel aus den Seitendaten den Videos ohne Namen der Reihe nach zuordnen
    found =[((names[i] if t == 'Video' and i < len(names) else t), u) for i, (t, u) in enumerate(found)]

    if not found:
        hosts = sorted({m.group(0)[:60] for m in _VIDEO_HINT.finditer(text)})[:8]
        log.log('[BILD] Kein Video im Seitentext. <video>=%d, VideoObject=%d, Hinweise: %s' % (
            len(re.findall(r'<video\b', text, re.I)), len(names), ', '.join(hosts) or '-'), log.LOGINFO)
    else:
        log.log('[BILD] %d Video(s) gefunden, erstes: %s' % (len(found), found[0][1][:100]), log.LOGINFO)
    return found[:limit]


def _probe(stream, referer):
    """Prüft, ob der Stream mit diesen Headern erreichbar ist.
    True = Antwort 200/206 (bei .m3u8 zusätzlich mit gültiger Playlist), False = Fehler (z. B. 404),
    None = nicht prüfbar (kein requests oder Netzwerkfehler)."""
    if requests is None:
        return None
    try:
        r = requests.get(stream, headers={'User-Agent': _UA, 'Referer': referer, 'Accept': '*/*'},
                         timeout=8, stream=True, allow_redirects=True)
        ok = r.status_code in (200, 206)
        head = b''
        if ok:
            for chunk in r.iter_content(512):
                head = chunk or b''
                break
        code = r.status_code
        r.close()
        if ok and '.m3u8' in stream.lower() and b'#EXTM3U' not in head:
            ok = False
        log.log('[BILD] Test %s -> HTTP %s%s' % (stream[:100], code, '' if ok else ' (nicht abspielbar)'))
        return ok
    except Exception as e:
        log.log('[BILD] Test %s nicht möglich: %s' % (stream[:100], e), log.LOGWARNING)
        return None


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
            'url':         e['link'] + ('#v=' + quote(e['video'], safe='') if e.get('video') else ''),
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
    """Artikel als kurze Liste: zuerst die Videos (abspielbar), danach der ganze Text in einem Feld."""
    feed_video = ''
    if '#v=' in url:
        url, feed_video = url.split('#v=', 1)
        feed_video = unquote(feed_video)
    html = _get(url)
    if not html:
        return [{'title': 'Artikel konnte nicht geladen werden.', 'url': 'lesen', 'no_cache': True,
                 'is_playable': False, 'next_func': 'nothing'}]
    t0 = time.time()
    ld = _ld_objects(html)
    heading = _meta(html, 'og:title')
    paras = article_text(html, url, ld)
    vids = article_videos(html, ld, feed_video, url)
    log.log('[BILD] Seite ausgewertet in %.1fs' % (time.time() - t0))

    items = []
    for i, (title, stream) in enumerate(vids):
        # Als URL dient der Artikel: der Stream wird erst beim Abspielen frisch aufgelöst (Token!)
        play_url = '%s#i=%d%s' % (url, i, '&v=' + quote(feed_video, safe='') if feed_video else '')
        items.append({
            'title':       '▶ Video abspielen' + (': %s' % title if title and title != 'Video' else (' %d' % (i + 1) if i else '')),
            'url':         play_url,
            'plot':        heading,
            'is_playable': True,
            'next_func':   'get_hosters',
        })
    # Der ganze Artikel in einem Feld (nur bei sehr langen Texten in wenige große Blöcke geteilt)
    for block in _chunks(paras):
        items.append({'title': block, 'url': 'lesen', 'plot': block, 'no_cache': True,
                      'is_playable': False, 'next_func': 'nothing'})
    return items


def nothing(url='', params=None):
    return []


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    if not url:
        return []
    article_url, index, feed_video = url, 0, ''
    if re.search(r'\.(m3u8|mp4)(\?|$)', url.split('#', 1)[0], re.I):
        streams = [url]                                # direkter Stream (alte Menüs): Referer bleibt bild.de
        referer = 'https://www.bild.de/'
    else:
        if '#' in url:
            article_url, frag = url.split('#', 1)
            q = dict(parse_qsl(frag))
            try:
                index = int(q.get('i', 0))
            except ValueError:
                index = 0
            feed_video = unquote(q.get('v', ''))
        referer = article_url                          # wie im Kodi-Addon: der Referer ist die Artikelseite
        vids = article_videos(_get(article_url), feed_video=feed_video, article_url=article_url, limit=20)
        cands = [u for _, u in vids]
        # der angeklickte Stream zuerst, danach die übrigen Kandidaten
        if cands and index < len(cands):
            cands.insert(0, cands.pop(index))
        # zusätzlich der Token-Stream aus der Video-ID der Artikel-URL (wie im Kodi-Addon)
        m = _URL_ID.search(article_url.split('?', 1)[0])
        if m and _token_stream(m.group(1)) not in cands:
            cands.append(_token_stream(m.group(1)))
        if not cands:
            log.log('[BILD] Kein Stream für %s' % article_url, log.LOGWARNING)
            return []
        # Kandidaten der Reihe nach testen (404 = Link unbrauchbar/abgelaufen), bis zu zwei erreichbare behalten
        streams = []
        for cand in cands[:4]:
            ok = _probe(cand, referer)
            if ok or ok is None:
                streams.append(cand)
                if ok is None or len(streams) >= 2:
                    break
        if not streams:
            log.log('[BILD] Kein Kandidat erreichbar, nehme den ersten: %s' % cands[0][:100], log.LOGWARNING)
            streams = [cands[0]]
    # Jede Quelle zweimal anbieten: wie im Kodi-Addon mit Header-Zusatz (|User-Agent&Referer) und als reine URL.
    # Ein App-Player versteht den |-Zusatz unter Umständen nicht; unter "Quelle wählen" lässt sich umschalten.
    headers = 'User-Agent=%s&Referer=%s' % (quote(_UA, safe=''), quote(referer, safe=''))
    out = []
    for n, s in enumerate(streams, 1):
        quality = 'HD' if '.m3u8' in s.lower() else ''
        name = 'BILD Video' if n == 1 else 'BILD Video %d' % n
        out.append((name, s + '|' + headers, True, quality, 'de'))
        out.append((name + ' (ohne Header)', s, True, quality, 'de'))
        log.log('[BILD] Quelle %d: %s (Referer %s)' % (n, s[:120], referer[:100]))
    return out
