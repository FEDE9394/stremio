"""Stremio HTTP addon for PoseidonHD.

The addon exposes the standard Stremio manifest, catalog, meta and stream
routes. Content IDs are opaque, URL-safe encodings of PoseidonHD page URLs.
"""

import base64
import json
import logging
import os
import re
from urllib.parse import quote_plus, unquote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

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
        "version": "1.3.0",
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
        images = entry.get("images") or {}
        titles = entry.get("titles") or {}
        release = str(entry.get("releaseDate") or "")
        items.append({
            "id": encode_id(href),
            "type": content_type,
            "name": clean_title(titles.get("name") or ""),
            "poster": images.get("poster") or "",
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
        meta["poster"] = serie.get("images", {}).get("poster", "") or meta["poster"]
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
    """Desempaqueta scripts ofuscados p,a,c,k,e,d (streamwish, filemoon, etc.).
    Soporta radix decimal y base 36."""
    match = re.search(
        r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.+?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)",
        html, re.S)
    if not match:
        return html
    packed, radix, count, words = match.group(1), int(match.group(2)), int(match.group(3)), match.group(4).split("|")
    unpacked = packed
    for i in range(count - 1, -1, -1):
        if i < len(words) and words[i]:
            token = _base36(i) if radix == 36 else str(i)
            unpacked = re.sub(r"\b%s\b" % re.escape(token), lambda m, word=words[i]: word, unpacked)
    return unpacked


def find_stream_in_html(html):
    patterns = [
        r'"(?:file|hls\d?|source|src)"\s*:\s*"(https?://[^" ]+\.(?:m3u8|mp4)(?:\?[^" ]*)?)"',
        r"(?:file|hls|source|src)\s*[:=]\s*['\"](https?://[^'\"]+\.(?:m3u8|mp4)(?:\?[^'\"]*)?)",
        r'"(?:file|hls\d?|source|src)"\s*:\s*"(https?://[^" ]+)"',
        r"(?:file|hls|source|src)\s*[:=]\s*['\"](https?://[^'\"]+)",
        r"(https?://[^\s\"'<>]+\.m3u8(?:\?[^\s\"'<>]*)?)",
        r"(https?://[^\s\"'<>]+\.mp4(?:\?[^\s\"'<>]*)?)",
    ]
    for html_variant in (html, jsunpack(html)):
        for pattern in patterns:
            match = re.search(pattern, html_variant, re.I)
            if match:
                return match.group(1).replace("\\u0026", "&").replace("\\/", "/")
    return None


STREAMWISH_MIRRORS = ["https://wishonly.site", "https://swhoi.com"]


def resolve(embed_url, content_url):
    if re.search(r"\.(m3u8|mp4)(\?|$)", embed_url, re.I):
        return embed_url
    parsed = urlparse(embed_url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    candidates = [embed_url]
    # Streamwish sirve una pagina "Loading..." con main.js que redirige a un
    # espejo; probamos espejos conocidos con el mismo path.
    if "streamwish" in parsed.netloc or "wish" in parsed.netloc:
        candidates += [mirror + parsed.path + ("?" + parsed.query if parsed.query else "") for mirror in STREAMWISH_MIRRORS]
    for candidate in candidates:
        try:
            html = fetch(candidate, referer)
        except requests.RequestException:
            continue
        stream_url = find_stream_in_html(html)
        if stream_url:
            return stream_url
    return None


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
                # Stream directo: se reproduce dentro de Stremio, sin navegador ni propagandas
                parsed = urlparse(stream_url)
                referer = f"{parsed.scheme}://{parsed.netloc}/"
                streams.append({
                    "name": source,
                    "title": label,
                    "url": stream_url,
                    "behaviorHints": {
                        "notWebReady": True,
                        "proxyHeaders": {
                            "request": {
                                "User-Agent": USER_AGENT,
                                "Referer": referer,
                            }
                        },
                    },
                })
    return jsonify({"streams": streams})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "7000")))
