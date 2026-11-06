import json
import os
import re
import time
import threading

from resources.lib import multiquest

VAVOO_UA = 'MediaHubMX/2'             # Kennung der Vavoo-App-Schnittstelle (signierte Anfragen)
_OLD_UA  = 'TiviMate/5.0.0 (Linux; Google TV)'   # nur noch für den Notfall ohne Signatur
_PING_URL = os.environ.get('VAVOO_PING') or 'https://www.vavoo.tv/api/app/ping'
_APP_VERSION = '4.2.2'
_APP_PACKAGE = 'tv.vavoo.app'
_PING_UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) vavoo/4.2.2 '
            'Chrome/146.0.7680.166 Electron/41.1.0 Safari/537.36')
_SIG_TTL = 840                          # Signatur ~14 min gültig
_SIG = {'v': '', 'ts': 0.0, 'err': ''}
_SIG_LOCK = threading.Lock()

BUNDLES = [
    ('vavoo.to',  'https://vavoo.to'),
    ('vavoo.net', 'https://vavoo.net'),
    ('vavoo.top', 'https://vavoo.top'),
    ('kool.to',   'https://kool.to'),
    ('oha.to',    'https://oha.to'),
    ('huhu.to',   'https://huhu.to'),
]

_KNOWN_PORTALS = {
    'oha.to':    {'prefix': '/mediaurl-',   'region': 'DE', 'discovery': '/mediaurl.json'},
    'huhu.to':   {'prefix': '/mediaurl-',   'region': 'DE', 'discovery': '/mediaurl.json'},
    'kool.to':   {'prefix': '/mediahubmx-', 'region': 'AT', 'discovery': '/mediahubmx.json'},
    'vavoo.to':  {'prefix': '/mediahubmx-', 'region': 'XX', 'discovery': '/mediahubmx.json'},
    'vavoo.top': {'prefix': '/mediahubmx-', 'region': 'XX', 'discovery': '/mediahubmx.json'},
    'vavoo.net': {'prefix': '/mediahubmx-', 'region': 'XX', 'discovery': '/mediahubmx.json'},
}

_HEADERS = {
    'User-Agent': VAVOO_UA,
    'Accept': 'application/json',
    'Accept-Charset': 'UTF-8',
    'Content-Type': 'application/json',
}


def _profile_dir():
    try:
        from resources.lib.control import addonProfile
        d = addonProfile()
        return d if d and os.path.isdir(d) else ''
    except Exception:
        return ''


def _device_id():
    d = _profile_dir()
    f = os.path.join(d, '.vavoo_device_id') if d else ''
    try:
        if f and os.path.isfile(f):
            cached = open(f).read().strip()
            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', cached, re.I):
                return cached
    except Exception:
        pass
    b = bytearray(os.urandom(16))
    b[6] = (b[6] & 0x0f) | 0x40
    b[8] = (b[8] & 0x3f) | 0x80
    h = b.hex()
    uid = '%s-%s-%s-%s-%s' % (h[0:8], h[8:12], h[12:16], h[16:20], h[20:32])
    try:
        if f:
            open(f, 'w').write(uid + '\n')
    except Exception:
        pass
    return uid


def get_signature(force=False, timeout=10):
    """Signatur der Vavoo-App ("addonSig"): Ohne sie liefern die Portale keine Senderliste mehr.
    Wird über den Ping der App geholt und ~14 min gemerkt (Speicher + Datei). Leer, wenn der Ping scheitert (Grund in last_signature_error())."""
    with _SIG_LOCK:
        if not force and _SIG['v'] and time.time() - _SIG['ts'] < _SIG_TTL:
            return _SIG['v']
    d = _profile_dir()
    cache = os.path.join(d, '.vavoo_sig_cache') if d else ''
    if not force and cache:
        try:
            if os.path.isfile(cache) and time.time() - os.path.getmtime(cache) < _SIG_TTL:
                v = open(cache).read().strip()
                if v:
                    with _SIG_LOCK:
                        _SIG.update(v=v, ts=os.path.getmtime(cache), err='')
                    return v
        except Exception:
            pass
    ts = int(time.time() * 1000)
    uid = _device_id()
    headers = {'User-Agent': _PING_UA, 'Accept': '*/*', 'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
               'Origin': 'https://vavoo.to', 'Referer': 'https://vavoo.to/', 'Connection': 'keep-alive',
               'Content-Type': 'application/json'}
    data = {
        'reason': 'app-focus', 'locale': 'de', 'theme': 'dark',
        'metadata': {'device': {'type': 'desktop', 'uniqueId': uid},
                     'os': {'name': 'linux', 'version': 'x86_64', 'abis': ['x64'], 'host': 'localhost'},
                     'app': {'platform': 'electron'},
                     'version': {'package': _APP_PACKAGE, 'binary': _APP_VERSION, 'js': _APP_VERSION}},
        'appFocusTime': 0, 'playerActive': False, 'playDuration': 0, 'devMode': False, 'hasAddon': True,
        'castConnected': False, 'package': _APP_PACKAGE, 'version': _APP_VERSION, 'process': 'app',
        'firstAppStart': ts, 'lastAppStart': ts, 'ipLocation': None, 'adblockEnabled': True,
        'proxy': {'supported': ['ss'], 'engine': 'Mu', 'enabled': False, 'autoServer': True},
        'iap': {'supported': False},
    }
    err = ''
    try:
        r = multiquest.post(_PING_URL, json=data, headers=headers, timeout=timeout)
        r.raise_for_status()
        sig = (r.json() or {}).get('addonSig', '')
        if sig:
            with _SIG_LOCK:
                _SIG.update(v=sig, ts=time.time(), err='')
            try:
                if cache:
                    open(cache, 'w').write(sig)
            except Exception:
                pass
            return sig
        err = 'Ping ohne Signatur'
    except Exception as e:
        err = '%s: %s' % (type(e).__name__, str(e)[:80])
    with _SIG_LOCK:
        _SIG['err'] = err
        if _SIG['v']:
            return _SIG['v']               # abgelaufene Signatur ist besser als keine
    return ''


def last_signature_error():
    return _SIG['err']


def _normalise_url(url):
    url = url.strip().rstrip('/')
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def _detect_portal(base_url, timeout):
    for domain, cfg in _KNOWN_PORTALS.items():
        if domain in base_url:
            return cfg['prefix'], cfg['region'], cfg['discovery']
    for discovery, prefix, region in [
        ('/mediaurl.json',   '/mediaurl-',   'DE'),
        ('/mediahubmx.json', '/mediahubmx-', 'DE'),
    ]:
        try:
            r = multiquest.post(
                base_url + discovery,
                data='{}',
                headers=_HEADERS,
                timeout=timeout,
            )
            if r.status_code == 200 and 'catalogs' in r.text:
                return prefix, region, discovery
        except Exception:
            pass
    return '/mediaurl-', 'DE', '/mediaurl.json'


class VavooClient:
    def __init__(self, portal_url, timeout=20):
        self._base = _normalise_url(portal_url)
        self._timeout = timeout
        self._prefix, self._region, self._discovery = _detect_portal(self._base, timeout)
        self._signed = True            # nach dem ersten Erfolg: so hat das Portal geantwortet
        self._sort = 'trending-region'
        self.last_error = ''

    def _path(self, name):
        return self._base + self._prefix + name + '.json'

    def _headers(self, signed=None):
        signed = self._signed if signed is None else signed
        h = dict(_HEADERS)
        sig = get_signature() if signed else ''
        if sig:
            h['mediahubmx-signature'] = sig
        elif signed:
            h['User-Agent'] = _OLD_UA     # keine Signatur erhalten: alte Anfrage-Form als letzter Versuch
        return h

    def _post(self, url, payload, signed=None):
        url_t = url + '?_t=%d' % int(time.time() * 1000)
        body = json.dumps(payload, separators=(',', ':'))
        hdrs = self._headers(signed)
        r = multiquest.post(url_t, data=body, headers=hdrs, timeout=self._timeout)
        if r.status_code in (401, 403) and hdrs.get('mediahubmx-signature'):      # Signatur abgelaufen/ersetzt: einmal neu holen
            fresh = get_signature(force=True)
            if fresh and fresh != hdrs['mediahubmx-signature']:
                hdrs['mediahubmx-signature'] = fresh
                r = multiquest.post(url_t, data=body, headers=hdrs, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def _build_payload(self, cursor=None, adult=True, region=None, sort=None):
        return {
            'language': 'de', 'region': region or self._region,
            'catalogId': 'iptv', 'id': '',
            'adult': adult, 'search': '',
            'sort': sort or self._sort,
            'filter': {}, 'cursor': cursor,
            'clientVersion': '3.1.0',
        }

    def test_connection(self):
        data = self._post(self._path('catalog'), self._build_payload())
        return isinstance(data, dict) and 'items' in data

    def _fetch_all(self, adult, signed, region, sort, budget, progress_callback=None):
        """Alle Katalogseiten eines Versuchs (Seiten laufen nacheinander, mehrere Versuche siehe get_all_channels)."""
        pages = {}
        lock = threading.Lock()
        threads = []
        total_count = [0]
        errors = []

        def fetch_page(cursor, slot):
            try:
                data = self._post(self._path('catalog'), self._build_payload(cursor=cursor, adult=adult, region=region, sort=sort), signed=signed)
                if not isinstance(data, dict) or 'items' not in data:
                    raise ValueError('Antwort ohne Senderliste: %s' % str(data)[:80])
                items = list(data.get('items') or [])
                next_c = data.get('nextCursor')
            except Exception as e:
                items = []
                next_c = None
                with lock:
                    errors.append('%s: %s' % (type(e).__name__, str(e)[:100]))
            with lock:
                pages[slot] = items
                total_count[0] += len(items)
                if next_c:
                    t = threading.Thread(target=fetch_page, args=(next_c, slot + 1))
                    t.daemon = True
                    threads.append(t)
                    t.start()

        t0 = threading.Thread(target=fetch_page, args=(None, 0))
        t0.daemon = True
        threads.append(t0)
        t0.start()

        deadline = time.time() + budget
        while True:
            with lock:
                alive = [t for t in threads if t.is_alive()]
                current_total = total_count[0]
            if progress_callback:
                try:
                    progress_callback(current_total, bool(alive))
                except Exception:
                    pass
            if not alive or time.time() > deadline:
                break
            time.sleep(0.3)
        channels = []
        with lock:
            for slot in sorted(pages):
                channels.extend(pages[slot])
            err = errors[0] if errors else ''
        return channels, err

    def get_all_channels(self, adult=True, progress_callback=None):
        """Holt die Senderliste. Vavoo verlangt inzwischen die App-Signatur; scheitert die erste Form, werden andere
        probiert (Region DE, Sortierung nach Name, ohne Signatur). Die erste, die Sender liefert, wird für Auflösen gemerkt."""
        sig = get_signature()
        tries = []
        for signed, region, sort in ((True, self._region, 'trending-region'), (True, 'DE', 'name'),
                                     (True, self._region, 'name'), (False, self._region, 'trending-region')):
            if (signed, region, sort) not in tries:
                tries.append((signed, region, sort))
        started = time.time()
        first_err = ''
        for i, (signed, region, sort) in enumerate(tries):
            left = self._timeout * 2.2 - (time.time() - started)
            if i and left < 3:
                break
            channels, err = self._fetch_all(adult, signed, region, sort, min(self._timeout, max(3, left)), progress_callback)
            first_err = first_err or err
            if channels:
                self._signed, self._region, self._sort = signed, region, sort
                self.last_error = ''
                return channels
            if not signed and not first_err:
                first_err = 'Portal liefert eine leere Liste'
        if not sig:
            first_err = ('Keine Vavoo-Signatur (%s)' % (last_signature_error() or 'unbekannt')) + ('; ' + first_err if first_err else '')
        self.last_error = first_err or 'Portal liefert keine Sender'
        return []

    def _resolve_task_request(self, task_id, task_data):
        fetch_url = task_data.get('url', '')
        params = task_data.get('params', {})
        method = params.get('method', 'GET').upper()
        headers = params.get('headers', {})
        try:
            if method == 'POST':
                r = multiquest.post(fetch_url, headers=headers, timeout=self._timeout)
            else:
                r = multiquest.get(fetch_url, headers=headers, timeout=self._timeout)
            response_payload = {
                'kind': 'taskResponse',
                'id': task_id,
                'data': {'text': r.text, 'status': r.status_code},
            }
        except Exception as e:
            response_payload = {
                'kind': 'taskResponse',
                'id': task_id,
                'data': {'error': str(e)},
            }
        return self._post(self._path('resolve'), response_payload)

    def resolve_stream_url(self, play_url):
        payload = {
            'language': 'de',
            'region': self._region,
            'url': play_url,
            'clientVersion': '3.1.0',
        }
        data = self._post(self._path('resolve'), payload)
        for _ in range(5):
            if isinstance(data, list) and data:
                return data[0].get('url', '')
            if isinstance(data, dict) and data.get('url'):
                return data['url']
            if isinstance(data, dict) and data.get('kind') == 'taskRequest':
                task_id = data.get('id', '')
                task_data = data.get('data', {})
                data = self._resolve_task_request(task_id, task_data)
                continue
            break
        raise ValueError('Vavoo resolve fehlgeschlagen für %s' % play_url)
