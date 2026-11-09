# -*- coding: utf-8 -*-
# Dokumentationen
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

SITE_ID = 'dokumentationen'
SITE_NAME = 'Dokumentationen'
SITE_DOMAIN = 'mediathekviewweb.de'
TYPE = 'both'
GLOBAL_SEARCH = True

# ----------------------------------------------------------------------------- EINSTELLUNGEN

CHANNELS = ['ARD', 'ZDF', 'ZDFinfo', 'ZDFneo', 'ARTE.DE', '3Sat', 'PHOENIX', 'ARD-alpha', 'WDR', 'NDR', 'BR', 'SWR', 'HR', 'MDR',
            'RBB', 'SR', 'ONE', 'tagesschau24', 'Radio Bremen']

MIN_MINUTES = 15

DOC_TOPICS = [
    'Terra X', 'ZDFzeit', 'ZDF-History', 'planet e.', '37°', 'ZDF.reportage', 'Die Story im Ersten', 'Geschichte im Ersten',
    'Die Reportage', 'Menschen hautnah', 'Die Nordreportage', 'Exakt - Die Story', 'Erlebnis Erde', 'Wildes Deutschland',
    'Länder - Menschen - Abenteuer', 'Schätze der Welt', 'Lebenslinien', 'Panorama - Die Reporter', 'Xenius',
    'Mit offenen Karten', 'ARTE Reportage', 'Re:', 'Quarks', 'Planet Wissen', 'Terra Xpress',
]

HIDE_VARIANTS = True

GERMAN_ONLY = True

# ----------------------------------------------------------------------------- Technik

_API = os.environ.get('MOVIESCOUT_MVW_API') or 'https://mediathekviewweb.de/api/query'
_TIMEOUT = 25
_PAGE = 60
_CACHE_TTL = 600
_BUILD_TTL = 1800
_CACHE = {}
_LOCK = threading.Lock()
_CH = {c.lower() for c in CHANNELS}
_VARIANT = re.compile(r'gebärdensprache|audiodeskription|hörfassung|\(ad\)|\(ds\)', re.I)
_SCRIPT = re.compile('[Ͱ-ϿЀ-ԯ֐-ࣿऀ-෿฀-໿぀-鿿가-힯]')
_LANG = re.compile(r'\bauf (ukrainisch|arabisch|persisch|russisch|türkisch|englisch)|\((ukr|ara|rus|eng)\)|originalfassung', re.I)
_NOT_TOPIC = re.compile(r'\b(nachrichten|tagesschau|tagesthemen|heute|wetter|trailer|vorschau|talk|quiz|tatort|polizeiruf|krimi)\b'
                        r'|zdfheute|sportschau|lanz|maischberger|illner|miosga|presseclub', re.I)
_DOCWORD = re.compile(r'doku|reportage', re.I)

_GENERIC = re.compile(r'^(dokus?|dokumentation(en)?|dokumentarfilme?|doku-?filme?|reportagen?|doku (&|und) reportage)$', re.I)
_NUM = re.compile(r'(\d+)')


def _tag(d):
    """Eindeutige Kennung eines Navigationsziels (geht als 'url' mit, damit die Engine die Menüs je Ebene getrennt cacht)."""
    return 'dok:' + _json.dumps(d or {}, sort_keys=True, ensure_ascii=False)


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


def _safe(fn):
    try:
        return fn()
    except Exception:                                               # noqa: BLE001 - eine Teilabfrage darf den Rest nicht kippen
        return []


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


def _keep(r):
    if not _best(r):
        return False
    if str(r.get('channel') or '').lower() not in _CH:
        return False
    try:
        d = int(r.get('duration') or 0)
    except (TypeError, ValueError):
        d = 0
    if d and d < MIN_MINUTES * 60:
        return False
    head = str(r.get('title') or '') + ' ' + str(r.get('topic') or '')
    if HIDE_VARIANTS and _VARIANT.search(head):
        return False
    if GERMAN_ONLY and (_SCRIPT.search(head + ' ' + str(r.get('description') or '')[:200]) or _LANG.search(head)):
        return False
    return True


def _item(r, show_topic=True):
    title = str(r.get('title') or '').strip() or 'Ohne Titel'
    topic = str(r.get('topic') or '').strip()
    generic = bool(_GENERIC.match(topic))
    label = title
    if show_topic and topic and not generic and topic.lower() not in title.lower():
        label = '%s: %s' % (topic.rstrip(': '), title)
    meta = ' · '.join(x for x in (r.get('channel') or '', _date(r.get('timestamp')), _fmt_dur(r.get('duration'))) if x)
    plot = str(r.get('description') or '').strip()
    return {
        'title': label, 'url': _best(r), 'poster': _poster_cached(topic) if topic and not generic else '',
        'plot': (plot + '\n\n' if plot else '') + meta,
        'year': _year(r.get('timestamp')), 'is_playable': True, 'next_func': 'get_hosters',
        'mediatype': 'movie' if generic or not topic else 'episode',
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


def _empty(text):
    return [{'title': text, 'is_playable': False, 'next_func': 'load', 'url': 'leer', 'params': {'lvl': 'root'}}]


def _sortkey(s):
    """Alphabetisch ohne Rücksicht auf Groß-/Kleinschreibung und Umlaute; Zahlen werden als Zahlen verglichen."""
    t = unicodedata.normalize('NFKD', str(s or '').lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'^[^0-9a-z]+', '', t)
    return [int(x) if x.isdigit() else x for x in _NUM.split(t)]


# ----------------------------------------------------------------------------- Poster (Wikipedia über die Engine)

_POSTER_FILE = os.path.join(tempfile.gettempdir(), 'dokumentationen_posters.json')
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
    if not e or not e.get('u'):
        return ''
    return e['u'] if time.time() - e.get('t', 0) < _POSTER_OK_TTL else ''


def _poster_known(topic):
    e = _posters().get(str(topic or '').strip().lower())
    if not e:
        return False
    return time.time() - e.get('t', 0) < (_POSTER_OK_TTL if e.get('u') else _POSTER_NO_TTL)


def _poster_lookup(topic):
    try:
        from engine import freemeta as FM
    except Exception:                                               # noqa: BLE001 - ohne Engine-Modul: ohne Poster
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
    """Fehlende Reihenbilder parallel suchen; wartet höchstens 'budget' Sekunden, der Rest läuft im Hintergrund weiter."""
    _posters()
    todo = []
    for t in dict.fromkeys(topics):
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


# ----------------------------------------------------------------------------- Bestand

def _build():
    """Sammelt Reihen, Dokumentarfilme und neueste Beiträge (Stand wird 30 Minuten gemerkt)."""
    hit = _cache_get('build', _BUILD_TTL)
    if hit is not None:
        return hit
    jobs = []
    for off in (0, 400, 800):
        jobs.append(('bulk', '', lambda o=off: _query([(['channel'], 'ZDFinfo')], size=400, offset=o, ttl=_BUILD_TTL)))
    for w in ('Doku', 'Dokumentation', 'Dokumentarfilm', 'Reportage'):
        jobs.append(('gen', '', lambda w=w: _query([(['topic'], w)], size=400, ttl=_BUILD_TTL)))
    for t in DOC_TOPICS:
        jobs.append(('cur', t, lambda t=t: _query([(['topic'], t)], size=30, ttl=_BUILD_TTL)))
    with ThreadPoolExecutor(max_workers=8) as ex:
        parts = list(ex.map(lambda j: _safe(j[2]), jobs))

    shows, generic, recent = {}, [], []
    for (kind, name, _), part in zip(jobs, parts):
        for r in part or []:
            if not _keep(r):
                continue
            t = str(r.get('topic') or '').strip()
            ch = str(r.get('channel') or '')
            if not t or _NOT_TOPIC.search(t):
                continue
            if kind == 'cur' and t.lower() != name.lower():
                continue
            if kind == 'gen' and not _DOCWORD.search(t):
                continue
            recent.append(r)
            if _GENERIC.match(t):
                generic.append(r)
                continue
            e = shows.setdefault((t.lower(), ch.lower()), [t, ch, 0])
            if kind != 'cur':
                e[2] += 1

    seen, rec = set(), []
    for r in sorted(recent, key=lambda x: x.get('timestamp') or 0, reverse=True):
        k = _best(r)
        if k not in seen:
            seen.add(k)
            rec.append(r)
    data = {'shows': [tuple(v) for v in shows.values()], 'generic': generic, 'recent': rec[:300]}
    if not (data['shows'] or generic or rec):
        raise RuntimeError('Mediathek-Index nicht erreichbar oder keine Treffer')
    _cache_put('build', data)
    return data


def _show_folders(shows, with_channel):
    """Reihen als Ordner, alphabetisch, mit Reihenbild (Wikipedia, wird gemerkt)."""
    names = {}
    for t, ch, n in shows:
        names.setdefault(t.lower(), set()).add(ch)
    shows = sorted(shows, key=lambda x: (_sortkey(x[0]), x[1]))
    _warm_posters([t for t, _, _ in shows])
    out = []
    for t, ch, n in shows:
        title = '%s (%s)' % (t, ch) if with_channel and len(names[t.lower()]) > 1 else t
        info = ' · '.join(x for x in (ch, ('%d Beitrag' % n if n == 1 else '%d Beiträge' % n) if n else '') if x)
        out.append(_folder(title, 'topic', info, poster=_poster_cached(t), t=t, ch=ch))
    return out


def _topic_items(topic, channel):
    queries = [(['topic'], topic)]
    if channel:
        queries.append((['channel'], channel))
    res = _query(queries, size=400)
    res = [r for r in res if str(r.get('topic') or '').strip().lower() == topic.strip().lower()
           and (not channel or str(r.get('channel') or '').lower() == channel.lower())]
    items = _items(res, show_topic=False)
    items.sort(key=lambda i: _sortkey(i['title']))
    poster = _poster_cached(topic)
    for i in items:
        i['poster'] = poster
    return items


# ----------------------------------------------------------------------------- Einstieg

def load(url='', params=None):
    params = params or {}
    lvl = params.get('lvl') or 'root'
    page = int(params.get('page') or 0)
    try:
        if lvl == 'root':
            return [
                _folder('Sendungen A–Z', 'shows', 'Dokureihen und Dokumentarsendungen, alphabetisch.'),
                _folder('Neu in der Mediathek', 'new', 'Die neuesten Dokumentationen.'),
                _folder('Dokumentarfilme', 'films', 'Einzelne Dokumentationen und Dokumentarfilme, alphabetisch.'),
                _folder('Nach Sender', 'chans', 'Die Reihen je Sender.'),
            ]
        if lvl == 'new':
            rec = _build()['recent']
            part = rec[page * _PAGE:(page + 1) * _PAGE]
            out = _items(part)
            if (page + 1) * _PAGE < len(rec):
                out.append(_more('new', page + 1))
            return out or _empty('Zurzeit nichts gefunden.')
        if lvl == 'films':
            items = _items(_build()['generic'], show_topic=False)
            items.sort(key=lambda i: _sortkey(i['title']))
            return items or _empty('Zurzeit keine Dokumentarfilme gefunden.')
        if lvl == 'shows':
            ch = params.get('ch') or ''
            shows = [s for s in _build()['shows'] if not ch or s[1].lower() == ch.lower()]
            return _show_folders(shows, with_channel=not ch) if shows else _empty('Keine Sendungen gefunden.')
        if lvl == 'chans':
            counts = {}
            for t, ch, n in _build()['shows']:
                counts[ch] = counts.get(ch, 0) + 1
            order = {c.lower(): i for i, c in enumerate(CHANNELS)}
            chans = sorted(counts, key=lambda c: (order.get(c.lower(), 99), c.lower()))
            return [_folder(c, 'shows', ('%d Reihe' % counts[c]) if counts[c] == 1 else '%d Reihen' % counts[c], ch=c) for c in chans] or _empty('Keine Sender gefunden.')
        if lvl == 'topic':
            return _topic_items(params.get('t') or '', params.get('ch') or '') or _empty('In dieser Sendung ist gerade nichts verfügbar.')
    except Exception as e:                                          # noqa: BLE001
        return _empty('Fehler: %s' % e)
    return []


def search(query=''):
    q = (query or '').strip()
    if len(q) < 2:
        return []
    res = _query([(['topic', 'title'], q)], size=300)
    return _items(res)[:150]


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
