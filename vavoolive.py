# -*- coding: utf-8 -*-
"""Vavoo Live TV - Senderliste (nach Land/Gruppe, A-Z, Suche) und Stream-Auflösung.

Nutzt resources/lib/vavootv.py (VavooClient). Der Anbieter ist unabhängig vom Film-/Serien-
Katalog "vavoo" (providers/vavoo.py).

Einstellungen / Umgebung (optional):
  * Einstellung `vavoo_portal`  bzw. Umgebungsvariable VAVOO_PORTAL: eigenes Portal, z.B. https://vavoo.to
  * Einstellung `vavoo_adult`   ('true' blendet Erwachsenen-Sender ein, Standard: aus)
"""
import json
import os
import re
import threading
import time

import xbmcgui
import xbmcaddon

from resources.lib import log
from resources.lib.vavootv import VavooClient, BUNDLES

SITE_ID       = 'vavoolive'
SITE_NAME     = 'Vavoo Live TV'
SITE_DOMAIN   = 'vavoo.to'
TYPE          = 'tv'
GLOBAL_SEARCH = False

_PLAY_UA     = 'VAVOO/2.6'          # übliche Kennung für die aufgelösten Vavoo-Streams
_CACHE_TTL   = 900                  # Senderliste 15 min im Speicher
_BIG_GROUP   = 120                  # ab so vielen Sendern A-Z-Unterebene
_MAX_SOURCES = 4                    # mehr Quellen (.b/.c/Backup) pro Sender werden nicht aufgelöst
_PREFER      = ('germany', 'deutschland', 'austria', 'österreich', 'switzerland', 'schweiz')

_lock = threading.Lock()
_state = {'client': None, 'channels': None, 'ts': 0.0, 'portal': ''}


# ----------------------------------------------------------------------------- Hilfen

def _setting(key, default=''):
    try:
        v = xbmcaddon.Addon().getSetting(key)
    except Exception:
        v = ''
    return v if v not in (None, '') else default


def _portals():
    custom = (os.environ.get('VAVOO_PORTAL') or _setting('vavoo_portal')).strip()
    out = [custom] if custom else []
    out += [u for _, u in BUNDLES if u not in out]
    return out


def _adult():
    return _setting('vavoo_adult', 'false').lower() == 'true'


_VARIANT = re.compile(r'\s*\.[a-z]\b', re.I)
_JUNK = re.compile(r'\b(backup|match ?time|live during events only|only during events|spieltag|raw)\b', re.I)
_QUAL = re.compile(r'\b(4k|uhd|fhd|hevc|hd|sd)\b', re.I)


def _clean(name):
    """Sender-Anzeigename ohne Varianten-Suffixe (.b/.c), Backup-Hinweise und Qualitätskürzel."""
    s = _VARIANT.sub('', name or '')
    s = _JUNK.sub('', s)
    s = _QUAL.sub('', s)
    s = re.sub(r'[^\w äöüÄÖÜß.,+&/\-]', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def _quality(name):
    m = _QUAL.findall(name or '')
    order = ['4k', 'uhd', 'fhd', 'hevc', 'hd', 'sd']
    for q in order:
        if q in [x.lower() for x in m]:
            return {'4k': '4K', 'uhd': '4K', 'fhd': 'FHD', 'hevc': 'HEVC', 'hd': 'HD', 'sd': 'SD'}[q]
    return ''


def _load_channels(force=False):
    """Holt die komplette Senderliste (Speicher-Cache) und probiert bei Ausfall weitere Portale."""
    with _lock:
        if (not force and _state['channels'] and time.time() - _state['ts'] < _CACHE_TTL):
            return _state['channels']

    deadline = time.time() + 38
    last_err = ''
    for portal in _portals():
        if time.time() > deadline:
            break
        try:
            client = VavooClient(portal, timeout=14)
            raw = client.get_all_channels(adult=_adult())
        except Exception as e:  # Netzwerk-/Portalfehler -> nächstes Portal
            last_err = '%s: %s' % (type(e).__name__, e)
            log.log('[VavooLive] Portal %s: %s' % (portal, last_err), log.LOGWARNING)
            continue
        channels = _group_channels(raw)
        if channels:
            with _lock:
                _state.update(client=client, channels=channels, ts=time.time(), portal=portal)
            log.log('[VavooLive] %d Sender (%s)' % (len(channels), portal))
            return channels
        log.log('[VavooLive] Portal %s lieferte keine Sender' % portal, log.LOGWARNING)
    with _lock:
        if _state['channels']:       # alter Stand ist besser als nichts
            return _state['channels']
    xbmcgui.Dialog().notification('Vavoo Live TV', 'Keine Senderliste erhalten. Portal nicht erreichbar? %s' % last_err[:80])
    return []


def _group_channels(raw):
    """Rohlisten-Einträge -> Sender; gleiche Namen (Varianten .b/.c/Backup) werden zu einem Sender mit mehreren Quellen."""
    by_key = {}
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        url = it.get('url') or ''
        name = it.get('name') or ''
        if not url or not name:
            continue
        group = (it.get('group') or 'Sonstige').strip() or 'Sonstige'
        disp = _clean(name) or name.strip()
        key = (group.lower(), disp.lower())
        ch = by_key.get(key)
        if not ch:
            ch = by_key[key] = {'name': disp, 'group': group, 'urls': [], 'logo': '', 'quality': ''}
        if url not in ch['urls']:
            ch['urls'].append(url)
        ch['logo'] = ch['logo'] or it.get('logo') or it.get('poster') or ''
        q = _quality(name)
        if q and (not ch['quality'] or q in ('FHD', '4K')):
            ch['quality'] = q
    out = list(by_key.values())
    out.sort(key=lambda c: c['name'].lower())
    return out


def _group_names(channels):
    counts = {}
    for c in channels:
        counts[c['group']] = counts.get(c['group'], 0) + 1

    def rank(g):
        gl = g.lower()
        pos = [i for i, p in enumerate(_PREFER) if p in gl]
        return (pos[0] // 2 if pos else 99, gl)      # Deutschland, Österreich, Schweiz, dann A-Z
    return [(g, counts[g]) for g in sorted(counts, key=rank)]


def _item(ch):
    return {
        'title': ch['name'],
        'url': '\n'.join(ch['urls'][:_MAX_SOURCES]),
        'poster': ch.get('logo') or '',
        'icon': ch.get('logo') or '',
        'plot': '[B]%s[/B]%s' % (ch['group'], ('\nQualität: ' + ch['quality']) if ch['quality'] else ''),
        'mediatype': 'video',
        'is_playable': True,
        'next_func': 'get_hosters',
    }


def _folder(title, url, func, plot=''):
    return {'title': title, 'url': url, 'plot': plot, 'is_playable': False, 'next_func': func}


# ----------------------------------------------------------------------------- Menüs

def load(url='', params=None):
    if not url:
        return [
            _folder('Sender nach Land / Gruppe', 'groups', 'showGroups', 'Deutschland, Österreich, Schweiz … zuerst.'),
            _folder('Alle Sender A–Z', 'all', 'showLetters', 'Alle Sender, nach Anfangsbuchstaben.'),
            _folder('Suche', '', 'search', 'Sender nach Namen suchen.'),
            _folder('Senderliste neu laden', '', 'reload'),
        ]
    return showGroups(url, params)


def reload(url='', params=None):
    with _lock:
        _state.update(channels=None, ts=0.0)
    ch = _load_channels(force=True)
    xbmcgui.Dialog().notification('Vavoo Live TV', '%d Sender geladen' % len(ch))
    return []


def showGroups(url='', params=None):
    channels = _load_channels()
    return [_folder('%s (%d)' % (g, n), 'g:' + g, 'showChannels') for g, n in _group_names(channels)]


def showLetters(url='', params=None):
    """Buchstaben-Ebene für 'Alle Sender' (url='all') oder eine große Gruppe (url='g:<Gruppe>')."""
    channels = _load_channels()
    scope = url[2:] if str(url).startswith('g:') else None
    pool = [c for c in channels if scope is None or c['group'] == scope]
    letters = {}
    for c in pool:
        l = c['name'][:1].upper()
        l = l if l.isalpha() else '#'
        letters[l] = letters.get(l, 0) + 1
    base = 'g:' + scope if scope is not None else 'all'
    return [_folder('%s (%d)' % (l, letters[l]), '%s\x1f%s' % (base, l), 'showChannels')
            for l in sorted(letters, key=lambda x: ('~' if x == '#' else x))]


def showChannels(url='', params=None):
    channels = _load_channels()
    url = str(url or '')
    base, _, letter = url.partition('\x1f')
    scope = base[2:] if base.startswith('g:') else None
    pool = [c for c in channels if scope is None or c['group'] == scope]
    if letter:
        pool = [c for c in pool if (c['name'][:1].upper() if c['name'][:1].isalpha() else '#') == letter]
    elif scope is None or len(pool) > _BIG_GROUP:
        return showLetters(url if scope is not None else 'all', params)
    return [_item(c) for c in pool]


def search(query='', params=None):
    q = (query or '').strip()
    if not q:
        q = xbmcgui.Dialog().input('Sender suchen')
    q = (q or '').strip().lower()
    if not q:
        return []
    hits = [c for c in _load_channels() if q in c['name'].lower()]
    hits.sort(key=lambda c: (not c['name'].lower().startswith(q), c['name'].lower()))
    return [_item(c) for c in hits[:300]]


# ----------------------------------------------------------------------------- Abspielen

def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    play_urls = [u for u in str(url or '').split('\n') if u.startswith('http')][:_MAX_SOURCES]
    if not play_urls:
        return []
    with _lock:
        client = _state['client']
    if client is None:
        _load_channels()
        with _lock:
            client = _state['client']
    if client is None:
        client = VavooClient(_portals()[0], timeout=14)

    hosters = []
    deadline = time.time() + 40
    for i, pu in enumerate(play_urls):
        if time.time() > deadline and hosters:
            break
        try:
            stream = client.resolve_stream_url(pu)
        except Exception as e:
            log.log('[VavooLive] resolve %s: %s: %s' % (pu, type(e).__name__, e), log.LOGWARNING)
            continue
        if not stream:
            continue
        label = 'Live' if len(play_urls) == 1 else 'Quelle %d' % (i + 1)
        path = stream.split('?')[0].lower()
        info = {'is_live': True}
        if not path.endswith(('.ts', '.mp4', '.mpd')):
            info['manifest_type'] = 'hls'     # Vavoo liefert Live-Streams als HLS, auch ohne .m3u8-Endung
        hosters.append([label, '%s|User-Agent=%s' % (stream, _PLAY_UA), info, 'Live', '', 'vavoo'])
    if not hosters:
        xbmcgui.Dialog().notification('Vavoo Live TV', 'Sender konnte nicht aufgelöst werden')
    return hosters
