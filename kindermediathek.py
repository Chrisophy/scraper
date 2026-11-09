# -*- coding: utf-8 -*-
# Kinder-Mediathek
# IT('s) Possible 
# 2026.11.09
import json as _json
import os
import re
import tempfile
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, wait

from resources.lib import multiquest

try:
    from engine import freemeta as _FM
except Exception:                                        
    _FM = None

SITE_ID = 'kindermediathek'
SITE_NAME = 'Kinder-Mediathek'
SITE_DOMAIN = 'mediathekviewweb.de'
TYPE = 'both'
GLOBAL_SEARCH = True

# ----------------------------------------------------------------------------- EINSTELLUNGEN

KIDS_CHANNEL = 'KiKA'

EXTRA_TOPICS = [
    'Die Sendung mit der Maus',
    'Löwenzahn',
    'logo!',
    'Der kleine Rabe Socke',
    'Der kleine Maulwurf',
    'Käpt\'n Blaubär',
    'Neue Geschichten vom Pumuckl',
    'Meister Eder und sein Pumuckl',
]


HIDE_VARIANTS = True

GERMAN_ONLY = True

# ----------------------------------------------------------------------------- Technik

_API = os.environ.get('MOVIESCOUT_MVW_API') or 'https://mediathekviewweb.de/api/query'
_TIMEOUT = 25
_PAGE = 60
_CACHE_TTL = 600
_SHOWS_TTL = 6 * 3600
_CACHE = {}
_LOCK = threading.Lock()
_VARIANT = re.compile(r'gebärdensprache|audiodeskription|hörfassung|\(ad\)|\(ds\)', re.I)
# Kyrillisch, Griechisch, Hebräisch, Arabisch, Indisch, Thai, CJK usw. oder Hinweis auf eine Fremdsprachenfassung
_SCRIPT = re.compile('[\u0370-\u03ff\u0400-\u052f\u0590-\u08ff\u0900-\u0dff\u0e00-\u0eff\u3040-\u9fff\uac00-\ud7af]')
_LANG = re.compile(r'\bauf (ukrainisch|arabisch|persisch|russisch|türkisch|englisch)|\((ukr|ara|rus|eng)\)|ukrainische fassung|originalfassung', re.I)
_NUM = re.compile(r'(\d+)')
_FILM_TOPIC = re.compile(r'^[\w\- ]{0,16}films?e?$', re.I)


def _tag(d):
    """Eindeutige Kennung eines Navigationsziels (geht als 'url' mit, damit die Engine die Menüs je Ebene getrennt cacht)."""
    return 'kmt:' + _json.dumps(d or {}, sort_keys=True, ensure_ascii=False)


def _cache_get(key, ttl):
    with _LOCK:
        e = _CACHE.get(key)
        if e and time.time() - e[0] < ttl:
            return e[1]
    return None


def _cache_put(key, val):
    with _LOCK:
        if len(_CACHE) > 200:
            for k in sorted(_CACHE, key=lambda x: _CACHE[x][0])[:50]:
                _CACHE.pop(k, None)
        _CACHE[key] = (time.time(), val)


def _query(queries, size=_PAGE, offset=0, sort='timestamp', order='desc', ttl=_CACHE_TTL):
    """Fragt den Mediathek-Index. queries = Liste von (Felder, Suchtext); alle müssen zutreffen. Liefert Liste von Treffern."""
    body = {'queries': [{'fields': list(f), 'query': q} for f, q in queries],
            'sortBy': sort, 'sortOrder': order, 'future': False, 'offset': int(offset), 'size': int(size)}
    key = _json.dumps(body, sort_keys=True)
    hit = _cache_get(key, ttl)
    if hit is not None:
        return hit
    last = None
    for attempt in range(2):
        try:
            r = multiquest.get(_API, params={'query': _json.dumps(body, ensure_ascii=False, separators=(',', ':'))}, timeout=_TIMEOUT)
            if r.status_code >= 400:
                raise RuntimeError('HTTP %s' % r.status_code)
            data = r.json()
            if data.get('err'):
                raise RuntimeError(str(data['err'])[:120])
            res = (data.get('result') or {}).get('results') or []
            _cache_put(key, res)
            return res
        except Exception as e:                                   # noqa: BLE001 - Netz/Server: einmal wiederholen
            last = e
            time.sleep(0.6)
    raise RuntimeError('Mediathek-Index nicht erreichbar: %s' % last)


def _best(r):
    return r.get('url_video_hd') or r.get('url_video') or r.get('url_video_low') or ''


def _fmt_dur(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ''
    if sec <= 0:
        return ''
    h, m = divmod(sec // 60, 60)
    return ('%d:%02d Std.' % (h, m)) if h else ('%d Min.' % max(1, m))


def _date(ts):
    try:
        return time.strftime('%d.%m.%Y', time.localtime(int(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


def _year(ts):
    try:
        return str(time.localtime(int(ts)).tm_year)
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


def _keep(r, with_variants=False):
    if not _best(r):
        return False
    if GERMAN_ONLY:
        head = str(r.get('title') or '') + ' ' + str(r.get('topic') or '')
        if _SCRIPT.search(head + ' ' + str(r.get('description') or '')[:200]) or _LANG.search(head):
            return False
    if HIDE_VARIANTS and not with_variants and _VARIANT.search(str(r.get('title') or '') + ' ' + str(r.get('topic') or '')):
        return False
    return True


def _item(r, show_topic=True):
    title = str(r.get('title') or '').strip() or 'Ohne Titel'
    topic = str(r.get('topic') or '').strip()
    label = title
    if show_topic and topic and topic.lower() not in title.lower():
        label = '%s: %s' % (topic, title)
    meta = ' · '.join(x for x in (r.get('channel') or '', _date(r.get('timestamp')), _fmt_dur(r.get('duration'))) if x)
    plot = str(r.get('description') or '').strip()
    return {
        'title': label, 'url': _best(r), 'poster': _poster_cached(topic) if topic else '', 'plot': (plot + '\n\n' if plot else '') + meta,
        'year': _year(r.get('timestamp')), 'is_playable': True, 'next_func': 'get_hosters',
        'mediatype': 'episode' if topic else 'movie',
        'params': {'hd': r.get('url_video_hd') or '', 'sd': r.get('url_video') or '', 'low': r.get('url_video_low') or '',
                   'sub': r.get('url_subtitle') or '', 'web': r.get('url_website') or ''},
    }


def _items(results, show_topic=True):
    out, seen = [], set()
    for r in results:
        if not _keep(r):
            continue
        k = _best(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(_item(r, show_topic))
    return out


def _folder(title, lvl, plot='', poster='', **extra):
    p = dict(extra, lvl=lvl)
    return {'title': title, 'is_playable': False, 'next_func': 'load', 'url': _tag(p), 'params': p, 'plot': plot, 'poster': poster}


def _more(lvl, page, **extra):
    p = dict(extra, lvl=lvl, page=page)
    return {'title': '[B]Weiter ▶[/B]', 'is_playable': False, 'next_func': 'load', 'url': _tag(p), 'params': p}



def _sortkey(s):
    """Alphabetisch ohne Rücksicht auf Groß-/Kleinschreibung und Umlaute; Zahlen werden als Zahlen verglichen."""
    t = unicodedata.normalize('NFKD', str(s or '').lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'^[^0-9a-z]+', '', t)
    return [int(x) if x.isdigit() else x for x in _NUM.split(t)]


_POSTER_FILE = os.path.join(tempfile.gettempdir(), 'kindermediathek_posters.json')
_POSTER_OK_TTL = 30 * 86400
_POSTER_NO_TTL = 3 * 86400
_PLOCK = threading.Lock()
_POSTERS = None
_PENDING = set()


def _posters():
    global _POSTERS
    with _PLOCK:
        if _POSTERS is None:
            try:
                with open(_POSTER_FILE, encoding='utf-8') as f:
                    d = _json.load(f)
                _POSTERS = d if isinstance(d, dict) else {}
            except Exception:                                       # noqa: BLE001 - keine Datei: leer starten
                _POSTERS = {}
        return _POSTERS


def _poster_save():
    try:
        with _PLOCK:
            data = _json.dumps(_POSTERS or {}, ensure_ascii=False)
        tmp = _POSTER_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(data)
        os.replace(tmp, _POSTER_FILE)
    except Exception:                                               # noqa: BLE001 - nur Komfort
        pass


def _poster_cached(topic):
    e = _posters().get(str(topic or '').strip().lower())
    if not e:
        return ''
    age = time.time() - e.get('t', 0)
    if e.get('u'):
        return e['u'] if age < _POSTER_OK_TTL else ''
    return ''


def _poster_known(topic):
    e = _posters().get(str(topic or '').strip().lower())
    if not e:
        return False
    return time.time() - e.get('t', 0) < (_POSTER_OK_TTL if e.get('u') else _POSTER_NO_TTL)


def _poster_lookup(topic):
    try:
        from engine import freemeta as FM
    except Exception:                                               # noqa: BLE001
        return None
    try:
        if not FM.enabled():
            return None
    except Exception:                                               # noqa: BLE001
        pass
    names = [topic]
    head = re.split(r'\s+[-–:]\s+', topic, 1)[0].strip()
    if head and head != topic and len(head) > 3:
        names.append(head)
    for n in names:
        try:
            r = FM.src_wiki(n, '', True) or {}
        except Exception:                                           # noqa: BLE001 - Netz: später nochmal
            return None
        if r.get('poster'):
            return r['poster']
    return ''


def _poster_job(topic):
    try:
        url = _poster_lookup(topic)
        if url is None:
            return
        with _PLOCK:
            _POSTERS[topic.strip().lower()] = {'u': url, 't': time.time()}
        _poster_save()
    finally:
        with _PLOCK:
            _PENDING.discard(topic)


def _warm_posters(topics, budget=9.0):
    """Fehlende Sendungsbilder parallel suchen; wartet höchstens 'budget' Sekunden, der Rest läuft im Hintergrund weiter."""
    _posters()
    todo = []
    for t in topics:
        if _poster_known(t):
            continue
        with _PLOCK:
            if t in _PENDING:
                continue
            _PENDING.add(t)
        todo.append(t)
    if not todo:
        return
    ex = ThreadPoolExecutor(max_workers=8)
    futs = [ex.submit(_poster_job, t) for t in todo]
    wait(futs, timeout=budget)
    ex.shutdown(wait=False)


# ----------------------------------------------------------------------------- Sendungen

def _kids_shows():
    """Alle Sendungen des Kindersenders mit Anzahl der Beiträge (aus den neuesten Beiträgen; Stand wird 6 Stunden gemerkt)."""
    hit = _cache_get('shows', _SHOWS_TTL)
    if hit is not None:
        return hit
    pages = [0, 400, 800, 1200]
    with ThreadPoolExecutor(max_workers=4) as ex:
        parts = list(ex.map(lambda o: _safe(lambda: _query([(['channel'], KIDS_CHANNEL)], size=400, offset=o, ttl=_SHOWS_TTL)), pages))
    counts = {}
    for part in parts:
        for r in part or []:
            if r.get('channel') and str(r['channel']).lower() != KIDS_CHANNEL.lower():
                continue
            if not _keep(r):
                continue
            t = str(r.get('topic') or '').strip()
            if t:
                counts[t] = counts.get(t, 0) + 1
    shows = sorted(counts.items(), key=lambda kv: kv[0].lower())
    if shows:
        _cache_put('shows', shows)
    return shows


def _safe(fn):
    try:
        return fn()
    except Exception:                                               # noqa: BLE001 - eine Teilabfrage darf den Rest nicht kippen
        return []


def _topic_items(topic, channel=''):
    queries = [(['topic'], topic)]
    if channel:
        queries.append((['channel'], channel))
    res = _query(queries, size=400, sort='timestamp', order='asc')
    exact = [r for r in res if str(r.get('topic') or '').strip().lower() == topic.strip().lower()]
    if channel:
        exact = [r for r in exact if str(r.get('channel') or '').lower() == channel.lower()]
    items = _items((exact or res) if not channel else exact, show_topic=False)
    items.sort(key=lambda i: _sortkey(i['title']))
    poster = _poster_cached(topic)
    for i in items:
        i['poster'] = poster
    return items


# ----------------------------------------------------------------------------- Einstieg

def _is_film_topic(topic):
    """Reihen wie „Filme“, „Kinderfilme“, „Spielfilm“ gehören nach „Filme“, nicht in die Sendungsliste."""
    return bool(_FILM_TOPIC.match(str(topic or '').strip()))


def _films():
    res = []
    for word in ('Filme', 'Film'):
        res += _safe(lambda w=word: _query([(['channel'], KIDS_CHANNEL), (['topic'], w)], size=400))
    res = [r for r in res if _is_film_topic(r.get('topic')) and str(r.get('channel') or KIDS_CHANNEL).lower() == KIDS_CHANNEL.lower()]
    items = _items(res, show_topic=False)
    items.sort(key=lambda i: _sortkey(i['title']))
    return items


def _all_shows():
    """KiKA-Sendungen plus die zusätzlichen Sendungen aus ARD/ZDF, alphabetisch gemischt."""
    kids = [(t, n, KIDS_CHANNEL) for t, n in _kids_shows() if not _is_film_topic(t)]
    have = {t.lower() for t, _, _ in kids}
    extra = [(t, 0, '') for t in EXTRA_TOPICS if t.lower() not in have]
    return kids + extra


def load(url='', params=None):
    params = params or {}
    lvl = params.get('lvl') or 'root'
    page = int(params.get('page') or 0)
    try:
        if lvl == 'root':
            return [
                _folder('Sendungen A–Z', 'shows', 'Alle Sendungen, alphabetisch.'),
                _folder('Neu in der Mediathek', 'new', 'Die neuesten Beiträge von %s.' % KIDS_CHANNEL),
                _folder('Filme', 'films', 'Spielfilme und Filme für Kinder.'),
            ]
        if lvl == 'new':
            res = _query([(['channel'], KIDS_CHANNEL)], size=_PAGE, offset=page * _PAGE)
            out = _items(res)
            if len(res) >= _PAGE:
                out.append(_more('new', page + 1))
            return out or _empty('Zurzeit nichts gefunden.')
        if lvl == 'films':
            return _films() or _empty('Zurzeit keine Filme gefunden.')
        if lvl == 'shows':
            shows = _all_shows()
            if not shows:
                return _empty('Sendungen konnten nicht geladen werden.')
            return _show_folders(shows)
        if lvl == 'topic':
            return _topic_items(params.get('t') or '', params.get('ch') or '') or _empty('In dieser Sendung ist gerade nichts verfügbar.')
    except Exception as e:                                          # noqa: BLE001
        return _empty('Fehler: %s' % e)
    return []


def _show_folders(shows):
    """Sendungen als Ordner, alphabetisch, mit Sendungsbild (Wikipedia, wird gemerkt)."""
    shows = sorted(shows, key=lambda x: _sortkey(x[0]))
    _warm_posters([t for t, _, _ in shows])
    return [_folder(t, 'topic', ('%d Beitrag' % n if n == 1 else '%d Beiträge' % n) if n else '', poster=_poster_cached(t), t=t, ch=ch) for t, n, ch in shows]


def _empty(text):
    return [{'title': text, 'is_playable': False, 'next_func': 'load', 'url': 'leer', 'params': {'lvl': 'root'}}]


def search(query=''):
    q = (query or '').strip()
    if len(q) < 2:
        return []
    jobs = [lambda: _query([(['channel'], KIDS_CHANNEL), (['topic', 'title'], q)], size=60)]
    for t in EXTRA_TOPICS:
        jobs.append(lambda t=t: _query([(['topic'], t), (['topic', 'title'], q)], size=20))
    with ThreadPoolExecutor(max_workers=5) as ex:
        parts = list(ex.map(lambda j: _safe(j), jobs))
    res, extra = parts[0] or [], []
    for part in parts[1:]:
        extra += [r for r in (part or []) if str(r.get('topic') or '').strip().lower() in {x.lower() for x in EXTRA_TOPICS}]
    items = _items(res + extra)[:150]
    items.sort(key=lambda i: _sortkey(i['title']))
    return items


def get_hosters(url='', params=None):
    params = params or {}
    out = []
    for key, name in (('hd', 'HD'), ('sd', 'Normal'), ('low', 'Niedrig')):
        u = params.get(key) or ''
        if u and u not in [h['url'] for h in out]:
            out.append({'name': name, 'url': u, 'direct': True})
    if not out and url:
        out.append({'name': 'Video', 'url': url, 'direct': True})
    sub = params.get('sub') or ''
    if sub and re.search(r'\.(vtt|srt|ass)(\?|$)', sub, re.I):
        for h in out:
            h['subtitles'] = [{'label': 'Deutsch', 'lang': 'de', 'url': sub, 'default': True}]
    return out
