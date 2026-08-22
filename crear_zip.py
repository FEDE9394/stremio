#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para crear el ZIP del addon de Kodi con la estructura correcta
"""

import os
import zipfile

# Configuración
ADDON_ID = "plugin.video.poseidon_search"
ADDON_VERSION = "1.0.0"
ARCHIVOS = ["addon.xml", "main.py"]

def crear_zip():
    """Crea el ZIP del addon con la estructura correcta para Kodi"""
    
    # Nombre del archivo ZIP
    zip_name = f"{ADDON_ID}-{ADDON_VERSION}.zip"
    
    # Eliminar ZIP anterior si existe
    if os.path.exists(zip_name):
        try:
            os.remove(zip_name)
            print(f"[OK] Eliminado ZIP anterior: {zip_name}")
        except Exception as e:
            print(f"[WARN] No se pudo eliminar ZIP anterior: {e}")
    
    # Crear nuevo ZIP
    try:
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Agregar archivos dentro de la carpeta del addon
            for archivo in ARCHIVOS:
                if os.path.exists(archivo):
                    # La ruta en el ZIP debe ser: plugin.video.poseidon_search/archivo
                    ruta_en_zip = f"{ADDON_ID}/{archivo}"
                    zipf.write(archivo, ruta_en_zip)
                    print(f"[OK] Agregado: {ruta_en_zip}")
                else:
                    print(f"[ERROR] No se encuentra {archivo}")
                    return False
    except Exception as e:
        print(f"[ERROR] Error al crear el ZIP: {e}")
        return False
    
    print(f"\n[OK] ZIP creado exitosamente: {zip_name}")
    print(f"[OK] Tamano: {os.path.getsize(zip_name)} bytes")
    print(f"\nPara instalar en Kodi:")
    print(f"1. Copia {zip_name} a tu dispositivo")
    print(f"2. En Kodi: Add-ons -> Instalar desde archivo zip")
    print(f"3. Selecciona {zip_name}")
    print(f"4. El addon aparecera en: Video -> Add-ons de video -> Buscador PoseidonHD")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("CREANDO ZIP DEL ADDON DE KODI")
    print("=" * 60)
    print()
    
    if crear_zip():
        print("\n[OK] PROCESO COMPLETADO")
    else:
        print("\n[ERROR] EN EL PROCESO")