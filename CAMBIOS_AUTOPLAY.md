# Cambios Implementados - Optimización de Autoplay

## 📋 Resumen de Cambios

Se realizaron optimizaciones en `main.py` para reducir el tiempo de espera del autoplay y mejorar la velocidad de reproducción.

## ⚡ Mejoras de Velocidad

### 1. **Reducción de Timeouts Globales**
- **`get_html()`**: Timeout reducido de **20s → 10s** (50% más rápido)
- **`get_json()`**: Timeout reducido de **20s → 10s** (50% más rápido)
- **`show_notification()`**: Tiempo de notificación reducido de **5s → 2s** por defecto

### 2. **Optimización de Resolvers de Video**

Todos los resolvers ahora usan timeouts más agresivos:

| Resolver | Timeout Anterior | Timeout Nuevo | Mejora |
|----------|-----------------|---------------|--------|
| **Streamwish** | 20s | 10s | 50% |
| **Streamtape** | 20s | 8s | 60% |
| **Doodstream** | 20s | 10s | 50% |
| **VOE** | 20s | 8s | 60% |
| **Mixdrop** | 20s | 8s | 60% |
| **Mp4upload** | 20s | 8s | 60% |
| **OK.ru** | 20s | 8s | 60% |
| **Netu/waaw** | 20s | 10s | 50% |
| **Genérico** | 20s | 8s | 60% |
| **_get_player_embed_url** | 20s | 8s | 60% |

### 3. **Eliminación de Notificaciones Lentas en Autoplay**

**Antes:**
```python
show_notification("Autoplay", f"Intentando reproducir...", time_ms=2000)
show_notification(ADDON_NAME, f"Reproduciendo: {option['label']}", time_ms=3000)
show_notification("Autoplay Fallido", "No se pudo reproducir...", time_ms=5000)
```

**Ahora:**
```python
# Sin notificaciones intermedias - solo error final si falla
show_notification("Autoplay Fallido", "No se pudo reproducir ningún servidor.", time_ms=1500)
```

**Beneficio:** El autoplay ahora intenta servidores consecutivamente sin pausas entre intentos.

### 4. **Mejora en Proceso de Autoplay**

**Flujo optimizado:**
1. Obtiene lista de opciones de video
2. Ordena por prioridad de idioma (Latino → Español → Inglés)
3. Intenta cada servidor **sin notificaciones intermedias**
4. Si tiene éxito: reproduce inmediatamente
5. Si falla: muestra notificación corta (1.5s)

**Resultado:** Reducción de ~3-5 segundos por cada intento fallido.

## 📊 Impacto en Rendimiento

### Tiempo Total Estimado de Autoplay

**Antes:**
- Timeout por servidor: 20s
- Notificaciones: 2s + 3s = 5s
- **Total por intento: ~25s**

**Ahora:**
- Timeout por servidor: 8-10s
- Sin notificaciones intermedias
- **Total por intento: ~8-10s**

**Mejora: ~60-70% más rápido**

### Caso Práctico

Si un video tiene 3 servidores y los 2 primeros fallan:

**Antes:** 25s + 25s + (tercero) = **50+ segundos**
**Ahora:** 10s + 10s + (tercero) = **20+ segundos**

**Ahorro: ~30 segundos por video**

## 🔧 Cambios Técnicos Específicos

### Archivo: `main.py`

#### Línea 89: Timeout de notificaciones
```python
def show_notification(title, message, icon=None, time_ms=2000):  # Era 5000
```

#### Líneas 95-110: Timeout de get_html()
```python
def get_html(url, referer=None, extra_headers=None, timeout=10):  # Era 20
```

#### Líneas 113-126: Timeout de get_json()
```python
def get_json(url, referer=None, extra_headers=None, timeout=10):  # Era 20
```

#### Líneas 1334-1376: Función _try_play_option()
- Eliminadas notificaciones de "Falló X, intentando siguiente..."
- Eliminada notificación de "Reproduciendo: X"
- Solo notifica si todos los servidores fallan

#### Líneas 1446-1464: Bucle de autoplay
- Eliminada notificación inicial "Intentando reproducir..."
- Sin pausas entre intentos de servidores
- Notificación de error final más corta (1.5s)

#### Líneas 276-304: Resolver Streamwish
```python
session.get(base_domain, timeout=5)  # Era 10
session.get(embed_url, timeout=10)   # Era 20
session.get(js_url, timeout=8)       # Era 15
```

#### Líneas 465-506: Resolver Doodstream
```python
requests.get(embed_url, timeout=10)      # Era 20
requests.get(pass_url, timeout=8)        # Era 20
```

#### Líneas 433-462: Resolver Streamtape
```python
get_html(embed_url, timeout=8)           # Era 20
requests.head(raw_url, timeout=5)        # Era 10
```

#### Resto de resolvers: Timeout uniforme de 8s
- VOE, Mixdrop, Mp4upload, OK.ru, Netu, Genérico

## ✅ Verificación

La estructura del proyecto ya incluye:
- ✅ Carpeta `core/` con todas las herramientas base
- ✅ Carpeta `servers/` con los resolvers específicos
- ✅ Integración completa en `main.py`
- ✅ Todas las importaciones funcionan correctamente

## 🚀 Cómo Probar

1. Instala el addon en Kodi
2. Navega a cualquier película o serie
3. Selecciona un video
4. El autoplay debería iniciarse **mucho más rápido**
5. Si falla el primer servidor, pasará al siguiente **sin demoras**

## 📝 Notas Adicionales

- Los timeouts de 8-10s son suficientes para conexiones normales
- Si experimentas timeouts frecuentes, puedes aumentar a 12-15s
- Las notificaciones reducidas mejoran la experiencia de usuario
- El autoplay sigue priorizando Latino > Español > Inglés

## 🔄 Reversibilidad

Todos los cambios son reversibles. Si necesitas restaurar los valores originales:

```python
# Restaurar timeouts originales
timeout = 20  # En get_html, get_json
time_ms = 5000  # En show_notification
```

## 📈 Próximos Pasos Sugeridos

1. **Probar en Kodi** y medir tiempos reales de reproducción
2. **Ajustar timeouts** según tu conexión (8-12s es el rango óptimo)
3. **Monitorear logs** para ver qué servidores fallan más
4. **Considerar agregar** más servidores a la lista de prioridad

---

**Fecha de implementación:** 24/07/2026
**Versión:** 2.0.0
**Autor:** DevPoseidon