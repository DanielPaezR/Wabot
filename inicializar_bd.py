#!/usr/bin/env python3
"""
Script para inicializar base de datos antes de iniciar la app
"""
import os
import sys
import time

print("🚀 INICIALIZANDO BASE DE DATOS EN PRODUCCIÓN...")

# Agregar el directorio actual al path
sys.path.append(os.path.dirname(__file__))

try:
    # Esperar un poco para asegurar que la BD esté lista
    time.sleep(2)
    
    from database import init_db, get_db_connection
    
    print("🔧 Ejecutando init_db()...")
    init_db()
    
    # Verificar que las tablas se crearon
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Listar tablas (compatible con SQLite y PostgreSQL)
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = cursor.fetchall()
        print(f"📊 Tablas SQLite: {[t[0] for t in tablas]}")
    except:
        try:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            tablas = cursor.fetchall()
            print(f"📊 Tablas PostgreSQL: {[t[0] for t in tablas]}")
        except Exception as e:
            print(f"⚠️ Error listando tablas: {e}")
    
    conn.close()
    print("✅ Base de datos inicializada y verificada correctamente")
    
except Exception as e:
    print(f"❌ Error en inicialización BD: {e}")
    # No salir con error para permitir que la app intente recuperarse
    print("⚠️ Continuando con el inicio de la aplicación...")