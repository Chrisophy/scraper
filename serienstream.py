# -*- coding: utf-8 -*-
import os
import re
import json
import threading
import base64
import hashlib
import struct
import time
from html import unescape as _html_unescape
from urllib.parse import quote, urljoin, urlparse
from resources.lib import multiquest, log

SITE_ID       = 'serienstream'
SITE_NAME     = 'SerienStream'
SITE_DOMAIN   = 'serienstream.to'
TYPE          = 'series'
GLOBAL_SEARCH = True

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
_LANG_MAP = {'1': 'DE', '2': 'EN', '3': 'DE+SUB', '4': 'EN+SUB'}

_S_SEASONS  = '__ss_seasons__:'
_S_EPS      = '__ss_eps__:'
_S_GENRES   = '__ss_genres__'
_S_SAMML    = '__ss_samml__'
_S_KALENDER = '__ss_kalender__'
_S_AZ       = '__ss_az__'
_S_NEUESTE  = '__ss_neueste__'
_S_TREND    = '__ss_trend__'
_S_WEEKLY   = '__ss_weekly__'
_S_TOPRATED = '__ss_toprated__'
_S_SEARCH   = '__ss_search__'

_HOME_SECTION_URLS = {
    1: ['/gerade-im-trend', '/trending-serien'],
    2: ['/woechentliche-favoriten', '/weekly-favorites'],
    3: ['/meistbewertete-serien', '/top-serien'],
}


def _base():
    return 'https://' + SITE_DOMAIN


def _log(msg, level=None):
    try:
        if level is None:
            log.log('[serienstream] ' + msg)
        else:
            log.log('[serienstream] ' + msg, level)
    except Exception:
        pass


def _err(msg):
    _log(msg, getattr(log, 'LOGERROR', None))


def _get(url, referer=None):
    headers = {'User-Agent': _UA, 'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'}
    if referer:
        headers['Referer'] = referer
    last = None
    for attempt, tmo in enumerate((12, 25), 1):
        try:
            r = multiquest.get(url, headers=headers, timeout=tmo)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
    _err('_get fehlgeschlagen url=%s error=%s' % (url, last))
    return ''


def _cleantitle(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def _follow_redirect(url, referer=''):
    try:
        headers = {'User-Agent': _UA, 'Referer': referer or _base() + '/'}
        r = multiquest.get(url, headers=headers, timeout=15, allow_redirects=True)
        return r.url if r.url != url else url
    except Exception as e:
        _err('_follow_redirect fehlgeschlagen url=%s error=%s' % (url, e))
        return url


# ---------------------------------------------------------------------------
# Hoster-Weiterleitung /r?t=... : seit 09/2026 steht dort ein Altcha-Gate
# (Proof-of-Work, kostenlos, rechnet der Scraper selbst). Ablauf wie im Widget:
# Challenge holen -> rechnen -> als Formularfeld "altcha" abschicken -> Weiterleitung
# auf den echten Hoster.
# ---------------------------------------------------------------------------
_ALTCHA_TIME_LIMIT = 30
_V1_DIGESTS = {'SHA-1': 'sha1', 'SHA-256': 'sha256', 'SHA-384': 'sha384', 'SHA-512': 'sha512'}
_V2_DIGESTS = {'SHA-256': 'sha256', 'SHA-384': 'sha384', 'SHA-512': 'sha512',
               'PBKDF2/SHA-256': 'sha256', 'PBKDF2/SHA-384': 'sha384', 'PBKDF2/SHA-512': 'sha512'}


def _altcha_v1(ch):
    algo = str(ch.get('algorithm', '')).upper()
    challenge = str(ch.get('challenge', '')).lower()
    salt = str(ch.get('salt', ''))
    sig = str(ch.get('signature', ''))
    fn = getattr(hashlib, _V1_DIGESTS.get(algo, ''), None)
    if fn is None or not (challenge and salt):
        _err('Altcha v1: unbekannte Challenge-Form (%s)' % algo)
        return ''
    try:
        max_n = int(ch.get('maxnumber') or 1000000)
    except (TypeError, ValueError):
        max_n = 1000000
    t0 = time.time()
    sb = salt.encode('utf-8')
    for n in range(max_n + 1):
        if fn(sb + str(n).encode('utf-8')).hexdigest() == challenge:
            payload = {'algorithm': ch.get('algorithm'), 'challenge': ch.get('challenge'),
                       'number': n, 'salt': salt, 'signature': sig, 'took': int((time.time() - t0) * 1000)}
            return base64.b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8')).decode('ascii')
        if n % 10000 == 0 and time.time() - t0 > _ALTCHA_TIME_LIMIT:
            _err('Altcha: Zeitgrenze erreicht bei %d' % n)
            return ''
    _err('Altcha: keine Lösung bis %d' % max_n)
    return ''


def _altcha_v2(ch):
    params = ch['parameters']
    algo = str(params.get('algorithm', ''))
    for extra in ('his', 'codeChallenge'):
        if extra in ch or extra in params:
            _err('Altcha v2: Zusatzprüfung %s nicht unterstützt' % extra)
            return ''
    digest = _V2_DIGESTS.get(algo)
    if not digest:
        _err('Altcha v2: unbekannte Rechenart %s' % algo)
        return ''
    try:
        nonce = bytes.fromhex(str(params.get('nonce', '')))
        salt = bytes.fromhex(str(params.get('salt', '')))
        cost = int(params.get('cost'))
        klen = int(params.get('keyLength') or 32)
        prefix = str(params.get('keyPrefix', '')).lower()
    except (TypeError, ValueError):
        _err('Altcha v2: Challenge unvollständig')
        return ''
    if not (nonce and salt and cost > 0 and klen > 0 and prefix and re.match(r'^[0-9a-f]+$', prefix)):
        _err('Altcha v2: Challenge unvollständig')
        return ''
    pbkdf2 = algo.startswith('PBKDF2/')

    def derive(pw):
        if pbkdf2:
            return hashlib.pbkdf2_hmac(digest, pw, salt, cost, klen)
        data = salt + pw
        for _ in range(cost):
            data = hashlib.new(digest, data).digest()
        return data[:klen]

    t0 = time.time()
    counter = 0
    while True:
        key = derive(nonce + struct.pack('>I', counter)).hex()
        if key.startswith(prefix):
            break
        counter += 1
        if counter % 16 == 0 and time.time() - t0 > _ALTCHA_TIME_LIMIT:
            _err('Altcha v2: Zeitgrenze erreicht')
            return ''
    payload = {'challenge': {'parameters': params, 'signature': ch.get('signature')},
               'solution': {'counter': counter, 'derivedKey': key, 'time': int((time.time() - t0) * 1000)}}
    return base64.b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8')).decode('ascii')


def _tag_attr(tag, *names):
    for name in names:
        m = re.search(r'(?<![\w-])%s\s*=\s*(?:"([^"]*)"|\'([^\']*)\')' % re.escape(name), tag, re.I)
        if m:
            return _html_unescape(m.group(1) if m.group(1) is not None else m.group(2))
    return ''


def _redirect_in_html(html, base_url):
    """Weiterleitungsziel im HTML (meta refresh, JS, atob, Link/iframe), falls vorhanden.

    Es zählt nur ein Ziel außerhalb der eigenen Domain."""
    own = urlparse(_base()).netloc
    cands = []
    # 1) meta refresh (beide Attribut-Reihenfolgen, Anführungszeichen optional)
    for mm in re.finditer(r'<meta\b[^>]*>', html, re.I):
        tag = mm.group(0)
        if re.search(r'http-equiv\s*=\s*["\']?refresh', tag, re.I):
            cm = re.search(r'url\s*=\s*["\']?([^"\'>\s;]+)', _tag_attr(tag, 'content'), re.I)
            if cm:
                cands.append(cm.group(1))
    # 2) JavaScript-Weiterleitung
    for jm in re.finditer(r'(?:location(?:\.href|\.replace|\.assign)?)\s*(?:=|\()\s*([\'"`])(.*?)\1', html, re.S):
        cands.append(jm.group(2))
    # 3) base64 in atob("...")
    for am in re.finditer(r'atob\(\s*[\'"]([A-Za-z0-9+/=_-]{8,})[\'"]\s*\)', html):
        try:
            raw = am.group(1).replace('-', '+').replace('_', '/')
            cands.append(base64.b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8', 'ignore'))
        except Exception:
            pass
    # 4) Link / iframe / data-Attribute mit absoluter Adresse
    for lm in re.finditer(r'(?:href|src|data-url|data-href|data-target)\s*=\s*["\'](https?://[^"\']+)["\']', html, re.I):
        cands.append(lm.group(1))
    for c in cands:
        c = _html_unescape((c or '').strip()).replace('\\/', '/')
        if not c or c.startswith(('javascript:', '#', 'data:')):
            continue
        full = urljoin(base_url, c)
        pu = urlparse(full)
        if pu.scheme in ('http', 'https') and pu.netloc and pu.netloc != own:
            return full
    return ''


# ---------------------------------------------------------------------------
# Hoster-Weiterleitung /r?t=... – so läuft sie im Browser (aus dem JavaScript der
# Episodenseite, episode-redirect-gate-*.js):
#   1. Der Hoster-Button lädt /r?t=TOKEN in einen iframe.
#   2. Die Seite im iframe ist nur eine "frameBridge": sie meldet das Token per
#      postMessage an die Elternseite.
#   3. Die Elternseite öffnet ein Formular (#player-prepare-form) mit dem Token als
#      verstecktem Feld. Je nach "Stufe" (data-redirect-gate-tier) kommen dazu:
#      Cloudflare Turnstile (cf-turnstile-response) und/oder Altcha (Feld "altcha").
#   4. Das Formular wird abgeschickt, der Server leitet auf den echten Hoster weiter.
# Genau das macht _EpisodeGate hier nach.
# ---------------------------------------------------------------------------
try:
    from resources.lib.captcha.captcha_helper import solve_recaptcha as _solve_captcha
except Exception:
    _solve_captcha = None
try:
    from resources.lib.captcha.captcha_helper import get_last_error as _captcha_last_error
except Exception:
    def _captcha_last_error():
        return ''


def _gate_diagnose(html, page_url):
    forms = []
    for fm in re.finditer(r'<form\b[^>]*>', html, re.I):
        forms.append('%s %s' % (_tag_attr(fm.group(0), 'method') or 'GET', _tag_attr(fm.group(0), 'action') or '(leer)'))
    widgets = re.findall(r'<altcha-widget\b[^>]*>', html, re.I)
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
    text = re.sub(r'\s+', ' ', re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S | re.I))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    raw = re.sub(r'\s+', ' ', html)[:1500 if len(html) <= 2000 else 700]
    _log('Gate-Diagnose url=%s len=%d forms=%s widgets=%s scripts=%s text=%s' % (
        page_url[:80], len(html), forms[:3], [w[:200] for w in widgets[:2]], scripts[:4], text[:200]),
        getattr(log, 'LOGWARNING', None))
    _log('Gate-HTML: %s' % raw, getattr(log, 'LOGWARNING', None))


# ---------------------------------------------------------------------------
# Einstellungen und Anmeldung (serienstream.user / serienstream.pass)
# ---------------------------------------------------------------------------
_VERSION = '2026-10-27-d (Hoster werden nicht geöffnet)'
_LOGIN_FILE = 'serienstream_login.json'


def _file_setting(key):
    """Zugangsdaten aus serienstream_login.json (neben dieser Datei): {"user": "...", "pass": "..."}."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _LOGIN_FILE)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            return str(data.get(key.split('.')[-1], '') or '')
    except Exception as e:
        _err('%s nicht lesbar: %s' % (_LOGIN_FILE, e))
    return ''


def _setting(key):
    """Wert lesen: 1. Datei serienstream_login.json, 2. Kodi-Einstellung, 3. Umgebungsvariable MOVIESCOUT_<KEY>."""
    val = _file_setting(key)
    if not val.strip() or val.strip().lower().startswith('hier '):
        val = ''
        try:
            import xbmcaddon
            val = xbmcaddon.Addon().getSetting(key) or ''
        except Exception:
            val = ''
    if not str(val).strip():
        val = os.environ.get('MOVIESCOUT_' + re.sub(r'[^A-Z0-9]', '_', key.upper()), '')
    val = str(val or '').strip()
    if val.lower().startswith('hier '):       # Platzhalter-Text der Einstellungen
        return ''
    return val


def _sreq(sess, method, url, **kw):
    """Anfrage über die Sitzung; Schlüsselwörter, die multiquest nicht kennt, fallen schrittweise weg."""
    fn = getattr(sess, method)
    drop = ['allow_redirects', 'headers', 'params', 'timeout']
    kw = dict(kw)
    while True:
        try:
            return fn(url, **kw)
        except TypeError:
            while drop and drop[0] not in kw:
                drop.pop(0)
            if not drop:
                raise
            kw.pop(drop.pop(0), None)


def _loc(resp, base_url):
    try:
        if int(getattr(resp, 'status_code', 0) or 0) in (301, 302, 303, 307, 308):
            h = getattr(resp, 'headers', None) or {}
            loc = h.get('location') or h.get('Location') or ''
            if loc:
                return urljoin(base_url, loc)
    except Exception:
        pass
    return ''


def _fetch(sess, url, headers=None, hops=5):
    """GET mit manuell verfolgten Weiterleitungen. Gibt (Antwort, endgültige URL) zurück."""
    cur = url
    resp = None
    for _ in range(hops):
        resp = _sreq(sess, 'get', cur, timeout=20, headers=headers or {}, allow_redirects=False)
        nxt = _loc(resp, cur)
        if not nxt:
            return resp, (getattr(resp, 'url', None) or cur)
        if urlparse(nxt).netloc not in ('', urlparse(_base()).netloc):
            return resp, nxt            # fremder Host (Hoster): nicht öffnen, Adresse zurückgeben
        cur = nxt
    return resp, cur


def _form_inputs(form_html):
    fields, types = {}, {}
    for im in re.finditer(r'<input\b[^>]*>', form_html, re.I):
        tag = im.group(0)
        name = _tag_attr(tag, 'name')
        if name:
            fields[name] = _tag_attr(tag, 'value')
            types[name] = (_tag_attr(tag, 'type') or 'text').lower()
    return fields, types


def _login(sess, user, pw):
    """Meldet sich bei SerienStream an. True bei Erfolg (Details im Log)."""
    warn = getattr(log, 'LOGWARNING', None)
    try:
        home, _u = _fetch(sess, _base() + '/')
        hm = re.search(r'href=["\']([^"\']*(?:login|anmeld)[^"\']*)["\']', getattr(home, 'text', '') or '', re.I)
        cands = []
        if hm:
            cands.append(urljoin(_base() + '/', _html_unescape(hm.group(1))))
        for path in ('/login', '/anmelden'):
            if _base() + path not in cands:
                cands.append(_base() + path)
        page, page_url, form_html, form_tag = None, '', '', ''
        for c in cands:
            page, page_url = _fetch(sess, c)
            html = getattr(page, 'text', '') or ''
            for fm in re.finditer(r'(<form\b[^>]*>)(.*?)</form>', html, re.S | re.I):
                if re.search(r'type=["\']password["\']', fm.group(2), re.I):
                    form_tag, form_html = fm.group(1), fm.group(2)
                    break
            if form_html:
                break
        if not form_html:
            _err('Login: keine Anmeldeseite mit Passwortfeld gefunden (%s)' % ', '.join(cands))
            if page is not None:
                _gate_diagnose(getattr(page, 'text', '') or '', page_url)
            return False

        fields, types = _form_inputs(form_html)
        user_field = next((n for n, t in types.items() if t == 'email'), '') or \
            next((n for n in fields if re.search(r'mail|user|login|name', n, re.I) and types[n] != 'password'), '')
        pass_field = next((n for n, t in types.items() if t == 'password'), '')
        if not (user_field and pass_field):
            _err('Login: Felder nicht erkannt (felder=%s)' % sorted(fields))
            return False
        fields[user_field] = user
        fields[pass_field] = pw
        for n in list(fields):
            if re.search(r'remember|angemeldet', n, re.I) and types.get(n) == 'checkbox':
                fields[n] = fields[n] or 'on'
            elif types.get(n) == 'checkbox' and n not in (user_field, pass_field):
                fields.pop(n, None)

        # Hürden auf der Anmeldeseite (Turnstile / Altcha)
        sk = _tag_attr(form_html, 'data-sitekey')
        if sk and 'turnstile' in (page.text or '').lower():
            tok = _solve_captcha(sk, page_url, captcha_type='turnstile', use_cache=False) if _solve_captcha else ''
            if not tok:
                _err('Login: Turnstile verlangt, aber nicht lösbar (%s)' % (
                    _captcha_last_error() or 'kein Captcha-Dienst eingerichtet'))
                return False
            fields['cf-turnstile-response'] = tok
        wm = re.search(r'<altcha-widget\b[^>]*>', form_html, re.I)
        if wm:
            cu = _tag_attr(wm.group(0), 'challengeurl')
            if cu:
                cr, _x = _fetch(sess, urljoin(page_url, cu), headers={'Accept': 'application/json', 'Referer': page_url})
                try:
                    ch = json.loads(cr.text)
                except Exception:
                    ch = None
                ans = ''
                if isinstance(ch, dict):
                    ans = _altcha_v2(ch) if isinstance(ch.get('parameters'), dict) else _altcha_v1(ch)
                if ans:
                    fields[_tag_attr(wm.group(0), 'name') or 'altcha'] = ans

        action = urljoin(page_url, _tag_attr(form_tag, 'action') or page_url)
        hdrs = {'Referer': page_url, 'Origin': _base()}
        resp = _sreq(sess, 'post', action, data=fields, timeout=25, headers=hdrs, allow_redirects=False)
        final = getattr(resp, 'url', None) or action
        hops = 0
        while hops < 4 and _loc(resp, final):
            final = _loc(resp, final)
            resp, final = _fetch(sess, final, headers={'Referer': page_url}, hops=1)[0], final
            hops += 1

        # Erfolgskontrolle: Startseite laden, Abmelden-Link / kein Login-Formular?
        chk, _u = _fetch(sess, _base() + '/')
        low = (getattr(chk, 'text', '') or '').lower()
        ok = ('logout' in low or 'abmelden' in low) and 'type="password"' not in low
        if ok:
            _log('Login als %s erfolgreich' % (user if '@' not in user else user.split('@')[0] + '@…'))
            return True
        _err('Login fehlgeschlagen (HTTP %s) – E-Mail/Passwort prüfen oder Anmeldung verlangt eine weitere Hürde' %
             getattr(resp, 'status_code', '?'))
        _gate_diagnose(getattr(resp, 'text', '') or '', final)
        return False
    except Exception as e:
        _err('Login-Fehler: %s' % e)
        return False


_AUTH = {'sess': None, 'ts': 0.0, 'ok': False, 'creds': None}
_AUTH_LOCK = threading.Lock()


def _auth_session():
    """Gemeinsame Sitzung (Cookies); angemeldet, sobald serienstream.user/pass gesetzt sind."""
    with _AUTH_LOCK:
        now = time.time()
        age = now - _AUTH['ts']
        creds = (_setting('serienstream.user'), _setting('serienstream.pass'))
        if _AUTH['sess'] is not None and _AUTH['creds'] == creds and age < (6 * 3600 if _AUTH['ok'] else 600):
            return _AUTH['sess']
        try:
            if _AUTH['sess'] is not None:
                _AUTH['sess'].close()
        except Exception:
            pass
        sess = multiquest.Session(headers={
            'User-Agent': _UA, 'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8', 'Referer': _base() + '/'})
        user, pw = creds
        ok = False
        _log('Version %s' % _VERSION)
        if user and pw:
            ok = _login(sess, user, pw)
        else:
            _log('kein Account eingetragen (MovieScout → Einstellungen → SerienStream: E-Mail / Passwort)')
        _AUTH.update({'sess': sess, 'ts': now, 'ok': ok, 'creds': creds})
        return sess


class _EpisodeGate(object):
    """Ein Gate-Durchlauf je Episodenseite (gemeinsame, ggf. angemeldete Sitzung)."""

    def __init__(self, ep_url):
        self.ep_url = ep_url
        self.own = urlparse(_base()).netloc
        self.sess = _auth_session()
        self.fatal = ''
        self.html = ''
        try:
            r, _u = _fetch(self.sess, ep_url, headers={'Referer': _base() + '/'})
            self.html = getattr(r, 'text', '') or ''
        except Exception as e:
            _err('Gate: Episodenseite nicht ladbar: %s' % e)
        self._parse(self.html)

    def _parse(self, html):
        root = re.search(r'<[^>]+id=["\']episode-redirect-gate-root["\'][^>]*>', html, re.I)
        rtag = root.group(0) if root else ''
        self.tier = (_tag_attr(rtag, 'data-redirect-gate-tier') or 'none').lower()
        self.sitekey = _tag_attr(rtag, 'data-turnstile-sitekey')
        self.altcha_url = _tag_attr(rtag, 'data-altcha-challenge-url')
        fm = re.search(r'(<form\b[^>]*id=["\']player-prepare-form["\'][^>]*>)(.*?)</form>', html, re.S | re.I)
        ftag, fhtml = (fm.group(1), fm.group(2)) if fm else ('', '')
        self.action = _tag_attr(ftag, 'action')
        self.method = (_tag_attr(ftag, 'method') or 'post').lower()
        self.token_field = 't'
        self.fields = {}
        for im in re.finditer(r'<input\b[^>]*>', fhtml, re.I):
            tag = im.group(0)
            name = _tag_attr(tag, 'name')
            if not name:
                continue
            if _tag_attr(tag, 'id') == 'player-prepare-token':
                self.token_field = name
                continue
            if name in ('cf-turnstile-response', 'g-recaptcha-response', 'altcha'):
                continue
            self.fields[name] = _tag_attr(tag, 'value')
        loggedin = 'angemeldet' if _AUTH['ok'] else 'anonym'
        if root or fm:
            _log('Gate-Konfig (%s): tier=%s sitekey=%s altcha=%s form=%s %s felder=%s tokenfeld=%s' % (
                loggedin, self.tier, (self.sitekey[:12] + '…') if self.sitekey else '-', self.altcha_url or '-',
                self.method.upper(), self.action or '(leer)', sorted(self.fields), self.token_field))
        else:
            _log('Gate-Konfig (%s): kein Gate-Element auf der Episodenseite gefunden' % loggedin)

    def _altcha_answer(self):
        r, _u = _fetch(self.sess, urljoin(self.ep_url, self.altcha_url),
                       headers={'Accept': 'application/json', 'Referer': self.ep_url})
        try:
            ch = json.loads(r.text)
        except Exception:
            ch = None
        if not isinstance(ch, dict):
            _err('Altcha: keine Challenge von %s' % self.altcha_url)
            return ''
        return _altcha_v2(ch) if isinstance(ch.get('parameters'), dict) else _altcha_v1(ch)

    def _turnstile_token(self):
        if _solve_captcha is None:
            self.fatal = 'Turnstile verlangt, aber kein Captcha-Dienst eingebunden (captcha_helper fehlt)'
            return ''
        try:
            tok = _solve_captcha(self.sitekey, self.ep_url, captcha_type='turnstile', use_cache=False)
        except Exception as e:
            tok = ''
            _err('Turnstile-Solver Fehler: %s' % e)
        if not tok:
            self.fatal = 'Turnstile nicht gelöst: %s' % (_captcha_last_error() or
                         'kein Captcha-Dienst eingerichtet (API-Schlüssel in captcha_solver.json eintragen)')
        return tok

    def _offsite(self, url):
        return bool(url) and urlparse(url).netloc not in ('', self.own)

    def resolve(self, play_url):
        """Hoster-Adresse für einen /r?t=...-Link oder '' bei Misserfolg."""
        if self.fatal:
            return ''
        url = urljoin(_base(), play_url)
        nav = {'Referer': self.ep_url, 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate',
               'Sec-Fetch-Site': 'same-origin'}
        r, page_url = _fetch(self.sess, url, headers=nav)
        if self._offsite(page_url):
            return page_url                                   # direkt weitergeleitet
        html = getattr(r, 'text', '') or ''
        nxt = _redirect_in_html(html, page_url)
        if nxt:
            return nxt
        tm = re.search(r'var\s+t\s*=\s*"([^"]+)"', html)
        if 'frameBridge' not in html or not tm:
            _gate_diagnose(html, page_url)
            return ''
        em = re.search(r'var\s+err\s*=\s*"([^"]+)"', html)
        if em:
            _log('Gate meldet Fehler: %s' % em.group(1), getattr(log, 'LOGWARNING', None))

        data = dict(self.fields)
        data[self.token_field] = tm.group(1)
        if 'altcha' in self.tier and self.altcha_url:
            ans = self._altcha_answer()
            if not ans:
                return ''
            data['altcha'] = ans
        if 'turnstile' in self.tier and self.sitekey:
            tok = self._turnstile_token()
            if not tok:
                _err('Gate: %s' % self.fatal)
                return ''
            data['cf-turnstile-response'] = tok

        action = urljoin(self.ep_url, self.action or '')
        hdrs = dict(nav)
        hdrs['Origin'] = _base()
        if self.method == 'get':
            resp = _sreq(self.sess, 'get', action, params=data, timeout=25, headers=hdrs, allow_redirects=False)
        else:
            resp = _sreq(self.sess, 'post', action, data=data, timeout=25, headers=hdrs, allow_redirects=False)
        final = getattr(resp, 'url', None) or action
        hop = 0
        while hop < 5 and _loc(resp, final):
            final = _loc(resp, final)
            if self._offsite(final):
                return final
            resp, final = _fetch(self.sess, final, headers=nav, hops=1)[0], final
            hop += 1
        if self._offsite(final):
            return final
        rhtml = getattr(resp, 'text', '') or ''
        nxt = _redirect_in_html(rhtml, final)
        if nxt:
            return nxt
        _err('Gate: Formular abgeschickt (%s %s), HTTP %s, keine Weiterleitung' % (
            self.method.upper(), action[:80], getattr(resp, 'status_code', '?')))
        _gate_diagnose(rhtml, final)
        return ''


_MAX_GATED = 6


def _extract_hosters_from_page(ep_url):
    gate = _EpisodeGate(ep_url)
    html = gate.html or _get(ep_url, _base())
    if not html:
        _log('Episodenseite leer: %s' % ep_url)
        return []
    pattern = (
        r'data-link-id=["\'](\d+)["\'].*?'
        r'data-play-url=["\']([^"\']+)["\'].*?'
        r'data-provider-name=["\']([^"\']+)["\'].*?'
        r'data-language-label=["\']([^"\']+)["\'].*?'
        r'data-language-id=["\'](\d+)["\']'
    )
    found = re.findall(pattern, html, re.S)
    if not found:
        _log('keine Hoster in %s gefunden, HTML-Größe=%d' % (ep_url, len(html)), getattr(log, 'LOGWARNING', None))
        return []

    result = []
    for _lid, play_url, provider, lang_label, lang_id in found[:_MAX_GATED]:
        try:
            resolved = gate.resolve(_html_unescape(play_url))
        except Exception as e:
            _err('Hoster %s: Gate fehlgeschlagen: %s' % (provider.strip(), e))
            resolved = ''
        if not resolved:
            if gate.fatal:
                break
            continue
        lang = _LANG_MAP.get(lang_id, lang_label)
        label = '%s | %s' % (lang, provider.strip())
        audio = 'de' if lang_id == '1' else ('sub' if lang_id in ('3', '4') else '')
        result.append((label, resolved, False, 'HD', audio))
    _log('%d von %d Hoster aufgelöst für %s' % (len(result), len(found), ep_url))
    return result


def _find_show_url(title):
    clean = _cleantitle(title)
    html = _get(_base() + '/serien')
    best = ('', 0)
    for href, name in re.findall(
        r'<li[^>]*class=["\'][^"\']*series-item[^"\']*["\'][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
        html, re.S
    ):
        c = _cleantitle(name)
        if c == clean:
            return _base() + href if href.startswith('/') else href
        if clean in c or c in clean:
            score = max(len(clean), len(c))
            if score > best[1]:
                best = (_base() + href if href.startswith('/') else href, score)
    return best[0]


def get_hosters(title='', year='', season=0, episode=0, imdb='', tmdb='', url='', params=None):
    season  = int(season  or 0)
    episode = int(episode or 0)
    if url and '/episode-' in url:
        return _extract_hosters_from_page(url)
    if url and '/staffel-' in url:
        ep_url = url.rstrip('/') + '/episode-%d' % episode if episode else url
        return _extract_hosters_from_page(ep_url)
    if url:
        base_url = url
    else:
        base_url = _find_show_url(title)
    if not base_url:
        return []
    if season and episode:
        ep_url = base_url.rstrip('/') + '/staffel-%d/episode-%d' % (season, episode)
    else:
        ep_url = base_url
    return _extract_hosters_from_page(ep_url)


def _get_seasons(show_url):
    html = _get(show_url, _base())
    og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    thumb = og_img.group(1) if og_img else ''
    desc_m = (
        re.search(r'<span[^>]+class=["\']description-text["\'][^>]*>(.*?)</span>', html, re.S | re.I) or
        re.search(r'<p[^>]*itemprop=["\']description["\'][^>]*>(.*?)</p>', html, re.S | re.I) or
        re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    )
    plot = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip() if desc_m else ''
    nav_m = re.search(r'id=["\']season-nav["\'].*?</ul>', html, re.S)
    items = []
    if nav_m:
        for href, s_num, label in re.findall(
            r'href=["\']([^"\']+/staffel-(\d+))["\'][^>]*>\s*([^<]+?)\s*</a>',
            nav_m.group(0), re.S
        ):
            full_url = href if href.startswith('http') else _base() + href
            item = {
                'title':       label.strip() if label.strip() and not label.strip().isdigit() else ('Staffel %s' % s_num),
                'url':         _S_EPS + full_url,
                'poster':      thumb,
                'mediatype':   'season',
                'is_playable': False,
                'next_func':   'load',
            }
            if plot:
                item['plot'] = plot
            items.append(item)
    return items


def _get_episodes(staffel_url):
    html = _get(staffel_url, _base())
    og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    thumb = og_img.group(1) if og_img else ''
    nav_m = re.search(r'id=["\']episode-nav["\'].*?</ul>', html, re.S)
    items = []
    if nav_m:
        for href, ep_num in re.findall(
            r'href=["\']([^"\']+/episode-(\d+))["\']',
            nav_m.group(0)
        ):
            ep_url = href if href.startswith('http') else _base() + href
            items.append({
                'title':       'Episode %s' % ep_num,
                'url':         ep_url,
                'poster':      thumb,
                'mediatype':   'episode',
                'is_playable': True,
                'next_func':   'get_hosters',
            })
    return items


def _parse_show_cards(html):
    try:
        from html import unescape as _unescape
    except ImportError:
        def _unescape(s): return s
    items = []
    for col in re.findall(r'<div class="col-6[^"]*">(.*?)</div>\s*</div>', html, re.S):
        href_m = re.search(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*show-card', col, re.S)
        if not href_m:
            continue
        href = href_m.group(1)
        name_m = re.search(r'<h6[^>]+title=["\']([^"\']+)["\']', col)
        if not name_m:
            name_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', col, re.S)
            if not name_m:
                continue
        name = _unescape(name_m.group(1).strip())
        thumb = ''
        img_m = re.search(r'<img([^>]+)>', col, re.S)
        if img_m:
            attrs = img_m.group(1)
            # tile-md in data-src is the lazy-loaded jpg (preferred for Kodi)
            ds = (
                re.search(r'\bdata-src=["\']([^"\']+tile-md[^"\']+format=jpg[^"\']*)["\']', attrs) or
                re.search(r'\bdata-src=["\']([^"\']+format=jpg[^"\']*)["\']', attrs) or
                re.search(r'\bdata-src=["\']([^"\']+)["\']', attrs)
            )
            if ds and not ds.group(1).startswith('data:'):
                thumb = ds.group(1)
            else:
                s = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs)
                if s and not s.group(1).startswith('data:'):
                    thumb = s.group(1)
        show_href = re.sub(r'/staffel-\d+$', '', href.rstrip('/'))
        full_url  = show_href if show_href.startswith('http') else _base() + show_href
        full_thumb = (thumb if thumb.startswith('http') else _base() + thumb) if thumb else ''
        items.append({
            'title':       name,
            'url':         _S_SEASONS + full_url,
            'poster':      full_thumb,
            'mediatype':   'tvshow',
            'is_playable': False,
            'next_func':   'load',
        })
    next_m = re.search(r'href=["\']([^"\']+\?page=\d+)["\'][^>]*>[^<]*Weiter[^<]*</a>', html, re.I)
    if next_m:
        nxt = next_m.group(1)
        full_next = nxt if nxt.startswith('http') else _base() + nxt
        items.append({'title': '[B]>>> Weiter[/B]', 'url': full_next, 'next_func': 'load', 'is_playable': False})
    return items


def _parse_series_list(html):
    items = []
    for href, name in re.findall(
        r'<li[^>]*class=["\'][^"\']*series-item[^"\']*["\'][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
        html, re.S
    ):
        full_url = href if href.startswith('http') else _base() + href
        items.append({
            'title':       name.strip(),
            'url':         _S_SEASONS + full_url,
            'mediatype':   'tvshow',
            'is_playable': False,
            'next_func':   'load',
        })
    return items


def _get_az_menu():
    items = []
    for letter in list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ['0']:
        display = '0-9' if letter == '0' else letter
        items.append({
            'title':       display,
            'url':         _base() + '/katalog/' + letter,
            'is_playable': False,
            'next_func':   'load',
        })
    return items


def _get_genres():
    html = _get(_base() + '/', _base())
    items = []
    for href, name in re.findall(
        r'href=["\']([^"\']*(?:/genre/)[^"\'?#]+)["\'][^>]*>\s*([^<]{2,50})\s*</a>',
        html, re.S
    ):
        name = name.strip()
        if not name:
            continue
        full_url = href if href.startswith('http') else _base() + href
        items.append({'title': name, 'url': full_url, 'next_func': 'load', 'is_playable': False})
    return items


def _get_sammlungen():
    html = _get(_base() + '/sammlungen', _base())
    items = []
    for href, name in re.findall(
        r'href=["\']([^"\']*sammlung[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']',
        html, re.S
    ):
        if 'sammlungen' in href:
            continue
        full_url = href if href.startswith('http') else _base() + href
        items.append({
            'title':       name.strip(),
            'url':         full_url,
            'is_playable': False,
            'next_func':   'load',
        })
    return items


def _get_kalender():
    text = _get(_base() + '/api/calendar', _base())
    try:
        data = json.loads(text)
    except Exception:
        return []
    items = []
    for date_str, eps in sorted(data.items()):
        for ep in eps:
            if not ep.get('released'):
                continue
            ep_url = ep.get('url', '')
            if not ep_url:
                continue
            full_url  = _base() + ep_url
            lang      = _LANG_MAP.get(str(ep.get('language_id', '')), ep.get('language', ''))
            title     = '%s S%02dE%02d [%s]' % (
                ep.get('title', ''), ep.get('season', 0), ep.get('episode', 0), lang
            )
            cover = ep.get('cover_url', '')
            thumb = (_base() + cover) if cover else ''
            items.append({
                'title':       title,
                'url':         full_url,
                'poster':      thumb,
                'mediatype':   'episode',
                'is_playable': True,
                'next_func':   'get_hosters',
            })
    return items


def _get_neueste_episoden():
    try:
        from html import unescape as _unescape
    except ImportError:
        def _unescape(s): return s
    html = _get(_base() + '/', _base())
    items = []
    day_label = ''
    for block in re.split(r'<div class="episodes-day-group">', html)[1:]:
        day_m = re.search(r'<div class="episodes-day-heading">([^<]+)</div>', block)
        day_label = day_m.group(1).strip() if day_m else day_label
        for href, time_str, title, season, episode, flag in re.findall(
            r'<a class="latest-episode-row[^"]*" href="([^"]+)"[^>]*>.*?'
            r'<span class="ep-time">([^<]+)</span>.*?'
            r'<span class="ep-title" title="([^"]+)">.*?'
            r'<span class="ep-season">([^<]+)</span>.*?'
            r'<span class="ep-episode">([^<]+)</span>.*?'
            r'icon-flag-(\w+)',
            block, re.S
        ):
            ep_url = href if href.startswith('http') else _base() + href
            lang = 'DE' if flag == 'german' else ('EN' if flag == 'english' else flag.upper())
            label = '[%s] %s %s %s (%s)' % (lang, _unescape(title), season, episode, time_str)
            items.append({
                'title':       label,
                'url':         ep_url,
                'mediatype':   'episode',
                'is_playable': True,
                'next_func':   'get_hosters',
            })
    return items


def _parse_section_html(html, section_id):
    try:
        from html import unescape as _unescape
    except ImportError:
        def _unescape(s): return s
    pat = 'id="section-%d"' % section_id
    idx = html.find(pat)
    if idx == -1:
        content = html
    else:
        chunk = html[idx:]
        next_m = re.search(r'id="section-\d+"', chunk[len(pat):])
        content = chunk[:next_m.start() + len(pat)] if next_m else chunk

    seen = set()
    items = []
    # Parse each card-mini block as an atomic unit to avoid cross-card mismatches
    card_blocks = re.findall(r'<div[^>]+class="[^"]*card-mini[^"]*"[^>]*>(.*?)</div>\s*</div>', content, re.S)
    if not card_blocks:
        # Fallback: split by col-6 divs
        card_blocks = re.findall(r'<div[^>]+class="col-6[^"]*"[^>]*>(.*?)</div>\s*</div>', content, re.S)
    for card in card_blocks:
        href_m = re.search(r'href=["\'](/serie/[^"\'?#\s>]+)', card)
        if not href_m:
            continue
        href = re.sub(r'/staffel-\d+(/episode-\d+)?$', '', href_m.group(1).rstrip('/'))
        if href in seen:
            continue
        seen.add(href)
        title_m = (
            re.search(r'<h\d[^>]+title=["\']([^"\']{2,80})["\']', card) or
            re.search(r'<img[^>]+alt=["\']([^"\']{2,80})["\']', card) or
            re.search(r'<h\d[^>]*>\s*<span>\s*([^<]{2,80})\s*</span>', card, re.I)
        )
        title = _unescape(title_m.group(1).strip()) if title_m else ''
        if not title or 'backdrop' in title.lower():
            title = href.split('/')[-1].replace('-', ' ').title()
        img_m = (
            re.search(r'data-src=["\']([^"\']+tile-md[^"\']+format=jpg[^"\']*)["\']', card) or
            re.search(r'data-src=["\']([^"\']+format=jpg[^"\']*)["\']', card) or
            re.search(r'data-src=["\']([^"\']+/media/images/[^"\']+)["\']', card) or
            re.search(r'src=["\']([^"\']+tile-md[^"\']+format=jpg[^"\']*)["\']', card) or
            re.search(r'src=["\']([^"\']+/media/images/backdrop/[^"\']+format=jpg[^"\']*)["\']', card)
        )
        thumb = img_m.group(1) if img_m and not img_m.group(1).startswith('data:') else ''
        if thumb and not thumb.startswith('http'):
            thumb = _base() + thumb
        items.append({
            'title':       title,
            'url':         _S_SEASONS + _base() + href,
            'poster':      thumb,
            'mediatype':   'tvshow',
            'is_playable': False,
            'next_func':   'load',
        })
    return items


def _get_home_show_section(section_id):
    # Sections 1-3 are tab-panes on the homepage, loaded server-side
    html = _get(_base() + '/', _base())
    if html:
        items = _parse_section_html(html, section_id)
        if items:
            return items
    # Fallback: try dedicated URLs
    for path in _HOME_SECTION_URLS.get(section_id, []):
        html = _get(_base() + path, _base())
        if html:
            items = _parse_show_cards(html)
            if items:
                return items
            items = _parse_section_html(html, section_id)
            if items:
                return items
    return []


def get_details(url='', params=None):
    real_url = url
    if real_url.startswith(_S_SEASONS):
        real_url = real_url[len(_S_SEASONS):]
    if not real_url or not real_url.startswith('http'):
        return {}
    html = _get(real_url, _base())
    if not html:
        return {}
    result = {}
    og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    if og_img:
        result['poster'] = og_img.group(1)
    desc_m = (
        re.search(r'<span[^>]+class=["\']description-text["\'][^>]*>(.*?)</span>', html, re.S | re.I) or
        re.search(r'<p[^>]*itemprop=["\']description["\'][^>]*>(.*?)</p>', html, re.S | re.I) or
        re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    )
    if desc_m:
        result['plot'] = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
    return result


def load(url='', params=None):
    if not url:
        return [
            {'title': 'Suche',                 'url': _S_SEARCH,                        'next_func': 'load', 'is_playable': False},
            {'title': 'Neueste Episoden',      'url': _S_NEUESTE,                       'next_func': 'load', 'is_playable': False},
            {'title': 'Gerade im Trend',       'url': _S_TREND,                         'next_func': 'load', 'is_playable': False},
            {'title': 'Wöchentliche Favoriten','url': _S_WEEKLY,                        'next_func': 'load', 'is_playable': False},
            {'title': 'Meistbewertete Serien', 'url': _S_TOPRATED,                      'next_func': 'load', 'is_playable': False},
            {'title': 'Beliebt',               'url': _base() + '/beliebte-serien',     'next_func': 'load', 'is_playable': False},
            {'title': 'Alle Serien',           'url': _base() + '/serien',              'next_func': 'load', 'is_playable': False},
            {'title': 'A-Z',                   'url': _S_AZ,                            'next_func': 'load', 'is_playable': False},
            {'title': 'Genre',                 'url': _S_GENRES,                        'next_func': 'load', 'is_playable': False},
            {'title': 'Sammlungen',            'url': _S_SAMML,                         'next_func': 'load', 'is_playable': False},
            {'title': 'Kalender',              'url': _S_KALENDER,                      'next_func': 'load', 'is_playable': False},
        ]
    if url == _S_SEARCH:
        try:
            import xbmcgui
            query = xbmcgui.Dialog().input('Suche', type=xbmcgui.INPUT_ALPHANUM)
            if query:
                return search(query)
        except Exception:
            _err('Suche fehlgeschlagen')
        return []
    if url == _S_NEUESTE:          return _get_neueste_episoden()
    if url == _S_TREND:            return _get_home_show_section(1)
    if url == _S_WEEKLY:           return _get_home_show_section(2)
    if url == _S_TOPRATED:         return _get_home_show_section(3)
    if url == _S_AZ:               return _get_az_menu()
    if url == _S_GENRES:           return _get_genres()
    if url == _S_SAMML:            return _get_sammlungen()
    if url == _S_KALENDER:         return _get_kalender()
    if url.startswith(_S_SEASONS): return _get_seasons(url[len(_S_SEASONS):])
    if url.startswith(_S_EPS):     return _get_episodes(url[len(_S_EPS):])
    html = _get(url, _base())
    if url.split('?')[0].rstrip('/') == _base() + '/serien':
        return _parse_series_list(html)
    return _parse_show_cards(html)


def search(query='', params=None):
    html = _get(_base() + '/serien')
    clean = _cleantitle(query)
    items = []
    for m in re.finditer(
        r'<li[^>]*class=["\'][^"\']*series-item[^"\']*["\'][^>]*data-search=["\']([^"\']+)["\'][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
        html, re.S
    ):
        search_str, href, name = m.group(1), m.group(2), m.group(3)
        if clean not in _cleantitle(search_str):
            continue
        full_url = href if href.startswith('http') else _base() + href
        items.append({
            'title':       name.strip(),
            'url':         _S_SEASONS + full_url,
            'mediatype':   'tvshow',
            'is_playable': False,
            'next_func':   'load',
        })
    return items
