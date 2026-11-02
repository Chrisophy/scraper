# -*- coding: utf-8 -*-
# JustWatch TV
# IT('s) Possible 
# 2026.11.02
"""MovieScout Scraper for Free JustWatch TV offers."""
import json
import re
import urllib.parse
from resources.lib import multiquest, log

SITE_ID       = 'justwatch'
SITE_NAME     = 'JustWatch TV'
SITE_DOMAIN   = 'www.justwatch.com'
TYPE          = 'both'
GLOBAL_SEARCH = True
ACTIVE        = True

_API_ENDPOINT = 'https://apis.justwatch.com/graphql'
_UA = 'MovieScout JustWatch addon/1.0'

POPULAR_QUERY = """
query GetPopularTitles($country: Country!, $first: Int!, $language: Language!, $offset: Int!, $popularTitlesFilter: TitleFilter!, $watchNowFilter: WatchNowOfferFilter!) {
  popularTitles(country: $country, filter: $popularTitlesFilter, first: $first, sortBy: POPULAR, offset: $offset) {
    edges { node {
      __typename id objectType
      content(country: $country, language: $language) {
        title fullPath originalReleaseYear posterUrl(profile: S718) ageCertification
      }
      watchNowOffer(country: $country, platform: WEB, filter: $watchNowFilter) {
        id standardWebURL streamUrlExternalPlayer streamUrl monetizationType
        package { clearName shortName technicalName }
      }
    } }
    pageInfo { hasNextPage }
    totalCount
  }
}
"""

SHOW_SEASONS_QUERY = """
query GetShowSeasons($fullPath: String!, $country: Country!, $language: Language!, $provider: String!) {
  urlV2(fullPath: $fullPath, site: "www") {
    node {
      __typename id
      ... on Show {
        content(country: $country, language: $language) { title }
        seasons(sortDirection: DESC) {
          id
          content(country: $country, language: $language) {
            title seasonNumber fullPath posterUrl
          }
          offers(country: $country, platform: WEB, filter: {packages: [$provider]}) {
            id monetizationType package { technicalName clearName }
          }
        }
      }
    }
  }
}
"""

SEASON_EPISODES_QUERY = """
query GetSeasonEpisodes($seasonId: ID!, $country: Country!, $language: Language!, $provider: String!, $limit: Int!) {
  node(id: $seasonId) {
    __typename id
    ... on Season {
      content(country: $country, language: $language) { title seasonNumber }
      episodes(limit: $limit) {
        id
        content(country: $country, language: $language) {
          title seasonNumber episodeNumber shortDescription runtime
        }
        offers(country: $country, platform: WEB, filter: {packages: [$provider]}) {
          id streamUrlExternalPlayer streamUrl monetizationType
          package { clearName shortName technicalName }
        }
      }
    }
  }
}
"""

TITLE_OFFERS_QUERY = """
query GetTitleOffers($fullPath: String!, $country: Country!) {
  urlV2(fullPath: $fullPath, site: "www") {
    node {
      __typename id
      ... on Movie {
        offers(country: $country, platform: WEB) {
          id monetizationType streamUrlExternalPlayer streamUrl
          package { clearName shortName technicalName }
        }
      }
    }
  }
}
"""

PLAY_INFORMATION_QUERY = """
mutation GetPlayInformation($input: GetPlayInformationInput!) {
  getPlayInformation(input: $input) {
    errorCode
    playbackId
    streams {
      url encodingType drmType manifestUrlDash
      drmConfigs { certificateURL drmType laURL }
    }
    offer { id streamUrlExternalPlayer streamUrl }
  }
}
"""


def _api_call(operation, query, variables):
    payload = json.dumps({"operationName": operation, "query": query, "variables": variables}, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json", "Content-Type": "application/json",
        "Origin": "https://www.justwatch.com", "Referer": "https://www.justwatch.com/",
        "User-Agent": _UA,
    }
    try:
        r = multiquest.post(_API_ENDPOINT, data=payload, headers=headers, timeout=20)
        if r.status_code >= 400:
            log.log('[JustWatch] API HTTP-Fehler %s bei %s' % (r.status_code, operation), log.LOGWARNING)
            return {}
        data = json.loads(r.text)
        return data.get("data", {})
    except Exception as exc:
        log.log('[JustWatch] API-Aufruf %s fehlgeschlagen: %s' % (operation, exc), log.LOGWARNING)
        return {}


def _api_context():
    return "DE", "en", "jwt"


def load(url='', params=None):
    if url:
        return showEntries(url, params)
    return [
        {'title': 'Beliebte kostenlose Titel', 'url': 'list', 'is_playable': False, 'next_func': 'showEntries'},
        {'title': 'Filme', 'url': 'movies', 'is_playable': False, 'next_func': 'showEntries'},
        {'title': 'Serien', 'url': 'series', 'is_playable': False, 'next_func': 'showEntries'},
        {'title': 'Suche', 'url': 'search', 'is_playable': False, 'next_func': 'search'},
    ]


def showEntries(url='', params=None):
    if not url or url == 'list':
        return _list_catalog(object_type='')
    if url == 'movies':
        return _list_catalog(object_type='MOVIE')
    if url == 'series':
        return _list_catalog(object_type='SHOW')
    if url.startswith('more:'):
        _, offset, object_type, search_text = url.split(':', 3)
        return _list_catalog(search_text=search_text, offset=int(offset), object_type=object_type)
    if url.startswith('seasons:'):
        fullpath, title = url[8:].split('||', 1)
        return _show_seasons(fullpath, title)
    if url.startswith('episodes:'):
        season_id, show_title = url[9:].split('||', 1)
        return _season_episodes(season_id, show_title)
    return []


def _list_catalog(search_text="", offset=0, object_type=""):
    country, language, provider = _api_context()
    providers = [provider]
    monetization = ["FREE"]
    size = 30

    filter_value = {
        "packages": providers,
        "monetizationTypes": monetization,
        "ageCertifications": [],
        "excludeGenres": [],
        "excludeProductionCountries": [],
        "objectTypes": [object_type] if object_type else [],
        "productionCountries": [],
        "subgenres": [],
        "genres": [],
        "excludeIrrelevantTitles": False,
        "presentationTypes": [],
        "searchQuery": search_text,
    }
    watch_filter = {"packages": providers, "monetizationTypes": monetization}
    variables = {
        "country": country, "language": language, "first": size, "offset": offset,
        "popularTitlesFilter": filter_value, "watchNowFilter": watch_filter,
    }

    result = _api_call("GetPopularTitles", POPULAR_QUERY, variables)
    listing = result.get("popularTitles") or {}
    items = []

    for edge in listing.get("edges") or []:
        node = (edge or {}).get("node") or {}
        content = node.get("content") or {}
        offer = node.get("watchNowOffer") or {}

        title = content.get("title") or "Unbenannter Titel"
        year = content.get("originalReleaseYear")
        show = node.get("__typename") == "Show" or node.get("objectType") == "SHOW"
        label = "%s (%s)" % (title, year) if year else title
        poster = content.get("posterUrl") or ""
        age = content.get("ageCertification") or ""

        item = {
            'title': label,
            'poster': poster,
            'fanart': poster,
            'year': str(year) if year else '',
            'mpaa': "FSK %s" % age if age else '',
            'plot': '',
            'mediatype': 'tvshow' if show else 'movie',
        }

        if show:
            fullpath = content.get("fullPath", "")
            item.update({
                'url': 'seasons:%s||%s' % (fullpath, title),
                'is_playable': False,
                'next_func': 'showEntries',
            })
        else:
            offer_id = offer.get("id", "")
            fullpath = content.get("fullPath", "")
            item.update({
                'url': 'offer:%s||%s||%s' % (offer_id, fullpath, title),
                'is_playable': True,
                'next_func': 'get_hosters',
            })
        items.append(item)

    if listing.get("pageInfo", {}).get("hasNextPage"):
        items.append({
            'title': 'Weitere Ergebnisse …',
            'url': 'more:%d||%s||%s' % (offset + size, object_type, search_text),
            'is_playable': False,
            'next_func': 'showEntries',
        })
    return items


def _show_seasons(fullpath, show_title):
    country, language, provider = _api_context()
    data = _api_call("GetShowSeasons", SHOW_SEASONS_QUERY, {
        "fullPath": fullpath, "country": country, "language": language, "provider": provider,
    })
    node = ((data.get("urlV2") or {}).get("node") or {})
    seasons = node.get("seasons") or []
    items = []
    for season in seasons:
        content = season.get("content") or {}
        number = content.get("seasonNumber")
        label = content.get("title") or ("Staffel %s" % number if number else "Staffel")
        poster = content.get("posterUrl") or ""
        items.append({
            'title': label,
            'url': 'episodes:%s||%s' % (season.get("id", ""), show_title),
            'poster': poster,
            'fanart': poster,
            'season': number or 0,
            'mediatype': 'season',
            'is_playable': False,
            'next_func': 'showEntries',
        })
    return items


def _season_episodes(season_id, show_title):
    country, language, provider = _api_context()
    result = _api_call("GetSeasonEpisodes", SEASON_EPISODES_QUERY, {
        "seasonId": season_id, "country": country, "language": language,
        "provider": provider, "limit": 100,
    })
    node = result.get("node") or {}
    episodes = node.get("episodes") or []
    items = []
    for episode in episodes:
        content = episode.get("content") or {}
        offers = episode.get("offers") or []
        offer = next((o for o in offers if o and o.get("id")), {})
        if not offer:
            continue
        number = content.get("episodeNumber")
        label = ("E%02d — " % number if isinstance(number, int) else "") + (content.get("title") or "Folge")
        offer_id = offer.get("id", "")
        items.append({
            'title': label,
            'url': 'offer:%s||||%s' % (offer_id, label),
            'poster': content.get("posterUrl") or "",
            'season': content.get("seasonNumber") or 0,
            'episode': number or 0,
            'mediatype': 'episode',
            'plot': content.get("shortDescription") or "",
            'duration': content.get("runtime") or 0,
            'is_playable': True,
            'next_func': 'get_hosters',
        })
    return items


def search(query='', params=None, url=''):
    if not query:
        try:
            import xbmcgui
            query = xbmcgui.Dialog().input('JustWatch Suche', type=xbmcgui.INPUT_ALPHANUM)
        except Exception:
            pass
    if not query:
        return []
    return _list_catalog(search_text=query)


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    if not url:
        return []
    offer_id, fullpath = "", ""
    if url.startswith('offer:'):
        parts = url[6:].split('||', 2)
        offer_id = parts[0]
        if len(parts) > 1:
            fullpath = parts[1]

    last_error_code = ""

    if offer_id:
        for variant in ({"drmType": "widevine", "deviceOs": "android"},
                        {"drmType": "playready", "deviceOs": "windows"},
                        {"deviceOs": "windows"}):
            play_input = {"offerId": offer_id}
            play_input.update(variant)
            res = _api_call("GetPlayInformation", PLAY_INFORMATION_QUERY, {"input": play_input})
            info = (res.get("getPlayInformation") or {})
            
            err = info.get("errorCode")
            if err:
                last_error_code = str(err)
                log.log('[JustWatch] PlayInformation errorCode: %s' % err, log.LOGWARNING)
                continue

            streams = info.get("streams") or []
            for s in streams:
                su = s.get("url") or ""
                drm = str(s.get("drmType") or "").lower()
                if su and drm in ("", "none", "null"):
                    return [('JustWatch', su, True, 'HD', 'de')]
                manifest = s.get("manifestUrlDash") or ""
                configs = s.get("drmConfigs") or []
                wv = next((c.get("laURL") for c in configs if str(c.get("drmType")).lower() == "widevine" and c.get("laURL")), "")
                if manifest and wv:
                    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
                    hdr = "Origin=%s&Referer=%s&User-Agent=%s" % (
                        urllib.parse.quote("https://www.justwatch.com"), urllib.parse.quote("https://www.justwatch.com/"), urllib.parse.quote(ua))
                    drm_info = {
                        'drm_type': 'widevine',
                        'drm_license': wv,
                        'drm_headers': hdr,
                        'manifest_headers': hdr,
                    }
                    return [('JustWatch DRM', manifest, drm_info)]

    if fullpath:
        country, language, provider = _api_context()
        data = _api_call("GetTitleOffers", TITLE_OFFERS_QUERY, {"fullPath": fullpath, "country": country})
        node = ((data.get("urlV2") or {}).get("node") or {})
        offers = [o for o in (node.get("offers") or []) if o and o.get("id")]
        for o in offers:
            direct = o.get("streamUrlExternalPlayer") or o.get("streamUrl") or ""
            if direct and direct.startswith("https://"):
                return [('JustWatch', direct, True, 'HD', 'de')]
            res = get_hosters(url='offer:%s||||' % o['id'])
            if res:
                return res

    if last_error_code:
        err_upper = last_error_code.upper()
        if '18' in err_upper or 'NIGHT' in err_upper or 'AGE' in err_upper:
            raise Exception('FSK ab 18 – erst ab 0 Uhr')
        if '16' in err_upper:
            raise Exception('FSK ab 16 – erst ab 22 Uhr')
        raise Exception('Wiedergabe nicht möglich: %s' % last_error_code)

    return []