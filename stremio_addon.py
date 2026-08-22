"""Stremio HTTP addon for PoseidonHD.

The addon exposes the standard Stremio manifest, catalog, meta and stream
routes. Content IDs are opaque, URL-safe encodings of PoseidonHD page URLs.
"""

import base64
import hashlib
import json
import logging
import os
import random
import re
import string
import struct
import time
from urllib.parse import quote_plus, unquote_plus, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, jsonify, request

BASE_URL = "https://www.poseidonhd2.co"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def encode_id(url):
    return "poseidon_" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def decode_id(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode()).decode()


def fetch(url, referer=None):
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def absolute_url(value):
    return urljoin(BASE_URL + "/", value or "")


def entry_poster(entry):
    images = entry.get("images") or {}
    image_values = images.values() if isinstance(images, dict) else []
    candidates = [
        images.get("poster") if isinstance(images, dict) else None,
        images.get("cover") if isinstance(images, dict) else None,
        images.get("thumbnail") if isinstance(images, dict) else None,
        entry.get("poster"),
        entry.get("image"),
        entry.get("thumbnail"),
        *image_values,
    ]
    for value in candidates:
        if isinstance(value, dict):
            value = value.get("url") or value.get("src")
        if isinstance(value, str) and value.strip():
            return absolute_url(value.strip())
    return ""


def thumbnail(tag):
    if not tag:
        return ""
    value = tag.get("data-src") or tag.get("data-lazy-src") or tag.get("src") or ""
    if not value:
        srcset = tag.get("srcset") or tag.get("srcSet") or ""
        if srcset:
            value = srcset.split(",")[0].split(" ")[0]
    if "url=" in value:
        value = value.split("url=", 1)[1].split("&", 1)[0]
    value = absolute_url(value)
    if value.startswith("//"):
        value = "https:" + value
    return value


def clean_title(value):
    value = re.sub(r"^(Pelicula|Serie)\s*", "", value or "", flags=re.I)
    return re.sub(r"\s*-\s*(Online|TV|4K|HD|FullBluRay)\s*$", "", value, flags=re.I).strip()


def card_to_item(card):
    link = card.find("a", href=True)
    if not link:
        return None
    url = absolute_url(link["href"])
    if "/pelicula/" not in url and "/serie/" not in url and "/episodio/" not in url:
        return None
    image = card.find("img")
    title = image.get("alt", "") if image else ""
    if not title:
        heading = card.find(["h2", "h3"])
        title = heading.get_text(" ", strip=True) if heading else link.get_text(" ", strip=True)
    plot = card.find(class_="Description")
    year = card.find(class_="Year")
    return {
        "id": encode_id(url),
        "url": url,
        "name": clean_title(title),
        "poster": thumbnail(image),
        "description": plot.get_text(" ", strip=True) if plot else "",
        "year": year.get_text(strip=True) if year else "",
        "type": "series" if "/serie/" in url else "movie",
    }


def parse_cards(html):
    """Extraccion robusta: recorre todos los enlaces a peliculas/series y
    busca el contenedor con la imagen aunque cambien las clases del tema."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    items = []
    for link in soup.find_all("a", href=True):
        href = absolute_url(link["href"])
        path = urlparse(href).path
        if "/pelicula/" not in path and "/serie/" not in path:
            continue
        if href.rstrip("/") in seen:
            continue
        # Buscar contenedor con imagen (li, article o div cercano)
        container = link
        image = None
        for _ in range(5):
            if container is None:
                break
            image = container.find("img")
            if image:
                break
            container = container.parent
        title = ""
        if image:
            title = image.get("alt", "") or image.get("title", "")
        if not title:
            heading = link.find(["h2", "h3"]) or (container.find(["h2", "h3"]) if container else None)
            title = heading.get_text(" ", strip=True) if heading else link.get_text(" ", strip=True)
        if not title:
            continue
        plot_el = container.find(class_=re.compile(r"[Dd]escription|[Cc]ontent", re.I)) if container else None
        year_el = container.find(class_=re.compile(r"[Yy]ear|[Dd]ate", re.I)) if container else None
        seen.add(href.rstrip("/"))
        items.append({
            "id": encode_id(href),
            "url": href,
            "name": clean_title(title),
            "poster": thumbnail(image),
            "description": plot_el.get_text(" ", strip=True) if plot_el else "",
            "year": year_el.get_text(strip=True) if year_el else "",
            "type": "series" if "/serie/" in path else "movie",
        })
    return items


def next_data(url):
    soup = BeautifulSoup(fetch(url), "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}, soup
    try:
        return json.loads(script.string), soup
    except json.JSONDecodeError:
        return {}, soup


def manifest():
    catalog_extras = [
        {"name": "search", "isRequired": False},
        {"name": "skip", "isRequired": False},
    ]
    return {
        "id": "community.poseidonhd.stremio",
        "version": "1.4.0",
        "name": "PoseidonHD",
        "description": "Peliculas y series de PoseidonHD",
        "resources": ["catalog", "meta", "stream"],
        "types": ["movie", "series"],
        "idPrefixes": ["poseidon_"],
        "catalogs": [
            {"type": "movie", "id": "poseidon_movies", "name": "PoseidonHD Peliculas", "extra": catalog_extras},
            {"type": "series", "id": "poseidon_series", "name": "PoseidonHD Series", "extra": catalog_extras},
            {"type": "movie", "id": "poseidon_movies_day", "name": "Peliculas - Tendencias del dia", "extra": catalog_extras},
            {"type": "movie", "id": "poseidon_movies_week", "name": "Peliculas - Tendencias de la semana", "extra": catalog_extras},
            {"type": "series", "id": "poseidon_series_day", "name": "Series - Tendencias del dia", "extra": catalog_extras},
            {"type": "series", "id": "poseidon_series_week", "name": "Series - Tendencias de la semana", "extra": catalog_extras},
        ],
    }


@app.get("/manifest.json")
def manifest_route():
    return jsonify(manifest())


def next_data_items(html, content_type):
    """Extrae items directamente del __NEXT_DATA__ (posters TMDB garantizados)."""
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []
    try:
        props = json.loads(script.string).get("props", {}).get("pageProps", {})
    except json.JSONDecodeError:
        return []
    key = "movies" if content_type == "movie" else "series"
    entries = props.get(key) or []
    items = []
    for entry in entries if isinstance(entries, list) else []:
        url = entry.get("url") or {}
        slug = url.get("slug") if isinstance(url, dict) else url
        if not slug:
            continue
        # El slug usa movies/ y series/, pero las paginas reales son
        # pelicula/ y serie/
        slug = re.sub(r"^/?movies/", "pelicula/", str(slug).lstrip("/"))
        slug = re.sub(r"^/?series/", "serie/", slug)
        href = absolute_url(slug)
        titles = entry.get("titles") or {}
        release = str(entry.get("releaseDate") or "")
        items.append({
            "id": encode_id(href),
            "type": content_type,
            "name": clean_title(titles.get("name") or ""),
            "poster": entry_poster(entry),
            "description": entry.get("overview") or "",
            "year": release[:4] if release else "",
        })
    return items


PAGE_SIZE = 30


@app.get("/catalog/<content_type>/<catalog_id>.json")
@app.get("/catalog/<content_type>/<catalog_id>/search=<query>.json")
def catalog_route(content_type, catalog_id, query=""):
    skip = request.args.get("skip") or ""
    # Stremio tambien manda skip dentro del path como search=&skip=
    match = re.search(r"skip=(\d+)", request.full_path)
    if not skip and match:
        skip = match.group(1)
    page = int(skip) // PAGE_SIZE + 1 if skip.isdigit() else 1

    urls = []
    if query:
        query_clean = unquote_plus(query)
        query_clean = re.sub(r"&skip=\d+", "", query_clean).strip()
        urls.append(f"{BASE_URL}/search?q={quote_plus(query_clean)}&page={page}")
        urls.append(f"{BASE_URL}/search?q={quote_plus(query_clean)}")
    else:
        section = "peliculas" if content_type == "movie" else "series"
        trend_period = ""
        if catalog_id.endswith("_day"):
            trend_period = "dia"
        elif catalog_id.endswith("_week"):
            trend_period = "semana"
        trend_path = f"/tendencias/{trend_period}" if trend_period else ""
        urls.append(f"{BASE_URL}/{section}{trend_path}/page/{page}/")
        urls.append(f"{BASE_URL}/{section}{trend_path}/")
        if trend_period:
            urls.append(f"{BASE_URL}/{section}/page/{page}/")
        urls.append(f"{BASE_URL}/{section}/?page={page}")
        urls.append(f"{BASE_URL}/{section}/")

    metas = []
    for url in urls:
        try:
            html = fetch(url)
        except requests.RequestException:
            continue
        # Prioridad 1: datos estructurados __NEXT_DATA__ (posters TMDB)
        metas = next_data_items(html, content_type)
        # Prioridad 2: scraping generico de tarjetas
        if not metas:
            metas = [item for item in parse_cards(html) if item["type"] == content_type]
        if metas:
            break
    return jsonify({"metas": [{key: item[key] for key in ("id", "type", "name", "poster", "description", "year")} for item in metas]})


def series_videos(url):
    data, _ = next_data(url)
    props = data.get("props", {}).get("pageProps", {})
    serie = props.get("thisSerie", {})
    return serie, [episode for season in serie.get("seasons", []) for episode in season.get("episodes", [])]


@app.get("/meta/<content_type>/<content_id>.json")
def meta_route(content_type, content_id):
    try:
        url = decode_id(content_id.removeprefix("poseidon_"))
        data, soup = next_data(url)
    except (ValueError, requests.RequestException):
        return jsonify({"meta": {"id": content_id, "type": content_type, "name": "PoseidonHD"}})

    item = card_to_item(soup) or {"name": soup.title.get_text(strip=True) if soup.title else "PoseidonHD", "poster": "", "description": "", "year": ""}
    meta = {"id": content_id, "type": content_type, "name": item["name"], "poster": item.get("poster", ""), "description": item.get("description", ""), "year": item.get("year", "")}
    if content_type == "series":
        props = data.get("props", {}).get("pageProps", {})
        serie = props.get("thisSerie", {})
        meta["poster"] = entry_poster(serie) or meta["poster"]
        meta["videos"] = [
            {"id": encode_id(absolute_url(ep.get("url", {}).get("slug", "").replace("series/", "serie/").replace("seasons", "temporada").replace("episodes", "episodio"))), "season": season.get("number", 1), "episode": ep.get("number", 1), "title": ep.get("title") or f"Episodio {ep.get('number', 1)}", "thumbnail": ep.get("image") or meta["poster"]}
            for season in serie.get("seasons", []) for ep in season.get("episodes", []) if ep.get("url", {}).get("slug")
        ]
    return jsonify({"meta": meta})


def extract_embed(player_url, content_url):
    html = fetch(player_url, content_url)
    match = re.search(r"var\s+url\s*=\s*['\"]([^'\"]+)", html)
    if match:
        return absolute_url(match.group(1))
    iframe = BeautifulSoup(html, "html.parser").find("iframe", src=True)
    return absolute_url(iframe["src"]) if iframe else player_url


def _base36(value):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value:
        value, rest = divmod(value, 36)
        out = digits[rest] + out
    return out


def jsunpack(html):
    """Desempaqueta variantes del packer de Dean Edwards."""
    match = re.search(r"eval\(function\(p,a,c,k,e,(?:r|d)\)\{.*?return p", html, re.S)
    if not match:
        return html
    inner = re.search(r"'((?:[^'\\]|\\.)*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'((?:[^'\\]|\\.)*)'", html[match.start():], re.S)
    if not inner:
        return html
    packed = inner.group(1).replace("\\'", "'").replace("\\\\", "\\")
    radix, count = int(inner.group(2)), int(inner.group(3))
    words = inner.group(4).replace("\\'", "'").split("|")

    def decode_token(token):
        digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        value = 0
        try:
            for char in token:
                value = value * radix + digits.index(char)
            return value
        except ValueError:
            return -1

    def replace_token(found):
        index = decode_token(found.group(0))
        return words[index] if 0 <= index < len(words) and words[index] else found.group(0)

    return re.sub(r"\b\w+\b", replace_token, packed)


# Dominios que nunca son streams de video (analytics, ads, CDNs de scripts)
NON_MEDIA_DOMAINS = (
    "googletagmanager.com", "google-analytics.com", "doubleclick.net",
    "googleadservices.com", "googlesyndication.com", "facebook.net",
    "twitter.com", "recaptcha", "cloudflare", "jsdelivr", "unpkg.com",
    "jquery", "bootstrap", "fontawesome", "gstatic.com", "adservice",
    "yandex", "metrika", "histats", "statcounter", "addthis",
    "sharethis", "onesignal", "pushnami", "exoclick", "juicyads",
    "popads", "propellerads", "adsterra", "clickadu", "hilltopads",
)


def _clean_stream_url(value):
    return (value.replace("\\u0026", "&").replace("\\/", "/")
            .replace("\\u003F", "?").replace("\\u003d", "="))


def find_stream_in_html(html):
    # Patrones que exigen extension de video: seguros sobre cualquier HTML
    media_patterns = [
        r'"(?:file|hls\d?|source|src)"\s*:\s*"(https?://[^" ]+\.(?:m3u8|mp4)(?:\?[^" ]*)?)"',
        r"(?:file|hls|source|src)\s*[:=]\s*['\"](https?://[^'\"]+\.(?:m3u8|mp4)(?:\?[^'\"]*)?)",
        r"(https?://[^\s\"'<>]+\.m3u8(?:\?[^\s\"'<>]*)?)",
        r"(https?://[^\s\"'<>]+\.mp4(?:\?[^\s\"'<>]*)?)",
    ]
    # Patrones genericos: solo se aceptan si el dominio no es de scripts/ads
    generic_patterns = [
        r'"(?:file|hls\d?|source|src)"\s*:\s*"(https?://[^" ]+)"',
        r"(?:file|hls|source|src)\s*[:=]\s*['\"](https?://[^'\"]+)",
    ]
    for html_variant in (html, jsunpack(html)):
        for pattern in media_patterns:
            match = re.search(pattern, html_variant, re.I)
            if match:
                return _clean_stream_url(match.group(1))
        for pattern in generic_patterns:
            for match in re.finditer(pattern, html_variant, re.I):
                candidate = match.group(1)
                low = candidate.lower()
                # Rechazar scripts (.js), imagenes y dominios de analitica/ads
                if re.search(r"\.(js|css|png|jpe?g|gif|svg|ico|woff2?)(\?|$)", low):
                    continue
                if any(domain in low for domain in NON_MEDIA_DOMAINS):
                    continue
                return _clean_stream_url(candidate)
    return None


STREAMWISH_MIRRORS = ["https://wishonly.site", "https://swhoi.com"]


def _solve_altcha(session, html):
    """Resuelve el captcha ALTCHA (proof-of-work) de los espejos de Voe."""
    challenge_match = re.search(r'<altcha-widget[^>]*challenge="([^"]+)"', html)
    token_match = re.search(r'name="_token"\s+value="([^"]+)"', html)
    form_match = re.search(r'<form[^>]*action="([^"]+)"', html)
    if not (challenge_match and token_match and form_match):
        return None
    try:
        challenge_data = session.get(challenge_match.group(1), timeout=15).json()
    except (requests.RequestException, ValueError):
        return None
    # Esquema PBKDF2 del widget: password = nonce(hex) + contador uint32 BE,
    # la clave derivada debe comenzar con keyPrefix.
    params = challenge_data.get("parameters") or {}
    nonce_hex = params.get("nonce", "")
    salt_hex = params.get("salt", "")
    prefix = params.get("keyPrefix", "")
    cost = int(params.get("cost", 10000))
    key_length = int(params.get("keyLength", 32))
    if not (nonce_hex and prefix):
        return None
    try:
        nonce_bytes = bytes.fromhex(nonce_hex)
        salt_bytes = bytes.fromhex(salt_hex) if salt_hex else b""
    except ValueError:
        return None
    number = None
    for candidate in range(1000000):
        password = nonce_bytes + struct.pack(">I", candidate)
        derived = hashlib.pbkdf2_hmac("sha256", password, salt_bytes,
                                      cost, dklen=key_length)
        if derived.hex().startswith(prefix):
            number = candidate
            break
    if number is None:
        return None
    payload = {
        "algorithm": params.get("algorithm", "PBKDF2/SHA-256"),
        "challenge": challenge_data.get("signature", ""),
        "number": number,
        "salt": salt_hex,
        "signature": challenge_data.get("signature", ""),
    }
    altcha_token = base64.b64encode(json.dumps(payload).encode()).decode()
    response = session.post(
        form_match.group(1),
        data={"_token": token_match.group(1), "access": "0", "altcha": altcha_token},
        headers={"Referer": form_match.group(1)},
        timeout=15,
    )
    if response.status_code == 200 and "altcha-widget" not in response.text:
        return response.text
    return None


def resolve_voe(embed_url):
    """Resuelve enlaces de voe.sx (varias estrategias segun la plantilla)."""
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://voe.sx/"})
    response = session.get(embed_url, timeout=15)
    html = response.text
    # Voe a veces sirve una pagina intermedia que redirige a un dominio espejo
    redirect = re.search(r"window\.location\.href\s*=\s*'([^']+)'", html)
    if redirect and "voe." not in urlparse(redirect.group(1)).netloc:
        response = session.get(redirect.group(1), timeout=15)
        html = response.text
        # El espejo puede pedir verificacion humana (ALTCHA): la resolvemos
        if "altcha-widget" in html:
            solved = _solve_altcha(session, html)
            if solved:
                html = solved
    # Estrategia 1: fuentes con URL en base64 (empiezan con aHR0)
    for match in re.finditer(r"(?:mp4|hls)['\"]?\s*:\s*['\"](aHR0[^'\"]+)['\"]", html):
        try:
            return base64.b64decode(match.group(1)).decode()
        except Exception:
            continue
    # Estrategia 2: let <hex>='<base64>' con JSON invertido {"file": ...}
    match = re.search(r"let\s+[0-9a-f]+\s*=\s*'([A-Za-z0-9+/=]+)'", html)
    if match:
        try:
            decoded = json.loads(base64.b64decode(match.group(1)).decode()[::-1])
            if decoded.get("file"):
                return decoded["file"]
        except Exception:
            pass
    # Estrategia 3: cualquier m3u8/mp4 directo o dentro del JS desempaquetado
    return find_stream_in_html(html)


def resolve_dood(embed_url):
    """Resuelve enlaces de doodstream y clones (pass_md5 + token)."""
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://www.poseidonhd2.co/"})
    response = session.get(embed_url, timeout=15)
    # doodstream.com y similares redirigen a su dominio real de reproduccion
    final_url = response.url
    parsed = urlparse(final_url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    html = response.text
    match = re.search(r"\$\.\s*get\('(/pass_md5/[^']+)'", html) or re.search(
        r"['\"](/pass_md5/[^'\"]+)['\"]", html)
    if not match:
        return find_stream_in_html(html)
    md5_response = session.get(host + match.group(1),
                               headers={"Referer": final_url}, timeout=15)
    video_base = md5_response.text.strip() if md5_response.status_code == 200 else ""
    if not video_base.startswith("http"):
        return None
    token = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    expiry = str(int(time.time() * 1000))
    return f"{video_base}{token}?token={token}&expiry={expiry}"


def resolve(embed_url, content_url):
    if re.search(r"\.(m3u8|mp4)(\?|$)", embed_url, re.I):
        return embed_url
    parsed = urlparse(embed_url)
    netloc = parsed.netloc.lower()
    # Resolutores especificos por servidor
    if "voe." in netloc or netloc.startswith("voe"):
        return resolve_voe(embed_url)
    if "dood" in netloc or "dsvplay" in netloc or "d000d" in netloc:
        return resolve_dood(embed_url)
    referer = embed_url.split("|", 1)[0]
    if "|" in embed_url:
        embed_url = referer
        parsed = urlparse(embed_url)
    candidates = [embed_url]
    # Streamwish sirve una pagina "Loading..." con main.js que redirige a un
    # espejo; probamos espejos conocidos con el mismo path.
    if "streamwish" in parsed.netloc or "wish" in parsed.netloc:
        candidates += [mirror + parsed.path + ("?" + parsed.query if parsed.query else "") for mirror in STREAMWISH_MIRRORS]
    for candidate in candidates:
        try:
            session = requests.Session()
            session.headers.update({**HEADERS, "Referer": referer})
            session.get(f"{parsed.scheme}://{parsed.netloc}/", timeout=8)
            response = session.get(candidate, timeout=15)
            response.raise_for_status()
            html = response.text
        except requests.RequestException:
            continue
        stream_url = find_stream_in_html(html)
        if stream_url:
            return stream_url
    return None


def _proxy_headers(target_url, referer):
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    parsed = urlparse(target_url)
    if parsed.scheme == "https":
        headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return headers


def _rewrite_playlist(text, target_url, referer):
    """Reescribe una playlist HLS apuntando cada recurso al proxy local."""
    base = request.base_url
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        if stripped.startswith("#"):
            # Solo se reescribe el atributo URI; otros como CODECS quedan intactos
            def replace_uri(m):
                value = m.group(1)
                absolute = urljoin(target_url, value)
                return 'URI="{}?{}"'.format(
                    base, urlencode({"url": absolute, "referer": referer}))
            line = re.sub(r'URI="([^"]*)"', replace_uri, line)
            lines.append(line)
            continue
        absolute = urljoin(target_url, stripped)
        lines.append(f"{base}?{urlencode({'url': absolute, 'referer': referer})}")
    return "\n".join(lines)


@app.route("/proxy")
def proxy_route():
    """Proxy de HLS/MP4: agrega CORS y las cabeceras (Referer/UA) que los
    CDNs exigen, permitiendo la reproduccion directa dentro de Stremio."""
    target_url = request.args.get("url", "")
    referer = request.args.get("referer", "")
    if not target_url.startswith("http"):
        return ("URL invalida", 400)
    range_header = request.headers.get("Range")
    headers = _proxy_headers(target_url, referer)
    if range_header:
        headers["Range"] = range_header
    try:
        upstream = requests.get(target_url, headers=headers,
                                stream=True, timeout=30)
    except requests.RequestException as exc:
        return (f"Error de upstream: {exc}", 502)

    content_type = upstream.headers.get("Content-Type", "")
    if "mpegurl" in content_type or target_url.split("?")[0].endswith(".m3u8"):
        playlist = _rewrite_playlist(upstream.text, target_url, referer)
        return Response(playlist, mimetype="application/vnd.apple.mpegurl",
                        headers={"Access-Control-Allow-Origin": "*"})

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Accept-Ranges": "bytes",
    }
    for key in ("Content-Length", "Content-Range"):
        if key in upstream.headers:
            response_headers[key] = upstream.headers[key]
    status = 206 if range_header and "Content-Range" in response_headers else 200
    return Response(generate(), status=status, content_type=content_type or "video/mp4",
                    headers=response_headers)


@app.get("/stream/<content_type>/<content_id>.json")
def stream_route(content_type, content_id):
    try:
        content_url = decode_id(content_id.removeprefix("poseidon_"))
        data, _ = next_data(content_url)
    except (ValueError, requests.RequestException):
        return jsonify({"streams": []})
    props = data.get("props", {}).get("pageProps", {})
    videos = next((value.get("videos") for value in props.values() if isinstance(value, dict) and value.get("videos")), {})
    streams = []
    for language, options in videos.items() if isinstance(videos, dict) else []:
        for option in options or []:
            player_url = option.get("result")
            if not player_url:
                continue
            try:
                embed = extract_embed(player_url, content_url)
                stream_url = resolve(embed, content_url)
            except requests.RequestException:
                embed = player_url
                stream_url = None
            label = f"{language} - {option.get('quality', 'HD')}"
            source = option.get("cyberlocker", "PoseidonHD")
            if stream_url:
                # Se sirve a traves del proxy local del addon: resuelve CORS
                # y las cabeceras Referer/User-Agent que exigen los CDNs.
                referer = embed.split("|", 1)[0]
                proxied = f"{request.host_url.rstrip('/')}/proxy?" + urlencode(
                    {"url": stream_url, "referer": referer})
                streams.append({
                    "name": source,
                    "title": label,
                    "url": proxied,
                    "behaviorHints": {"notWebReady": True},
                })
    return jsonify({"streams": streams})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "7000")))