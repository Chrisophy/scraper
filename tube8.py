# -*- coding: utf-8 -*-
# Tube8 
# IT('s) Possible 
# 2026.10.28
import html as _html
import json
import re
import unicodedata
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

from resources.lib import log, multiquest

SITE_ID       = 'tube8'
SITE_NAME     = 'Tube8 (18+)'
SITE_DOMAIN   = 'www.tube8.com'
TYPE          = 'adult'
GLOBAL_SEARCH = False
ACTIVE        = True

DOMAIN = 'https://www.tube8.com'
MIN_SETTING = 'tube8_min_minutes'
MIN_CHOICES = ['5', '10', '15', '20', '30', '45', '0']        
MIN_LABELS = {'5': '5 Minuten', '10': '10 Minuten', '15': '15 Minuten', '20': '20 Minuten',
              '30': '30 Minuten', '45': '45 Minuten', '0': 'keine (alle Videos)'}
FETCH_PAGES = 5            
WANT_VIDEOS = 30

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

CATEGORIES = [
    ('18-25', '/cat/teens/'), ('Amateur', '/cat/amateur/'), ('Anal', '/cat/anal/'), ('Arab', '/cat/arab/'), ('Asian', '/cat/asian/'),
    ('BBW', '/cat/bbw/'), ('Big Ass', '/cat/bigass/'), ('Big Dick', '/cat/bigdick/'), ('Big Tits', '/cat/bigtits/'), ('Blonde', '/cat/blonde/'),
    ('Blowjob', '/cat/blowjob/'), ('Bondage', '/cat/bondage/'), ('Brazilian', '/cat/brazilian/'), ('Brunette', '/cat/brunette/'), ('Bukkake', '/cat/bukkake/'),
    ('Cartoon', '/cat/cartoon/'), ('Casting', '/cat/casting/'), ('Celebrity', '/cat/celebrity/'), ('College (18+)', '/cat/college/'), ('Compilation', '/cat/compilation/'),
    ('Cosplay', '/cat/cosplay/'), ('Creampie', '/cat/creampie/'), ('Cuckold', '/cat/cuckold/'), ('Cumshot', '/cat/cumshot/'), ('Double Penetration', '/cat/doublepenetration/'),
    ('Ebony', '/cat/ebony/'), ('Erotic', '/cat/erotic/'), ('Feet', '/cat/feet/'), ('Female Orgasm', '/cat/femaleorgasm/'), ('Fetish', '/cat/fetish/'),
    ('Fingering', '/cat/fingering/'), ('Fisting', '/cat/fisting/'), ('French', '/cat/french/'), ('Funny', '/cat/funny/'), ('Gangbang', '/cat/gangbang/'),
    ('German', '/cat/german/'), ('Group', '/cat/group/'), ('HD', '/cat/hd/'), ('Handjob', '/cat/handjob/'), ('Hardcore', '/cat/hardcore/'),
    ('Hentai', '/cat/hentai/'), ('Indian', '/cat/indian/'), ('Interracial', '/cat/interracial/'), ('Japanese', '/cat/japanese/'), ('Latina', '/cat/latina/'),
    ('Lesbian', '/cat/lesbian/'), ('MILF', '/cat/milf/'), ('Massage', '/cat/massage/'), ('Masturbation', '/cat/masturbation/'), ('Mature', '/cat/mature/'),
    ('Orgy', '/cat/orgy/'), ('POV', '/cat/pov/'), ('Parody', '/cat/parody/'), ('Party', '/cat/party/'), ('Pissing', '/cat/pissing/'),
    ('Popular With Women', '/cat/popular-with-women/'), ('Public', '/cat/public/'), ('Pussy Licking', '/cat/pussy-licking/'), ('Reality', '/cat/reality/'), ('Redhead', '/cat/redhead/'),
    ('Rough', '/cat/rough/'), ('Small Tits', '/cat/small-tits/'), ('Solo Male', '/cat/solomale/'), ('Squirting', '/cat/squirting/'), ('Step Fantasy', '/cat/stepfantasy/'),
    ('Strip', '/cat/strip/'), ('Striptease', '/cat/striptease/'), ('Threesome', '/cat/threesome/'), ('Toys', '/cat/toys/'), ('Transgender', '/cat/transgender/'),
    ('Verified Amateurs', '/cat/verifiedamateurs/'), ('Vintage', '/cat/vintage/'), ('Virtual Reality', '/cat/virtualreality/'), ('Webcam', '/cat/webcam/'), ('Young (18+) and Old', '/cat/youngandold/'),
]

_THUMB_ATTRS = ('data-image', 'data-thumb', 'data-thumb_url', 'data-master_thumb', 'data-poster', 'data-src',
                'data-original', 'data-lazy-src', 'data-mediabook', 'data-bkg', 'poster', 'src')


# ----------------------------------------------------------------------------- Hilfen

def _get(url, referer=None, accept='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', timeout=20):
    headers = {'User-Agent': _UA, 'Referer': referer or DOMAIN + '/', 'Accept': accept,
               'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'}
    try:
        r = multiquest.get(url, headers=headers, timeout=timeout)
        if r.status_code >= 400:
            log.log('[TUBE8] HTTP %s: %s' % (r.status_code, url), log.LOGWARNING)
            return ''
        return r.text or ''
    except Exception as e:
        log.log('[TUBE8] Fehler beim Laden %s: %s' % (url, e), log.LOGWARNING)
        return ''


def _clean(value):
    if not value:
        return ''
    val = _html.unescape(str(value))
    val = re.sub(r'<[^>]+>', ' ', val)
    return re.sub(r'\s+', ' ', val).strip()


def _abs(url):
    if not url:
        return ''
    url = _html.unescape(url).replace('\\/', '/')
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return urljoin(DOMAIN, url)
    if url.startswith(('http://', 'https://')):
        return url
    return urljoin(DOMAIN + '/', url)


def _page_url(url, page):
    try:
        p = urlsplit(url)
        q = dict(parse_qsl(p.query, keep_blank_values=True))
        q['page'] = str(page)
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ''))
    except Exception:
        return url + ('&' if '?' in url else '?') + 'page=' + str(page)


def _natural_key(value):
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', str(value).casefold())]


def _secs(value):
    val = str(value or '').strip()
    m = re.match(r'^(\d+):(\d{2})$', val)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r'^(\d+):(\d{2}):(\d{2})$', val)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return 0


def _iso_secs(value):
    m = re.match(r'^P(?:([0-9]+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$', str(value or '').upper().strip())
    if not m:
        return 0
    d, h, mi, s = m.groups()
    return int(int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0))


def _fmt_dur(seconds):
    try:
        seconds = int(seconds)
    except Exception:
        return ''
    if seconds <= 0:
        return ''
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return '%d:%02d:%02d' % (h, m, s) if h else '%d:%02d' % (m, s)


def _folder(label, url, plot='', thumb=''):
    return {'title': label, 'url': url, 'plot': plot, 'poster': thumb, 'fanart': thumb,
            'is_playable': False, 'next_func': 'showEntries'}


# ----------------------------------------------------------------------------- Einstellungen (Mindestdauer)

def _min_minutes():
    try:
        import xbmcaddon
        v = (xbmcaddon.Addon().getSetting(MIN_SETTING) or '5').strip()
    except Exception:
        v = '5'
    return int(v) if v in MIN_CHOICES else 5


def _cycle_min():
    cur = str(_min_minutes())
    nxt = MIN_CHOICES[(MIN_CHOICES.index(cur) + 1) % len(MIN_CHOICES)] if cur in MIN_CHOICES else '5'
    try:
        import xbmcaddon
        xbmcaddon.Addon().setSetting(MIN_SETTING, nxt)
    except Exception as e:
        log.log('[TUBE8] Filter konnte nicht gespeichert werden: %s' % e, log.LOGWARNING)


# ----------------------------------------------------------------------------- Seiten lesen (wie im Kodi-Addon)

def _duration_from_block(block):
    for pat in (r'itemprop\s*=\s*["\']duration["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
                r'content\s*=\s*["\']([^"\']+)["\'][^>]*itemprop\s*=\s*["\']duration["\']',
                r'["\']duration["\']\s*:\s*["\']([^"\']+)["\']',
                r'data-duration\s*=\s*["\']([^"\']+)["\']'):
        m = re.search(pat, block, re.I | re.S)
        if m:
            val = _html.unescape(m.group(1))
            secs = _iso_secs(val) or _secs(val)
            if secs:
                return secs
    times = re.findall(r'(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)(?!\d)', _clean(block))
    if times:
        times.sort(key=_secs, reverse=True)
        return _secs(times[0])
    return 0


def _thumb_from(text):
    for attr in _THUMB_ATTRS:
        m = re.search(r'%s\s*=\s*["\']([^"\']+)["\']' % attr, text, re.I)
        if m:
            cand = _abs(m.group(1))
            if cand and not cand.startswith('data:image') and 'blank' not in cand.lower():
                return cand
    return ''


def parse_videos(page_html):
    """Videokarten einer Listenseite -> [{url, title, thumb, duration}]"""
    main = page_html
    cm = re.search(r'(<div[^>]*class=["\'][^"\']*(?:video-list|main-content|blogs-list|section_videos|search-results)'
                   r'[^"\']*["\'].*?)</section>', page_html, re.I | re.S)
    if cm:
        main = cm.group(1)
    pattern = re.compile(r'<a\b[^>]*href\s*=\s*["\']([^"\']*?/porn-video/[^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)

    def collect(source):
        vmap, order = {}, []
        for m in pattern.finditer(source):
            path = _html.unescape(m.group(1)).strip()
            if not path:
                continue
            full = _abs(path)
            if '/porn-video/' not in full:
                continue
            key = full.casefold()
            if key not in vmap:
                vmap[key] = {'path': path, 'url': full, 'blocks': []}
                order.append(key)
            vmap[key]['blocks'].append(m.group(0))
        return vmap, order

    vmap, order = collect(main)
    if not order and main is not page_html: 
        main = page_html
        vmap, order = collect(main)

    out = []
    for key in order:
        d = vmap[key]
        block = ' '.join(d['blocks'])
        title = ''
        tm = re.search(r'(?:title|data-title|alt)\s*=\s*["\']([^"\']+)["\']', block, re.I)
        if tm:
            title = _clean(tm.group(1))
        if not title:
            title = _clean(' '.join(re.findall(r'>([^<]+)</a>', block)).strip())
        if not title or len(title) < 3:
            continue
        thumb = _thumb_from(block)
        if not thumb:
            bg = re.search(r'background(?:-image)?\s*:\s*url\([\'"]?([^\'"()]+)[\'"]?\)', block, re.I)
            if bg:
                cand = _abs(bg.group(1))
                if cand and not cand.startswith('data:image'):
                    thumb = cand
        if not thumb:
            ctx = re.search(r'.{0,350}' + re.escape(d['path']) + r'.{0,350}', main, re.I | re.S)
            if ctx:
                thumb = _thumb_from(ctx.group(0))
        out.append({'url': d['url'], 'title': title, 'thumb': thumb, 'duration': _duration_from_block(block)})
    return out


def _pages_in(page_html):
    pages = set()
    for pat in (r'href\s*=\s*["\']([^"\']*?[?&]page=(\d+)[^"\']*)["\']', r'href\s*=\s*["\']([^"\']*?/page/(\d+)[^"\']*)["\']'):
        for m in re.finditer(pat, page_html, re.I):
            if int(m.group(2)) > 0:
                pages.add(int(m.group(2)))
    for m in re.finditer(r'(?:https?:)?//[^"\'>\s]+[?&]page=(\d+)', page_html, re.I):
        if int(m.group(1)) > 0:
            pages.add(int(m.group(1)))
    return sorted(pages)


def parse_channels(page_html):
    out, seen = [], set()
    pattern = re.compile(r'<a\b[^>]*href\s*=\s*["\']([^"\']*?/channel/[^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for m in pattern.finditer(page_html):
        path = _html.unescape(m.group(1)).strip()
        block = m.group(2)
        if not path:
            continue
        full = _abs(path)
        if full.casefold() in seen:
            continue
        name = ''
        tm = re.search(r'(?:title|alt)\s*=\s*["\']([^"\']+)["\']', block, re.I)
        if tm:
            name = _clean(tm.group(1))
        if not name:
            name = _clean(block)
        if not name or len(name) < 2:
            continue
        seen.add(full.casefold())
        out.append({'name': name, 'url': full, 'thumb': _thumb_from(block)})
    return out


def _initial(name, path=''):
    text = ''.join(c for c in unicodedata.normalize('NFKD', name or '') if not unicodedata.combining(c))
    m = re.search(r'[A-Za-z]', text)
    if m:
        return m.group(0).lower()
    slug = ''.join(c for c in unicodedata.normalize('NFKD', path.rstrip('/').split('/')[-1]) if not unicodedata.combining(c))
    m = re.search(r'[A-Za-z]', slug)
    return m.group(0).lower() if m else ''


def parse_pornstars(page_html, letter):
    letter = (letter or '').casefold()
    out, seen = [], set()
    pattern = re.compile(r'<a\b[^>]*href\s*=\s*["\']([^"\']*?/pornstar/[^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for m in pattern.finditer(page_html):
        path = _html.unescape(m.group(1)).strip()
        block = m.group(2)
        if not path:
            continue
        name = _clean(block)
        if not name:
            am = re.search(r'(?:alt|title)\s*=\s*["\']([^"\']+)["\']', block, re.I)
            if am:
                name = _clean(am.group(1))
        if not name or _initial(name, path) != letter:
            continue
        full = _abs(path)
        if full.casefold() in seen:
            continue
        seen.add(full.casefold())
        out.append({'name': name, 'url': full})
    return sorted(out, key=lambda x: _natural_key(x['name']))


# ----------------------------------------------------------------------------- Listen

def _video_items(url, first_page):
    """Videos ab Seite first_page laden, nach Mindestdauer filtern (höchstens FETCH_PAGES Seiten)."""
    min_secs = _min_minutes() * 60
    depth = FETCH_PAGES if min_secs > 0 else 1
    videos, seen = [], set()
    page, last_html, last_page = first_page, '', first_page
    for _ in range(depth):
        fetch = _page_url(url, page) if page > 1 else url
        page_html = _get(fetch)
        if not page_html:
            break
        last_html, last_page = page_html, page
        raw = parse_videos(page_html)
        if not raw:
            break
        for v in raw:
            if v['url'] in seen:
                continue
            if min_secs > 0 and 0 < v['duration'] < min_secs:
                continue
            seen.add(v['url'])
            videos.append(v)
        if len(videos) >= WANT_VIDEOS or min_secs == 0:
            break
        page += 1
    items = []
    for v in videos:
        dur = _fmt_dur(v['duration'])
        items.append({
            'title':       v['title'],
            'url':         v['url'],
            'plot':        '\n\n'.join(x for x in ('Dauer: %s' % dur if dur else '', v['title']) if x),
            'poster':      v['thumb'],
            'fanart':      v['thumb'],
            'live':        True,   
            'mediatype':   'video',
            'is_playable': True,
            'next_func':   'get_hosters',
        })
    nxt = next((n for n in _pages_in(last_html) if n > last_page), None) if last_html else None
    if nxt is None and len(videos) >= 15:
        nxt = last_page + 1
    if nxt:
        items.append(_folder('Nächste Seite >>', 'list:%d:%s' % (nxt, url), 'Weitere Videos laden.'))
    log.log('[TUBE8] %s ab Seite %d: %d Videos' % (url, first_page, len(videos)))
    return items


def _channels(page):
    url = DOMAIN + '/top-channels/?orderBy=al'
    if page > 1:
        url = _page_url(url, page)
    page_html = _get(url)
    chans = parse_channels(page_html) if page_html else []
    items = [_folder(c['name'], 'list:1:' + c['url'], '', c['thumb']) for c in chans]
    nxt = next((n for n in _pages_in(page_html) if n > page), None) if page_html else None
    if nxt is None and len(chans) >= 20:
        nxt = page + 1
    if nxt:
        items.append(_folder('Nächste Seite >>', 'channels:%d' % nxt, 'Weitere Channels laden.'))
    log.log('[TUBE8] Channels Seite %d: %d' % (page, len(chans)))
    return items


def _stars(letter, page):
    url = DOMAIN + '/pornstars/alphabetical/' + letter.lower() + '/'
    if page > 1:
        url = _page_url(url, page)
    page_html = _get(url)
    stars = parse_pornstars(page_html, letter) if page_html else []
    items = [_folder(s['name'], 'list:1:' + s['url']) for s in stars]
    nxt = next((n for n in _pages_in(page_html) if n > page), None) if page_html else None
    if nxt is None and len(stars) >= 30:
        nxt = page + 1
    if nxt:
        items.append(_folder('Nächste Seite >>', 'stars:%s:%d' % (letter, nxt), 'Weitere Pornstars laden.'))
    log.log('[TUBE8] Pornstars %s Seite %d: %d' % (letter, page, len(stars)))
    return items


# ----------------------------------------------------------------------------- Menüs (MovieScout)

def load(url='', params=None):
    if url == 'toggle_dauer':
        _cycle_min()
        url = ''
    cur = str(_min_minutes())
    return [
        _folder('Neueste Videos', 'list:1:' + DOMAIN + '/newest.html', 'Die neuesten Videos auf Tube8.'),
        {'title': '[ Suche nach ]', 'url': 'search', 'plot': 'Suche auf Tube8 nach einem Begriff.',
         'is_playable': False, 'next_func': 'do_search'},
        _folder('Pornstars', 'letters', 'Pornstars von A bis Z.'),
        _folder('Channels', 'channels:1', 'Alle Channels alphabetisch.'),
        _folder('Kategorien', 'cats', 'Alle Kategorien von 18-25 bis Young (18+) and Old.'),
        {'title': 'Filter: Mindestdauer %s (ändern)' % MIN_LABELS.get(cur, cur + ' Minuten'), 'url': 'toggle_dauer',
         'plot': 'Kürzere Videos werden in den Listen ausgeblendet. Ein Klick schaltet weiter: '
                 '5 / 10 / 15 / 20 / 30 / 45 Minuten oder keine.',
         'is_playable': False, 'next_func': 'load'},
    ]


def showEntries(url='', params=None):
    if not url:
        return load()
    if url == 'cats':
        return [_folder(name, 'list:1:' + DOMAIN + path) for name, path in CATEGORIES]
    if url == 'letters':
        return [_folder(c, 'stars:%s:1' % c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
    if url.startswith('stars:'):
        _, letter, p = url.split(':', 2)
        return _stars(letter, int(p))
    if url.startswith('channels:'):
        return _channels(int(url.split(':', 1)[1]))
    page = 1
    if url.startswith('list:'):
        _, p, url = url.split(':', 2)
        page = int(p)
    return _video_items(url, page)


def search(query='', params=None):
    q = (query or '').strip()
    if not q:
        return []
    return _video_items(DOMAIN + '/searches.html?q=' + quote_plus(q.lower()), 1)


def do_search(url='', params=None):
    import xbmcgui
    q = xbmcgui.Dialog().input('Tube8 Suche', type=xbmcgui.INPUT_ALPHANUM)
    return search(q) if q else []


# ----------------------------------------------------------------------------- Abspielen

def _media_resolvers(page_html):
    text = _html.unescape(page_html).replace('\\/', '/')
    found, seen = [], set()
    for m in re.finditer(r'(?:https?:)?//www\.tube8\.com/media/(hls|mp4)/\?s=([^"\'<>\s]+)', text, re.I):
        kind, token = m.group(1).lower(), m.group(2)
        url = 'https://www.tube8.com/media/%s/?s=%s' % (kind, token)
        if url not in seen:
            seen.add(url)
            found.append((kind, url))
    return sorted(found, key=lambda x: 0 if x[0] == 'hls' else 1)


def _sources(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, list):
        for it in obj:
            _sources(it, out)
        return out
    if not isinstance(obj, dict):
        return out
    u = obj.get('videoUrl') or obj.get('videoURL') or obj.get('url')
    if u:
        u = _abs(str(u))
        if u.startswith(('http://', 'https://')):
            out.append({'url': u, 'format': str(obj.get('format') or '').lower(), 'quality': str(obj.get('quality') or ''),
                        'height': obj.get('height'), 'default': bool(obj.get('defaultQuality'))})
    for v in obj.values():
        if isinstance(v, (dict, list)):
            _sources(v, out)
    return out


def _quality(src):
    m = re.search(r'(\d{3,4})', src.get('quality') or '')
    if m:
        return int(m.group(1))
    m = re.search(r'[_-](\d{3,4})P(?:[_-]|/)', src.get('url', ''), re.I)
    if m:
        return int(m.group(1))
    try:
        return int(src.get('height') or 0)
    except Exception:
        return 0


def _best(sources, want_hls):
    pick = []
    for s in sources:
        u = s['url'].lower()
        if want_hls:
            if '.m3u8' in u or s['format'] == 'hls':
                pick.append(s)
        elif (s['format'] == 'mp4' or '.mp4' in u) and not any(b in u for b in ('_fb.mp4', 'preview', 'thumb', 'thumbnail')):
            pick.append(s)
    pick.sort(key=lambda s: (_quality(s), 1 if s['default'] else 0), reverse=True)
    return pick[0] if pick else None


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    if not url:
        return []
    page_html = _get(url)
    if not page_html:
        return []
    resolvers = _media_resolvers(page_html)
    if not resolvers:
        log.log('[TUBE8] Keine Media-Resolver auf der Videoseite gefunden: %s' % url, log.LOGWARNING)
        return []
    hdr = '|Referer=%s&Origin=%s&User-Agent=%s' % (url, DOMAIN, _UA)
    hosters = []
    for kind, rurl in resolvers:
        raw = _get(rurl, referer=url, accept='application/json,text/plain,*/*')
        try:
            data = json.loads(raw.lstrip('﻿').strip()) if raw else None
        except Exception:
            try:
                data = json.loads(_html.unescape(raw))
            except Exception:
                data = None
        if data is None:
            continue
        best = _best(_sources(data), kind == 'hls')
        if best:
            q = _quality(best)
            hosters.append(('Tube8 %s' % ('HLS' if kind == 'hls' else 'MP4'), best['url'] + hdr, True,
                            '%dp' % q if q else '', 'en'))
    log.log('[TUBE8] %s: %d Quellen' % (url, len(hosters)))
    return hosters
