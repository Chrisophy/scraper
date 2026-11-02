# -*- coding: utf-8 -*-
# JustWatch TV
# IT('s) Possible 
# 2026.11.02
"""MovieScout Scraper für Free JustWatch TV Angebote.
Nur kostenlose Angebote mit nachgewiesener deutscher Tonspur.
"""

import json
import time
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
        audioLanguages(language: $language)
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
            title seasonNumber fullPath posterUrl ageCertification
          }
          offers(country: $country, platform: WEB, filter: {packages: [$provider]}) {
            id monetizationType
            audioLanguages(language: $language)
            package { technicalName clearName }
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
          title seasonNumber episodeNumber shortDescription runtime ageCertification
        }
        offers(country: $country, platform: WEB,
          filter: {packages: [$provider], monetizationTypes: [FREE], bestOnly: true}) {
          id streamUrlExternalPlayer streamUrl monetizationType
          audioLanguages(language: $language)
          package { clearName shortName technicalName }
        }
      }
    }
  }
}
"""


TITLE_OFFERS_QUERY = """
query GetTitleOffers($fullPath: String!, $country: Country!, $language: Language!) {
  urlV2(fullPath: $fullPath, site: "www") {
    node {
      __typename id
      ... on Movie {
        offers(country: $country, platform: WEB) {
          id monetizationType streamUrlExternalPlayer streamUrl
          audioLanguages(language: $language)
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
    payload = json.dumps({
        "operationName": operation,
        "query": query,
        "variables": variables
    }, separators=(",", ":")).encode("utf-8")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.justwatch.com",
        "Referer": "https://www.justwatch.com/",
        "User-Agent": _UA,
    }

    try:
        response = multiquest.post(
            _API_ENDPOINT,
            data=payload,
            headers=headers,
            timeout=20
        )

        if response.status_code >= 400:
            log.log(
                '[JustWatch] API HTTP-Fehler %s bei %s' %
                (response.status_code, operation),
                log.LOGWARNING
            )
            return {}

        data = json.loads(response.text)

        if data.get("errors"):
            log.log(
                '[JustWatch] GraphQL-Fehler bei %s: %s' %
                (operation, data.get("errors")),
                log.LOGWARNING
            )

        return data.get("data") or {}

    except Exception as exc:
        log.log(
            '[JustWatch] API-Aufruf %s fehlgeschlagen: %s' %
            (operation, exc),
            log.LOGWARNING
        )
        return {}


def _api_context():
    return "DE", "de", "jwt"


def _has_german_audio(offer):
    """Prüft, ob JustWatch ausdrücklich Deutsch als Audiosprache meldet."""

    if not isinstance(offer, dict):
        return False

    languages = offer.get("audioLanguages") or []

    if not isinstance(languages, list):
        return False

    for language in languages:
        if not isinstance(language, str):
            continue

        code = language.strip().lower().replace("_", "-")

        if code == "de" or code.startswith("de-"):
            return True

    return False


def _is_free_german_offer(offer):
    if not isinstance(offer, dict):
        return False

    return (
        offer.get("monetizationType") == "FREE"
        and _has_german_audio(offer)
        and bool(offer.get("id"))
    )


def load(url='', params=None):
    if url:
        return showEntries(url, params)

    return [
        {
            'title': 'Beliebte kostenlose Titel',
            'url': 'list',
            'is_playable': False,
            'next_func': 'showEntries'
        },
        {
            'title': 'Filme',
            'url': 'movies',
            'is_playable': False,
            'next_func': 'showEntries'
        },
        {
            'title': 'Serien',
            'url': 'series',
            'is_playable': False,
            'next_func': 'showEntries'
        },
        {
            'title': 'Suche',
            'url': 'search',
            'is_playable': False,
            'next_func': 'search'
        },
    ]


def showEntries(url='', params=None):
    if not url or url == 'list':
        return _list_catalog(object_type='')

    if url == 'movies':
        return _list_catalog(object_type='MOVIE')

    if url == 'series':
        return _list_catalog(object_type='SHOW')

    if url.startswith('more:'):
        parts = url[5:].split('||', 2)

        offset = int(parts[0]) if parts and parts[0] else 0
        object_type = parts[1] if len(parts) > 1 else ""
        search_text = parts[2] if len(parts) > 2 else ""

        return _list_catalog(
            search_text=search_text,
            offset=offset,
            object_type=object_type
        )

    if url.startswith('seasons:'):
        parts = url[8:].split('||', 1)

        fullpath = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else ""

        return _show_seasons(fullpath, title)

    if url.startswith('episodes:'):
        parts = url[9:].split('||', 1)

        season_id = parts[0] if parts else ""
        show_title = parts[1] if len(parts) > 1 else ""

        return _season_episodes(season_id, show_title)

    return []


def _list_catalog(search_text="", offset=0, object_type=""):
    country, language, provider = _api_context()

    size = 30

    filter_value = {
        "packages": [provider],
        "monetizationTypes": ["FREE"],
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

    watch_filter = {
        "packages": [provider],
        "monetizationTypes": ["FREE"]
    }

    variables = {
        "country": country,
        "language": language,
        "first": size,
        "offset": offset,
        "popularTitlesFilter": filter_value,
        "watchNowFilter": watch_filter,
    }

    result = _api_call(
        "GetPopularTitles",
        POPULAR_QUERY,
        variables
    )

    listing = result.get("popularTitles") or {}
    items = []

    for edge in listing.get("edges") or []:
        node = (edge or {}).get("node") or {}
        content = node.get("content") or {}
        offer = node.get("watchNowOffer") or {}

        if not _is_free_german_offer(offer):
            continue

        title = content.get("title") or "Unbenannter Titel"
        year = content.get("originalReleaseYear")
        age_cert = content.get("ageCertification") or ""

        show = (
            node.get("__typename") == "Show"
            or node.get("objectType") == "SHOW"
        )

        label = "%s (%s)" % (title, year) if year else title
        poster = content.get("posterUrl") or ""

        item = {
            'title': label,
            'poster': poster,
            'fanart': poster,
            'year': str(year) if year else '',
            'plot': '',
            'mediatype': 'tvshow' if show else 'movie',
        }

        if age_cert:
            item['mpaa'] = age_cert
            item['certification'] = age_cert

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
                'url': 'offer:%s||%s||%s||%s' % (
                    offer_id, fullpath, title, age_cert
                ),
                'is_playable': True,
                'next_func': 'get_hosters',
            })

        items.append(item)

    if listing.get("pageInfo", {}).get("hasNextPage"):
        items.append({
            'title': 'Weitere Ergebnisse …',
            'url': 'more:%d||%s||%s' % (
                offset + size, object_type, search_text
            ),
            'is_playable': False,
            'next_func': 'showEntries',
        })

    return items


def _show_seasons(fullpath, show_title):
    country, language, provider = _api_context()

    data = _api_call(
        "GetShowSeasons",
        SHOW_SEASONS_QUERY,
        {
            "fullPath": fullpath,
            "country": country,
            "language": language,
            "provider": provider,
        }
    )

    node = ((data.get("urlV2") or {}).get("node") or {})
    seasons = node.get("seasons") or []

    items = []

    for season in seasons:
        offers = season.get("offers") or []

        if not any(
            _is_free_german_offer(offer)
            for offer in offers
        ):
            continue

        content = season.get("content") or {}
        number = content.get("seasonNumber")

        label = content.get("title") or (
            "Staffel %s" % number if number else "Staffel"
        )

        poster = content.get("posterUrl") or ""
        age_cert = content.get("ageCertification") or ""

        item = {
            'title': label,
            'url': 'episodes:%s||%s' % (
                season.get("id", ""), show_title
            ),
            'poster': poster,
            'fanart': poster,
            'season': number or 0,
            'mediatype': 'season',
            'is_playable': False,
            'next_func': 'showEntries',
        }

        if age_cert:
            item['mpaa'] = age_cert
            item['certification'] = age_cert

        items.append(item)

    return items


def _season_episodes(season_id, show_title):
    country, language, provider = _api_context()

    result = _api_call(
        "GetSeasonEpisodes",
        SEASON_EPISODES_QUERY,
        {
            "seasonId": season_id,
            "country": country,
            "language": language,
            "provider": provider,
            "limit": 100,
        }
    )

    node = result.get("node") or {}
    episodes = node.get("episodes") or []

    items = []

    for episode in episodes:
        content = episode.get("content") or {}
        offers = episode.get("offers") or []

        german_offer = next(
            (
                offer for offer in offers
                if _is_free_german_offer(offer)
            ),
            None
        )

        if not german_offer:
            continue

        number = content.get("episodeNumber")

        label = (
            ("E%02d — " % number if isinstance(number, int) else "")
            + (content.get("title") or "Folge")
        )

        offer_id = german_offer.get("id", "")
        age_cert = content.get("ageCertification") or ""

        item = {
            'title': label,
            'url': 'offer:%s||||%s||%s' % (
                offer_id, label, age_cert
            ),
            'poster': content.get("posterUrl") or "",
            'season': content.get("seasonNumber") or 0,
            'episode': number or 0,
            'mediatype': 'episode',
            'plot': content.get("shortDescription") or "",
            'duration': content.get("runtime") or 0,
            'is_playable': True,
            'next_func': 'get_hosters',
        }

        if age_cert:
            item['mpaa'] = age_cert
            item['certification'] = age_cert

        items.append(item)

    return items


def search(query='', params=None, url=''):
    if not query:
        try:
            import xbmcgui

            query = xbmcgui.Dialog().input(
                'JustWatch Suche',
                type=xbmcgui.INPUT_ALPHANUM
            )
        except Exception:
            pass

    if not query:
        return []

    return _list_catalog(search_text=query)


def get_hosters(
    title='', year='', season=0, episode=0,
    imdb='', tmdb='', url='', params=None
):
    if not url:
        return []

    offer_id = ""
    fullpath = ""
    fsk = ""

    if url.startswith('offer:'):
        parts = url[6:].split('||')

        offer_id = parts[0] if len(parts) > 0 else ""

        if len(parts) > 1 and parts[1]:
            fullpath = parts[1]
            fsk = parts[3] if len(parts) > 3 else ""

        else:
            fullpath = ""
            fsk = parts[4] if len(parts) > 4 else ""

    if fsk:
        fsk_clean = str(fsk).replace("FSK", "").strip()
        current_hour = time.localtime().tm_hour

        if fsk_clean == "16" and 6 <= current_hour < 22:
            raise Exception(
                "FSK 16: Inhalt ist erst ab 22:00 Uhr abspielbar "
                "(Jugendschutz)."
            )

        if fsk_clean == "18" and 6 <= current_hour < 23:
            raise Exception(
                "FSK 18: Inhalt ist erst ab 23:00 Uhr abspielbar "
                "(Jugendschutz)."
            )

    country, language, provider = _api_context()

    if fullpath:
        data = _api_call(
            "GetTitleOffers",
            TITLE_OFFERS_QUERY,
            {
                "fullPath": fullpath,
                "country": country,
                "language": language,
            }
        )

        node = ((data.get("urlV2") or {}).get("node") or {})
        offers = node.get("offers") or []

        german_offers = [
            offer for offer in offers
            if _is_free_german_offer(offer)
        ]

        matching_offer = next(
            (
                offer for offer in german_offers
                if offer.get("id") == offer_id
            ),
            None
        )

        if matching_offer:
            offer_id = matching_offer.get("id", "")

        elif german_offers:
            offer_id = german_offers[0].get("id", "")

        else:
            raise Exception(
                "Keine kostenlose deutsche Tonspur verfügbar."
            )

    if not offer_id:
        raise Exception(
            "Kein überprüftes deutsches Angebot gefunden."
        )

    for variant in (
        {"drmType": "widevine", "deviceOs": "android"},
        {"drmType": "playready", "deviceOs": "windows"},
        {"deviceOs": "windows"},
    ):
        play_input = {"offerId": offer_id}
        play_input.update(variant)

        res = _api_call(
            "GetPlayInformation",
            PLAY_INFORMATION_QUERY,
            {"input": play_input}
        )

        info = res.get("getPlayInformation") or {}
        err_code = info.get("errorCode")

        if err_code:
            log.log(
                '[JustWatch] GetPlayInformation error code: %s'
                % err_code,
                log.LOGWARNING
            )

            if (
                'AGE' in str(err_code).upper()
                or 'PARENTAL' in str(err_code).upper()
                or 'CERTIFICATION' in str(err_code).upper()
                or 'RESTRICTION' in str(err_code).upper()
            ):
                raise Exception(
                    "Jugendschutz greift: Inhalt ist "
                    "altersbeschränkt und derzeit gesperrt."
                )

            continue

        offer_data = info.get("offer") or {}

        direct_offer_url = (
            offer_data.get("streamUrlExternalPlayer")
            or offer_data.get("streamUrl")
            or ""
        )

        if (
            direct_offer_url
            and isinstance(direct_offer_url, str)
            and direct_offer_url.startswith("https://")
        ):
            return [
                ('JustWatch', direct_offer_url, True, 'HD', 'de')
            ]

        streams = info.get("streams") or []

        for stream in streams:
            stream_url = stream.get("url") or ""
            drm = str(stream.get("drmType") or "").lower()

            if stream_url and drm in ("", "none", "null"):
                return [
                    ('JustWatch', stream_url, True, 'HD', 'de')
                ]

            manifest = stream.get("manifestUrlDash") or ""
            configs = stream.get("drmConfigs") or []

            widevine_url = next(
                (
                    config.get("laURL")
                    for config in configs
                    if str(config.get("drmType")).lower() == "widevine"
                    and config.get("laURL")
                ),
                ""
            )

            if manifest and widevine_url:
                ua = (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"
                )

                hdr = "Origin=%s&Referer=%s&User-Agent=%s" % (
                    urllib.parse.quote(
                        "https://www.justwatch.com"
                    ),
                    urllib.parse.quote(
                        "https://www.justwatch.com/"
                    ),
                    urllib.parse.quote(ua)
                )

                drm_info = {
                    'drm_type': 'widevine',
                    'drm_license': widevine_url,
                    'drm_headers': hdr,
                    'manifest_headers': hdr,
                }

                return [
                    ('JustWatch DRM', manifest, drm_info)
                ]

    return []
