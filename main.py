# -*- coding: utf-8 -*-
"""
Buscador PoseidonHD - Addon para Kodi
Interfaz estilo Netflix con navegación completa
Compatible con Kodi 19 Matrix, 20 Nexus y 21 Omega
Sitio objetivo: https://www.poseidonhd2.co/
Versión 2.0.0 - Con interfaz Netflix y resolvers integrados
"""

import sys
import re
import json
import time
import base64
import hashlib
from urllib.parse import parse_qsl, quote_plus, urlparse, parse_qs, urlencode

import xbmc
import xbmcaddon
import xbmcplugin
import xbmcgui
import xbmcvfs
import requests
from bs4 import BeautifulSoup

# Intentar importar resolveurl como último recurso
try:
    import resolveurl
    RESOLVEURL_AVAILABLE = True
except ImportError:
    RESOLVEURL_AVAILABLE = False

# Intentar importar cryptography para AES-GCM (necesario para Filemoon)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAVE_CRYPTOGRAPHY = True
except ImportError:
    _HAVE_CRYPTOGRAPHY = False
    AESGCM = None

# Intentar PyCryptodome como fallback para AES-GCM
try:
    from Cryptodome.Cipher import AES as PyCryptoAES
    _HAVE_PYCRYPTO = True
except ImportError:
    try:
        from Crypto.Cipher import AES as PyCryptoAES
        _HAVE_PYCRYPTO = True
    except ImportError:
        _HAVE_PYCRYPTO = False
        PyCryptoAES = None

# Configuración básica
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = "PoseidonHD Netflix"
BASE_URL = 'https://www.poseidonhd2.co'

# Headers de navegador de escritorio real
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# ===========================================================================
# ICONOS Y RECURSOS
# ===========================================================================

def get_icon_path(icon_name):
    """Retorna la ruta al icono solicitado."""
    resources_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('path') + '/resources')
    icon_path = f"{resources_dir}/{icon_name}.png"
    if xbmcvfs.exists(icon_path):
        return icon_path
    return ADDON.getAddonInfo('icon')

# ===========================================================================
# UTILIDADES GENERALES
# ===========================================================================

def log(message, level=xbmc.LOGINFO):
    """Escribe logs en el sistema de Kodi."""
    xbmc.log(f"[{ADDON_NAME}] {message}", level)


def show_notification(title, message, icon=None, time_ms=3000):
    """Muestra una notificación en la interfaz de Kodi."""
    dialog = xbmcgui.Dialog()
    dialog.notification(title, message, icon or xbmcgui.NOTIFICATION_INFO, time_ms)


def get_html(url, referer=None, extra_headers=None, timeout=15):
    """Realiza una petición HTTP GET y retorna el texto HTML."""
    headers = HEADERS.copy()
    if referer:
        headers['Referer'] = referer
    if extra_headers:
        headers.update(extra_headers)
    try:
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        log(f"Error realizando petición HTTP a {url}: {str(e)}", xbmc.LOGERROR)
        return None


def get_json(url, referer=None, extra_headers=None, timeout=15):
    """Realiza una petición HTTP GET y retorna el JSON parseado."""
    headers = HEADERS.copy()
    if referer:
        headers['Referer'] = referer
    if extra_headers:
        headers.update(extra_headers)
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"Error obteniendo JSON de {url}: {str(e)}", xbmc.LOGERROR)
        return None


def extract_next_data(html):
    """Extrae y parsea el objeto __NEXT_DATA__ de una página Next.js."""
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, 'html.parser')
        script_tag = soup.find('script', id='__NEXT_DATA__')
        if script_tag and script_tag.string:
            return json.loads(script_tag.string)
    except Exception as e:
        log(f"Error al extraer __NEXT_DATA__: {str(e)}", xbmc.LOGERROR)
    return None


def clean_title(title):
    """Limpia el título eliminando prefijos y etiquetas."""
    title = re.sub(r'^(Pelicula|Serie)\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*-\s*(?:Online|TV|4K|HD|FullBluRay)\s*$', '', title, flags=re.IGNORECASE)
    return title.strip()


def extract_thumbnail(img_tag):
    """Extrae la URL de la miniatura desde una etiqueta img."""
    if not img_tag:
        return ""
    img_src = img_tag.get('src') or img_tag.get('data-src') or ""
    if 'url=' in img_src:
        try:
            parsed = urlparse(img_src)
            qs = parse_qs(parsed.query)
            if 'url' in qs:
                return qs['url'][0]
        except Exception:
            pass
    if not img_src:
        return ""
    if img_src.startswith('//'):
        return 'https:' + img_src
    if img_src.startswith('/'):
        return BASE_URL + img_src
    return img_src


# ===========================================================================
# UNPACKER DE DEAN EDWARDS (P,A,C,K,E,D) - Implementación pura Python
# ===========================================================================

def _packer_detect(source):
    """Detecta si el código JS está empaquetado con el packer de Dean Edwards."""
    return source.strip().startswith("eval(function(p,a,c,k,e,")


def _packer_unpack(source):
    """
    Desempaqueta código JavaScript comprimido con el packer de Dean Edwards.
    Implementación pura en Python sin js2py.
    """
    try:
        # Extraer los argumentos del packer: p, a, c, k, e, d
        match = re.search(
            r"eval\(function\(p,a,c,k,e,(?:r|d)\)\{.*?return p\}",
            source, re.DOTALL
        )
        if not match:
            return source

        # Extraer parámetros: código, radix, count, keywords
        inner = re.search(
            r"'((?:[^'\\]|\\.)*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'((?:[^'\\]|\\.)*)'",
            source
        )
        if not inner:
            return source

        payload = inner.group(1).replace("\\'", "'").replace("\\\\", "\\")
        radix = int(inner.group(2))
        count = int(inner.group(3))
        keywords_raw = inner.group(4).replace("\\'", "'")

        # Dividir keywords
        if '|' in keywords_raw:
            keywords = keywords_raw.split('|')
        else:
            keywords = re.split(r'\|', keywords_raw)

        def base_decode(num_str, base):
            """Convierte un número en base 'base' a entero."""
            chars = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
            result = 0
            num_str = num_str.strip()
            for char in num_str:
                result = result * base + chars.index(char)
            return result

        def replace_match(m):
            """Reemplaza cada token con su keyword correspondiente."""
            word = m.group(0)
            try:
                index = base_decode(word, radix)
                if index < len(keywords) and keywords[index]:
                    return keywords[index]
                return word
            except (ValueError, IndexError):
                return word

        # Reemplazar todos los tokens en el payload
        unpacked = re.sub(r'\b\w+\b', replace_match, payload)
        return unpacked

    except Exception as e:
        log(f"Error en _packer_unpack: {str(e)}", xbmc.LOGWARNING)
        return source


# ===========================================================================
# RESOLVERS DE SERVIDORES DE VIDEO
# ===========================================================================

def resolve_streamwish(embed_url):
    """
    Resuelve URLs de Streamwish, Wishonly, JwplayerHLS y sitios similares.
    Usa una sesión con cookies para obtener el contenido real del player.
    """
    log(f"[Resolver] Streamwish: {embed_url}")

    # Extraer referer del pipe si existe: url|Referer=...
    referer = embed_url
    if '|Referer=' in embed_url or '|referer=' in embed_url:
        parts = embed_url.split('|', 1)
        embed_url = parts[0]
        qs = dict(p.split('=', 1) for p in parts[1].split('&') if '=' in p)
        referer = qs.get('Referer') or qs.get('referer') or embed_url

    parsed = urlparse(embed_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    # Usar sesión con cookies para simular un navegador real
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
        'Referer': referer,
    })

    # Paso 1: Visitar la página principal del dominio para obtener cookies
    try:
        session.get(base_domain, timeout=8)
    except Exception:
        pass

    # Paso 2: Obtener la página del embed
    try:
        resp = session.get(embed_url, timeout=15)
        html = resp.text
    except Exception as e:
        log(f"[Resolver] Streamwish: Error HTTP: {str(e)}", xbmc.LOGWARNING)
        return None

    if not html or len(html) < 100:
        log("[Resolver] Streamwish: HTML vacío o demasiado corto.", xbmc.LOGWARNING)
        return None

    # Si la página es la de 'loading...' (SPA protegida), intentar el main.js
    if 'Page is loading' in html or (len(html) < 1000 and 'main.js' in html):
        log("[Resolver] Streamwish: Página de carga detectada, intentando main.js...", xbmc.LOGWARNING)
        try:
            js_ver = re.search(r'main\.js\?v=([\d.]+)', html)
            js_url = f"{base_domain}/main.js" + (f"?v={js_ver.group(1)}" if js_ver else "")
            js_resp = session.get(js_url, timeout=12)
            js_content = js_resp.text
            api_paths = re.findall(r'["\'](\/(?:api|get|source|player)\/[^"\',]{2,50})["\']', js_content)
            log(f"[Resolver] Streamwish: API paths en main.js: {api_paths[:5]}")
        except Exception:
            pass
        return None

    # Buscar sección packed P,A,C,K,E,D en el HTML
    packed_html = html
    pack_match = re.search(r'(eval\(function\(p,a,c,k,e,(?:r|d)\).*?)</script>', html, re.DOTALL)
    if pack_match:
        packed_code = pack_match.group(1)
        unpacked = _packer_unpack(packed_code)
        packed_html = unpacked + html
    else:
        packed_html = html

    # Patrones para extraer la fuente m3u8/mp4 (ordenados por prioridad)
    patterns = [
        r'["\']hls[2]?["\']\s*:\s*["\']([^"\']+(m3u8|mp4)[^"\']*)["\'`]',
        r'(?:file|"hls\d*")\s*:\s*["\']([^"\']+(m3u8|mp4)[^"\']*)["\'`]',
        r'"file"\s*:\s*"(https?://[^"]+)"',
        r"source\s*:\s*'(https?://[^']+\.m3u8[^']*)'" ,
        r'sources\s*:\s*\[.*?"file"\s*:\s*"([^"]+)"',
        r'"src"\s*:\s*"(https?://[^"]+\.m3u8[^"]*)',
        r'(?:file|src)\s*=\s*["\']?(https?://[^"\'>\s]+\.(?:m3u8|mp4)[^"\'>\s]*)',
        r'(https?://[^\s"\',<>]+\.m3u8(?:\?[^\s"\',<>]*)?)',
    ]

    for pattern in patterns:
        m = re.search(pattern, packed_html, re.DOTALL | re.IGNORECASE)
        if m:
            url = m.group(1)
            if url and url.startswith('http') and ('m3u8' in url or 'mp4' in url):
                log(f"[Resolver] Streamwish => {url}")
                return url

    log("[Resolver] Streamwish: No se encontró fuente de video en el HTML.", xbmc.LOGWARNING)
    return None


def resolve_filemoon(embed_url):
    """
    Resuelve URLs de Filemoon/Filemooon usando su API y descifrado AES-256-GCM.
    """
    log(f"[Resolver] Filemoon: {embed_url}")

    if not (_HAVE_CRYPTOGRAPHY or _HAVE_PYCRYPTO):
        log("[Resolver] Filemoon: No hay librería AES disponible.", xbmc.LOGWARNING)
        return None

    match = re.search(r'/(?:e|d)/([a-z0-9]+)', embed_url)
    if not match:
        log("[Resolver] Filemoon: No se encontró ID de video en la URL.", xbmc.LOGWARNING)
        return None

    video_id = match.group(1)
    parsed = urlparse(embed_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    playback_url = f"{base_domain}/api/videos/{video_id}/embed/playback"
    headers_extra = {'Referer': embed_url}
    data = get_json(playback_url, extra_headers=headers_extra)

    if not data or data.get('error'):
        playback_url = f"https://filemooon.link/api/videos/{video_id}/embed/playback"
        data = get_json(playback_url, extra_headers=headers_extra)

    if not data or data.get('error'):
        log(f"[Resolver] Filemoon: Error al obtener datos de playback.", xbmc.LOGWARNING)
        return None

    playback_data = data.get('playback', {})
    try:
        algorithm = playback_data.get('algorithm')
        iv_b64 = playback_data.get('iv')
        payload_b64 = playback_data.get('payload')
        key_parts = playback_data.get('key_parts', [])

        if algorithm != 'AES-256-GCM' or len(key_parts) != 2:
            log(f"[Resolver] Filemoon: Algoritmo no soportado.", xbmc.LOGWARNING)
            return None

        def b64u_decode(s):
            s = s.replace('-', '+').replace('_', '/')
            padding = len(s) % 4
            if padding:
                s += '=' * (4 - padding)
            return base64.b64decode(s)

        iv = b64u_decode(iv_b64)
        payload = b64u_decode(payload_b64)
        kp1, kp2 = key_parts

        try:
            k1 = b64u_decode(kp1)
        except Exception:
            k1 = kp1.encode()
        try:
            k2 = b64u_decode(kp2)
        except Exception:
            k2 = kp2.encode()

        raw_key = k1 + k2
        key = raw_key if len(raw_key) == 32 else hashlib.sha256(raw_key).digest()

        pt = None
        if _HAVE_CRYPTOGRAPHY and AESGCM is not None:
            aesgcm = AESGCM(key)
            pt = aesgcm.decrypt(iv, payload, None)
        elif _HAVE_PYCRYPTO and PyCryptoAES is not None:
            if len(payload) < 16:
                raise ValueError('Payload demasiado corto para tag GCM')
            tag = payload[-16:]
            ciphertext = payload[:-16]
            cipher = PyCryptoAES.new(key, PyCryptoAES.MODE_GCM, nonce=iv)
            pt = cipher.decrypt_and_verify(ciphertext, tag)
        else:
            return None

        decrypted = json.loads(pt.decode('utf-8', errors='replace'))
        m3u8_url = decrypted.get('sources', [{}])[0].get('url')
        if m3u8_url:
            log(f"[Resolver] Filemoon => {m3u8_url}")
            host = base_domain
            header_str = f"|Referer={host}/&Origin={host}"
            return m3u8_url + header_str

    except Exception as e:
        log(f"[Resolver] Filemoon: Error de descifrado: {str(e)}", xbmc.LOGERROR)

    return None


def resolve_streamtape(embed_url):
    """Resuelve URLs de Streamtape extrayendo el enlace directo desde la página."""
    log(f"[Resolver] Streamtape: {embed_url}")

    html = get_html(embed_url, referer=embed_url, timeout=12)
    if not html:
        return None

    if 'Video not found' in html or 'Video is converting' in html:
        log("[Resolver] Streamtape: Video no encontrado o convirtiendo.", xbmc.LOGWARNING)
        return None

    matches = re.findall(r"innerHTML\s*=\s*([^;]+)", html)
    if len(matches) >= 2:
        try:
            part1 = re.search(r"'([^']+)'", matches[-2])
            part2 = re.search(r"'([^']+)'", matches[-1])
            if part1 and part2:
                raw_url = "https:" + part1.group(1) + part2.group(1)
                try:
                    resp = requests.head(raw_url, headers=HEADERS, timeout=8, allow_redirects=True)
                    final_url = resp.url
                except Exception:
                    final_url = raw_url
                log(f"[Resolver] Streamtape => {final_url}")
                return f"{final_url}|User-Agent={HEADERS['User-Agent']}"
        except Exception as e:
            log(f"[Resolver] Streamtape: Error procesando JS: {str(e)}", xbmc.LOGWARNING)

    return None


def resolve_doodstream(embed_url):
    """Resuelve URLs de DoodStream generando el token de reproducción."""
    log(f"[Resolver] Doodstream: {embed_url}")

    headers = HEADERS.copy()
    headers['Referer'] = embed_url

    try:
        resp = requests.get(embed_url, headers=headers, timeout=15, allow_redirects=True)
        html = resp.text
        final_url = resp.url
    except Exception as e:
        log(f"[Resolver] Doodstream: Error HTTP: {str(e)}", xbmc.LOGWARNING)
        return None

    if 'Video not found' in html:
        return None

    pass_match = re.search(r"\$\.get\('(/pass_md5[^']+)'", html)
    if not pass_match:
        pass_match = re.search(r"(/pass_md5/[^'\"]+)", html)

    if not pass_match:
        log("[Resolver] Doodstream: No se encontró pass_md5.", xbmc.LOGWARNING)
        return None

    parsed = urlparse(final_url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    pass_url = host + pass_match.group(1)

    headers['Referer'] = final_url
    try:
        pass_resp = requests.get(pass_url, headers=headers, timeout=12)
        base_video_url = pass_resp.text.strip()
    except Exception as e:
        log(f"[Resolver] Doodstream: Error obteniendo pass_md5: {str(e)}", xbmc.LOGWARNING)
        return None

    token = str(int(time.time() * 1000))
    final_video_url = base_video_url + token
    log(f"[Resolver] Doodstream => {final_video_url}")
    return f"{final_video_url}|Referer={final_url}"


def resolve_voe(embed_url):
    """Resuelve URLs de VOE extrayendo el enlace .m3u8 o .mp4 de la página."""
    log(f"[Resolver] VOE: {embed_url}")

    html = get_html(embed_url, referer=embed_url, timeout=12)
    if not html:
        return None

    patterns = [
        r"'hls'\s*:\s*'([^']+)'",
        r'"hls"\s*:\s*"([^"]+)"',
        r"'mp4'\s*:\s*'([^']+)'",
        r'"mp4"\s*:\s*"([^"]+)"',
        r"sources\s*=\s*\[.*?\"file\"\s*:\s*\"([^\"]+)\"",
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if m:
            url = m.group(1)
            log(f"[Resolver] VOE => {url}")
            return url

    log("[Resolver] VOE: No se encontró fuente de video.", xbmc.LOGWARNING)
    return None


def resolve_mixdrop(embed_url):
    """Resuelve URLs de Mixdrop buscando la URL del video en el HTML/JS."""
    log(f"[Resolver] Mixdrop: {embed_url}")

    html = get_html(embed_url, referer=embed_url, timeout=12)
    if not html:
        return None

    if _packer_detect(html):
        pack_match = re.search(r'(eval\(function\(p,a,c,k,e,(?:r|d)\).*?)</script>', html, re.DOTALL)
        if pack_match:
            html = _packer_unpack(pack_match.group(1))

    patterns = [
        r'MDCore\.wurl\s*=\s*"([^"]+)"',
        r'"wurl"\s*:\s*"([^"]+)"',
        r"wurl\s*=\s*'([^']+)'",
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            url = m.group(1)
            if not url.startswith('http'):
                url = 'https:' + url
            log(f"[Resolver] Mixdrop => {url}")
            return url

    return None


def resolve_mp4upload(embed_url):
    """Resuelve URLs de mp4upload extrayendo la fuente del player."""
    log(f"[Resolver] Mp4upload: {embed_url}")
    html = get_html(embed_url, referer='https://www.mp4upload.com/', timeout=12)
    if not html:
        return None
    m = re.search(r'"file"\s*:\s*"([^"]+\.mp4[^"]*)"', html, re.IGNORECASE)
    if m:
        url = m.group(1)
        log(f"[Resolver] Mp4upload => {url}")
        return url
    return None


def resolve_okru(embed_url):
    """Resuelve URLs de OK.ru extrayendo la mejor calidad disponible."""
    log(f"[Resolver] OK.ru: {embed_url}")
    html = get_html(embed_url, referer=embed_url, timeout=12)
    if not html:
        return None

    m = re.search(r'data-options="([^"]+)"', html)
    if m:
        try:
            data_str = m.group(1).replace('"', '"')
            data = json.loads(data_str)
            videos = data.get('flashvars', {}).get('metadata', {}).get('videos', [])
            if videos:
                best = max(videos, key=lambda x: x.get('seekSchema', 0))
                url = best.get('url', '')
                if url:
                    log(f"[Resolver] OK.ru => {url}")
                    return url
        except Exception as e:
            log(f"[Resolver] OK.ru: Error procesando datos: {str(e)}", xbmc.LOGWARNING)

    return None


def resolve_netu(embed_url):
    """
    Resuelve URLs de Netu / waaw.to / hqq.tv
    """
    log(f"[Resolver] Netu/waaw: {embed_url}")

    embed_url = re.sub(r'/f/([a-zA-Z0-9]+)', r'/e/\1', embed_url)

    parsed = urlparse(embed_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    file_id = re.search(r'/e/([a-zA-Z0-9]+)', embed_url)
    if not file_id:
        log("[Resolver] Netu: No se encontró ID de archivo.", xbmc.LOGWARNING)
        return None
    file_id = file_id.group(1)

    h = HEADERS.copy()
    h['Referer'] = embed_url

    try:
        resp = requests.get(embed_url, headers=h, timeout=15)
        html = resp.text
    except Exception as e:
        log(f"[Resolver] Netu: Error HTTP: {str(e)}", xbmc.LOGWARNING)
        return None

    ws_match = re.search(r"var ws\s*=\s*'([^']+)'", html)
    if not ws_match:
        log("[Resolver] Netu: No se encontró token ws.", xbmc.LOGWARNING)
        return None

    ws_token = ws_match.group(1)

    player_url = f"{base}/player/index.php?v={file_id}"
    try:
        player_resp = requests.post(
            player_url,
            data={'r': '', 'd': parsed.netloc},
            headers={**h, 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15
        )
        player_data = player_resp.text
        if player_data:
            video_urls = re.findall(r'(https?://[^\s"\',<>]+\.(?:m3u8|mp4)[^\s"\',<>]*)', player_data)
            if video_urls:
                url = video_urls[0] + ws_token
                log(f"[Resolver] Netu (player.php) => {url}")
                return url
    except Exception as e:
        log(f"[Resolver] Netu: Error player.php: {str(e)}", xbmc.LOGWARNING)

    log("[Resolver] Netu: No se pudo resolver (requiere JS).", xbmc.LOGWARNING)
    return None


def resolve_generic_iframe(embed_url):
    """Resuelve genérico: busca fuentes de video directas (.m3u8, .mp4) en el HTML."""
    log(f"[Resolver] Genérico: {embed_url}")
    html = get_html(embed_url, referer=embed_url, timeout=12)
    if not html:
        return None

    if _packer_detect(html):
        pack_match = re.search(r'(eval\(function\(p,a,c,k,e,(?:r|d)\).*?)</script>', html, re.DOTALL)
        if pack_match:
            html = _packer_unpack(pack_match.group(1)) + html

    patterns = [
        r'"file"\s*:\s*"(https?://[^"]+\.(?:m3u8|mp4)[^"]*)"',
        r"'file'\s*:\s*'(https?://[^']+\.(?:m3u8|mp4)[^']*)'",
        r'src\s*[=:]\s*["\']?(https?://[^"\'>\s]+\.(?:m3u8|mp4)[^"\'>\s]*)',
        r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)',
    ]

    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if m:
            url = m.group(1)
            log(f"[Resolver] Genérico => {url}")
            return url

    return None


def resolve_server(embed_url, server_name=''):
    """Enrutador principal de resolvers."""
    if not embed_url:
        return None

    url_lower = embed_url.lower()
    server_lower = server_name.lower()

    log(f"[Resolver] Intentando resolver: {embed_url} (servidor={server_name})")

    # --- Streamwish y variantes ---
    streamwish_domains = [
        'streamwish', 'wishonly', 'jwplayerhls', 'embedwish', 'vidhidepro',
        'swdyu', 'filelions', 'playerwish', 'ajmidyad', 'tntsport',
        'wishfast', 'vidmovies', 'vidclouds', 'sfastwish', 'streamwish.to',
        'wishfast.top', 'streamwish.com'
    ]
    if any(d in url_lower or d in server_lower for d in streamwish_domains):
        result = resolve_streamwish(embed_url)
        if result:
            return result

    # --- Netu / waaw.to / hqq.tv ---
    netu_domains = ['waaw.to', 'netu.ac', 'netu.tv', 'hqq.tv', 'hqq.to', 'akpdm.top', 'netu']
    if any(d in url_lower or d in server_lower for d in netu_domains):
        result = resolve_netu(embed_url)
        if result:
            return result
        log(f"[Resolver] Netu/waaw requiere JS — no se puede resolver sin navegador.", xbmc.LOGWARNING)
        return None

    # --- Filemoon y variantes ---
    filemoon_domains = ['filemoon', 'filemooon', 'moonplayer', 'kerapoxy']
    if any(d in url_lower or d in server_lower for d in filemoon_domains):
        result = resolve_filemoon(embed_url)
        if result:
            return result

    # --- Streamtape ---
    if 'streamtape' in url_lower or 'streamtape' in server_lower:
        result = resolve_streamtape(embed_url)
        if result:
            return result

    # --- Doodstream y variantes ---
    dood_domains = ['doodstream', 'dood.', 'ds2play', 'doods.', 'dooood']
    if any(d in url_lower or d in server_lower for d in dood_domains):
        result = resolve_doodstream(embed_url)
        if result:
            return result

    # --- VOE ---
    if 'voe.sx' in url_lower or 'voe' in server_lower:
        result = resolve_voe(embed_url)
        if result:
            return result

    # --- Mixdrop ---
    if 'mixdrop' in url_lower or 'mixdrop' in server_lower:
        result = resolve_mixdrop(embed_url)
        if result:
            return result

    # --- Mp4upload ---
    if 'mp4upload' in url_lower or 'mp4upload' in server_lower:
        result = resolve_mp4upload(embed_url)
        if result:
            return result

    # --- OK.ru ---
    if 'ok.ru' in url_lower or 'okru' in server_lower:
        result = resolve_okru(embed_url)
        if result:
            return result

    # --- Si la URL ya es directa (.m3u8, .mp4) ---
    if any(ext in url_lower for ext in ['.m3u8', '.mp4', '.mkv', '.avi']):
        log(f"[Resolver] URL ya es directa: {embed_url}")
        return embed_url

    # --- Intentar resolver con resolveurl si está disponible ---
    if RESOLVEURL_AVAILABLE:
        try:
            log("[Resolver] Intentando con resolveurl...")
            result = resolveurl.resolve(embed_url)
            if result:
                log(f"[Resolver] resolveurl => {result}")
                return result
        except Exception as e:
            log(f"[Resolver] resolveurl falló: {str(e)}", xbmc.LOGWARNING)

    # --- Último recurso: resolver genérico ---
    result = resolve_generic_iframe(embed_url)
    if result:
        return result

    log(f"[Resolver] No se pudo resolver la URL: {embed_url}", xbmc.LOGWARNING)
    return None


# ===========================================================================
# INTERFAZ NETFLIX - NAVEGACIÓN PRINCIPAL
# ===========================================================================

def build_main_menu():
    """
    Construye el menú principal estilo Netflix con categorías visuales.
    """
    handle = int(sys.argv[1])
    
    # =========================================================================
    # CATEGORÍA: Películas
    # =========================================================================
    list_item = xbmcgui.ListItem(label="🎬 Películas")
    list_item.setArt({
        'thumb': 'DefaultMovies.png',
        'poster': 'DefaultMovies.png',
        'icon': 'DefaultMovies.png'
    })
    list_item.setProperty('IsPlayable', 'false')
    url = f"{sys.argv[0]}?action=sub_menu&type=peliculas&url={quote_plus(BASE_URL + '/peliculas/')}"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # =========================================================================
    # CATEGORÍA: Series
    # =========================================================================
    list_item = xbmcgui.ListItem(label="📺 Series")
    list_item.setArt({
        'thumb': 'DefaultTVShows.png',
        'poster': 'DefaultTVShows.png',
        'icon': 'DefaultTVShows.png'
    })
    list_item.setProperty('IsPlayable', 'false')
    url = f"{sys.argv[0]}?action=sub_menu&type=series&url={quote_plus(BASE_URL + '/series/')}"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # =========================================================================
    # CATEGORÍA: Tendencias
    # =========================================================================
    list_item = xbmcgui.ListItem(label="🔥 Tendencias")
    list_item.setArt({
        'thumb': 'DefaultFavourites.png',
        'poster': 'DefaultFavourites.png',
        'icon': 'DefaultFavourites.png'
    })
    list_item.setProperty('IsPlayable', 'false')
    url = f"{sys.argv[0]}?action=trends_menu"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # =========================================================================
    # CATEGORÍA: Buscar
    # =========================================================================
    list_item = xbmcgui.ListItem(label="🔍 Buscar")
    list_item.setArt({
        'thumb': 'DefaultAddonsSearch.png',
        'poster': 'DefaultAddonsSearch.png',
        'icon': 'DefaultAddonsSearch.png'
    })
    list_item.setProperty('IsPlayable', 'false')
    url = f"{sys.argv[0]}?action=search"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    xbmcplugin.setContent(handle, 'files')
    xbmcplugin.endOfDirectory(handle)


def build_sub_menu(type_name, base_url):
    """
    Construye el submenú para Películas o Series con opciones de filtrado.
    """
    handle = int(sys.argv[1])
    
    icon_map = {
        'peliculas': 'DefaultMovies.png',
        'series': 'DefaultTVShows.png'
    }
    default_icon = icon_map.get(type_name, 'DefaultMovies.png')
    
    # Todas
    list_item = xbmcgui.ListItem(label="📋 Todas")
    list_item.setArt({'thumb': default_icon, 'poster': default_icon, 'icon': default_icon})
    url = f"{sys.argv[0]}?action=list_all&type={type_name}&url={quote_plus(base_url)}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Estrenos
    list_item = xbmcgui.ListItem(label="✨ Estrenos")
    list_item.setArt({'thumb': default_icon, 'poster': default_icon, 'icon': default_icon})
    url = f"{sys.argv[0]}?action=list_all&type={type_name}&url={quote_plus(base_url + 'estrenos')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Tendencias Semana
    list_item = xbmcgui.ListItem(label="📈 Tendencias de la Semana")
    list_item.setArt({'thumb': default_icon, 'poster': default_icon, 'icon': default_icon})
    url = f"{sys.argv[0]}?action=list_all&type={type_name}&url={quote_plus(base_url + 'tendencias/semana')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Tendencias Día
    list_item = xbmcgui.ListItem(label="📊 Tendencias del Día")
    list_item.setArt({'thumb': default_icon, 'poster': default_icon, 'icon': default_icon})
    url = f"{sys.argv[0]}?action=list_all&type={type_name}&url={quote_plus(base_url + 'tendencias/dia')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Géneros (solo para películas)
    if type_name == 'peliculas':
        list_item = xbmcgui.ListItem(label="🏷️ Géneros")
        list_item.setArt({'thumb': default_icon, 'poster': default_icon, 'icon': default_icon})
        url = f"{sys.argv[0]}?action=genres&type={type_name}"
        xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Nuevos Episodios (solo para series)
    if type_name == 'series':
        list_item = xbmcgui.ListItem(label="🆕 Nuevos Episodios")
        list_item.setArt({'thumb': default_icon, 'poster': default_icon, 'icon': default_icon})
        url = f"{sys.argv[0]}?action=list_all&type=episodios&url={quote_plus(BASE_URL + '/episodios')}&page=1"
        xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    xbmcplugin.setContent(handle, 'files')
    xbmcplugin.endOfDirectory(handle)


def build_trends_menu():
    """Menú de tendencias."""
    handle = int(sys.argv[1])
    
    # Tendencias Semana - Películas
    list_item = xbmcgui.ListItem(label="🎬 Películas - Tendencias Semana")
    list_item.setArt({'thumb': 'DefaultMovies.png', 'poster': 'DefaultMovies.png'})
    url = f"{sys.argv[0]}?action=list_all&type=peliculas&url={quote_plus(BASE_URL + '/peliculas/tendencias/semana')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Tendencias Día - Películas
    list_item = xbmcgui.ListItem(label="🎬 Películas - Tendencias Día")
    list_item.setArt({'thumb': 'DefaultMovies.png', 'poster': 'DefaultMovies.png'})
    url = f"{sys.argv[0]}?action=list_all&type=peliculas&url={quote_plus(BASE_URL + '/peliculas/tendencias/dia')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Tendencias Semana - Series
    list_item = xbmcgui.ListItem(label="📺 Series - Tendencias Semana")
    list_item.setArt({'thumb': 'DefaultTVShows.png', 'poster': 'DefaultTVShows.png'})
    url = f"{sys.argv[0]}?action=list_all&type=series&url={quote_plus(BASE_URL + '/series/tendencias/semana')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    # Tendencias Día - Series
    list_item = xbmcgui.ListItem(label="📺 Series - Tendencias Día")
    list_item.setArt({'thumb': 'DefaultTVShows.png', 'poster': 'DefaultTVShows.png'})
    url = f"{sys.argv[0]}?action=list_all&type=series&url={quote_plus(BASE_URL + '/series/tendencias/dia')}&page=1"
    xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    xbmcplugin.setContent(handle, 'files')
    xbmcplugin.endOfDirectory(handle)


def build_genres_menu():
    """Menú de géneros para películas."""
    handle = int(sys.argv[1])
    
    genres = [
        ("Acción", "accion"),
        ("Animación", "animacion"),
        ("Aventura", "aventura"),
        ("Bélica", "belica"),
        ("Ciencia Ficción", "ciencia-ficcion"),
        ("Comedia", "comedia"),
        ("Crimen", "crimen"),
        ("Documental", "documental"),
        ("Drama", "drama"),
        ("Familia", "familia"),
        ("Fantasía", "fantasia"),
        ("Historia", "historia"),
        ("Misterio", "misterio"),
        ("Música", "musica"),
        ("Romance", "romance"),
        ("Suspenso", "suspenso"),
        ("Terror", "terror"),
        ("Western", "western"),
    ]
    
    for genre_name, genre_slug in genres:
        list_item = xbmcgui.ListItem(label=genre_name)
        list_item.setArt({
            'thumb': 'DefaultMovies.png',
            'poster': 'DefaultMovies.png'
        })
        genre_url = f"{BASE_URL}/genero/{genre_slug}/"
        url = f"{sys.argv[0]}?action=list_all&type=peliculas&url={quote_plus(genre_url)}&page=1"
        xbmcplugin.addDirectoryItem(handle, url, list_item, isFolder=True)
    
    xbmcplugin.setContent(handle, 'files')
    xbmcplugin.endOfDirectory(handle)


# ===========================================================================
# LISTADO DE CONTENIDO (PELÍCULAS, SERIES, EPISODIOS)
# ===========================================================================

def list_content(list_url, content_type, page=1):
    """
    Lista el contenido desde una URL del sitio con paginación.
    content_type: 'peliculas', 'series', 'episodios'
    """
    handle = int(sys.argv[1])
    log(f"Listando contenido: {list_url} (tipo={content_type}, página={page})")
    
    # Agregar paginación a la URL si no es página 1
    if page > 1:
        if '/page/' in list_url:
            list_url = re.sub(r'/page/\d+', f'/page/{page}', list_url)
        else:
            if list_url.endswith('/'):
                list_url += f'page/{page}/'
            else:
                list_url += f'/page/{page}/'
    
    html = get_html(list_url, timeout=12)
    if not html:
        show_notification("Error", f"No se pudo cargar el contenido de {list_url}")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Buscar tarjetas de contenido
    cards = soup.find_all('li', class_='TPostMv') or soup.find_all('div', class_='TPost')
    
    if not cards:
        # Intentar con otro selector
        cards = soup.select('.MovieList.Rows li, .MovieList.Rows div.TPostMv')
    
    if not cards:
        show_notification("Sin Resultados", "No se encontró contenido en esta categoría.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    items_added = 0
    for card in cards:
        try:
            a_tag = card.find('a', href=True)
            if not a_tag:
                continue
            
            href = a_tag['href']
            
            # Determinar si es película o serie
            is_series = '/serie/' in href
            is_movie = '/pelicula/' in href
            
            # Para episodios recientes
            is_episode = '/episodio/' in href or '/temporada/' in href
            
            if not (is_series or is_movie or is_episode):
                continue
            
            url = href if href.startswith('http') else BASE_URL + href
            
            # Título
            img_tag = card.find('img')
            title = ""
            if img_tag and img_tag.get('alt'):
                title = img_tag['alt'].strip()
            
            if not title:
                h2_tag = card.find(['h2', 'h3'])
                title = h2_tag.get_text(strip=True) if h2_tag else a_tag.get_text(strip=True)
            
            title = clean_title(title)
            
            # Para episodios, extraer temporada/episodio
            season_num = None
            episode_num = None
            if is_episode:
                sxe_match = re.search(r'(\d+)x(\d+)', title)
                if sxe_match:
                    season_num = sxe_match.group(1)
                    episode_num = sxe_match.group(2)
            
            # Miniatura
            thumbnail = extract_thumbnail(img_tag)
            
            # Año
            year = ""
            year_span = card.find('span', class_='Year')
            if year_span:
                year = year_span.get_text(strip=True)
            if not year:
                year_match = re.search(r'(\d{4})', title)
                if year_match:
                    year = year_match.group(1)
            
            # Calidad
            quality = ""
            q_tag = card.find('span', class_='Qlty')
            if q_tag:
                quality = q_tag.get_text(strip=True)
            
            # Sinopsis/Descripción
            plot = ""
            description_div = card.find('div', class_='Description')
            if description_div:
                # Extraer todo el texto del div, incluyendo todos los párrafos
                plot = description_div.get_text(strip=True, separator=' ')
            
            # Crear item
            list_item = xbmcgui.ListItem(label=title)
            list_item.setArt({
                'thumb': thumbnail,
                'poster': thumbnail,
                'fanart': thumbnail
            })
            
            # Info tags
            info_labels = {
                'title': title,
                'year': year,
                'mediatype': 'movie' if is_movie else 'tvshow',
                'plot': plot
            }
            if quality:
                info_labels['rating'] = quality
            
            list_item.setInfo('video', info_labels)
            
            if is_series:
                # Serie - ir a temporadas
                callback_url = f"{sys.argv[0]}?action=seasons&url={quote_plus(url)}&title={quote_plus(title)}&thumbnail={quote_plus(thumbnail)}"
                is_folder = True
            elif is_episode:
                # Episodio - reproducible directamente
                list_item.setProperty('IsPlayable', 'true')
                ep_title = title
                if season_num and episode_num:
                    ep_title = f"{season_num}x{episode_num:02d} - {title}"
                    list_item.setLabel(ep_title)
                callback_url = f"{sys.argv[0]}?action=play&url={quote_plus(url)}&autoplay=1"
                is_folder = False
            else:
                # Película - reproducible directamente
                list_item.setProperty('IsPlayable', 'true')
                callback_url = f"{sys.argv[0]}?action=play&url={quote_plus(url)}&autoplay=1"
                is_folder = False
            
            xbmcplugin.addDirectoryItem(handle, callback_url, list_item, isFolder=is_folder)
            items_added += 1
            
        except Exception as e:
            log(f"Error procesando tarjeta: {str(e)}", xbmc.LOGWARNING)
            continue
    
    # Paginación - buscar enlace a siguiente página
    next_page = soup.find('a', class_='next page-numbers') or soup.find('a', class_='next')
    if next_page and next_page.get('href'):
        next_url = next_page['href']
        if next_url.startswith('http'):
            next_page_num = page + 1
        else:
            next_page_num = page + 1
        
        list_item = xbmcgui.ListItem(label=">> Página Siguiente >>")
        list_item.setArt({'thumb': 'DefaultFolder.png', 'poster': 'DefaultFolder.png'})
        next_callback = f"{sys.argv[0]}?action=list_all&type={content_type}&url={quote_plus(list_url)}&page={next_page_num}"
        # Usar la URL base sin page para la paginación
        base_list_url = re.sub(r'/page/\d+', '', list_url)
        next_callback = f"{sys.argv[0]}?action=list_all&type={content_type}&url={quote_plus(base_list_url)}&page={next_page_num}"
        xbmcplugin.addDirectoryItem(handle, next_callback, list_item, isFolder=True)
    
    if items_added == 0:
        show_notification("Sin Resultados", "No se encontró contenido.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    # Configurar vista estilo Netflix según el tipo
    if content_type == 'series':
        xbmcplugin.setContent(handle, 'tvshows')
    elif content_type == 'episodios':
        xbmcplugin.setContent(handle, 'episodes')
    else:
        xbmcplugin.setContent(handle, 'movies')
    
    xbmcplugin.endOfDirectory(handle)


# ===========================================================================
# TEMPORADAS Y EPISODIOS
# ===========================================================================

def list_seasons(series_url, series_title="", series_thumbnail=""):
    """Muestra el listado de temporadas de una serie."""
    handle = int(sys.argv[1])
    log(f"Listando temporadas para: {series_url}")
    
    html = get_html(series_url, timeout=12)
    next_data = extract_next_data(html)
    
    if not next_data:
        show_notification("Error", "No se pudieron obtener las temporadas.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    try:
        page_props = next_data.get('props', {}).get('pageProps', {})
        this_serie = page_props.get('thisSerie', {})
        seasons = this_serie.get('seasons', [])
        
        if not seasons:
            show_notification("Aviso", "Esta serie no contiene temporadas disponibles.")
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
        
        poster = this_serie.get('images', {}).get('poster', '') or series_thumbnail
        
        for season in seasons:
            season_num = season.get('number')
            if season_num is None or not season.get('episodes'):
                continue
            
            label = f"Temporada {season_num}" if season_num != 0 else "Especiales / Temporada 0"
            
            list_item = xbmcgui.ListItem(label=label)
            list_item.setArt({
                'thumb': poster,
                'poster': poster,
                'fanart': poster
            })
            list_item.setInfo('video', {
                'title': label,
                'season': season_num,
                'mediatype': 'season'
            })
            
            callback_url = f"{sys.argv[0]}?action=episodes&url={quote_plus(series_url)}&season={season_num}&title={quote_plus(series_title)}&thumbnail={quote_plus(poster)}"
            xbmcplugin.addDirectoryItem(handle, callback_url, list_item, isFolder=True)
        
        xbmcplugin.setContent(handle, 'seasons')
        xbmcplugin.endOfDirectory(handle)
        
    except Exception as e:
        log(f"Error procesando temporadas: {str(e)}", xbmc.LOGERROR)
        show_notification("Error", "Fallo al procesar listado de temporadas.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)


def list_episodes(series_url, season_num, series_title="", series_thumbnail=""):
    """Muestra los episodios de una temporada específica."""
    handle = int(sys.argv[1])
    log(f"Listando episodios para la temporada {season_num} de: {series_url}")
    
    html = get_html(series_url, timeout=12)
    next_data = extract_next_data(html)
    
    if not next_data:
        show_notification("Error", "No se pudieron obtener los episodios.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    try:
        page_props = next_data.get('props', {}).get('pageProps', {})
        this_serie = page_props.get('thisSerie', {})
        seasons = this_serie.get('seasons', [])
        
        target_season = None
        for s in seasons:
            if str(s.get('number')) == str(season_num):
                target_season = s
                break
        
        if not target_season or not target_season.get('episodes'):
            show_notification("Aviso", "No se encontraron episodios en esta temporada.")
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
        
        poster = this_serie.get('images', {}).get('poster', '') or series_thumbnail
        
        for ep in target_season.get('episodes', []):
            ep_num = ep.get('number', 1)
            title = ep.get('title') or f"Episodio {ep_num}"
            
            slug = ep.get('url', {}).get('slug', '')
            if not slug:
                continue
            
            # Convertir slug de API a URL de la web
            slug = slug.replace('seasons', 'temporada').replace('episodes', 'episodio').replace('series/', 'serie/')
            ep_url = f"{BASE_URL}/{slug}" if not slug.startswith('http') else slug
            
            ep_label = f"{season_num}x{ep_num:02d} - {title}"
            list_item = xbmcgui.ListItem(label=ep_label)
            
            thumb = ep.get('image') or poster
            list_item.setArt({
                'thumb': thumb,
                'poster': thumb,
                'fanart': thumb
            })
            list_item.setProperty('IsPlayable', 'true')
            list_item.setInfo('video', {
                'title': ep_label,
                'season': int(season_num),
                'episode': ep_num,
                'mediatype': 'episode'
            })
            
            callback_url = f"{sys.argv[0]}?action=play&url={quote_plus(ep_url)}&autoplay=1"
            xbmcplugin.addDirectoryItem(handle, callback_url, list_item, isFolder=False)
        
        xbmcplugin.setContent(handle, 'episodes')
        xbmcplugin.endOfDirectory(handle)
        
    except Exception as e:
        log(f"Error al listar episodios: {str(e)}", xbmc.LOGERROR)
        show_notification("Error", "Fallo al procesar listado de episodios.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)


# ===========================================================================
# REPRODUCCIÓN
# ===========================================================================

def _get_player_embed_url(player_page_url, content_url):
    """
    Obtiene la URL del embed del reproductor desde una URL de player.php.
    """
    player_html = get_html(player_page_url, referer=content_url, timeout=12)
    if not player_html:
        return None, None

    # Patrón 1: var url = 'https://streamwish.to/e/...'
    m = re.search(r"var\s+url\s*=\s*['\"]([^'\"]+)['\"]", player_html)
    if m:
        return m.group(1), player_html

    # Patrón 2: iframe con src
    m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', player_html, re.IGNORECASE)
    if m:
        return m.group(1), player_html

    # Patrón 3: buscar cualquier enlace https en el JS
    m = re.search(r'["\']((https?://(?:streamwish|filemoon|filemooon|doodstream|streamtape|voe|mixdrop)[^"\']+))["\']',
                  player_html, re.IGNORECASE)
    if m:
        return m.group(1), player_html

    # Patrón 4: buscar enlace en data o script tags
    soup = BeautifulSoup(player_html, 'html.parser')
    for script in soup.find_all('script'):
        script_text = script.string or ''
        m = re.search(r"(?:url|src|source|embed)\s*[=:]\s*['\"]?(https?://[^'\">\s]+)['\"]?",
                      script_text, re.IGNORECASE)
        if m:
            url = m.group(1)
            if any(d in url.lower() for d in ['streamwish', 'filemoon', 'dood', 'streamtape', 'voe', 'mixdrop', 'jwplayer', 'wishonly']):
                return url, player_html

    return None, player_html


def _try_play_option(option, content_url, handle):
    """
    Intenta reproducir una opción específica.
    Retorna True si tuvo éxito, False si falló.
    """
    player_page_url = option['player_url']
    server_name = option['server']
    log(f"[Autoplay] Intentando: {option['label']} => {player_page_url}")

    # PASO 1: Ir a player.php para obtener la URL del embed externo
    embed_url, _ = _get_player_embed_url(player_page_url, content_url)

    if not embed_url:
        embed_url = player_page_url

    log(f"[Autoplay] URL del embed obtenida: {embed_url}")

    # PASO 2: Resolver la URL del embed al stream final
    final_url = resolve_server(embed_url, server_name)

    if not final_url:
        log(f"[Autoplay] No se pudo resolver {server_name}", xbmc.LOGWARNING)
        return False

    log(f"[Autoplay] Reproduciendo URL final: {final_url}")
    play_item = xbmcgui.ListItem(path=final_url)
    
    # Configurar headers si la URL los incluye con pipe
    if '|' in final_url:
        url_part, headers_part = final_url.split('|', 1)
        play_item = xbmcgui.ListItem(path=url_part)
        play_item.setProperty('inputstream.adaptive.stream_headers', headers_part)
        play_item.setProperty('inputstream.adaptive.manifest_headers', headers_part)

    xbmcplugin.setResolvedUrl(handle, True, play_item)
    return True


def play(content_url, autoplay=False):
    """Visita la URL del contenido, resuelve el reproductor y lo reproduce en Kodi."""
    log(f"Preparando reproducción de contenido desde: {content_url}")

    html = get_html(content_url, timeout=12)
    next_data = extract_next_data(html)

    if not next_data:
        show_notification("Error de Datos", "No se pudo leer la información de los videos.")
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem())
        return

    try:
        page_props = next_data.get('props', {}).get('pageProps', {})

        # Buscar la sección de videos
        videos_data = None
        for key in ['thisMovie', 'episode', 'thisSerie', 'thisEpisode']:
            if key in page_props and 'videos' in page_props[key]:
                videos_data = page_props[key]['videos']
                break

        if not videos_data:
            for k, v in page_props.items():
                if isinstance(v, dict) and 'videos' in v:
                    videos_data = v['videos']
                    break

        if not videos_data or not isinstance(videos_data, dict):
            show_notification("Sin Enlaces", "No se encontraron enlaces de video disponibles.")
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem())
            return

        # Construir la lista de opciones de reproducción
        options = []
        for lang, list_vids in videos_data.items():
            if not list_vids or not isinstance(list_vids, list):
                continue
            for vid in list_vids:
                cyberlocker = vid.get('cyberlocker', 'Desconocido')
                quality = vid.get('quality', 'HD')
                player_url = vid.get('result', '')

                if player_url:
                    lang_display = {
                        'latino': 'Latino',
                        'spanish': 'Español',
                        'english': 'Inglés',
                        'subtitulado': 'Subtitulado'
                    }.get(lang.lower(), lang.upper())

                    options.append({
                        'label': f"[{lang_display}] {cyberlocker.capitalize()} ({quality})",
                        'player_url': player_url,
                        'server': cyberlocker.lower(),
                        'lang': lang_display,
                        'lang_priority': 0 if lang.lower() == 'latino' else (1 if lang.lower() in ['spanish', 'español'] else 2),
                        'quality': quality
                    })

        if not options:
            show_notification("Sin Servidores", "No hay servidores de reproducción disponibles.")
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem())
            return

        handle = int(sys.argv[1])

        # MODO AUTOPLAY: Intentar automáticamente priorizando latino
        if autoplay:
            options_sorted = sorted(options, key=lambda x: x['lang_priority'])
            
            log(f"[Autoplay] Intentando {len(options_sorted)} opciones, priorizando latino")

            for i, option in enumerate(options_sorted):
                log(f"[Autoplay] Opción {i+1}/{len(options_sorted)}: {option['label']}")
                success = _try_play_option(option, content_url, handle)
                if success:
                    return
            
            show_notification(
                "Autoplay Fallido",
                "No se pudo reproducir ningún servidor.",
                time_ms=1500
            )
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            return

        # MODO MANUAL: Mostrar diálogo de selección al usuario
        dialog = xbmcgui.Dialog()
        labels = [opt['label'] for opt in options]
        selected_index = dialog.select("Selecciona idioma y servidor", labels)

        if selected_index == -1:
            log("Reproducción cancelada por el usuario.")
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            return

        selected = options[selected_index]
        success = _try_play_option(selected, content_url, handle)
        
        if not success:
            show_notification(
                "Error de Servidor",
                f"No se pudo obtener el stream de '{selected['server'].capitalize()}'.",
                time_ms=2000
            )
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())

    except Exception as e:
        log(f"Error general en play(): {str(e)}", xbmc.LOGERROR)
        show_notification("Error Inesperado", f"Error: {str(e)}")
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), False, xbmcgui.ListItem())


# ===========================================================================
# BÚSQUEDA
# ===========================================================================

def search(query=""):
    """Realiza la búsqueda en el sitio y muestra los resultados en Kodi."""
    if not query:
        keyboard = xbmc.Keyboard('', f"{ADDON_NAME} - ¿Qué deseas buscar?")
        keyboard.doModal()
        if keyboard.isConfirmed():
            query = keyboard.getText().strip()
        else:
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return
    
    if not query:
        xbmcgui.Dialog().ok(ADDON_NAME, "No ingresaste ningún texto de búsqueda.")
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return
    
    search_url = f"{BASE_URL}/search?q={quote_plus(query)}"
    log(f"Iniciando búsqueda para: {query}")
    
    handle = int(sys.argv[1])
    html = get_html(search_url, timeout=12)
    
    if not html:
        show_notification("Error", "No se pudo realizar la búsqueda.")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.find_all('li', class_='TPostMv') or soup.find_all('div', class_='TPost')
    
    results = []
    for card in cards:
        try:
            a_tag = card.find('a', href=True)
            if not a_tag:
                continue
            
            href = a_tag['href']
            if '/pelicula/' not in href and '/serie/' not in href:
                continue
            
            url = href if href.startswith('http') else BASE_URL + href
            
            img_tag = card.find('img')
            title = ""
            if img_tag and img_tag.get('alt'):
                title = img_tag['alt'].strip()
            
            if not title:
                h2_tag = card.find(['h2', 'h3'])
                title = h2_tag.get_text(strip=True) if h2_tag else a_tag.get_text(strip=True)
            
            title = clean_title(title)
            thumbnail = extract_thumbnail(img_tag)
            
            # Sinopsis/Descripción
            plot = ""
            description_div = card.find('div', class_='Description')
            if description_div:
                # Extraer todo el texto del div, incluyendo todos los párrafos
                plot = description_div.get_text(strip=True, separator=' ')
            
            results.append({
                'title': title,
                'url': url,
                'thumbnail': thumbnail,
                'is_series': '/serie/' in href,
                'plot': plot
            })
        except Exception as e:
            log(f"Error procesando tarjeta de resultado: {str(e)}", xbmc.LOGWARNING)
            continue
    
    if not results:
        dialog = xbmcgui.Dialog()
        dialog.ok("Sin Resultados", f"No se encontraron películas o series para: '{query}'")
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    
    for item in results:
        list_item = xbmcgui.ListItem(label=item['title'])
        list_item.setArt({
            'thumb': item['thumbnail'],
            'poster': item['thumbnail'],
            'fanart': item['thumbnail']
        })
        list_item.setInfo('video', {
            'title': item['title'],
            'mediatype': 'movie' if not item['is_series'] else 'tvshow',
            'plot': item.get('plot', '')
        })
        
        if item['is_series']:
            callback_url = f"{sys.argv[0]}?action=seasons&url={quote_plus(item['url'])}&title={quote_plus(item['title'])}&thumbnail={quote_plus(item['thumbnail'])}"
            is_folder = True
        else:
            list_item.setProperty('IsPlayable', 'true')
            callback_url = f"{sys.argv[0]}?action=play&url={quote_plus(item['url'])}&autoplay=1"
            is_folder = False
        
        xbmcplugin.addDirectoryItem(handle, callback_url, list_item, isFolder=is_folder)
    
    xbmcplugin.setContent(handle, 'movies')
    xbmcplugin.endOfDirectory(handle)


# ===========================================================================
# PUNTO DE ENTRADA
# ===========================================================================

def main():
    """Punto de entrada principal del addon."""
    paramstring = sys.argv[2] if len(sys.argv) > 2 else ''
    params = dict(parse_qsl(paramstring.lstrip('?')))
    
    action = params.get('action')
    log(f"Acción recibida: {action}, params: {dict((k,v[:50] if len(v)>50 else v) for k,v in params.items())}")
    
    if not action:
        # Menú principal estilo Netflix
        build_main_menu()
    
    elif action == 'sub_menu':
        type_name = params.get('type', 'peliculas')
        base_url = params.get('url', BASE_URL + '/peliculas/')
        build_sub_menu(type_name, base_url)
    
    elif action == 'trends_menu':
        build_trends_menu()
    
    elif action == 'genres':
        build_genres_menu()
    
    elif action == 'list_all':
        list_url = params.get('url', '')
        content_type = params.get('type', 'peliculas')
        page = int(params.get('page', '1'))
        if list_url:
            list_content(list_url, content_type, page)
    
    elif action == 'seasons':
        series_url = params.get('url')
        series_title = params.get('title', '')
        series_thumbnail = params.get('thumbnail', '')
        if series_url:
            list_seasons(series_url, series_title, series_thumbnail)
    
    elif action == 'episodes':
        series_url = params.get('url')
        season_num = params.get('season')
        series_title = params.get('title', '')
        series_thumbnail = params.get('thumbnail', '')
        if series_url and season_num is not None:
            list_episodes(series_url, season_num, series_title, series_thumbnail)
    
    elif action == 'play':
        content_url = params.get('url')
        if content_url:
            autoplay = params.get('autoplay', '0') == '1'
            play(content_url, autoplay=autoplay)
    
    elif action == 'search':
        query = params.get('q', '')
        search(query)


if __name__ == '__main__':
    main()