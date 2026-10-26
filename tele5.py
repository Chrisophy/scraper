# -*- coding: utf-8 -*-
# Scraper by Zusatzmetall
# IT('s) Possible Team
# 2026.09.22
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib import multiquest


SITE_ID = 'tele5'
SITE_NAME = 'TELE 5'
SITE_DOMAIN = 'tele5.de'
TYPE = 'both'
GLOBAL_SEARCH = True

_PUBLIC = 'https://public.aurora.enhanced.live'
_MEDIATHEK = (
    _PUBLIC
    + '/site/page/mediathek/?include=default,advancedSearch'
      '&filter[environment]=tele5&v=2'
)
_PAGE = (
    _PUBLIC
    + '/site/page/{}/?include=default,advancedSearch'
      '&filter[environment]=tele5&v=2&parent_slug=mediathek'
)
_PLAYER = _PUBLIC + '/playback/v3/videoPlaybackInfo'
_TOKEN = _PUBLIC + '/token?realm=de'

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)

_HEADERS = {
    'User-Agent': _UA,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    'Origin': 'https://tele5.de',
    'Referer': 'https://tele5.de/',
    'DNT': '1',
}

_STONE_HEADERS = dict(_HEADERS)
_STONE_HEADERS.update({
    'Content-Type': 'application/json; charset=utf-8',
    'X-Device-Info': 'STONEJS/1 (Unknown/Unknown; Windows/NT 10.0; Unknown)',
    'X-disco-client': 'WEB:UNKNOWN:wbdatv:2.1.9',
    'X-disco-params': 'realm=de',
})

_MAX_WORKERS = 8
_CACHE_TTL = 6 * 60 * 60
_TOKEN_CACHE = {'token': None, 'time': 0}
_MEM = {}


def _icon():
    try:
        return xbmcaddon.Addon().getAddonInfo('icon')
    except Exception:
        return ''


_ICON = _icon()


def _log(message, level=xbmc.LOGINFO):
    try:
        xbmc.log('[MovieScout][tele5] ' + str(message), level)
    except Exception:
        pass


def _clean(value):
    if value is None:
        return ''
    text = str(value)
    text = re.sub(r'<[^>]+>', '', text)
    replacements = {
        '&nbsp;': ' ',
        '&amp;': '&',
        '&quot;': '"',
        '&#39;': "'",
        '&#x27;': "'",
        '&lt;': '<',
        '&gt;': '>',
        '&ndash;': '-',
        '&mdash;': '-',
        '\n': ' ',
        '\r': ' ',
        '\t': ' ',
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return re.sub(r'\s+', ' ', text).strip()


def _get(url, timeout=20):
    try:
        response = multiquest.get(
            url,
            headers=_HEADERS,
            timeout=timeout
        )
        if getattr(response, 'status_code', 0) == 200:
            return response
        _log('GET HTTP %s: %s' % (
            getattr(response, 'status_code', 0), url
        ), xbmc.LOGWARNING)
    except Exception as exc:
        _log('GET Fehler: %s' % exc, xbmc.LOGERROR)
    return None


def _post(url, payload, headers=None, timeout=30):
    try:
        hdr = dict(_HEADERS)
        hdr['Content-Type'] = 'application/json; charset=utf-8'
        if headers:
            hdr.update(headers)
        response = multiquest.post(
            url,
            data=json.dumps(payload, separators=(',', ':')),
            headers=hdr,
            timeout=timeout
        )
        if getattr(response, 'status_code', 0) in (200, 201, 204):
            return response
        _log('POST HTTP %s: %s' % (
            getattr(response, 'status_code', 0), url
        ), xbmc.LOGWARNING)
    except Exception as exc:
        _log('POST Fehler: %s' % exc, xbmc.LOGERROR)
    return None


def _json(response):
    if response is None:
        return None
    try:
        return response.json()
    except Exception:
        pass
    try:
        return json.loads(response.text)
    except Exception:
        return None


def _cache_get(key):
    now = time.time()
    if key in _MEM:
        stamp, value = _MEM[key]
        if now - stamp < _CACHE_TTL:
            return value
        _MEM.pop(key, None)
    return None


def _cache_put(key, value):
    _MEM[key] = (time.time(), value)


def _slug(value):
    if not value:
        return ''
    value = str(value).strip().strip('/')
    return value.rsplit('/', 1)[-1]


def _image_url(obj, role='default'):
    if not isinstance(obj, dict):
        return ''
    media = obj.get('media') or {}
    if isinstance(media, dict) and media.get('url'):
        return media['url']

    for key in ('image', 'poster', 'thumbnail', 'src', 'url'):
        value = obj.get(key)
        if isinstance(value, dict):
            value = value.get('url') or value.get('src')
        if isinstance(value, str) and value.startswith('http'):
            return value

    for entry in obj.get('metaMedia') or []:
        if not isinstance(entry, dict):
            continue
        if entry.get('role') == role:
            media = entry.get('media') or {}
            if isinstance(media, dict) and media.get('url'):
                return media['url']

    return ''


def _taxonomies(item):
    genres = []
    show = item.get('show') or {}
    for source in (
        item.get('taxonomies'),
        show.get('taxonomies') if isinstance(show, dict) else None
    ):
        if not isinstance(source, list):
            continue
        for tax in source:
            if not isinstance(tax, dict):
                continue
            if tax.get('category') in (None, '', 'genre'):
                title = _clean(tax.get('title'))
                if title and title not in genres:
                    genres.append(title)
    return genres


def _year_from(item):
    if not isinstance(item, dict):
        return ''
    sources = [item]
    show = item.get('show')
    if isinstance(show, dict):
        sources.append(show)

    for src in sources:
        for key in ('productionYear', 'year', 'releaseYear'):
            val = src.get(key)
            if val is not None and str(val).isdigit():
                y = int(val)
                if 1900 <= y <= 2100:
                    return str(y)
    return ''


def _item_from_video(item, forced_type=None):
    if not isinstance(item, dict):
        return None

    video_id = (
        item.get('id')
        or item.get('videoId')
        or item.get('ctaVideoId')
    )
    title = _clean(item.get('title') or item.get('name'))
    if not video_id or not title:
        return None

    duration_ms = item.get('videoDuration')
    try:
        duration = int(duration_ms) // 1000
    except Exception:
        duration = 0

    if duration and duration < 60:
        return None

    show = item.get('show') or {}
    show_title = _clean(show.get('title')) if isinstance(show, dict) else ''

    video_type = str(item.get('videoType') or '').upper()
    mediatype = forced_type or (
        'episode' if video_type != 'STANDALONE' and show_title else 'movie'
    )

    lower = title.lower()
    if lower.startswith('trailer:') or ' trailer ' in (' ' + lower + ' '):
        return None

    poster = (
        _image_url(item, 'default')
        or _image_url(item, 'preview')
        or _image_url(show, 'default')
        or _ICON
    )

    plot = _clean(
        item.get('description')
        or item.get('synopsis')
        or item.get('subtitle')
        or (show.get('description') if isinstance(show, dict) else '')
    )

    publish = item.get('publishStart') or item.get('publishedAt') or ''
    season = item.get('seasonNumber') or 0
    episode = item.get('episodeNumber') or 0

    try:
        season = int(season)
    except Exception:
        season = 0

    try:
        episode = int(episode)
    except Exception:
        episode = 0

    genres = _taxonomies(item)
    if not genres:
        genres = ['TELE 5']

    result = {
        'title': title,
        'url': str(video_id),
        'plot': plot,
        'year': _year_from(item),
        'genre': genres,
        'duration': duration,
        'poster': poster,
        'icon': poster,
        'fanart': poster,
        'mediatype': mediatype,
        'is_playable': True,
        'next_func': 'get_hosters',
        'date': publish,
        'show': show_title,
        'season': season,
        'episode': episode,
        'search': title,
        'director': '',
        'actors': [],
    }

    for key in ('director', 'directors'):
        value = item.get(key) or (show.get(key) if isinstance(show, dict) else None)
        if isinstance(value, list):
            names = []
            for entry in value:
                if isinstance(entry, dict):
                    name = entry.get('name') or entry.get('title')
                else:
                    name = entry
                if name:
                    names.append(_clean(name))
            if names:
                result['director'] = ', '.join(names)
                break
        elif value:
            result['director'] = _clean(value)
            break

    for key in ('actors', 'cast', 'performers'):
        value = item.get(key) or (show.get(key) if isinstance(show, dict) else None)
        if isinstance(value, list):
            names = []
            for entry in value:
                if isinstance(entry, dict):
                    name = entry.get('name') or entry.get('title')
                else:
                    name = entry
                if name:
                    names.append(_clean(name))
            result['actors'] = names[:30]
            if names:
                break

    if result['show']:
        result['plot'] = (
            result['show'] + '[CR][CR]' + result['plot']
            if result['plot'] else result['show']
        )

    return result


def _extract_category_links(data):
    links = []
    seen = set()

    for block in (data.get('blocks') or []):
        if not isinstance(block, dict):
            continue
        if block.get('type') != 'categoryCollectionBlock':
            continue

        for entry in block.get('items') or []:
            if not isinstance(entry, dict):
                continue

            title = _clean(entry.get('title'))
            slug = (
                entry.get('slug')
                or entry.get('url')
                or entry.get('parentSlug')
            )

            if not slug:
                show = entry.get('show') or {}
                if isinstance(show, dict):
                    title = title or _clean(show.get('title'))
                    slug = show.get('slug') or show.get('id')

            slug = _slug(slug)
            if not slug or slug in seen:
                continue

            tunein = _clean(
                entry.get('attributes', {}).get('tuneinInfo', '')
                if isinstance(entry.get('attributes'), dict)
                else entry.get('tuneinInfo', '')
            ).upper()
            if 'NICHT IM PROGRAMM' in tunein:
                continue

            seen.add(slug)
            links.append({
                'title': title or slug.replace('-', ' ').title(),
                'slug': slug,
                'url': _PAGE.format(quote(slug, safe=''))
            })

    return links


def _fetch_mediathek():
    cache = _cache_get('mediathek')
    if isinstance(cache, dict):
        return cache

    response = _get(_MEDIATHEK)
    data = _json(response)
    if not isinstance(data, dict):
        return {}

    _cache_put('mediathek', data)
    return data


def _category_urls():
    data = _fetch_mediathek()
    return _extract_category_links(data)


def _fetch_category(link):
    slug = _slug(link)
    if not slug:
        return {}

    cache = _cache_get('page_' + slug)
    if isinstance(cache, dict):
        return cache

    response = _get(_PAGE.format(quote(slug, safe='')))
    data = _json(response)
    if not isinstance(data, dict):
        return {}

    _cache_put('page_' + slug, data)
    return data


def _blocks_to_items(data):
    items = []
    seen = set()

    if not isinstance(data, dict):
        return items

    for block in data.get('blocks') or []:
        if not isinstance(block, dict):
            continue

        elements = []
        if block.get('type') == 'sonicShowBlock':
            elements = block.get('items') or []
        elif (
            block.get('type') == 'sonicVideoBlock'
            and isinstance(block.get('item'), dict)
        ):
            elements = [block['item']]
        elif (
            block.get('type') == 'showHeaderBlock'
            and isinstance(block.get('item'), dict)
        ):
            elements = [block['item']]

        for raw in elements:
            if not isinstance(raw, dict):
                continue

            if raw.get('videoType', 'EPISODE').upper() != 'STANDALONE':
                if not raw.get('show'):
                    continue

            if not str(raw.get('videoDuration')).isdigit():
                continue

            if 'NICHT IM PROGRAMM' in _clean(raw.get('subtitle')).upper():
                continue

            item = _item_from_video(raw)
            if not item:
                continue

            uid = item['url']
            if uid in seen:
                continue

            seen.add(uid)
            items.append(item)

    return items


def _all_items():
    cache = _cache_get('all_items')
    if isinstance(cache, list) and cache:
        return cache

    links = _category_urls()
    all_items = []
    seen = set()

    with ThreadPoolExecutor(
        max_workers=min(_MAX_WORKERS, max(1, len(links)))
    ) as executor:
        futures = {
            executor.submit(_fetch_category, x['slug']): x['slug']
            for x in links
        }

        for future in as_completed(futures):
            try:
                for item in _blocks_to_items(future.result()):
                    if item['url'] not in seen:
                        seen.add(item['url'])
                        all_items.append(item)
            except Exception as exc:
                _log('Kategoriefehler: %s' % exc, xbmc.LOGWARNING)

    all_items.sort(
        key=lambda x: str(x.get('date') or ''),
        reverse=True
    )

    if all_items:
        _cache_put('all_items', all_items)

    return all_items


def _find_by_query(query):
    q = _clean(query).lower()
    if not q:
        return []

    result = []
    for item in _all_items():
        haystack = ' '.join([
            str(item.get('title') or ''),
            str(item.get('plot') or ''),
            str(item.get('show') or ''),
            str(item.get('director') or ''),
            ' '.join(item.get('actors') or []),
            ' '.join(item.get('genre') or []),
        ]).lower()

        if q in haystack:
            result.append(item)

    return result


def _sort_unique(items):
    out = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        uid = str(item.get('url') or '')
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(item)
    return out


def load(url='', params=None):
    return [
        {
            'title': 'Suche',
            'url': '',
            'plot': 'TELE5 nach Filmen und Serien durchsuchen.',
            'poster': _ICON,
            'icon': _ICON,
            'is_playable': False,
            'next_func': 'search',
        },
        {
            'title': 'Neu hinzugefügt',
            'url': 'newest',
            'plot': 'Aktuell auf TELE5 neu veröffentlichte Filme und Episoden',
            'poster': _ICON,
            'icon': _ICON,
            'is_playable': False,
            'next_func': 'showEntries',
        },
        {
            'title': 'Filme',
            'url': 'movies',
            'plot': 'Alle verfügbaren TELE5 Spielfilme.',
            'poster': _ICON,
            'icon': _ICON,
            'is_playable': False,
            'next_func': 'showEntries',
        },
        {
            'title': 'Serien',
            'url': 'series',
            'plot': 'Alle verfügbaren Tele5 Serien und Episoden.',
            'poster': _ICON,
            'icon': _ICON,
            'is_playable': False,
            'next_func': 'showEntries',
        },
    ]


def showEntries(url='', params=None):
    mode = _slug(url)
    items = _all_items()

    if mode == 'movies':
        items = [
            x for x in items
            if x.get('mediatype') == 'movie'
            and int(x.get('duration') or 0) >= 2400
        ]

    elif mode == 'series':
        shows = {}
        for item in items:
            if item.get('mediatype') != 'episode':
                continue
            show = item.get('show') or ''
            if not show:
                continue
            key = show.lower()
            if key not in shows:
                shows[key] = {
                    'title': show,
                    'url': 'show:' + show,
                    'plot': item.get('plot', ''),
                    'poster': item.get('poster') or _ICON,
                    'icon': item.get('icon') or _ICON,
                    'is_playable': False,
                    'next_func': 'showSeries',
                }
        return sorted(
            shows.values(),
            key=lambda x: x['title'].lower()
        )

    elif mode == 'newest':
        items = sorted(
            items,
            key=lambda x: str(x.get('date') or ''),
            reverse=True
        )

    elif mode.startswith('show:'):
        wanted = mode[5:].strip().lower()
        items = [
            x for x in items
            if str(x.get('show') or '').lower() == wanted
        ]

    else:
        category_data = _fetch_category(mode)
        category_items = _blocks_to_items(category_data)
        if category_items:
            items = category_items
        else:
            items = [
                x for x in items
                if mode.lower() in [
                    str(g).lower() for g in x.get('genre') or []
                ]
            ]

    return _sort_unique(items)


def showSeries(url='', params=None):
    if not url.startswith('show:'):
        return []
    wanted = url[5:].strip().lower()
    return [
        item for item in _all_items()
        if str(item.get('show') or '').lower() == wanted
    ]


def search(query='', params=None, url=''):
    if not query:
        if isinstance(params, dict):
            query = (
                params.get('query')
                or params.get('keyword')
                or params.get('search')
                or ''
            )
        elif isinstance(url, str) and url:
            query = url

    if not query:
        try:
            query = xbmcgui.Dialog().input('TELE 5 Suche').strip()
        except Exception:
            query = ''

    if not query:
        return []

    return _find_by_query(query)


def _get_token():
    now = time.time()
    if (
        _TOKEN_CACHE['token']
        and now - _TOKEN_CACHE['time'] < 3000
    ):
        return _TOKEN_CACHE['token']

    response = _get(_TOKEN, timeout=20)
    data = _json(response)

    token = ''
    if isinstance(data, dict):
        token = (
            data.get('token')
            or data.get('access_token')
            or (
                data.get('data', {})
                .get('attributes', {})
                .get('token')
                if isinstance(data.get('data'), dict)
                else ''
            )
        )

    if token:
        _TOKEN_CACHE['token'] = token
        _TOKEN_CACHE['time'] = now

    return token


def _playback(video_id):
    token = _get_token()
    if not token:
        return {}, 401

    payload = {
        'deviceInfo': {
            'adBlocker': False,
            'drmSupported': True,
            'hdrCapabilities': [],
            'hwDecodingCapabilities': [],
            'soundCapabilities': [],
        },
        'wisteriaProperties': {},
        'videoId': str(video_id),
    }

    headers = dict(_STONE_HEADERS)
    headers['Authorization'] = 'Bearer ' + token

    response = _post(
        _PLAYER,
        payload,
        headers=headers,
        timeout=30
    )
    status = getattr(response, 'status_code', 0)
    data = _json(response)
    if not isinstance(data, dict):
        return {}, status

    return data, status


def _is_geolocked(data, status):
    if status == 403:
        return True
    errors = data.get('errors') or []
    for err in errors:
        code = str(err.get('code', '')).upper()
        detail = str(err.get('detail', '')).lower()
        if any(k in code or k in detail for k in ('geo', 'region', 'country', 'block')):
            return True
    return False


def _notify_geolock():
    try:
        xbmcgui.Dialog().notification(
            'TELE 5 VPN / Geoblock',
            'Inhalt regional gesperrt (nur aus DE abspielbar)',
            xbmcgui.NOTIFICATION_WARNING,
            4000
        )
    except Exception:
        pass


def _streams_from_playback(data):
    try:
        streams = data['data']['attributes']['streaming']
    except Exception:
        streams = []

    if not isinstance(streams, list):
        return []

    result = []

    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if stream.get('type') != 'hls' or not stream.get('url'):
            continue

        result.append({
            'name': 'TELE 5 HLS',
            'url': stream['url'],
            'quality': 'HD',
            'language': 'de',
            'type': 'hls',
            'drm': bool(
                stream.get('protection', {}).get('drmEnabled', False)
            ),
        })

    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if stream.get('type') != 'dash' or not stream.get('url'):
            continue

        protection = stream.get('protection') or {}
        schemes = protection.get('schemes') or {}
        widevine = schemes.get('widevine') or {}

        result.append({
            'name': 'TELE 5 DASH',
            'url': stream['url'],
            'quality': 'HD',
            'language': 'de',
            'type': 'mpd',
            'drm': bool(protection.get('drmEnabled')),
            'license_url': widevine.get('licenseUrl') or '',
            'drm_token': protection.get('drmToken') or '',
        })

    return result


def _hoster_tuple(stream):
    url = str(stream.get('url') or '')
    if not url:
        return None

    if stream.get('type') == 'hls' and not stream.get('drm'):
        return (
            stream.get('name', 'TELE 5'),
            url,
            True,
            stream.get('quality', 'HD'),
            stream.get('language', 'de')
        )

    extras = []
    if stream.get('type') == 'mpd':
        extras.append('inputstream=inputstream.adaptive')
        extras.append('inputstream.adaptive.manifest_type=mpd')

    license_url = stream.get('license_url')
    drm_token = stream.get('drm_token')

    if license_url:
        extras.append(
            'inputstream.adaptive.license_type=com.widevine.alpha'
        )
        license_key = license_url
        if drm_token:
            license_key += '|PreAuthorization=' + quote(str(drm_token), safe='')
        extras.append(
            'inputstream.adaptive.license_key='
            + quote(license_key, safe='')
        )

    extras.append('User-Agent=' + quote(_UA, safe=''))

    final_url = url
    if extras:
        final_url += '|' + '&'.join(extras)

    return (
        stream.get('name', 'TELE 5'),
        final_url,
        True,
        stream.get('quality', 'HD'),
        stream.get('language', 'de')
    )


def get_hosters(
    title='',
    year='',
    season=0,
    episode=0,
    imdb='',
    tmdb='',
    url='',
    params=None
):
    vid = str(url or '')
    if not vid:
        return []
        
    data, status = _playback(vid)
    if _is_geolocked(data, status):
        _notify_geolock()
        return []
        
    streams = _streams_from_playback(data)
    result = []
    for stream in streams:
        hoster = _hoster_tuple(stream)
        if hoster:
            result.append(hoster)
    return result
