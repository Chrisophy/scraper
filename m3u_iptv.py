# -*- coding: utf-8 -*-
# IT('s) Possible
# MovieScout Scraper m3u_iptv.py
# Eigene M3U-Playlisten (IPTV) + EPG (XMLTV), URLs kommen aus den Engine-Einstellungen.
import json as _json
import re
import threading
import time

import xbmcaddon
from engine import epg as EPG          # gemeinsame EPG-Logik (auch für Stalker-Portale)
from resources.lib import multiquest

SITE_ID = 'm3u_iptv'
SITE_NAME = 'M3U / IPTV'
SITE_DOMAIN = ''
TYPE = 'live'
GLOBAL_SEARCH = True

_EXTINF = re.compile(r'^#EXTINF:(?P<dur>-?\d+)(?P<attrs>.*?),(?P<name>[^\r\n]*)$')
_ATTR = re.compile(r'([A-Za-z0-9\-]+)="([^"]*)"')
_VLCOPT = re.compile(r'^#EXTVLCOPT:(\S+?)=(.+)$')

_LOCK = threading.Lock()
_M3U_CACHE = {}           # url -> (geladen_um, [channel, ...])
_M3U_TTL = 6 * 3600


def _tag(d):
    """Eindeutige Kennung für ein Navigationsziel - geht als 'url' mit (die Engine cacht Menüs nach
    provider+next_func+url; ohne das würden alle Ebenen, die nur 'params' nutzen, denselben
    Cache-Eintrag treffen)."""
    return 'm3u:' + _json.dumps(d or {}, sort_keys=True, ensure_ascii=False)


def _settings():
    return xbmcaddon.all_settings()


def _playlists():
    """Jede Zeile in den Einstellungen: entweder nur eine URL, oder "Name = URL"."""
    raw = (_settings().get('m3u_urls') or '').strip()
    out = []
    for i, line in enumerate(raw.splitlines()):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, sep, url = line.partition('=')
        if sep and re.match(r'^[A-Za-z][A-Za-z0-9+.\-]*://', url.strip()):
            out.append({'name': name.strip() or ('Liste %d' % (i + 1)), 'url': url.strip()})
        else:
            out.append({'name': 'Liste %d' % (i + 1), 'url': line})
    return out


def _parse_m3u(text, list_name):
    chans = []
    pending = None
    pending_headers = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            m = _EXTINF.match(line)
            if not m:
                pending = None
                continue
            attrs = dict(_ATTR.findall(m.group('attrs') or ''))
            pending = {
                'name': (m.group('name') or '').strip() or attrs.get('tvg-name') or 'Unbenannt',
                'tvg_id': attrs.get('tvg-id') or '',
                'tvg_name': attrs.get('tvg-name') or '',
                'logo': attrs.get('tvg-logo') or attrs.get('tvg-logo-small') or '',
                'group': attrs.get('group-title') or list_name,
            }
            pending_headers = {}
        elif line.startswith('#EXTVLCOPT:'):
            m = _VLCOPT.match(line)
            if m and pending is not None:
                k, v = m.group(1).lower(), m.group(2).strip()
                if k == 'http-referrer':
                    pending_headers['Referer'] = v
                elif k == 'http-user-agent':
                    pending_headers['User-Agent'] = v
        elif line.startswith('#'):
            continue
        else:
            if pending is not None:
                pending['url'] = line
                pending['headers'] = pending_headers
                chans.append(pending)
            pending = None
            pending_headers = {}
    return chans


def _load_playlist(pl):
    with _LOCK:
        hit = _M3U_CACHE.get(pl['url'])
        if hit and time.time() - hit[0] < _M3U_TTL:
            return hit[1]
    r = multiquest.get(pl['url'], headers={'User-Agent': 'MovieScout'}, timeout=25)
    if r.status_code != 200 or not r.text:
        raise RuntimeError('Playlist nicht erreichbar (HTTP %s): %s' % (r.status_code, pl['name']))
    chans = _parse_m3u(r.text, pl['name'])
    with _LOCK:
        _M3U_CACHE[pl['url']] = (time.time(), chans)
    return chans


def _all_channels(playlists):
    out = []
    for pl in playlists:
        try:
            out.extend(_load_playlist(pl))
        except Exception:
            continue
    return out


def _groups(channels):
    seen = []
    have = set()
    for c in channels:
        g = c['group'] or 'Ohne Kategorie'
        if g not in have:
            have.add(g)
            seen.append(g)
    return sorted(seen, key=lambda s: s.lower())


def _channel_item(c, epg):
    plot, now = EPG.now_next(epg, c) if epg else ('', '')
    return {
        'title': c['name'], 'url': c['url'], 'poster': c.get('logo') or '',
        'is_playable': True, 'live': True, 'plot': plot, 'now': now,
        'params': {'hdr': '&'.join('%s=%s' % (k, v) for k, v in (c.get('headers') or {}).items())},
        'next_func': 'get_hosters',
    }


# ----------------------------------------------------------------------------- Navigation

def load(url='', params=None):
    params = params or {}
    lvl = params.get('lvl') or 'root'
    playlists = _playlists()
    if lvl == 'refresh':
        with _LOCK:
            _M3U_CACHE.clear()
        EPG.clear()
        lvl = 'root'
        EPG.prefetch()                                  # Guide gleich im Hintergrund neu holen
    if not playlists:
        return [{'title': 'Keine Playlist eingetragen – unter Einstellungen → M3U/IPTV hinzufügen',
                 'is_playable': False, 'next_func': 'load'}]
    if lvl == 'root':
        channels = _all_channels(playlists)
        groups = _groups(channels)
        items = [{'title': 'Alle Sender (%d)' % len(channels), 'is_playable': False, 'next_func': 'load',
                  'url': _tag({'lvl': 'group', 'g': '*'}), 'params': {'lvl': 'group', 'g': '*'}}]
        items += [{'title': g, 'is_playable': False, 'next_func': 'load',
                   'url': _tag({'lvl': 'group', 'g': g}), 'params': {'lvl': 'group', 'g': g}} for g in groups]
        st = EPG.status_line(channels)
        if st:
            miss = EPG.unmatched(channels)
            items.append({'title': st, 'is_playable': False, 'next_func': 'load', 'url': 'epgstatus', 'params': {'lvl': 'root'},
                          'plot': ('Ohne Guide-Eintrag, z. B.: ' + ', '.join(miss)) if miss else ''})
        items.append({'title': '[B][ Playlisten aktualisieren ][/B]', 'is_playable': False,
                      'url': 'refresh', 'next_func': 'load', 'params': {'lvl': 'refresh'}})
        return items
    if lvl == 'group':
        g = params.get('g') or '*'
        channels = _all_channels(playlists)
        if g != '*':
            channels = [c for c in channels if (c['group'] or 'Ohne Kategorie') == g]
        epg = EPG.get() if channels else {}
        return [_channel_item(c, epg) for c in channels]
    return []


def search(query=''):
    q = (query or '').strip().lower()
    if not q:
        return []
    channels = [c for c in _all_channels(_playlists()) if q in c['name'].lower()]
    epg = EPG.get() if channels else {}
    return [_channel_item(c, epg) for c in channels[:200]]


def get_hosters(url='', params=None):
    if not url:
        return []
    headers = {}
    hdr = (params or {}).get('hdr') or ''
    for part in hdr.split('&'):
        k, sep, v = part.partition('=')
        if sep:
            headers[k] = v
    h = {'name': 'M3U', 'url': url, 'direct': True, 'live': True}
    if headers:
        h['headers'] = headers
    return [h]
