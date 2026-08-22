# -*- coding: utf-8 -*-
# -*- Channel PoseidonHD -*-
# -*- Created for Alfa-addon -*-
# -*- By the Alfa Develop Group -*-

import sys
import threading
PY3 = False
if sys.version_info[0] >= 3: PY3 = True; unicode = str; unichr = chr; long = int; _dict = dict

from lib import AlfaChannelHelper
if not PY3: _dict = dict; from AlfaChannelHelper import dict
from AlfaChannelHelper import DictionaryAllChannel
from AlfaChannelHelper import re, traceback, time, base64, xbmcgui
from AlfaChannelHelper import Item, servertools, scrapertools, jsontools, get_thumb, config, logger, filtertools, autoplay
from core import downloadtools

IDIOMAS = AlfaChannelHelper.IDIOMAS
list_language = list(set(IDIOMAS.values()))
list_quality_movies = AlfaChannelHelper.LIST_QUALITY_MOVIES
list_quality_tvshow = AlfaChannelHelper.LIST_QUALITY_TVSHOW
list_quality = list_quality_movies + list_quality_tvshow
list_servers = AlfaChannelHelper.LIST_SERVERS
forced_proxy_opt = 'ProxyCF'

canonical = {
             'channel': 'poseidonhd', 
             'host': config.get_setting("current_host", 'poseidonhd', default=''), 
             'host_alt': ["https://www.poseidonhd2.co/"], 
             'host_black_list': ["https://www.poseidonhd2.com/", "https://tekilaz.co/"], 
             'set_tls': True, 'set_tls_min': True, 'retries_cloudflare': 1, 'forced_proxy_ifnot_assistant': forced_proxy_opt, 
             'CF': False, 'CF_test': False, 'alfa_s': True
            }
host = canonical['host'] or canonical['host_alt'][0]

timeout = 5
kwargs = {}
debug = config.get_setting('debug_report', default=False)
movie_path = "/pelicula"
tv_path = '/serie'
language = []
url_replace = [("/series/", "/serie/")]

finds = {'find': dict([('find', [{'tag': ['ul'], 'class': ['MovieList Rows', 'MovieList Rows episodes']}]), 
                       ('find_all', [{'tag': ['li'], 'class': ['TPostMv']}])]),
         'categories': {'find': [{'tag': ['li'], 'id': ['menu-item-1953']}], 'find_all': [{'tag': ['li']}]}, 
         'search': {}, 
         'get_language': {'find_all': [{'tag': ['span'], 'class': ['flag']}]}, 
         'get_language_rgx': '(?:flags\/|-)(\w+)\.(?:png|jpg|jpeg|webp)', 
         'get_quality': {}, 
         'get_quality_rgx': '', 
         'next_page': {}, 
         'next_page_rgx': [['\/page\/\d+', '/page/%s']], 
         'last_page': dict([('find', [{'tag': ['a'], 'class': ['next page-numbers']}]), 
                            ('find_previous', [{'tag': ['span'], 'class': ['page-link'], '@TEXT': '(\d+)'}])]), 
         'year': dict([('find', [{'tag': ['span']}]), 
                       ('get_text', [{'tag': '', '@STRIP': True, '@TEXT': '(\d+)'}])]), 
         'season_episode': {'find': [{'tag': ['img'], '@ARG': 'alt', '@TEXT': '(?i)(\d+x\d+)'}]}, 
         'seasons': dict([('find', [{'tag': ['select'], 'id': ['select-season']}]), 
                          ('find_all', [{'tag': ['option']}])]), 
         'season_num': {}, 
         'seasons_search_num_rgx': '', 
         'seasons_search_qty_rgx': '', 
         'episode_url': '', 
         'episodes': dict([('find', [{'tag': ['script'], 'id': ['__NEXT_DATA__']}]), 
                           ('get_text', [{'tag': '', '@STRIP': False, '@JSON': 'props,pageProps,thisSerie,seasons|DEFAULT'}])]), 
         'episode_num': [], 
         'episode_clean': [], 
         'plot': dict([('find', [{'tag': ['div'], 'class': ['Description']}, 
                                 {'tag': ['p']}]), 
                       ('get_text', [{'tag': '', '@STRIP': True}])]), 
         'findvideos': dict([('find', [{'tag': ['script'], 'id': ['__NEXT_DATA__']}]), 
                             ('get_text', [{'tag': '', '@STRIP': False, '@JSON': 'props,pageProps,episode/thisMovie/thisSerie,videos|DEFAULT'}])]), 
         'title_clean': [['(?i)TV|Online|(4k-hdr)|(fullbluray)|4k| - 4k|(3d)|miniserie|\s*\(\d{4}\)', ''],
                         ['[\(|\[]\s*[\)|\]]', '']],
         'quality_clean': [['(?i)proper|unrated|directors|cut|repack|internal|real|extended|masted|docu|super|duper|amzn|uncensored|hulu', '']],
         'language_clean': [], 
         'url_replace': [], 
         'controls': {'duplicates': [], 'min_temp': False, 'url_base64': False, 'add_video_to_videolibrary': True, 
                      'get_lang': False, 'reverse': False, 'videolab_status': True, 'tmdb_extended_info': True, 'seasons_search': False}, 
         'timeout': timeout}
AlfaChannel = DictionaryAllChannel(host, movie_path=movie_path, tv_path=tv_path, canonical=canonical, finds=finds, 
                                   idiomas=IDIOMAS, language=language, list_language=list_language, list_servers=list_servers, 
                                   list_quality_movies=list_quality_movies, list_quality_tvshow=list_quality_tvshow, 
                                   channel=canonical['channel'], actualizar_titulos=True, url_replace=url_replace, debug=debug)


def mainlist(item):
    logger.info()

    autoplay.init(item.channel, list_servers, list_quality)

    itemlist = list()

    itemlist.append(Item(channel=item.channel, title='Peliculas', action='sub_menu', url=host+'peliculas/', 
                         thumbnail=get_thumb('movies', auto=True), c_type='peliculas'))

    itemlist.append(Item(channel=item.channel, title='Series',  action='sub_menu', url=host+'series/', 
                         thumbnail=get_thumb('tvshows', auto=True), c_type='series'))

    itemlist.append(Item(channel=item.channel, title="Descargas", action="list_downloads",
                         thumbnail=get_thumb("downloads", auto=True) or "https://i.imgur.com/6YQ5Q5Q.png"))

    itemlist.append(Item(channel=item.channel, title="Buscar...", action="search", url=host,
                         thumbnail=get_thumb("search", auto=True)))

    itemlist = filtertools.show_option(itemlist, item.channel, list_language, list_quality_tvshow, list_quality_movies)

    autoplay.show_option(item.channel, itemlist)

    return itemlist


def sub_menu(item):
    logger.info()

    itemlist = list()

    itemlist.append(Item(channel=item.channel, title='Todas', url=item.url, action='list_all',
                         thumbnail=get_thumb('all', auto=True), c_type=item.c_type))

    itemlist.append(Item(channel=item.channel, title='Estrenos', url=item.url+'estrenos', action='list_all',
                         thumbnail=get_thumb('premieres', auto=True), c_type=item.c_type))

    itemlist.append(Item(channel=item.channel, title='Tendencias Semana', url=item.url+'tendencias/semana', action='list_all',
                         thumbnail=get_thumb('last', auto=True), c_type=item.c_type))

    itemlist.append(Item(channel=item.channel, title='Tendencias Día', url=item.url+'tendencias/dia', action='list_all',
                         thumbnail=get_thumb('last', auto=True), c_type=item.c_type))
    
    if item.c_type == 'peliculas':
        itemlist.append(Item(channel=item.channel, title='Generos', action='section', url=host,
                             thumbnail=get_thumb('genres', auto=True), c_type=item.c_type))
    else:
        itemlist.append(Item(channel=item.channel, title='Nuevos Episodios', action='list_all', url=host+'episodios',
                             thumbnail=get_thumb('new episodes', auto=True), c_type='episodios'))

    return itemlist


def section(item):
    logger.info()

    return AlfaChannel.section(item, **kwargs)


def list_all(item):
    logger.info()

    return AlfaChannel.list_all(item, matches_post=list_all_matches, **kwargs)


def list_all_matches(item, matches_int, **AHkwargs):
    logger.info()

    matches = []
    findS = AHkwargs.get('finds', finds)

    for elem in matches_int:
        elem_json = {}
        #logger.error(elem)

        try:
            if item.c_type == 'episodios':
                sxe = AlfaChannel.parse_finds_dict(elem, findS.get('season_episode', {}), c_type=item.c_type)
                elem_json['season'], elem_json['episode'] = sxe.split('x')
                elem_json['season'] = int(elem_json['season'] or 1)
                elem_json['episode'] = int(elem_json['episode'] or 1)
                elem_json['year'] = '-'

            elem_json['url'] = elem.a.get('href', '')
            elem_json['title'] = elem.img.get('alt', '') if item.c_type != 'episodios' else elem.img.get('alt', '').replace(sxe, '').strip()
            elem_json['thumbnail'] = elem.img.get('src', '')
            elem_json['year'] = elem_json.get('year', AlfaChannel.parse_finds_dict(elem, findS.get('year', {}), year=True, c_type=item.c_type))
            if findS.get('plot', {}) and AlfaChannel.parse_finds_dict(elem, findS.get('plot', {}), c_type=item.c_type):
                elem_json['plot'] = AlfaChannel.parse_finds_dict(elem, findS.get('plot', {}), c_type=item.c_type)
        except:
            logger.error(elem)
            logger.error(traceback.format_exc())
            continue
        
        if not elem_json['url']: continue

        matches.append(elem_json.copy())

    return matches


def seasons(item):
    logger.info()

    return AlfaChannel.seasons(item, **kwargs)


def episodios(item):
    logger.info()

    itemlist = []

    templist = seasons(item)

    for tempitem in templist:
        itemlist += episodesxseason(tempitem)

    return itemlist


def episodesxseason(item):
    logger.info()

    kwargs['matches_post_get_video_options'] = findvideos_matches

    return AlfaChannel.episodes(item, matches_post=episodesxseason_matches, **kwargs)


def episodesxseason_matches(item, matches_int, **AHkwargs):
    logger.info()

    matches = []
    findS = AHkwargs.get('finds', finds)

    for x, elem_season in enumerate(matches_int):
        #logger.error(elem_season)

        if item.contentSeason != elem_season.get('number', 1): continue
        for elem in elem_season.get('episodes', []):
            elem_json = {}
            #logger.error(elem)

            try:
                elem_json['url'] = elem.get('url', {}).get('slug', '').replace('seasons', 'temporada')\
                                                                      .replace('episodes', 'episodio').replace('series/', 'serie/')
                elem_json['title'] = elem.get('title', '')
                elem_json['season'] = item.contentSeason
                elem_json['episode'] = int(elem.get('number', '1') or '1')
                elem_json['thumbnail'] = elem.get('image', '')
            except:
                logger.error(elem)
                logger.error(traceback.format_exc())
                continue

            if not elem_json.get('url', ''): 
                continue

            matches.append(elem_json.copy())

    return matches


def findvideos(item):
    logger.info()

    kwargs['matches_post_episodes'] = episodesxseason_matches

    itemlist = AlfaChannel.get_video_options(item, item.url, data='', matches_post=findvideos_matches, 
                                             verify_links=False, findvideos_proc=True, **kwargs)
    
    # Agregar opción de descarga al final de la lista
    if itemlist:
        download_item = Item(channel=item.channel, 
                            title="[COLOR chartreuse]Descargar[/COLOR]", 
                            action="download_video",
                            url=item.url,
                            thumbnail=get_thumb("downloads", auto=True) or "https://i.imgur.com/6YQ5Q5Q.png",
                            contentTitle=getattr(item, 'contentTitle', '') or getattr(item, 'title', ''),
                            contentSerieName=getattr(item, 'contentSerieName', ''),
                            contentType=getattr(item, 'contentType', ''),
                            contentSeason=getattr(item, 'contentSeason', 1),
                            contentEpisodeNumber=getattr(item, 'contentEpisodeNumber', 1))
        
        # Clonar información del item original
        if hasattr(item, 'infoLabels'):
            download_item.infoLabels = item.infoLabels.copy()
        
        itemlist.append(download_item)
    
    return itemlist


def findvideos_matches(item, matches_int, langs, response, **AHkwargs):
    logger.info()

    matches = []
    findS = AHkwargs.get('finds', finds)
    servers = {'drive': 'gvideo', 'fembed': 'fembed', "player": "oprem", "openplay": "oprem", "embed": "mystream"}

    for lang, elem in list(matches_int.items()):
        #logger.error(elem)

        for link in elem:
            elem_json = {}
            #logger.error(link)

            try:
                elem_json['server'] = link.get('cyberlocker', '')
                elem_json['url'] = link.get('result', '')
                elem_json['language'] = '*%s' % lang
                elem_json['quality'] = '*%s' % link.get('quality', '')
                elem_json['title'] = '%s'
            except:
                logger.error(link)
                logger.error(traceback.format_exc())
                continue

            if not elem_json['url']: continue

            if elem_json['server'].lower() in ["waaw", "jetload"]: continue
            if elem_json['server'].lower() in servers:
               elem_json['server'] = servers[elem_json['server'].lower()]

            matches.append(elem_json.copy())

    return matches, langs


def play(item):
    logger.info()

    itemlist = list()
    kwargs = {'set_tls': True, 'set_tls_min': True, 'retries_cloudflare': -1, 
              'CF': False, 'cf_assistant': False, 'canonical': {}}
    
    try:
        data = AlfaChannel.create_soup(item.url, forced_proxy_opt=forced_proxy_opt, **kwargs)
        data = url = scrapertools.find_single_match(str(data), "var\s*url\s*=\s*'([^']+)'")
        
        if not data.startswith('http'):
            base_url = "%sr.php" % host
            post = {"data": data}
            kwargs['soup'] = False
            url = AlfaChannel.create_soup(base_url, post=post, forced_proxy_opt=forced_proxy_opt, **kwargs).url
            if not url: return itemlist
        
        if "fs.%s" % host.replace("https://", "") in url:
            api_url = "%sr.php" % host.replace("https://", "https://fs.")
            v_id = scrapertools.find_single_match(url, r"\?h=([A-z0-9]+)")
            post = {"h": v_id}
            kwargs['soup'] = False
            url = AlfaChannel.create_soup(api_url, post=post, forced_proxy_opt=forced_proxy_opt, **kwargs).url
        
        itemlist.append(item.clone(url=url, server=""))
        itemlist = servertools.get_servers_itemlist(itemlist)
    except:
        logger.error(traceback.format_exc())

    return itemlist


def actualizar_titulos(item):
    logger.info()
    #Llamamos al método que actualiza el título con tmdb.find_and_set_infoLabels

    return AlfaChannel.do_actualizar_titulos(item)


def search(item, texto, **AHkwargs):
    logger.info()
    kwargs.update(AHkwargs)

    try:
        texto = texto.replace(" ", "+")
        item.url = host + 'search?q=' + texto

        if texto:
            item.c_type = "search"
            item.texto = texto
            return list_all(item)
        else:
            return []

    # Se captura la excepción, para no interrumpir al buscador global si un canal falla
    except:
        for line in sys.exc_info():
            logger.error("%s" % line)
        return []


def list_downloads(item):
    logger.info()
    
    itemlist = []
    download_path = config.get_setting("downloadpath", default='')
    
    if not download_path or not filetools.exists(download_path):
        from platformcode import platformtools
        platformtools.dialog_ok("Descargas", "No hay una carpeta de descargas configurada", 
                                "Por favor, configura la carpeta de descargas en los ajustes")
        return itemlist
    
    # Listar archivos descargados
    try:
        files = filetools.listdir(download_path)
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
        
        downloaded_files = []
        for file in files:
            if any(file.lower().endswith(ext) for ext in video_extensions):
                file_path = filetools.join(download_path, file)
                file_size = filetools.getsize(file_path)
                size_mb = round(file_size / (1024 * 1024), 2)
                
                downloaded_files.append({
                    'name': file,
                    'path': file_path,
                    'size': size_mb
                })
        
        if downloaded_files:
            for video in downloaded_files:
                itemlist.append(Item(channel=item.channel,
                                    title=video['name'],
                                    action="play",
                                    url=video['path'],
                                    thumbnail="",
                                    contentTitle=video['name'],
                                    contentType="movie",
                                    folder=False))
        else:
            from platformcode import platformtools
            platformtools.dialog_ok("Descargas", "No hay descargas disponibles")
    
    except Exception as e:
        logger.error("Error al listar descargas: %s" % str(e))
    
    return itemlist


def download_video(item):
    logger.info()
    
    from platformcode import platformtools
    from modules import downloads
    
    # Obtener la lista de servidores de video
    itemlist = AlfaChannel.get_video_options(item, item.url, data='', matches_post=findvideos_matches, 
                                             verify_links=False, findvideos_proc=True, **kwargs)
    
    if not itemlist:
        platformtools.dialog_ok("Error", "No se encontraron opciones de video para descargar")
        return []
    
    # Filtrar solo las opciones de servidores (excluyendo la opción de descarga)
    download_options = []
    for video_item in itemlist:
        if hasattr(video_item, 'server') and video_item.server and video_item.action != 'download_video':
            download_options.append(video_item)
    
    if not download_options:
        platformtools.dialog_ok("Error", "No hay servidores disponibles para descargar")
        return []
    
    # Mostrar diálogo de selección de servidor
    server_names = []
    for opt in download_options:
        server_name = getattr(opt, 'server', 'Directo')
        quality = getattr(opt, 'quality', '')
        lang = getattr(opt, 'language', '')
        server_names.append("%s %s %s" % (server_name, quality, lang))
    
    selection = platformtools.dialog_select("Selecciona servidor para descargar", server_names)
    
    if selection >= 0:
        selected_item = download_options[selection]
        
        # Preparar título del archivo
        title = getattr(item, 'contentTitle', '') or getattr(item, 'title', '') or "video"
        if getattr(item, 'contentSerieName', ''):
            season = getattr(item, 'contentSeason', 1)
            episode = getattr(item, 'contentEpisodeNumber', 1)
            title = "%s S%02dE%02d - %s" % (item.contentSerieName, season, episode, title)
        
        # Limpiar título para nombre de archivo
        from core import scrapertools
        import re
        title = re.sub(r'[\\/*?:"<>|]', '', title)
        title = title.strip()
        
        # Crear item de descarga
        download_item = item.clone()
        download_item.action = 'download'
        download_item.title = title
        download_item.url = selected_item.url
        download_item.server = selected_item.server
        download_item.downloadFilename = title
        
        # Iniciar descarga usando el sistema de descargas del addon
        try:
            platformtools.dialog_ok("Descargando", "Iniciando descarga de: %s" % title)
            
            # Usar el sistema de descargas del addon
            threading.Thread(target=downloads.start_download, args=(download_item,)).start()
            
            platformtools.dialog_notification("Descarga iniciada", "En segundo plano: %s" % title)
            
        except Exception as e:
            logger.error("Error en descarga: %s" % str(e))
            platformtools.dialog_ok("Error", "Error al descargar: %s" % str(e))
    
    return []


def newest(categoria, **AHkwargs):
    logger.info()
    kwargs.update(AHkwargs)

    item = Item()

    try:
        if categoria in ['peliculas']:
            item.url = host + 'movies'
        elif categoria == 'infantiles':
            item.url = host + 'category/animacion/'
        elif categoria == 'terror':
            item.url = host + 'category/terror/'
        item.type = "movies"
        itemlist = list_all(item)
        if len(itemlist) > 0 and ">> Página siguiente" in itemlist[-1].title:
            itemlist.pop()

    except:
        import sys
        for line in sys.exc_info():
            logger.error("{0}".format(line))
        return []

    return itemlist
