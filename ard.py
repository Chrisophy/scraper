# -*- coding: utf-8 -*-
# Tube8 
# IT('s) Possible 
# 2026.10.28
"""ARD Mediathek – erzeugt mit dem MovieScout Scraper-Baukasten (2026-10-28).

Alle Einstellungen stehen unten in CFG. Diese Datei kann im Baukasten wieder geöffnet und weiterbearbeitet werden.
Zum Benutzen nur nach providers/ kopieren – Engine und App bleiben unverändert.
"""
import json
import re
import urllib.error
import urllib.request
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, quote, quote_plus, unquote, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from resources.lib import log, multiquest

try:
    from resources.lib import htmlscrape
except Exception:
    htmlscrape = None

SITE_ID       = "ard"
SITE_NAME     = "ARD Mediathek"
SITE_DOMAIN   = "www.ardmediathek.de"
TYPE          = "news"
GLOBAL_SEARCH = True
ACTIVE        = True

CFG = json.loads(r'''{
 "meta": {
  "name": "ARD Mediathek",
  "id": "ard",
  "domain": "www.ardmediathek.de",
  "type": "news",
  "globalSearch": true,
  "ua": "desktop",
  "uaCustom": "",
  "referer": "",
  "headers": "",
  "tokenUrl": "",
  "tokenFrom": "",
  "useCf": false
 },
 "menu": [
  {
   "kind": "list",
   "title": "Rubriken",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true#sec=^Menü$",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Die besten Videos",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true#sec=^Die besten Videos",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Top-Serien",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true#sec=^Unsere Top-Serien",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Film-Empfehlungen",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true#sec=^Film-Empfehlungen",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Dokus und Reportagen",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true#sec=^Spannende Dokus",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Nachrichten",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true#sec=^tagesschau",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Sendungen A-Z",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/editorial/experiment-a-z?embedded=true",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  },
  {
   "kind": "list",
   "title": "Alle Startseiten-Abschnitte",
   "url": "https://api.ardmediathek.de/page-gateway/pages/ard/home?embedded=true",
   "plot": "",
   "rule": "nav a",
   "group": "",
   "profile": 0
  }
 ],
 "entry": "video",
 "extra": [
  {
   "entry": "video",
   "next": 0,
   "list": {
    "mode": "json",
    "json": {
     "path": "showResults + vodResults",
     "title": "shortTitle || mediumTitle || longTitle",
     "link": "links.target.href",
     "poster": "images.aspect16x9.src || images.aspect1x1.src",
     "plot": "synopsis || description",
     "date": "broadcastedOn",
     "duration": "duration",
     "video": "",
     "videoAny": false,
     "videoExclude": "",
     "imageAny": false,
     "folderField": "links.target.href",
     "folderPattern": "^(?!.*/(item|live|event)/).+",
     "sectionPath": "",
     "sectionTitle": "",
     "sectionItems": "",
     "sectionSkip": "^Menü$",
     "sectionLink": "links.self.href",
     "folderNote": "Serie / Sendung – öffnet die Folgen"
    },
    "html": {
     "item": "article",
     "title": "h2@text || h3@text || a@title",
     "link": "a@href",
     "poster": "img@data-src|data-lazy-src|src",
     "plot": "p@text",
     "date": "",
     "duration": "",
     "video": ""
    },
    "links": {
     "scope": "",
     "contains": "",
     "exclude": "impressum,datenschutz,kontakt",
     "regex": "",
     "sameSite": true,
     "plotFromParent": false,
     "skipNoise": true,
     "underCategory": false,
     "poster": "",
     "durationAuto": false,
     "durationRule": ""
    },
    "regex": {
     "pattern": ""
    },
    "minTitle": 1,
    "maxTitle": 0,
    "blocked": "Audiodeskription, Gebärdensprache, Hörfassung",
    "sortId": false,
    "sortDate": false,
    "perPage": 30,
    "minMinutes": 0,
    "filterMenu": false
   },
   "paging": {
    "mode": "param",
    "param": "showPageNumber,vodPageNumber",
    "pattern": "",
    "rule": "",
    "start": 0,
    "min": 1,
    "moreField": "",
    "nextField": "",
    "totalField": "showTotal,vodTotal",
    "sizeField": "showPageSize,vodPageSize"
   }
  }
 ],
 "list": {
  "mode": "json",
  "html": {
   "item": "article",
   "title": "h2@text || h3@text || a@title",
   "link": "a@href",
   "poster": "img@data-src|data-lazy-src|src",
   "plot": "p@text",
   "date": "",
   "duration": "",
   "video": ""
  },
  "links": {
   "scope": "",
   "contains": "",
   "exclude": "impressum,datenschutz,kontakt",
   "regex": "",
   "sameSite": true,
   "plotFromParent": false,
   "skipNoise": true,
   "underCategory": false,
   "poster": "",
   "durationAuto": false,
   "durationRule": ""
  },
  "json": {
   "path": "",
   "title": "shortTitle || mediumTitle || longTitle",
   "link": "links.target.href",
   "poster": "images.aspect16x9.src || images.aspect1x1.src",
   "plot": "synopsis || description",
   "date": "broadcastedOn",
   "duration": "duration",
   "video": "",
   "videoAny": false,
   "videoExclude": "",
   "imageAny": false,
   "folderField": "links.target.href",
   "folderPattern": "^(?!.*/(item|live|event)/).+",
   "folderNote": "Serie / Sendung – öffnet die Folgen",
   "sectionPath": "widgets",
   "sectionTitle": "title",
   "sectionItems": "teasers",
   "sectionSkip": "^Menü$",
   "sectionLink": "links.self.href"
  },
  "regex": {
   "pattern": ""
  },
  "minTitle": 1,
  "maxTitle": 0,
  "blocked": "Audiodeskription, Gebärdensprache, Hörfassung",
  "sortId": false,
  "sortDate": false,
  "perPage": 30,
  "minMinutes": 0,
  "filterMenu": false
 },
 "paging": {
  "mode": "param",
  "param": "pageNumber",
  "pattern": "",
  "rule": "",
  "start": 0,
  "min": 1,
  "moreField": "",
  "nextField": "",
  "totalField": "pagination.totalElements",
  "sizeField": "pagination.pageSize"
 },
 "next": 0,
 "search": {
  "url": "https://api.ardmediathek.de/page-gateway/pages/ard/search?searchString={q}&pageSize=24&embedded=true",
  "profile": 1,
  "method": "get",
  "body": "",
  "tokenUrl": "",
  "tokenFrom": ""
 },
 "series": {
  "enabled": false,
  "isSeries": "",
  "seasonInTitle": "",
  "seasonsFrom": "",
  "episodesFrom": "",
  "episodeNames": "",
  "sectionFrom": ""
 },
 "video": {
  "methods": {
   "direct": false,
   "jsonld": false,
   "og": false,
   "tags": false,
   "iframe": false,
   "json": true,
   "regex": "",
   "apiFrom": "",
   "apiUrl": ""
  },
  "regexDirect": false,
  "nameFromHost": false,
  "qualityFrom": "",
  "skip": "",
  "follow": "",
  "referer": "none",
  "origin": false,
  "sendUa": false,
  "resolveRedirect": true,
  "hlsFirst": true,
  "lang": "de",
  "max": 8
 },
 "article": {
  "selectors": "article p, .article-body p",
  "minLen": 40,
  "useLd": true,
  "showDate": true,
  "paywall": ""
 },
 "texts": {
  "next": "Nächste Seite >>",
  "search": "[ Suche nach ]",
  "searchPrompt": "Suche nach",
  "empty": "Keine Einträge gefunden.",
  "video": "▶ Video abspielen",
  "hoster": "ARD",
  "plot": "{datum}\nDauer: {dauer}\n\n{beschreibung}",
  "dateFmt": "%d.%m.%Y, %H:%M Uhr",
  "published": "Veröffentlicht am:",
  "loadError": "Seite konnte nicht geladen werden.",
  "locked": "Dieser Beitrag ist nicht frei lesbar.",
  "noText": "Kein Artikeltext gefunden.",
  "filter": "Filter: Mindestdauer {min} (ändern)"
 },
 "title": {
  "case": "",
  "prefix": "",
  "suffix": "",
  "max": 0
 },
 "rules": []
}''')

# ============================================================================ ab hier: Laufzeit (nicht ändern)
_M, _L, _V, _A, _T = CFG['meta'], CFG['texts'], CFG['video'], CFG['article'], CFG['title']
_PROFILES = [{'entry': CFG.get('entry') or 'video', 'list': CFG['list'], 'paging': CFG['paging'], 'next': CFG.get('next')}] + list(CFG.get('extra') or [])


def _pr(i):
    try:
        return _PROFILES[int(i)]
    except Exception:
        return _PROFILES[0]

_TAG = '[%s]' % SITE_ID.upper()
_UAS = {
    'desktop': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'mobile': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
}
_STREAM = re.compile(r'\.(?:m3u8|mp4|m4v|mov|mpd|webm)(?:\?|$)', re.I)
_STREAM_URL = re.compile(r'https?://[^"\'\s<>\\]+?\.(?:m3u8|mp4|m4v|mov|mpd)(?:\?[^"\'\s<>\\]*)?', re.I)
_BAD = re.compile(r'thumb|preview|poster|sprite', re.I)
_SITE = SITE_DOMAIN.lower().replace('www.', '')


# ----------------------------------------------------------------------------- Hilfen

def _ua():
    if _M.get('ua') == 'custom' and (_M.get('uaCustom') or '').strip():
        return _M['uaCustom'].strip()
    return _UAS.get(_M.get('ua'), _UAS['desktop'])


_TOK = {'v': '', 't': 0.0}


def _token():
    """Kennung (Token) von der Adresse „tokenUrl“ holen und 10 Minuten merken (für Kopfzeilen mit {token})."""
    rx = _rx(_M.get('tokenFrom') or '', re.I | re.S)
    if not rx:
        return ''
    if _TOK['v'] and time.time() - _TOK['t'] < 600:
        return _TOK['v']
    try:
        r = multiquest.get((_M.get('tokenUrl') or '').strip() or 'https://%s/' % SITE_DOMAIN, headers=_headers(with_token=False), timeout=15)
        m = rx.search(r.text or '') if r.status_code < 400 else None
        _TOK['v'] = ((m.group(1) if m and m.groups() else (m.group(0) if m else '')) or '')
        _TOK['t'] = time.time()
    except Exception as e:
        log.log('%s Kennung nicht geholt: %s' % (_TAG, e), log.LOGWARNING)
        _TOK['v'] = ''
    return _TOK['v']


def _headers(referer=None, accept=None, with_token=True):
    h = {'User-Agent': _ua(), 'Accept-Language': 'de-DE,de;q=0.9,en;q=0.7'}
    if accept:
        h['Accept'] = accept
    ref = referer or (_M.get('referer') or '').strip() or 'https://%s/' % SITE_DOMAIN
    h['Referer'] = ref
    for line in (_M.get('headers') or '').splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            if k.strip() and v.strip():
                v = v.strip()
                if '{token}' in v:
                    t = _token() if with_token else ''
                    if not t:
                        continue
                    v = v.replace('{token}', t)
                h[k.strip()] = v
    return h


def _get(url, referer=None, accept=None):
    try:
        kw = {'headers': _headers(referer, accept), 'timeout': 20}
        if _M.get('useCf'):
            kw['use_cf'] = True
        r = multiquest.get(url, **kw)
        if r.status_code >= 400:
            log.log('%s HTTP %s: %s' % (_TAG, r.status_code, url), log.LOGWARNING)
            return ''
        return r.text or ''
    except Exception as e:
        log.log('%s Fehler beim Laden %s: %s' % (_TAG, url, e), log.LOGWARNING)
        return ''


def _post(url, template, query=''):
    """POST mit Vorlage; {q} wird durch den Suchbegriff ersetzt (JSON-Rumpf wird als JSON, sonst als Formular gesendet)."""
    try:
        t = (template or '').strip()
        kw = {'headers': _headers(), 'timeout': 20}
        if _M.get('useCf'):
            kw['use_cf'] = True
        if not t.startswith(('{', '[')):
            kw['headers'] = dict(kw['headers'], **{'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://%s/' % SITE_DOMAIN})
        if t.startswith(('{', '[')):
            kw['json'] = json.loads(t.replace('{q}', json.dumps(query)[1:-1]))
        else:
            kw['data'] = dict(parse_qsl(t.replace('{q}', quote_plus(query))))
        r = multiquest.post(url, **kw)
        if r.status_code >= 400:
            log.log('%s HTTP %s (POST): %s' % (_TAG, r.status_code, url), log.LOGWARNING)
            return ''
        return r.text or ''
    except Exception as e:
        log.log('%s Fehler beim POST %s: %s' % (_TAG, url, e), log.LOGWARNING)
        return ''


def _clean(v):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', str(v or '')))).strip()


def _abs(u, base):
    u = unescape(str(u or '')).strip().replace('\\/', '/')
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    return urljoin(base or 'https://%s/' % SITE_DOMAIN, u)


def _unjs(text):
    t = text or ''
    for a, b in (('\\u002F', '/'), ('\\u002f', '/'), ('\\u0026', '&'), ('\\/', '/'), ('&amp;', '&')):
        t = t.replace(a, b)
    return t


def _date(raw):
    raw = (raw or '').strip()
    if not raw:
        return ''
    dt = None
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except Exception:
            return raw
    if dt is None:
        return raw
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    try:
        return dt.strftime(_L.get('dateFmt') or '%d.%m.%Y, %H:%M Uhr')
    except Exception:
        return raw


def _title(t):
    t = _clean(t)
    for r in CFG.get('rules') or []:
        f = r.get('find') or ''
        if not f:
            continue
        try:
            t = re.sub(f, r.get('repl') or '', t) if r.get('regex') else t.replace(f, r.get('repl') or '')
        except re.error:
            pass
    t = re.sub(r'\s+', ' ', t).strip()
    case = _T.get('case')
    if case == 'upper':
        t = t.upper()
    elif case == 'lower':
        t = t.lower()
    elif case == 'title':
        t = t.title()
    elif case == 'first':
        t = t[:1].upper() + t[1:]
    mx = int(_T.get('max') or 0)
    if mx and len(t) > mx:
        t = t[:mx - 1].rstrip() + '…'
    return (_T.get('prefix') or '') + t + (_T.get('suffix') or '') if t else ''


def _plot(rec):
    tpl = _L.get('plot') or '{beschreibung}'
    dur = str(rec.get('duration') or '')
    if dur.isdigit() and int(dur) >= 60:                         # Sekunden -> „9 Min.“ / „1 Std. 42 Min.“
        mn = int(round(int(dur) / 60.0))
        dur = ('%d Std. %d Min.' % (mn // 60, mn % 60)) if mn >= 60 else '%d Min.' % mn
    vals = {'titel': rec.get('title') or '', 'beschreibung': rec.get('plot') or '',
            'datum': _date(rec.get('date')), 'dauer': dur}
    lines = []
    for line in tpl.split('\n'):
        ph = re.findall(r'\{(\w+)\}', line)
        if ph and not any(vals.get(p) for p in ph):
            continue
        for k, v in vals.items():
            line = line.replace('{%s}' % k, v)
        lines.append(line.rstrip())
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _dur_secs(v):
    v = str(v or '').strip()
    m = re.match(r'^(\d+):(\d{2})(?::(\d{2}))?$', v)
    if m:
        return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))) if m.group(3) else int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r'^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$', v.upper())
    if m:
        d, h_, mi, sec = m.groups()
        return int(int(d or 0) * 86400 + int(h_ or 0) * 3600 + int(mi or 0) * 60 + float(sec or 0))
    return int(v) if v.isdigit() else 0


_MIN_CHOICES = ['5', '10', '15', '20', '30', '45', '0']


def _min_minutes(P):
    try:
        import xbmcaddon
        v = (xbmcaddon.Addon().getSetting('%s_min_minutes' % SITE_ID) or '').strip()
    except Exception:
        v = ''
    if v in _MIN_CHOICES:
        return int(v)
    return int(P['list'].get('minMinutes') or 0)


def _cycle_min():
    cur = str(_min_minutes(next((q for q in _PROFILES if q['list'].get('filterMenu')), _PROFILES[0])))
    nxt = _MIN_CHOICES[(_MIN_CHOICES.index(cur) + 1) % len(_MIN_CHOICES)] if cur in _MIN_CHOICES else _MIN_CHOICES[0]
    try:
        import xbmcaddon
        xbmcaddon.Addon().setSetting('%s_min_minutes' % SITE_ID, nxt)
    except Exception as e:
        log.log('%s Filter nicht gespeichert: %s' % (_TAG, e), log.LOGWARNING)


def _row(text):
    # Textzeile: ein Klick tut nichts (die Liste bleibt einfach stehen)
    return {'title': text, 'url': 'lesen', 'no_cache': True, 'is_playable': False, 'next_func': 'nothing'}


def _folder(label, url, plot=''):
    return {'title': label, 'url': url, 'plot': plot, 'is_playable': False, 'next_func': 'showEntries'}


def _rec(title='', link='', poster='', plot='', date='', duration='', video=''):
    return {'title': title, 'link': link, 'poster': poster, 'plot': plot, 'date': date,
            'duration': duration, 'video': video}


# ----------------------------------------------------------------------------- Listen lesen

def _from_rss(data):
    if isinstance(data, str):
        data = data.encode('utf-8', 'replace')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []

    def tag(el):
        return el.tag.rsplit('}', 1)[-1].lower() if isinstance(el.tag, str) else ''

    def img(u, mime=''):
        return bool(u) and (mime.lower().startswith('image') if mime else bool(re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', u, re.I)))

    out = []
    for it in root.iter():
        if tag(it) not in ('item', 'entry'):
            continue
        r = _rec()
        desc = ''
        for ch in it.iter():
            if ch is it:
                continue
            t, text = tag(ch), (ch.text or '').strip()
            if t == 'title' and not r['title']:
                r['title'] = text
            elif t == 'link' and not r['link']:
                r['link'] = text or (ch.get('href') or '').strip()
            elif t == 'guid' and not r['link'] and text.startswith('http'):
                r['link'] = text
            elif t in ('description', 'summary', 'encoded') and not desc:
                desc = ch.text or ''
            elif t in ('pubdate', 'published', 'updated', 'date') and not r['date']:
                r['date'] = text
            elif t in ('enclosure', 'content') and ch.get('url'):
                u, mime = ch.get('url'), (ch.get('type') or '')
                if (mime.lower().startswith('video') or _STREAM.search(u)) and not r['video']:
                    r['video'] = u
                elif (img(u, mime) or (ch.get('medium') or '').lower() == 'image') and not r['poster']:
                    r['poster'] = u
            elif t == 'thumbnail' and ch.get('url') and not r['poster']:
                r['poster'] = ch.get('url')
        if not r['poster']:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)', desc, re.I)
            if m:
                r['poster'] = unescape(m.group(1))
        r['plot'] = _clean(desc)
        if r['title'] and r['link']:
            out.append(r)
    return out


def _walk(obj, path):
    for part in [p for p in re.split(r'[./]', path or '') if p]:
        if isinstance(obj, list) and not part.isdigit():       # Feldname auf einer Liste: aus allen Einträgen einsammeln (cluster.teaser)
            vals = []
            for o in obj:
                v = o.get(part) if isinstance(o, dict) else None
                if isinstance(v, list):
                    vals.extend(v)
                elif v is not None:
                    vals.append(v)
            obj = vals
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except Exception:
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _jval(it, rule):
    for alt in (rule or '').split('||'):
        alt = alt.strip()
        if not alt:
            continue
        if '{' in alt:
            v = re.sub(r'\{([^{}]+)\}', lambda m: str(_walk(it, m.group(1)) if _walk(it, m.group(1)) is not None else ''), alt)
        else:
            v = _walk(it, alt)
        if isinstance(v, list):
            v = v[0] if v else ''
        if isinstance(v, dict):
            v = v.get('url') or v.get('src') or _pick_image(v)
        if v not in (None, ''):
            return str(v).strip()
    return ''


def _pick_image(d):
    """Tabelle mit Bildgrößen {"1": {"url": …}, …}: das kleinste Bild ab 480 Pixel Breite, sonst das größte."""
    urls = [x.get('url') for x in d.values() if isinstance(x, dict) and isinstance(x.get('url'), str) and x.get('url')]
    if not urls:
        return ''
    sized = []
    for u in urls:
        m = re.search(r'(\d{3,4})x(\d{3,4})', u)
        if m:
            sized.append((int(m.group(1)), u))
    if sized:
        big = sorted(x for x in sized if x[0] >= 480)
        return (big[0] if big else max(sized))[1]
    return urls[len(urls) // 2]


def _best_stream(urls):
    def score(u):
        u = u.lower()
        sc = 15 if '.m3u8' in u else 0
        if any(k in u for k in ('hd', '1080', '720', 'hq', 'high')):
            sc += 10
        if any(k in u for k in ('sd', '480', '360', 'lq', 'low')):
            sc -= 10
        return sc
    return sorted(urls, key=score, reverse=True)[0] if urls else ''


_LIST_KEYS = ('items', 'results', 'videos', 'data', 'payload', 'mixes', 'entries', 'list', 'content', 'docs', 'hits')


def _auto_list(x, depth=0):
    """Pfad zeigt auf eine Liste -> fertig. Zeigt er auf ein Objekt, die Liste darin suchen (bekannte Namen, sonst die größte)."""
    if isinstance(x, list) or not isinstance(x, dict):
        return x
    for k in _LIST_KEYS:
        v = x.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    if depth < 2:
        for k in _LIST_KEYS:
            if isinstance(x.get(k), dict):
                r = _auto_list(x[k], depth + 1)
                if isinstance(r, list) and r and isinstance(r[0], dict):
                    return r
    lists = [v for v in x.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
    if lists:
        return max(lists, key=len)
    vals = list(x.values())
    return vals if vals and all(isinstance(v, dict) for v in vals) else [x]


def _from_json(text, base, P, sec=None):
    j = P['list']['json']
    try:
        data = json.loads((text or '').lstrip('﻿'))
    except Exception:
        return []
    if (j.get('sectionPath') or '').strip() and sec is not None:      # Abschnitt Nr. sec der Seite
        secs = _walk(data, j['sectionPath'].strip())
        node = secs[sec] if isinstance(secs, list) and 0 <= sec < len(secs) else None
        items = _walk(node, (j.get('sectionItems') or 'teasers').strip()) if node is not None else []
    elif '+' in (j.get('path') or ''):                         # mehrere Listen hintereinander: pfad1 + pfad2
        items = []
        for pp in j['path'].split('+'):
            sub = _auto_list(_walk(data, pp.strip()))
            items += [x for x in sub if isinstance(x, dict)] if isinstance(sub, list) else []
    else:
        items = _auto_list(_walk(data, j.get('path')))
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        video = _abs(_jval(it, j.get('video')), base) if j.get('video') else ''
        poster = _abs(_jval(it, j.get('poster')).replace('{width}', '480').replace('{height}', '270'), base)
        if j.get('videoAny') or (j.get('imageAny') and not poster):
            blob = json.dumps(it).replace('\\/', '/')
            if j.get('videoAny') and not video:
                bad = [x.strip() for x in (j.get('videoExclude') or '').split(',') if x.strip()]
                urls = [u for u in set(_STREAM_URL.findall(blob)) if not any(b in u for b in bad) and not _BAD.search(u)]
                video = _best_stream(urls)
            if j.get('imageAny') and not poster:
                imgs = re.findall(r'https?://[^"\'\s<>\\]+?\.(?:jpe?g|png|webp)(?:\?[^"\'\s<>\\]*)?', blob, re.I)
                poster = imgs[0] if imgs else ''
        link = _abs(_jval(it, j.get('link')), base) or video
        r = _rec(_jval(it, j.get('title')), link, poster, _jval(it, j.get('plot')), _jval(it, j.get('date')),
                 _jval(it, j.get('duration')), video)
        if (j.get('folderField') or '').strip():                  # Eintrag ist ein Ordner (z. B. Sendung), wenn das Feld zum Muster passt
            fv = _jval(it, j['folderField'])
            frx = _rx(j.get('folderPattern') or '')
            r['folder'] = bool(frx.search(fv)) if frx else bool(fv)
        out.append(r)
    return out


def _from_regex(text, base, P):
    try:
        rx = re.compile(P['list']['regex'].get('pattern') or '(?!x)x', re.I | re.S)
    except re.error as e:
        log.log('%s Ungültiger Regex: %s' % (_TAG, e), log.LOGWARNING)
        return []
    out = []
    for m in rx.finditer(text or ''):
        g = m.groupdict()
        out.append(_rec(_clean(g.get('title')), _abs(g.get('url') or g.get('link'), base), _abs(g.get('image') or g.get('poster'), base),
                        _clean(g.get('plot')), g.get('date') or '', g.get('duration') or '', ''))
    return out


def _from_html(html, base, P):
    if htmlscrape is None:
        return []
    h = P['list']['html']
    root = htmlscrape.parse(html)
    out = []
    for n in htmlscrape.select(root, h.get('item') or ''):
        def g(k):
            return htmlscrape.get(n, h.get(k), base) if h.get(k) else ''
        link = g('link')
        if not link and n.tag == 'a' and n.attrs.get('href'):        # Eintrag ist selbst der Link
            link = _abs(n.attrs.get('href'), base)
        out.append(_rec(g('title'), link, g('poster'), g('plot'), g('date'), g('duration'), g('video')))
    return out


def _from_links(html, base, cat, P):
    if htmlscrape is None:
        return []
    lk = P['list']['links']
    root = htmlscrape.parse(html)
    scopes = htmlscrape.select(root, lk['scope']) if lk.get('scope') else [root]
    must = [s.strip().lower() for s in (lk.get('contains') or '').split(',') if s.strip()]
    nope = [s.strip().lower() for s in (lk.get('exclude') or '').split(',') if s.strip()]
    rx = None
    if lk.get('regex'):
        try:
            rx = re.compile(lk['regex'])
        except re.error:
            rx = None
    seen, out = set(), []
    cat_path = urlparse(cat or '').path.rstrip('/').lower() if lk.get('underCategory') else ''
    poster_rule = lk.get('poster') or 'img@data-src|data-lazy-src|data-original|src||@bg'

    def in_noise(n):
        p = n.parent
        while p is not None:
            if p.tag in ('nav', 'header', 'footer', 'aside'):
                return True
            p = p.parent
        return False

    for sc in scopes:
        for a in sc.iter():
            if a.tag != 'a':
                continue
            if lk.get('skipNoise', True) and in_noise(a):
                continue
            href = (a.attrs.get('href') or '').strip()
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            url = _abs(href, base)
            low = url.lower()
            host = (urlparse(url).hostname or '').lower().replace('www.', '')
            if lk.get('sameSite', True) and host and host != _SITE and not host.endswith('.' + _SITE):
                continue
            if must and not any(s in low for s in must):
                continue
            if any(s in low for s in nope):
                continue
            path = urlparse(url).path
            if rx and not rx.search(path):
                continue
            if cat_path and not path.lower().startswith(cat_path):
                continue
            if url in seen:
                continue
            heads = [x for x in a.iter() if x.tag in ('h1', 'h2', 'h3', 'h4', 'h5')]
            title = _clean(heads[0].text()) if heads else ''
            if not title:
                title = _clean(a.attrs.get('title') or '')
            if not title:
                imgs = [x for x in a.iter() if x.tag == 'img' and x.attrs.get('alt')]
                title = _clean(imgs[0].attrs['alt']) if imgs else ''
            if not title:
                raw = _clean(a.text())
                half = len(raw) // 2
                title = raw[:half].strip() if len(raw) > 20 and len(raw) % 2 == 0 and raw[:half] == raw[half:] else raw
            if not title:
                continue
            seen.add(url)
            poster = htmlscrape.get(a, poster_rule, base)
            if not poster and a.parent is not None:
                poster = htmlscrape.get(a.parent, poster_rule, base)
            dur = ''
            if lk.get('durationRule'):
                dur = htmlscrape.get(a, lk['durationRule'], base) or (htmlscrape.get(a.parent, lk['durationRule'], base) if a.parent is not None else '')
            elif lk.get('durationAuto'):
                for src in (a, a.parent):
                    if src is None:
                        continue
                    ts = re.findall(r'(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)(?!\d)', _clean(src.text())[:400])
                    if ts:
                        dur = sorted(ts, key=_dur_secs, reverse=True)[0]
                        break
            plot = ''
            if lk.get('plotFromParent'):
                box = a.parent
                while box is not None and box.tag not in ('article', 'div', 'li', '#root'):
                    box = box.parent
                if box is not None and box.tag != '#root':
                    ps = [x for x in box.iter() if x.tag == 'p' and len(_clean(x.text())) > 20]
                    plot = _clean(ps[0].text()) if ps else ''
            out.append(_rec(title, url, poster, plot, '', dur))
    return out


def _finish(recs, P):
    mn, mx = int(P['list'].get('minTitle') or 0), int(P['list'].get('maxTitle') or 0)
    blocked = [s.strip().lower() for s in (P['list'].get('blocked') or '').split(',') if s.strip()]
    seen, out = set(), []
    minsec = _min_minutes(P) * 60
    for r in recs:
        r['title'] = _title(r['title'])
        t = r['title']
        if not t or not r['link'] or r['link'] in seen:
            continue
        if len(t) < mn or (mx and len(t) > mx) or any(b in t.lower() for b in blocked):
            continue
        if r['link'].startswith(('#', 'javascript:')):
            continue
        d = _dur_secs(r.get('duration'))
        if minsec and 0 < d < minsec:
            continue
        seen.add(r['link'])
        out.append(r)
    if P['list'].get('sortDate'):
        def dkey(r):
            raw = (r.get('date') or '').strip()
            try:
                return parsedate_to_datetime(raw).timestamp()
            except Exception:
                try:
                    return datetime.fromisoformat(raw.replace('Z', '+00:00')).timestamp()
                except Exception:
                    return 0
        out.sort(key=dkey, reverse=True)
    if P['list'].get('sortId'):
        def key(r):
            m = re.search(r'(\d+)(?:\.\w+)?/?$', urlparse(r['link']).path)
            return int(m.group(1)) if m else 0
        out.sort(key=key, reverse=True)
    return out


def _parse(body, base, cat, P, sec=None):
    mode = P['list'].get('mode')
    if mode == 'rss':
        recs = _from_rss(body)
    elif mode == 'json':
        recs = _from_json(body, base, P, sec)
    elif mode == 'regex':
        recs = _from_regex(body, base, P)
    elif mode == 'links':
        recs = _from_links(body, base, cat, P)
    else:
        recs = _from_html(body, base, P)
    for r in recs:
        r['link'] = _abs(r['link'], base)
    return _finish(recs, P)


# ----------------------------------------------------------------------------- Seitenschaltung

def _with_param(url, name, value):
    try:
        p = urlsplit(url)
        q = dict(parse_qsl(p.query, keep_blank_values=True))
        q[name] = str(value)
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ''))
    except Exception:
        return url + ('&' if '?' in url else '?') + '%s=%s' % (name, value)


def _with_params(url, names, value):
    """Seitennummer setzen; mehrere Namen (durch Komma getrennt) werden alle gesetzt."""
    for nm in [x.strip() for x in str(names or 'page').split(',') if x.strip()] or ['page']:
        url = _with_param(url, nm, value)
    return url


def _sections(body, url, pi, J):
    """Seite aus Abschnitten (z. B. widgets[] mit Titel und teasers[]): jeder Abschnitt wird ein Ordner. Nur ein Abschnitt -> gleich dessen Inhalt."""
    try:
        data = json.loads((body or '').lstrip('\ufeff'))
    except Exception:
        return [], None
    secs = _walk(data, J['sectionPath'].strip())
    skip = _rx(J.get('sectionSkip') or '')
    rows, valid = [], []
    for i, sc in enumerate(secs if isinstance(secs, list) else []):
        its = _walk(sc, (J.get('sectionItems') or 'teasers').strip())
        t = _title(_clean(_jval(sc, J.get('sectionTitle') or 'title')))
        if not isinstance(its, list) or not its or (skip and skip.search(t)):
            continue
        valid.append(i)
        rows.append(_folder(t or 'Abschnitt %d' % (len(valid)), 'list:1:%d:%s#sec=%d' % (int(pi), url, i), '%d Einträge' % len(its)))
    return rows, (valid[0] if len(valid) == 1 else None)


def _sec_by_name(body, J, pat):
    """Nummer des ersten Abschnitts, dessen Titel zum Muster passt (…#sec=^Unsere Top-Serien)."""
    try:
        data = json.loads((body or '').lstrip('\ufeff'))
    except Exception:
        return -1
    rx = _rx(pat)
    secs = _walk(data, J['sectionPath'].strip())
    for i, sc in enumerate(secs if isinstance(secs, list) else []):
        its = _walk(sc, (J.get('sectionItems') or 'teasers').strip())
        if rx and isinstance(its, list) and its and rx.search(_clean(_jval(sc, J.get('sectionTitle') or 'title'))):
            return i
    return -1


def _list(url, page, search=False, pi=0, prefetched=None):
    P = _pr(pi)
    sec, secname = None, ''
    msec = re.search(r'#sec=(.+)$', url)
    if msec:
        if msec.group(1).isdigit():
            sec = int(msec.group(1))
        else:
            secname = msec.group(1)
        url = url[:msec.start()]
    mode = P['paging'].get('mode') or 'none'
    if search and mode == 'pattern':
        mode = 'param'
    start = P['paging'].get('start')
    start = 1 if start in (None, '') else int(start)           # 0 ist erlaubt (Seiten ab 0 gezählt)
    fetch = url
    J = P['list'].get('json') or {}
    SL = (J.get('sectionLink') or '').strip() if (P['list'].get('mode') == 'json' and (J.get('sectionPath') or '').strip()) else ''
    use_sl = bool(SL) and page > 1 and mode == 'param' and prefetched is None     # weitere Seiten über die Adresse des Abschnitts selbst
    if page > 1 and mode == 'param' and not use_sl:
        fetch = _with_params(url, P['paging'].get('param') or 'page', page - 1 + start)
    elif page > 1 and mode == 'pattern':
        fetch = (P['paging'].get('pattern') or '{url}/page/{page}/').replace('{url}', url.rstrip('/')).replace('{page}', str(page - 1 + start))
    body = _get(fetch) if prefetched is None else prefetched
    auto_sec = False
    if P['list'].get('mode') == 'json' and (J.get('sectionPath') or '').strip() and prefetched is None:
        if secname:
            sec = _sec_by_name(body, J, secname)
            if sec < 0:
                return [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
        if sec is None:
            rows, one = _sections(body, url, pi, J)
            if one is None:
                return rows or [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
            sec = one
            auto_sec = True
        if not auto_sec:
            mode = 'none'                                  # gewählter Abschnitt einer Sammelseite: keine Seitenschaltung
        elif use_sl:
            try:                                           # Seite 2, 3, …: Adresse des Abschnitts (z. B. links.self.href) mit neuer Seitennummer abrufen
                secs = _walk(json.loads(body.lstrip('\ufeff')), J['sectionPath'].strip())
                link = _walk(secs[sec], SL)
                wurl = _with_params(_abs(link, fetch), P['paging'].get('param') or 'page', page - 1 + start)
                root = node = {}
                parts = J['sectionPath'].strip().split('.')
                for part in parts[:-1]:
                    node[part] = {}
                    node = node[part]
                node[parts[-1]] = [json.loads(_get(wurl).lstrip('\ufeff'))]
                body, sec, fetch = json.dumps(root), 0, wurl
            except Exception:
                return [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
    recs = _parse(body, fetch, url, P, sec)
    last = page
    if _min_minutes(P) and mode in ('param', 'pattern'):          # nach dem Filter genug Einträge sammeln
        seen_l = {r['link'] for r in recs}
        for extra in range(1, 5):
            if len(recs) >= 20:
                break
            pn = page + extra
            nf = _with_params(url, P['paging'].get('param') or 'page', pn - 1 + start) if mode == 'param' else \
                (P['paging'].get('pattern') or '{url}/page/{page}/').replace('{url}', url.rstrip('/')).replace('{page}', str(pn - 1 + start))
            more = [r for r in _parse(_get(nf), nf, url, P, sec) if r['link'] not in seen_l]
            if not more:
                break
            seen_l.update(r['link'] for r in more)
            recs += more
            last = pn
    nxt = None
    mf = (P['paging'].get('moreField') or '').strip()
    if mf and mode in ('param', 'pattern'):
        try:
            if not _walk(json.loads(body.lstrip('\ufeff')), mf):
                mode = 'none'                    # API meldet: keine weitere Seite
        except Exception:
            pass
    tf, sf = (P['paging'].get('totalField') or '').strip(), (P['paging'].get('sizeField') or '').strip()
    if tf and sf and mode in ('param', 'pattern'):          # Gesamtzahl und Seitengröße aus der Antwort: weiter nur, wenn noch etwas fehlt
        try:
            data = json.loads(body.lstrip('\ufeff'))
            node = data
            if sec is not None and (J.get('sectionPath') or '').strip():
                secs = _walk(data, J['sectionPath'].strip())
                node = secs[sec] if isinstance(secs, list) and 0 <= sec < len(secs) else data
            tfs, sfs = [x.strip() for x in tf.split(',') if x.strip()], [x.strip() for x in sf.split(',') if x.strip()]
            more_left = False
            for tfx, sfx in zip(tfs, sfs):                      # mehrere Paare (z. B. Sendungen und Videos): weiter, solange bei einem noch etwas fehlt
                total, size = float(_walk(node, tfx)), float(_walk(node, sfx))
                if size > 0 and total > (page - 1 + start + 1) * size:
                    more_left = True
            if not more_left:
                mode = 'none'
        except Exception:
            pass
    if prefetched is not None:
        mode = 'none'                            # Treffer einer POST-Suche: keine weiteren Seiten
    state = 'slist' if search else 'list'
    sp = lambda pg, u: '%s:%d:%d:%s' % (state, pg, int(pi), u)
    if mode in ('param', 'pattern'):
        if len(recs) >= max(1, int(P['paging'].get('min') or 1)):
            nxt = sp(last + 1, url)
    elif mode == 'link' and recs and htmlscrape is not None and P['paging'].get('rule'):
        n = htmlscrape.pick(body, P['paging']['rule'], fetch)
        if n and n != fetch:
            nxt = sp(1, n)
    elif mode == 'jsonnext' and recs and (P['paging'].get('nextField') or '').strip():
        try:
            n = _walk(json.loads(body.lstrip('\ufeff')), P['paging']['nextField'].strip())
        except Exception:
            n = None
        if isinstance(n, str) and n.strip() and _abs(n, fetch) != fetch:
            nxt = sp(1, _abs(n, fetch))
    elif mode == 'local':
        per = max(1, int(P['list'].get('perPage') or 30))
        s = (page - 1) * per
        if len(recs) > s + per:
            nxt = sp(page + 1, url)
        recs = recs[s:s + per]
    items = [_item(r, P, pi) for r in recs]
    if not items:
        return [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
    if nxt:
        items.append(_folder(_L.get('next') or 'Nächste Seite >>', nxt))
    log.log('%s %s Seite %d: %d Einträge' % (_TAG, fetch, page, len(items)))
    return items


def _next_profile(P, pi):
    try:
        n = int(P.get('next'))
        if 0 <= n < len(_PROFILES):
            return n
    except (TypeError, ValueError):
        pass
    return int(pi)


_SER = CFG.get('series') or {}


def _rx(pat, flags=re.I):
    try:
        return re.compile(pat, flags) if (pat or '').strip() else None
    except re.error:
        return None


def _series_item(it, r):
    """Eintrag einer Serie: öffnet erst die Staffeln (oder gleich die Folgen, wenn die Staffel im Titel steht)."""
    rx = _rx(_SER.get('isSeries'))
    if not rx or not rx.search(r['title']):
        return False
    sm = _rx(_SER.get('seasonInTitle'))
    m = sm.search(r['title']) if sm else None
    if m and m.groups() and (m.group(1) or '').isdigit():
        it['url'] = 'eps:%d:%s' % (int(m.group(1)), r['link'])
        it['season'] = int(m.group(1))
    else:
        it['url'] = 'seasons:' + r['link']
    it.update({'is_playable': False, 'next_func': 'showEntries', 'mediatype': 'tvshow'})
    return True


def _numbers(body, lines, season=None):
    """Zahlen aus der Seite: je Zeile ein Muster, die erste Zeile mit Treffern gewinnt (sortiert, ohne Doppelte)."""
    for line in (lines or '').splitlines():
        line = line.strip().replace('{season}', str(season if season is not None else ''))
        rx = _rx(line, re.I | re.S)
        if not rx:
            continue
        nums = sorted({int(m.group(1) if m.groups() else m.group(0)) for m in rx.finditer(body)
                       if (m.group(1) if m.groups() else m.group(0)).strip().isdigit()})
        if nums:
            return nums
    return []


def _seasons(url):
    body = _get(url)
    nums = _numbers(body, _SER.get('seasonsFrom'))
    if not nums:
        return [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
    return [dict(_folder('%s %d' % (_L.get('season') or 'Staffel', n), 'eps:%d:%s' % (n, url)), season=n) for n in nums]


def _episodes(season, url):
    body = _get(url)
    nums = _numbers(body, _SER.get('episodesFrom'), season)
    names, per = [], '{episode}' in (_SER.get('episodeNames') or '')
    if not per:                                     # ein Muster, das alle Namen der Reihe nach findet
        nrx = _rx(_SER.get('episodeNames'), re.I | re.S)
        if nrx:
            names = [_title(_clean(m.group(1) if m.groups() else m.group(0))) for m in nrx.finditer(body)]
        if not nums and names:
            nums = list(range(1, len(names) + 1))
    if not nums:
        return [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
    out = []
    for i, n in enumerate(nums):
        if per:                                     # Muster mit {season} und {episode}: Name genau dieser Folge
            nrx = _rx(_SER['episodeNames'].replace('{season}', str(season)).replace('{episode}', str(n)), re.I | re.S)
            nm = nrx.search(body) if nrx else None
            name = _title(_clean(nm.group(1) if nm and nm.groups() else (nm.group(0) if nm else '')))
        else:
            name = names[i] if i < len(names) else ''
        name = name or '%s %d' % (_L.get('episode') or 'Folge', n)
        out.append({'title': name, 'url': 'ep:%d:%d:%s' % (season, n, url), 'season': season, 'episode': n,
                    'is_playable': True, 'next_func': 'get_hosters'})
    return out


def _episode_part(body, season, episode):
    """Der Teil der Seite, in dem die Quellen genau dieser Folge stehen (Fallback: ganze Seite)."""
    for line in (_SER.get('sectionFrom') or '').splitlines():
        rx = _rx(line.strip().replace('{season}', str(season)).replace('{episode}', str(episode)), re.I | re.S)
        m = rx.search(body) if rx else None
        if m:
            return m.group(1) if m.groups() else m.group(0)
    return body


def _item(r, P, pi):
    e = P.get('entry') or 'video'
    it = {'title': r['title'], 'poster': r['poster'], 'fanart': r['poster'], 'plot': _plot(r)}
    if _M.get('type') in ('news', 'live', 'adult') or e == 'article':
        it['live'] = True                       # kein Abgleich mit der Film-Datenbank
    ym = re.search(r'\b(19|20)\d{2}\b', r.get('date') or '')
    if ym and e in ('video', 'stream', 'folder'):
        it['year'] = ym.group(0)
    if e == 'folder' or (r.get('folder') and e in ('video', 'stream')):
        it.update({'url': 'list:1:%d:%s' % (_next_profile(P, pi), r['link']), 'is_playable': False, 'next_func': 'showEntries'})
        note = (P['list'].get('json') or {}).get('folderNote') or ''
        if r.get('folder') and note.strip():
            it['plot'] = (note.strip() + ('\n\n' + it['plot'] if it['plot'] else ''))
    elif e == 'article':
        it.update({'url': r['link'] + (('#v=' + quote(r['video'], safe='')) if r['video'] else ''), 'is_playable': False, 'next_func': 'showArticle'})
    elif e == 'stream':
        it.update({'url': 'stream:' + (r['video'] or r['link']), 'is_playable': True, 'next_func': 'get_hosters'})
    elif e == 'video' and _SER.get('enabled') and _series_item(it, r):
        return it
    else:
        it.update({'url': ('stream:' + r['video']) if r['video'] else r['link'], 'is_playable': True, 'next_func': 'get_hosters'})
    if e in ('video', 'stream') and not r.get('folder'):
        it['mediatype'] = 'movie' if _M.get('type') in ('movie', 'both') else 'video'
    return it


# ----------------------------------------------------------------------------- Menüs (MovieScout)

def _dates(u):
    """{date} = heute, {date-1} = gestern, {date-2} …  (Format 2026-10-28)"""
    return re.sub(r'\{date(?:([+-]\d+))?\}', lambda m: (datetime.now() + timedelta(days=int(m.group(1) or 0))).strftime('%Y-%m-%d'), u or '')


def _menu_items(group):
    """Menüpunkte der Hauptebene (group=None; Gruppen erscheinen als Ordner) oder einer Gruppe."""
    items, seen = [], set()
    for i, m in enumerate(CFG.get('menu') or []):
        if not m.get('url'):
            continue
        g = (m.get('group') or '').strip()
        if group is None and g:
            if g not in seen:
                seen.add(g)
                items.append(_folder(g, 'grp:%d' % i, ''))
            continue
        if group is not None and g != group:
            continue
        if m.get('kind') == 'links':
            items.append(_folder(m['title'], 'menu:%d' % i, m.get('plot') or ''))
        else:
            items.append(_folder(m['title'], 'list:1:%d:%s' % (int(m.get('profile') or 0), _dates(m['url'])), m.get('plot') or ''))
    return items


def load(url='', params=None):
    if url == 'toggle_dauer':
        _cycle_min()
        url = ''
    if url:
        return showEntries(url)
    items = _menu_items(None)
    items.append({'title': _L.get('search') or '[ Suche nach ]', 'url': 'search', 'plot': '', 'is_playable': False, 'next_func': 'do_search'})
    fp = next((q for q in _PROFILES if q['list'].get('filterMenu')), None)
    if fp is not None:
        cur = str(_min_minutes(fp))
        items.append({'title': (_L.get('filter') or 'Filter: Mindestdauer {min} (ändern)').replace('{min}', 'keine' if cur == '0' else cur + ' Min.'),
                      'url': 'toggle_dauer', 'plot': 'Kürzere Videos ausblenden. Ein Klick schaltet weiter: 5 / 10 / 15 / 20 / 30 / 45 Minuten oder keine.',
                      'is_playable': False, 'next_func': 'load'})
    return items


def _menu_links(i):
    try:
        m = CFG['menu'][i]
    except Exception:
        return []
    body = _get(_dates(m['url']))
    if htmlscrape is None:
        return []
    out, seen = [], set()
    for a in htmlscrape.select(htmlscrape.parse(body), m.get('rule') or 'a'):
        if a.tag != 'a':
            continue
        href = _abs(a.attrs.get('href'), m['url'])
        t = _title(_clean(a.text() or a.attrs.get('title')))
        if href and t and href not in seen and not href.startswith(('#', 'javascript:')):
            seen.add(href)
            out.append(_folder(t, 'list:1:%d:%s' % (int(m.get('profile') or 0), href)))
    return out or [_row(_L.get('empty') or 'Keine Einträge gefunden.')]


def showEntries(url='', params=None):
    if not url:
        return load()
    if url.startswith('menu:'):
        return _menu_links(int(url[5:]))
    if url.startswith('seasons:'):
        return _seasons(url[8:])
    if url.startswith('eps:'):
        _, sn, link = url.split(':', 2)
        return _episodes(int(sn), link)
    if url.startswith('grp:'):
        try:
            return _menu_items((CFG['menu'][int(url[4:])].get('group') or '').strip()) or [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
        except Exception:
            return [_row(_L.get('empty') or 'Keine Einträge gefunden.')]
    page, search, pi = 1, False, 0
    for pre in ('slist:', 'list:'):
        if url.startswith(pre):
            search = pre == 'slist:'
            parts = url.split(':', 3)
            if len(parts) == 4 and parts[2].isdigit():          # list:<seite>:<aufbau>:<adresse>
                page, pi, url = int(parts[1]), int(parts[2]), parts[3]
            else:                                              # ältere Form list:<seite>:<adresse>
                _, p, url = url.split(':', 2)
                page = int(p)
            break
    return _list(url, page, search, pi)

def search(query='', params=None):
    q = (query or '').strip()
    tpl = (CFG.get('search') or {}).get('url') or ''
    if not q or not tpl:
        return []
    sc = CFG.get('search') or {}
    tok = ''
    if (sc.get('tokenFrom') or '').strip():                  # Kennung vorher von einer Seite holen (z. B. dle_login_hash, nonce)
        trx = _rx(sc['tokenFrom'], re.I | re.S)
        tm = trx.search(_get((sc.get('tokenUrl') or '').strip() or 'https://%s/' % SITE_DOMAIN)) if trx else None
        tok = (tm.group(1) if tm and tm.groups() else (tm.group(0) if tm else '')) or ''
        if not tok:
            log.log('%s Suche: Kennung nicht gefunden' % _TAG, log.LOGWARNING)
            return []
    fill = lambda t, form: (t or '').replace('{token}', quote_plus(tok) if form else tok)
    if sc.get('method') == 'post':
        body = sc.get('body') or ''
        body = fill(body, not body.strip().startswith(('{', '[')))
        u = fill(tpl, True).replace('{q}', quote_plus(q))
        return _list(u, 1, True, int(sc.get('profile') or 0), prefetched=_post(u, body, q))
    return _list(fill(tpl, True).replace('{q}', quote_plus(q)), 1, True, int(sc.get('profile') or 0))


def do_search(url='', params=None):
    import xbmcgui
    q = xbmcgui.Dialog().input(_L.get('searchPrompt') or 'Suche nach', type=xbmcgui.INPUT_ALPHANUM)
    return search(q) if q else []


def nothing(url='', params=None):
    return []


# ----------------------------------------------------------------------------- Artikel

def _meta(html, prop):
    for pat in (r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)',
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']'):
        m = re.search(pat % re.escape(prop), html or '', re.I)
        if m:
            return unescape(m.group(1)).strip()
    return ''


def _ld(html):
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


def _article_text(html, url=''):
    words = [w.strip().lower() for w in (_A.get('paywall') or '').split(',') if w.strip()]
    teaser = _meta(html, 'og:description') or _meta(html, 'description')
    low = ((html or '') + ' ' + (url or '')).lower()
    body, locked = '', False
    for o in _ld(html):
        if any(t.endswith('article') or t == 'blogposting' for t in _types(o)):
            if str(o.get('isAccessibleForFree')).lower() == 'false':
                locked = True
            if not body and isinstance(o.get('articleBody'), str):
                body = o['articleBody']
    if locked or (words and any(w in low for w in words)):
        return [teaser or _L.get('locked') or 'Dieser Beitrag ist nicht frei lesbar.', _L.get('locked') or 'Der vollständige Beitrag ist nicht frei lesbar.']
    paras = []
    if body and _A.get('useLd', True):
        paras = [p.strip() for p in re.split(r'\n\s*\n', unescape(body)) if p.strip()]
    mn = int(_A.get('minLen') or 40)
    if not paras and htmlscrape is not None:
        root = htmlscrape.parse(html)
        for sel in [s.strip() for s in (_A.get('selectors') or 'article p').split(',') if s.strip()]:
            found = []
            for n in htmlscrape.select(root, sel):
                t = _clean(n.text())
                if len(t) >= mn and t not in found:
                    found.append(t)
            if found:
                paras = found
                break
    return paras or [teaser or _L.get('noText') or 'Kein Artikeltext gefunden.']


def showArticle(url='', params=None):
    extra = ''
    if '#v=' in url:                                  # Video aus dem Feed (Anhang) mitgeführt
        url, extra = url.split('#v=', 1)
        extra = unquote(extra)
    html = _get(url)
    if not html and not extra:
        return [_row(_L.get('loadError') or 'Seite konnte nicht geladen werden.')]
    items = []
    if html and _find(html, url):
        items.append({'title': _L.get('video') or '▶ Video abspielen', 'url': url, 'plot': _meta(html, 'og:title'),
                      'poster': _abs(_meta(html, 'og:image'), url), 'is_playable': True, 'next_func': 'get_hosters'})
    elif extra:
        items.append({'title': _L.get('video') or '▶ Video abspielen', 'url': 'stream:' + extra, 'plot': '',
                      'poster': _abs(_meta(html, 'og:image'), url) if html else '', 'is_playable': True, 'next_func': 'get_hosters'})
    if not html:
        return items
    if _A.get('showDate', True):
        d = ''
        m = re.search(r'<time\b[^>]*>(.*?)</time>', html, re.S | re.I)
        if m:
            d = _clean(m.group(1))
        if not d:
            d = _date(_meta(html, 'article:published_time') or _meta(html, 'pubdate'))
        if d:
            items.append(_row('%s %s' % (_L.get('published') or 'Veröffentlicht am:', d)))
    items.extend(_row(p) for p in _article_text(html, url))
    return items


# ----------------------------------------------------------------------------- Videos finden

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _final_url(url):
    """Token-Link ohne Dateiendung -> die Datei, auf die er weiterleitet (bei Fehler die Original-URL)."""
    try:
        req = urllib.request.Request(url, headers=_headers())
        try:
            urllib.request.build_opener(_NoRedirect).open(req, timeout=10).close()
        except urllib.error.HTTPError as e:
            loc = e.headers.get('Location') if e.code in (301, 302, 303, 307, 308) else ''
            if loc:
                return urljoin(url, loc)
    except Exception as e:
        log.log('%s Weiterleitung nicht aufgelöst (%s): %s' % (_TAG, url, e), log.LOGWARNING)
    return url


_QUAL = {}                       # Adresse -> Bildhöhe, falls die Antwort sie neben dem Link nennt ("quality": "1080")
_URL_KEYS = ('videoUrl', 'videoURL', 'url', 'src', 'file', 'contentUrl', 'stream', 'href', 'link')
_QUAL_KEYS = ('quality', 'height', 'maxVResolutionPx', 'resolution', 'label', 'res', 'definition')


_QNAMES = {'low': 288, 'med': 360, 'medium': 360, 'high': 480, 'veryhigh': 720, 'hd': 1080, 'fhd': 1080, 'uhd': 2160}


def _json_streams(obj, out, q=0):
    if isinstance(obj, dict):
        if str(obj.get('class') or '').lower() == 'ad' or obj.get('isAudioDescription') is True:           # Audiodeskription (Hörfilm-Tonspur) auslassen
            return
        qn = obj.get('quality')
        if isinstance(qn, str) and qn.lower() in _QNAMES:
            q = _QNAMES[qn.lower()]
        for k in _URL_KEYS:
            v = obj.get(k)
            if isinstance(v, str):
                u = _unjs(v)
                if u.startswith('//'):
                    u = 'https:' + u
                if u.startswith(('http://', 'https://')) and _STREAM.search(u):
                    for qk in _QUAL_KEYS:
                        m = re.search(r'(\d{3,4})', str(obj.get(qk) or ''))
                        if m and 144 <= int(m.group(1)) <= 4320:
                            _QUAL[u] = int(m.group(1))
                            break
        for v in obj.values():
            _json_streams(v, out, q)
    elif isinstance(obj, list):
        for v in obj:
            _json_streams(v, out, q)
    elif isinstance(obj, str):
        u = _unjs(obj)
        if u.startswith(('http://', 'https://', '//')) and _STREAM.search(u):
            out.append(u)
            if q and u not in _QUAL:
                _QUAL[u] = q


def _find(html, base):
    """Videos/Hoster einer Seite -> [{'url','direct','name'}] – nach den im Baukasten angehakten Verfahren."""
    html = html or ''
    text = _unjs(html)
    m = _V.get('methods') or {}
    out, seen = [], set()

    def add(u, direct, name=''):
        u = _unjs(str(u or '')).strip()
        if not u:
            return
        u = _abs(u, base)
        if not u.startswith('http') or u in seen:
            return
        if direct and _BAD.search(urlparse(u).path):
            return
        seen.add(u)
        out.append({'url': u, 'direct': direct, 'name': name})

    if m.get('jsonld'):
        for o in _ld(html):
            if 'videoobject' in _types(o) and o.get('contentUrl'):
                add(o['contentUrl'], True, _clean(o.get('name') or ''))
    if m.get('og'):
        for prop in ('og:video', 'og:video:url', 'og:video:secure_url', 'twitter:player:stream'):
            v = _meta(html, prop)
            if v and _STREAM.search(v):
                add(v, True)
    if m.get('tags'):
        for mm in re.finditer(r'<(?:video|source)\b[^>]+\bsrc=["\']([^"\']+)', text, re.I):
            add(unescape(mm.group(1)), True)
    if m.get('direct'):
        for mm in _STREAM_URL.finditer(text):
            if not _BAD.search(mm.group(0)):
                add(mm.group(0), True)
    for line in (m.get('regex') or '').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rx = re.compile(line, re.I | re.S)
        except re.error:
            continue
        for mm in list(rx.finditer(text))[:40]:
            u = mm.group(1) if mm.groups() else mm.group(0)
            lab = ''
            if len(mm.groups()) >= 2 and mm.group(2):                 # zweite Klammer = Beschriftung des Hosters (z. B. „VOE 1080p“)
                lab = re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', mm.group(2)))).strip()[:60]
            add(u, bool(_STREAM.search(u or '')) or bool(_V.get('regexDirect')), lab)
    if m.get('iframe') and htmlscrape is not None:
        for e in htmlscrape.embeds(html, base):
            add(e['url'], e['direct'], e['name'])
    if m.get('json') and text.lstrip().startswith(('{', '[')):       # Seite ist JSON: Streams samt Qualität daraus lesen
        try:
            found_j = []
            _json_streams(json.loads(text.lstrip('\ufeff').strip()), found_j)
            for f in found_j:
                add(f, True)
        except Exception:
            pass
    if m.get('apiFrom') and m.get('apiUrl'):
        try:
            rx = re.compile(m['apiFrom'], re.I | re.S)
        except re.error:
            rx = None
        done_api = set()
        for mm in (list(rx.finditer(text))[:6] if rx else []):
            u = m['apiUrl']
            for i, g in enumerate(mm.groups(), 1):
                u = u.replace('{%d}' % i, g or '')
            if u in done_api:
                continue
            done_api.add(u)
            body = _get(u, referer=None if (_M.get('referer') or '').strip() else base, accept='application/json,text/plain,*/*')
            found = []
            try:
                _json_streams(json.loads(body.lstrip('﻿').strip()), found)
            except Exception:
                pass
            if not found:                                             # kein JSON/keine Links darin: im Text suchen
                found += _STREAM_URL.findall(_unjs(body))
            for f in found:
                add(f, True)
    return out


def _label_quality(label):
    t = label or ''
    if re.search(r'2160|4k|uhd', t, re.I):
        return '4K'
    mm = re.search(r'(1440|1080|720|576|480|360)', t)
    return ('%sp' % mm.group(1)) if mm else ''


def _quality_from(body):
    """Qualität aus einem Text der Seite (Muster aus „Qualität lesen aus“), z. B. Release-Name -> 1080p."""
    rx = (_V.get('qualityFrom') or '').strip()
    if not rx or not body:
        return ''
    try:
        m = re.search(rx, body, re.I)
    except re.error:
        return ''
    t = (m.group(1) if m and m.groups() else (m.group(0) if m else '')) or ''
    if re.search(r'2160|4k|uhd', t, re.I):
        return '4K'
    mm = re.search(r'(1440|1080|720|576|480|360)', t)
    return ('%sp' % mm.group(1)) if mm else ''


def _host_name(u):
    try:
        h = urlparse(u).netloc.lower()
        return h[4:] if h.startswith('www.') else h
    except Exception:
        return ''


def _hdr(page):
    parts = []
    ref = _V.get('referer') or 'page'
    if ref == 'page' and page:
        parts.append('Referer=' + quote(page, safe=''))
    elif ref == 'site':
        parts.append('Referer=' + quote('https://%s/' % SITE_DOMAIN, safe=''))
    if _V.get('origin'):
        parts.append('Origin=' + quote('https://%s' % SITE_DOMAIN, safe=''))
    if _V.get('sendUa', True):
        parts.append('User-Agent=' + quote(_ua(), safe=''))
    return ('|' + '&'.join(parts)) if parts else ''


def _follow(cands, page):
    """Zweistufig: Links, die auf „weiter öffnen“ passen, werden geladen; ihre Quellen ersetzen den Link."""
    rx = _rx('|'.join(l.strip() for l in (_V.get('follow') or '').splitlines() if l.strip()))
    if not rx:
        return cands
    out, seen = [], set()
    for c in cands:
        if c['direct'] or not rx.search(c['url']):
            if c['url'] not in seen:
                seen.add(c['url'])
                out.append(c)
            continue
        body = re.sub(r'<!--.*?-->', '', _get(c['url']), flags=re.S)
        for sub in _find(body, c['url']):
            if sub['url'] not in seen and not rx.search(sub['url']):
                seen.add(sub['url'])
                out.append(sub)
    return out


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    if not url:
        return []
    page = ''
    _pq = ''
    if url.startswith('stream:'):
        cands = [{'url': url[7:], 'direct': True, 'name': ''}]
    else:
        sn = ep = 0
        if url.startswith('ep:'):
            _, sn, ep, url = url.split(':', 3)
            sn, ep = int(sn), int(ep)
        page = url
        _body = _get(url)
        if sn:
            _body = _episode_part(_body, sn, ep)
        cands = _find(_body, url)
        _pq = _quality_from(_body)
        cands = _follow(cands, url)
    skip = _rx('|'.join(l.strip() for l in (_V.get('skip') or '').splitlines() if l.strip()))
    if skip:
        cands = [c for c in cands if not skip.search(c['url'])]
    if not cands:
        log.log('%s Keine Quellen auf %s' % (_TAG, url), log.LOGWARNING)
        return []
    name = _L.get('hoster') or 'Video'
    def q_of(u):
        v = int((re.search(r'(\d{3,4})p', u) or [0, 0])[1] or 0) or _QUAL.get(u, 0)
        if not v:                                                  # …avc-720.mp4 / …_1080.m3u8
            mm = re.search(r'[-_](240|270|288|360|432|480|540|576|720|1080|1440|2160)\.(?:mp4|m3u8)', u)
            v = int(mm.group(1)) if mm else 0
        return v
    direct = [c for c in cands if c['direct']]
    others = [c for c in cands if not c['direct']]
    if _V.get('hlsFirst', True):
        direct.sort(key=lambda c: (0 if '.m3u8' in c['url'].lower() else 1, -q_of(c['url'])))
    else:
        direct.sort(key=lambda c: -q_of(c['url']))
    mixed = len({'.m3u8' in c['url'].lower() for c in direct[:int(_V.get('max') or 6)]}) > 1   # HLS und MP4 -> Namen unterscheiden
    out = []
    for c in (direct + others)[:int(_V.get('max') or 6)]:
        u = c['url']
        if c['direct']:
            if not _STREAM.search(u) and _V.get('resolveRedirect', True):
                u = _final_url(u)
            q = q_of(u)
            hls = '.m3u8' in u.lower()
            nm = ('%s %s' % (name, 'HLS' if hls else 'MP4')) if mixed else name
            if _V.get('nameFromHost'):
                nm = _host_name(u)
            out.append((nm, u + _hdr(page or 'https://%s/' % SITE_DOMAIN), True,
                        ('%dp' % q) if q else (_pq or ('HD' if (hls or re.search(r'(?:[_/.-]|^)(?:hd|fullhd)(?:[_/.-]|$)', urlparse(u).path, re.I)) else '')), _V.get('lang') or ''))
        else:
            out.append((_host_name(u) if _V.get('nameFromHost') else (c['name'] or name), u, False, _label_quality(c['name']) or _pq, _V.get('lang') or ''))
    log.log('%s %s: %d Quellen' % (_TAG, url, len(out)))
    return out
