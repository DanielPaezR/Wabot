#!/usr/bin/env python3
"""
Script para inicializar base de datos antes de iniciar la app - POSTGRESQL
"""
import os
import sys
import time

print("🚀 INICIALIZANDO BASE DE DATOS EN PRODUCCIÓN...")

# Agregar el directorio actual al path
sys.path.append(os.path.dirname(__file__))

def is_postgresql():
    """Determinar si estamos usando PostgreSQL"""
    database_url = os.getenv('DATABASE_URL', '')
    return database_url.startswith('postgresql://')

try:
    # Esperar un poco para asegurar que la BD esté lista
    time.sleep(2)
    
    from database import init_db, get_db_connection
    
    print("🔧 Ejecutando init_db()...")
    init_db()
    
    # Verificar que las tablas se crearon
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Listar tablas según el tipo de base de datos
    if is_postgresql():
        print("📊 Listando tablas PostgreSQL...")
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
        tablas = cursor.fetchall()
        print(f"📊 Tablas PostgreSQL: {[t['table_name'] for t in tablas]}")
    else:
        print("📊 Listando tablas SQLite...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tablas = cursor.fetchall()
        print(f"📊 Tablas SQLite: {[t[0] for t in tablas]}")
    
    # Verificar datos básicos
    print("🔍 Verificando datos básicos...")
    
    # Verificar negocios
    if is_postgresql():
        cursor.execute("SELECT COUNT(*) as count FROM negocios")
    else:
        cursor.execute("SELECT COUNT(*) as count FROM negocios")
    
    resultado = cursor.fetchone()
    count_negocios = resultado['count'] if is_postgresql() else resultado[0]
    print(f"📋 Negocios en sistema: {count_negocios}")
    
    # Verificar usuarios
    if is_postgresql():
        cursor.execute("SELECT COUNT(*) as count FROM usuarios")
    else:
        cursor.execute("SELECT COUNT(*) as count FROM usuarios")
    
    resultado = cursor.fetchone()
    count_usuarios = resultado['count'] if is_postgresql() else resultado[0]
    print(f"👥 Usuarios en sistema: {count_usuarios}")
    
    # Verificar plantillas
    if is_postgresql():
        cursor.execute("SELECT COUNT(*) as count FROM plantillas_mensajes")
    else:
        cursor.execute("SELECT COUNT(*) as count FROM plantillas_mensajes")
    
    resultado = cursor.fetchone()
    count_plantillas = resultado['count'] if is_postgresql() else resultado[0]
    print(f"📝 Plantillas en sistema: {count_plantillas}")
    
    conn.close()
    print("✅ Base de datos inicializada y verificada correctamente")
    
except Exception as e:
    print(f"❌ Error en inicialización BD: {e}")
    import traceback
    traceback.print_exc()
    # No salir con error para permitir que la app intente recuperarse
    print("⚠️ Continuando con el inicio de la aplicación...")