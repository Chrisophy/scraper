# -*- coding: utf-8 -*-
# Stalker Pro
# IT('s) Possible 
# 2026.11.08
import json
import math
import threading
import time
from datetime import datetime, timezone

import xbmcaddon
from resources.lib import multiquest

try:
    from engine import epg as EPG          
except Exception:                           
    EPG = None

SITE_ID = 'stalker_pro'
SITE_NAME = 'Stalker Pro'
SITE_DOMAIN = ''
TYPE = 'live'
GLOBAL_SEARCH = False

_UA = ('Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) '
       'MAG200 stbapp ver: 4 rev: 1812 Mobile Safari/533.3')
_TIMEOUT = 15
_TOKENS = {}           
_TOKEN_TTL = 3000
_CH_TTL = 600           # Senderliste je Portal
_EPG_TTL = 900          # Programm je Portal
_PLAN_N = 8             # so viele kommende Sendungen in der Beschreibung
_CH = {}
_PE = {}
_LOCK = threading.Lock()


def _tag(d):
    """Eindeutige Kennung für ein Navigationsziel, als 'url' mitgegeben (die Engine cacht Menüs nach
    provider+next_func+url; ohne das würden alle Ebenen, die nur 'params' nutzen, denselben
    Cache-Eintrag treffen)."""
    return 'stalker:' + json.dumps(d or {}, sort_keys=True, ensure_ascii=False)


def _settings():
    return xbmcaddon.all_settings()


def _portals():
    raw = (_settings().get('stalker_portals') or '').strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    for p in data if isinstance(data, list) else []:
        if isinstance(p, dict) and p.get('url') and p.get('mac'):
            out.append({'name': (p.get('name') or '').strip() or p['url'],
                        'url': p['url'].rstrip('/'), 'mac': p['mac'].strip()})
    return out


def _portal(i):
    ps = _portals()
    try:
        i = int(i)
    except (TypeError, ValueError):
        i = -1
    return ps[i] if 0 <= i < len(ps) else None


def _headers(portal, token=None):
    h = {
        'User-Agent': _UA,
        'X-User-Agent': 'Model: MAG254; Link: Ethernet',
        'Accept': '*/*',
        'Referer': portal['url'] + '/c/',
        'Cookie': 'mac=%s; stb_lang=en; timezone=Europe%%2FBerlin;' % portal['mac'],
    }
    if token:
        h['Authorization'] = 'Bearer ' + token
        h['Cookie'] += ' access_token=%s;' % token          
    return h


def _token(portal, force=False):
    with _LOCK:
        hit = _TOKENS.get(portal['url'])
        if hit and not force and time.time() - hit[1] < _TOKEN_TTL:
            return hit[0]
    r = multiquest.post(portal['url'] + '/portal.php',
                        params={'type': 'stb', 'action': 'handshake', 'JsHttpRequest': '1-xml'},
                        data=None, headers=_headers(portal), timeout=_TIMEOUT)
    js = _js(r)
    token = (js or {}).get('token') or ''
    if not token:
        raise RuntimeError('Portal antwortet nicht wie erwartet (Handshake fehlgeschlagen)')
    multiquest.post(portal['url'] + '/portal.php',
                    params={'type': 'stb', 'action': 'get_profile', 'hd': '1', 'num_banks': '1',
                            'stb_type': 'MAG254', 'not_valid_token': '0', 'JsHttpRequest': '1-xml'},
                    data=None, headers=_headers(portal, token), timeout=_TIMEOUT)
    with _LOCK:
        _TOKENS[portal['url']] = (token, time.time())
    return token


def _js(r):
    if r.status_code != 200 or not r.text:
        return None
    try:
        return r.json().get('js')
    except Exception:
        return None


def _call(portal, params, retried=False):
    token = _token(portal)
    r = multiquest.post(portal['url'] + '/portal.php', params=dict(params, JsHttpRequest='1-xml'),
                        data=None, headers=_headers(portal, token), timeout=_TIMEOUT)
    js = _js(r)
    if js is None and not retried:
        _token(portal, force=True)
        return _call(portal, params, retried=True)
    if js is None:
        raise RuntimeError('Portal-Antwort ungültig (HTTP %s)' % r.status_code)
    return js


def _logo(portal, path):
    if not path:
        return ''
    if path.startswith('http://') or path.startswith('https://'):
        return path
    return portal['url'] + (path if path.startswith('/') else '/' + path)


def _channels(portal):
    """Alle Sender des Portals (kurz zwischengespeichert)."""
    with _LOCK:
        hit = _CH.get(portal['url'])
        if hit and time.time() - hit[0] < _CH_TTL:
            return hit[1]
    js = _call(portal, {'type': 'itv', 'action': 'get_all_channels'})
    rows = [c for c in ((js or {}).get('data') or []) if isinstance(c, dict)]
    with _LOCK:
        _CH[portal['url']] = (time.time(), rows)
    return rows


def _hm(ts):
    try:
        dt = datetime.fromtimestamp(float(ts), timezone.utc)
        dt = EPG._local(dt) if EPG else dt.astimezone()
        return dt.strftime('%H:%M')
    except Exception:
        return ''


def _day(ts):
    try:
        dt = datetime.fromtimestamp(float(ts), timezone.utc)
        now = datetime.now(timezone.utc)
        if EPG:
            dt, now = EPG._local(dt), EPG._local(now)
        else:
            dt, now = dt.astimezone(), now.astimezone()
        d = (dt.date() - now.date()).days
        return 'Heute' if d == 0 else 'Morgen' if d == 1 else dt.strftime('%d.%m.')
    except Exception:
        return ''


def _portal_epg(portal):
    """Programm aus dem Portal: {Sender-ID: [(start, stop, titel, beschreibung)]} (ein Aufruf für alle Sender, kurz zwischengespeichert)."""
    with _LOCK:
        hit = _PE.get(portal['url'])
        if hit and time.time() - hit[0] < _EPG_TTL:
            return hit[1]
    out = {}
    try:
        js = _call(portal, {'type': 'itv', 'action': 'get_epg_info', 'period': '24'})
        data = js.get('data') if isinstance(js, dict) else js
        if isinstance(data, dict):
            for cid, rows in data.items():
                lst = []
                for r in rows if isinstance(rows, list) else []:
                    try:
                        a, b = int(r.get('start_timestamp') or 0), int(r.get('stop_timestamp') or 0)
                    except (TypeError, ValueError):
                        continue
                    if a and b and b > a:
                        lst.append((a, b, str(r.get('name') or '').strip(), str(r.get('descr') or '').strip()))
                if lst:
                    out[str(cid)] = sorted(lst)
    except Exception:
        out = {}
    with _LOCK:
        _PE[portal['url']] = (time.time(), out)
    return out


def _xmltv_rows(epg, c):
    """Programm aus der XMLTV-Adresse der Einstellungen für einen Sender."""
    if not epg:
        return []
    try:
        key = EPG.epg_id(epg, {'name': c.get('name') or '', 'tvg_id': str(c.get('xmltv_id') or ''), 'tvg_name': ''})
    except Exception:
        return []
    return [(int(a.timestamp()), int(b.timestamp()), t, '') for a, b, t in (epg.get('progs', {}).get(key) or [])]


def _rows_for(c, pe, xepg):
    rows = pe.get(str(c.get('id') or ''))
    return rows if rows else _xmltv_rows(xepg, c)


def _upcoming(rows):
    now = time.time()
    return [r for r in rows if r[1] > now]


def _plot(rows):
    """Erste Zeile: Jetzt / Danach (steht in der Senderliste), danach die nächsten Sendungen."""
    up = _upcoming(rows)
    if not up:
        return '', ''
    cur = up[0] if up[0][0] <= time.time() else None
    nxt = up[1 if cur else 0:]
    head = []
    if cur:
        head.append('Jetzt: %s (bis %s)' % (cur[2], _hm(cur[1])))
    if nxt:
        head.append('Danach: %s' % nxt[0][2])
    lines = ['%s  %s' % (_hm(r[0]), r[2]) for r in nxt[:_PLAN_N]]
    return ' · '.join(head) + (('\n\n' + '\n'.join(lines)) if lines else ''), (cur[2] if cur else '')


def _info(title, plot=''):
    return {'title': title, 'is_playable': False, 'next_func': 'load', 'plot': plot}


def load(url='', params=None):
    params = params or {}
    lvl = params.get('lvl') or 'root'

    if lvl == 'root':
        ps = _portals()
        if not ps:
            return [{'title': 'Kein Portal eingetragen – unter Einstellungen → Stalker-Portale hinzufügen',
                     'is_playable': False, 'next_func': 'load'}]
        return [{'title': p['name'], 'is_playable': False, 'next_func': 'load',
                'url': _tag({'lvl': 'home', 'i': i}), 'params': {'lvl': 'home', 'i': i}} for i, p in enumerate(ps)]

    i = params.get('i')
    portal = _portal(i)
    if not portal:
        return [{'title': 'Portal nicht gefunden (Einstellungen geändert?)', 'is_playable': False, 'next_func': 'load'}]

    try:
        if lvl == 'home':
            return [
                {'title': '[B]Live TV[/B]', 'is_playable': False, 'next_func': 'load',
                 'url': _tag({'lvl': 'genres', 'i': i}), 'params': {'lvl': 'genres', 'i': i}},
                {'title': '[B]Filme[/B]', 'is_playable': False, 'next_func': 'load',
                 'url': _tag({'lvl': 'vodgen', 'i': i}), 'params': {'lvl': 'vodgen', 'i': i}},
                {'title': '[B]Serien[/B]', 'is_playable': False, 'next_func': 'load',
                 'url': _tag({'lvl': 'sergen', 'i': i}), 'params': {'lvl': 'sergen', 'i': i}},
            ]
        if lvl == 'genres':
            if EPG:
                try:
                    EPG.prefetch()
                except Exception:                             
                    pass
            js = _call(portal, {'type': 'itv', 'action': 'get_genres'})
            out = []
            for g in (js or []):
                if not isinstance(g, dict):
                    continue
                p = {'lvl': 'channels', 'i': i, 'gid': g.get('id') or ''}
                out.append({'title': g.get('title') or '?', 'is_playable': False, 'next_func': 'load',
                           'url': _tag(p), 'params': p})
            return out
        if lvl == 'channels':
            gid = params.get('gid') or ''
            rows = [c for c in _channels(portal) if not gid or str(c.get('tv_genre_id')) == str(gid)]
            pe = _portal_epg(portal)
            try:
                xepg = EPG.get() if (EPG and rows and not pe) else {}
            except Exception:
                xepg = {}
            p = {'lvl': 'plan', 'i': i, 'gid': gid}
            out = [{'title': '[B]Tagesplan dieser Gruppe[/B]', 'is_playable': False, 'next_func': 'load',
                    'plot': 'Alle Sender dieser Gruppe mit ihrem Programm.', 'url': _tag(p), 'params': p}]
            for c in rows:
                plot, now = _plot(_rows_for(c, pe, xepg))
                out.append({'title': c.get('name') or '?', 'poster': _logo(portal, c.get('logo') or ''),
                           'is_playable': True, 'live': True, 'next_func': 'get_hosters', 'plot': plot, 'now': now,
                           'params': {'i': i, 't': 'itv', 'cmd': c.get('cmd') or ''}})
            if not pe and EPG:
                try:
                    chs = [{'name': c.get('name') or '', 'tvg_id': str(c.get('xmltv_id') or ''), 'tvg_name': ''} for c in rows]
                    st = EPG.status_line(chs)
                except Exception:
                    st = ''
                if st:
                    out.append(_info(st))
            return out
        if lvl == 'plan':
            gid = params.get('gid') or ''
            rows = [c for c in _channels(portal) if not gid or str(c.get('tv_genre_id')) == str(gid)]
            pe = _portal_epg(portal)
            try:
                xepg = EPG.get() if (EPG and rows and not pe) else {}
            except Exception:
                xepg = {}
            out = []
            for c in rows:
                plot, now = _plot(_rows_for(c, pe, xepg))
                p = {'lvl': 'chplan', 'i': i, 'cid': str(c.get('id') or ''), 'gid': gid}
                out.append({'title': '%s%s' % (c.get('name') or '?', ('  –  ' + now) if now else ''),
                            'poster': _logo(portal, c.get('logo') or ''), 'is_playable': False, 'next_func': 'load',
                            'plot': plot, 'url': _tag(p), 'params': p})
            return out or [_info('Keine Sender in dieser Gruppe')]
        if lvl == 'chplan':
            cid = str(params.get('cid') or '')
            c = next((x for x in _channels(portal) if str(x.get('id') or '') == cid), None)
            if not c:
                return [_info('Sender nicht gefunden')]
            pe = _portal_epg(portal)
            try:
                xepg = EPG.get() if (EPG and not pe.get(cid)) else {}
            except Exception:
                xepg = {}
            out = [{'title': '[B]Live ansehen[/B]', 'poster': _logo(portal, c.get('logo') or ''), 'is_playable': True, 'live': True,
                    'next_func': 'get_hosters', 'params': {'i': i, 't': 'itv', 'cmd': c.get('cmd') or ''}}]
            last = ''
            up = _upcoming(_rows_for(c, pe, xepg))
            for a, b, t, d in up:
                day = _day(a)
                if day != last:
                    out.append(_info('[B]%s[/B]' % day))
                    last = day
                out.append(_info('%s–%s  %s' % (_hm(a), _hm(b), t or '(ohne Titel)'), d))
            if not up:
                out.append(_info('Kein Programm für diesen Sender gefunden (Portal und EPG-Adresse liefern nichts)'))
            return out
        if lvl == 'vodgen':
            js = _call(portal, {'type': 'vod', 'action': 'get_categories'})
            out = []
            for g in (js or []):
                if not isinstance(g, dict):
                    continue
                p = {'lvl': 'vod', 'i': i, 'cat': g.get('id') or ''}
                out.append({'title': g.get('title') or '?', 'is_playable': False, 'next_func': 'load',
                           'url': _tag(p), 'params': p})
            return out
        if lvl == 'vod':
            return _vod_list(portal, i, params.get('cat') or '', 'vod')
        if lvl == 'sergen':
            js = _call(portal, {'type': 'series', 'action': 'get_categories'})
            out = []
            for g in (js or []):
                if not isinstance(g, dict):
                    continue
                p = {'lvl': 'series', 'i': i, 'cat': g.get('id') or ''}
                out.append({'title': g.get('title') or '?', 'is_playable': False, 'next_func': 'load',
                           'url': _tag(p), 'params': p})
            return out
        if lvl == 'series':
            return _vod_list(portal, i, params.get('cat') or '', 'series')
        if lvl == 'seasons':
            return _season_list(portal, i, params.get('cat') or '', params.get('cat2') or '')
        if lvl == 'episodes':
            return _episode_list(portal, i, params.get('cat') or '', params.get('cat2') or '')
    except Exception as e:
        return [{'title': 'Fehler: %s' % e, 'is_playable': False, 'next_func': 'load'}]
    return []


def _vod_list(portal, i, cat, kind):
    out, page, pages = [], 1, 1
    while page <= pages and page <= 60:
        js = _call(portal, {'type': kind, 'action': 'get_ordered_list', 'category': cat,
                            'sortby': 'added', 'not_ended': '0', 'p': page, 'fav': '0'})
        total = float((js or {}).get('total_items') or 0)
        per = float((js or {}).get('max_page_items') or 1) or 1
        pages = max(1, math.ceil(total / per))
        for r in (js or {}).get('data') or []:
            if kind == 'vod':
                out.append({'title': r.get('name') or '?', 'poster': _logo(portal, r.get('screenshot_uri') or ''),
                           'plot': r.get('description') or '', 'year': r.get('year') or '',
                           'is_playable': True, 'next_func': 'get_hosters',
                           'params': {'i': i, 't': 'vod', 'cmd': r.get('cmd') or ''}})
            else:
                p = {'lvl': 'seasons', 'i': i, 'cat': r.get('id') or '', 'cat2': r.get('category_id') or cat}
                out.append({'title': r.get('name') or '?', 'poster': _logo(portal, r.get('screenshot_uri') or ''),
                           'plot': r.get('description') or '', 'year': r.get('year') or '',
                           'is_playable': False, 'next_func': 'load', 'url': _tag(p), 'params': p})
        page += 1
    return out


def _season_list(portal, i, movie_id, category):
    out, page, pages = [], 1, 1
    while page <= pages and page <= 60:
        js = _call(portal, {'type': 'series', 'action': 'get_ordered_list', 'category': category,
                            'movie_id': movie_id, 'sortby': 'added', 'season_id': '0', 'episod_id': '0', 'p': page})
        total = float((js or {}).get('total_items') or 0)
        per = float((js or {}).get('max_page_items') or 1) or 1
        pages = max(1, math.ceil(total / per))
        for r in (js or {}).get('data') or []:
            if not r.get('series'):
                continue
            p = {'lvl': 'episodes', 'i': i, 'cat': r.get('id') or '', 'cat2': r.get('category_id') or category}
            out.append({'title': r.get('name') or '?', 'poster': _logo(portal, r.get('screenshot_uri') or ''),
                       'plot': r.get('description') or '', 'is_playable': False, 'next_func': 'load',
                       'url': _tag(p), 'params': p})
        page += 1
    return out


def _episode_list(portal, i, season_cat, category):
    js = _call(portal, {'type': 'series', 'action': 'get_ordered_list', 'category': category,
                        'movie_id': season_cat, 'sortby': 'added', 'season_id': '0', 'episod_id': '0', 'p': 1})
    rows = (js or {}).get('data') or []
    row = next((r for r in rows if str(r.get('id')) == str(season_cat)), None)
    if not row:
        return []
    out = []
    for ep in row.get('series') or []:
        out.append({'title': 'Folge %s' % ep, 'is_playable': True, 'next_func': 'get_hosters',
                   'params': {'i': i, 't': 'series', 'cmd': row.get('cmd') or '', 'series': str(ep)}})
    return out


def _stream_of(js):
    raw = ''
    if isinstance(js, dict):
        raw = str(js.get('cmd') or '')
    raw = raw[len('ffmpeg '):] if raw.startswith('ffmpeg ') else raw
    stream, _, hdr = raw.partition('|')
    stream = stream.strip().split(' ')[-1].strip().replace('"', '')
    headers = {}
    for part in hdr.split('&'):
        k, sep, v = part.partition('=')
        if sep:
            headers[k.strip()] = v.strip()
    return stream, headers


def get_hosters(url='', params=None):
    params = params or {}
    i = params.get('i')
    portal = _portal(i)
    cmd = params.get('cmd') or ''
    if not portal or not cmd:
        return []
    t = params.get('t') or 'itv'
    call_params = {'type': 'itv' if t == 'itv' else 'vod', 'action': 'create_link', 'cmd': cmd}
    if t != 'itv':                                              
        call_params.update({'forced_storage': 'undefined', 'disable_ad': '0'})
    if t == 'series' and params.get('series'):
        call_params['series'] = params['series']
    js = _call(portal, call_params)
    stream, headers = _stream_of(js)
    if not stream and t == 'series':
        call_params.pop('series', None)                         
        stream, headers = _stream_of(_call(portal, call_params))
    if not stream:
        answer = json.dumps(js, ensure_ascii=False)[:300] if js is not None else 'leer'
        raise RuntimeError('Portal liefert für diesen Eintrag keine Adresse (Antwort: %s)' % answer)
    h = {'name': portal['name'], 'url': stream, 'direct': True, 'live': t == 'itv'}
    if headers:
        h['headers'] = headers
    return [h]
