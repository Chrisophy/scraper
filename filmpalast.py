# -*- coding: utf-8 -*-
# filmpalast.py
import re
from html import unescape
from urllib.parse import quote_plus
import xbmcgui

from resources.lib import multiquest, log

SITE_ID       = 'filmpalast'
SITE_NAME     = 'FilmPalast'
SITE_DOMAIN   = 'filmpalast.to'
GLOBAL_SEARCH = True

_URL_MAIN       = 'https://' + SITE_DOMAIN
_URL_MOVIES_NEW = _URL_MAIN + '/movies/new'
_URL_MOVIES_TOP = _URL_MAIN + '/movies/top'
_URL_SERIES     = _URL_MAIN + '/serien/view'
_URL_SEARCH     = _URL_MAIN + '/search/title/%s/page/1'
_URL_STREAM     = _URL_MAIN + '/stream/%s'

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_HEADERS = {'User-Agent': _UA, 'Accept-Language': 'de-DE,de;q=0.9'}

_RE_THUMB         = re.compile(r'<img[^>]+src="(/files/movies/\d+/[^"]+)"[^>]+alt="([^"]+)"')
_RE_YEAR          = re.compile(r'\b((?:19[5-9]|20[0-3])\d)\b')
_RE_RELEASE_TEXT  = re.compile(r'id="release_text"[^>]*>([^<&]+)')
_RE_HOST_BLOCK    = re.compile(r'<ul class="currentStreamLinks">(.*?)</ul>', re.S)
_RE_HOST_NAME     = re.compile(r'class="hostName">([^<]+)<')
_RE_PLAYER_URL    = re.compile(r'data-player-url="(https?://[^"]+)"')
_RE_HREF_URL      = re.compile(r'href="(https?://(?!filmpalast)[^"]+)"')
_RE_OG_TITLE      = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']')
_RE_OG_IMAGE      = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']')
_RE_OG_DESC       = re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']')
_RE_CANONICAL     = re.compile(r'<link rel="canonical" href="[^"]+/stream/([a-z0-9\-]+)"')


def _get(url):
    try:
        r = multiquest.get(url, headers=_HEADERS, timeout=15, use_cf=True)
        if r and r.text:
            return r.text
    except Exception:
        log.error()
    return ''


def _lang_from_signals(sTitle='', sSlug='', sRelease=''):
    title_up   = sTitle.upper()
    slug_up    = sSlug.upper()
    release_up = sRelease.upper().replace('-', '.')

    if 'ENGLISH' in title_up or title_up.endswith('*ENGLISH*') or '*ENGLISH*' in title_up:
        return 'en'
    if slug_up.endswith('-ENGLISH') or '-ENGLISH-' in slug_up:
        return 'en'

    if sRelease:
        parts = set(release_up.split('.'))
        if 'GERMAN' in release_up or 'DEUTSCH' in release_up:
            return 'de'
        if 'DL' in parts:
            return 'de'
        if 'OV' in parts or 'ENGLISH' in release_up or 'ENG' in parts:
            return 'en'
        if 'MULTi' in sRelease or 'MULTI' in release_up:
            if 'GERMAN' not in release_up and 'DL' not in parts:
                return 'en'
        return 'unbekannt'

    return 'unbekannt'


def _extract_hosters_from_page(sHtml, sSlug=''):
    sRelease = ''
    mRel = _RE_RELEASE_TEXT.search(sHtml)
    if mRel:
        sRelease = unescape(mRel.group(1)).strip()

    mOgTitle = _RE_OG_TITLE.search(sHtml)
    sTitle = unescape(mOgTitle.group(1)).strip() if mOgTitle else ''

    sLang = _lang_from_signals(sTitle, sSlug, sRelease)

    quality = 'HD'
    rel_up = sRelease.upper()
    if 'CAM' in rel_up or 'TELESYNC' in rel_up or '.TS.' in rel_up:
        quality = 'CAM'
    elif '1080' in rel_up:
        quality = '1080'
    elif '720' in rel_up:
        quality = '720'

    hosters = []
    seen_urls = set()
    for block in _RE_HOST_BLOCK.findall(sHtml):
        mName = _RE_HOST_NAME.search(block)
        sName = unescape(mName.group(1)).strip() if mName else 'Hoster'
        mUrl = _RE_PLAYER_URL.search(block)
        if not mUrl:
            mUrl = _RE_HREF_URL.search(block)
        if not mUrl:
            continue
        sUrl = mUrl.group(1)
        if sUrl in seen_urls or 'youtube' in sUrl:
            continue
        seen_urls.add(sUrl)
        # Exaktes Tupel-Format: (Name, Link, direkt?, Qualität, Sprache, Quelle)
        hosters.append((sName, sUrl, False, quality, sLang, SITE_NAME))
    return hosters


def _parse_items(sHtml):
    items = []
    seen = set()
    
    # 1. Hauptsuche nach Stream-Einträgen
    for m in re.finditer(r'href=["\'](?:https?://[^/]+)?/stream/([a-z0-9\-]+)["\']([^>]*)>(.*?)</a>', sHtml, re.S):
        sSlug = m.group(1)
        link_attrs = m.group(2)
        inner_html = m.group(3)
        
        if sSlug in seen:
            continue
            
        sTitle = ''
        mAlt = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', inner_html, re.I)
        if mAlt:
            sTitle = mAlt.group(1)
        else:
            mTitleAttr = re.search(r'title=["\']([^"\']+)["\']', link_attrs, re.I)
            if mTitleAttr:
                sTitle = mTitleAttr.group(1)
            else:
                clean = re.sub(r'<[^>]+>', '', inner_html).strip()
                if clean:
                    sTitle = clean
                    
        # Umgebungskontext für Titel-Fallback, Poster & Jahr ermitteln
        start_pos = max(0, m.start() - 200)
        end_pos = min(len(sHtml), m.end() + 200)
        context = sHtml[start_pos:end_pos]

        if not sTitle:
            mContextAlt = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', context, re.I)
            if mContextAlt:
                sTitle = mContextAlt.group(1)
                
        if not sTitle:
            continue
            
        # "Stream"-Präfixe säubern
        sTitle = re.sub(r'^(?:stream\s*[:\-]?\s*)', '', sTitle, flags=re.I).strip()

        # Poster extrahieren
        poster = ''
        mThumb = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', context, re.I)
        if mThumb:
            p_src = mThumb.group(1)
            if p_src.startswith('/'):
                poster = _URL_MAIN + p_src
            elif p_src.startswith('http'):
                poster = p_src

        # Erscheinungsjahr extrahieren
        year = 0
        mYear = _RE_YEAR.search(context)
        if mYear:
            try:
                year = int(mYear.group(1))
            except Exception:
                pass

        seen.add(sSlug)
        item = {
            'title': unescape(sTitle).strip(),
            'url': _URL_STREAM % sSlug,
            'slug': sSlug,
            'is_playable': True,
            'next_func': 'get_hosters',
        }
        if poster:
            item['poster'] = poster
        if year:
            item['year'] = year

        items.append(item)
            
    # 2. Fallback-Suche über Img-Tags
    if not items:
        for m in re.finditer(r'<img[^>]+alt=["\']([^"\']+)["\'][^>]*>', sHtml, re.I):
            sTitle = m.group(1)
            start_pos = m.start()
            end_pos = min(len(sHtml), m.end() + 300)
            context = sHtml[start_pos:end_pos]
            mSlug = re.search(r'/stream/([a-z0-9\-]+)', context)
            if mSlug:
                sSlug = mSlug.group(1)
                if sSlug in seen or not sTitle:
                    continue
                
                sTitle = re.sub(r'^(?:stream\s*[:\-]?\s*)', '', sTitle, flags=re.I).strip()

                poster = ''
                mThumb = re.search(r'src=["\']([^"\']+)["\']', m.group(0), re.I)
                if mThumb:
                    p_src = mThumb.group(1)
                    if p_src.startswith('/'):
                        poster = _URL_MAIN + p_src
                    elif p_src.startswith('http'):
                        poster = p_src

                year = 0
                mYear = _RE_YEAR.search(context)
                if mYear:
                    try:
                        year = int(mYear.group(1))
                    except Exception:
                        pass

                seen.add(sSlug)
                item = {
                    'title': unescape(sTitle).strip(),
                    'url': _URL_STREAM % sSlug,
                    'slug': sSlug,
                    'is_playable': True,
                    'next_func': 'get_hosters',
                }
                if poster:
                    item['poster'] = poster
                if year:
                    item['year'] = year

                items.append(item)

    # 3. Nächste Seite (Pagination) anhängen
    mNext = re.search(r'href=["\']([^"\']+/page/(\d+))["\'][^>]*>(?:[^<]*Nächste|[^<]*&raquo;|[^<]*»|[^<]*Next)[^<]*</a>', sHtml, re.I)
    if not mNext:
        mNext = re.search(r'href=["\']([^"\']+/page/\d+)["\']', sHtml, re.I)

    if mNext:
        n_url = mNext.group(1)
        if n_url.startswith('/'):
            n_url = _URL_MAIN + n_url

        if items:
            items.append({
                'title': 'Nächste Seite >>',
                'url': n_url,
                'next_func': 'load',
                'is_playable': False,
            })

    return items


def load(url='', params=None):
    if not url:
        return [
            {'title': 'Filme (Neu)', 'url': _URL_MOVIES_NEW, 'next_func': 'load', 'is_playable': False},
            {'title': 'Filme (Top / Beliebt)', 'url': _URL_MOVIES_TOP, 'next_func': 'load', 'is_playable': False},
            {'title': 'Serien', 'url': _URL_SERIES, 'next_func': 'load', 'is_playable': False},
            {'title': 'Genres', 'url': 'genres', 'next_func': 'load', 'is_playable': False},
        ]
    if url == 'genres':
        genres = [
            ('Abenteuer', 'Abenteuer'),
            ('Action', 'Action'),
            ('Animation', 'Animation'),
            ('Biographie', 'Biographie'),
            ('Dokumentation', 'Dokumentation'),
            ('Drama', 'Drama'),
            ('Englisch', 'Englisch'),
            ('Familie', 'Familie'),
            ('Fantasy', 'Fantasy'),
            ('Geschichte', 'Geschichte'),
            ('Horror', 'Horror'),
            ('Komödie', 'Komödie'),
            ('Krieg', 'Krieg'),
            ('Krimi', 'Krimi'),
            ('Musik', 'Musik'),
            ('Mystery', 'Mystery'),
            ('Romantik', 'Romatik'),
            ('Sci-Fi', 'Sci-Fi'),
            ('Sport', 'Sport'),
            ('Thriller', 'Thriller'),
            ('Western', 'Western'),
            ('Zeichentrick', 'Zeichentrick'),
        ]
        return [
            {'title': g[0], 'url': _URL_MAIN + '/search/genre/' + g[1], 'next_func': 'load', 'is_playable': False}
            for g in genres
        ]
    
    sHtml = _get(url)
    if not sHtml:
        return []
    return _parse_items(sHtml)


def search(query='', params=None):
    q = query or xbmcgui.Dialog().input('Suche')
    if not q:
        return []
    sHtml = _get(_URL_SEARCH % quote_plus(q))
    return _parse_items(sHtml)


def get_hosters(title='', year='', season=0, episode=0, url='', params=None):
    if int(season or 0) > 0:
        return []

    if url and url.startswith('http'):
        mSlug = _RE_CANONICAL.search(_get(url))
        sSlug = mSlug.group(1) if mSlug else url.rstrip('/').split('/')[-1]
        sHtml = _get(url)
        if not sHtml:
            return []
        return _extract_hosters_from_page(sHtml, sSlug)

    if not title:
        return []

    sHtml = _get(_URL_SEARCH % quote_plus(title))
    if not sHtml:
        return []

    items = _parse_items(sHtml)
    if not items:
        log.log('[FilmPalast] Keine Treffer für "%s"' % title)
        return []

    title_clean = title.lower().strip()
    year_str    = str(year) if year else ''

    best_url  = ''
    best_slug = ''
    for item in items:
        t = item['title'].lower()
        t_base = re.sub(r'\s*\*[^*]+\*\s*', '', t).strip()
        if title_clean not in t and t_base not in title_clean and title_clean not in t_base:
            continue
        if year_str and year_str not in item.get('url', '') and year_str not in item['title']:
            pass
        best_url  = item['url']
        best_slug = item['slug']
        break

    if not best_url:
        best_url  = items[0]['url']
        best_slug = items[0]['slug']

    log.log('[FilmPalast] Detail: %s' % best_url)
    sHtml = _get(best_url)
    if not sHtml:
        return []
    return _extract_hosters_from_page(sHtml, best_slug)
