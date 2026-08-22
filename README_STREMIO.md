# PoseidonHD para Stremio

Este directorio contiene un addon HTTP de Stremio independiente del addon de Kodi.

## Instalacion facil con GitHub y Render

1. Sube el contenido de esta carpeta a un repositorio nuevo de GitHub.
2. Entra en [render.com](https://render.com), crea una cuenta y selecciona
	**New + > Blueprint**.
3. Conecta el repositorio de GitHub y confirma el despliegue.
4. Render te dara una URL parecida a `https://poseidonhd-stremio.onrender.com`.
5. En Stremio instala esta URL agregando `/manifest.json` al final.

Ejemplo:

`https://poseidonhd-stremio.onrender.com/manifest.json`

El servicio gratuito de Render puede tardar unos segundos en despertar después
de estar inactivo.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python stremio_addon.py
```

En Stremio se instala usando:

`http://127.0.0.1:7000/manifest.json`

Para usarlo localmente, ejecuta el servidor y usa la URL indicada abajo. El addon conserva búsqueda,
catálogos, fichas, temporadas/episodios y resolución de fuentes directas que el
servidor entregue como `.m3u8` o `.mp4`. El manifiesto incluye catálogos separados de tendencias del día y de la semana
para películas y series. En Android solo se muestran fuentes directas que
Stremio puede reproducir internamente; los reproductores web externos se
descartan para evitar abrir el navegador.