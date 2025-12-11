# =============================================================================
# database.py - SISTEMA GENÉRICO DE CITAS - POSTGRESQL COMPLETO
# =============================================================================
import os
from datetime import datetime, timedelta
import json
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3  # Para fallback


def get_db_connection():
    """Establecer conexión a la base de datos (PostgreSQL o SQLite)"""
    database_url = os.getenv('DATABASE_URL')
    
    # Si estamos en producción con PostgreSQL
    if database_url and database_url.startswith('postgresql://'):
        try:
            # Convertir URL de PostgreSQL para psycopg2
            if database_url.startswith('postgresql://'):
                database_url = database_url.replace('postgresql://', 'postgres://')
            
            # Conectar con cursor que retorna diccionarios
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            return conn
            
        except Exception as e:
            print(f"❌ Error conectando a PostgreSQL: {e}")
            print("🔄 Fallback a SQLite...")
            conn = sqlite3.connect('negocio.db')
            conn.row_factory = sqlite3.Row
            return conn
    else:
        # Desarrollo local con SQLite
        conn = sqlite3.connect('negocio.db')
        conn.row_factory = sqlite3.Row
        return conn


def is_postgresql():
    """Determinar si estamos usando PostgreSQL"""
    database_url = os.getenv('DATABASE_URL', '')
    return database_url.startswith('postgresql://')


def execute_sql(cursor, sql, params=()):
    """Ejecutar SQL adaptado para PostgreSQL o SQLite - VERSIÓN MEJORADA"""
    if is_postgresql():
        # Reemplazar ? por %s para PostgreSQL
        sql = sql.replace('?', '%s')
        # Usar execute directamente para PostgreSQL
        cursor.execute(sql, params)
    else:
        # SQLite
        cursor.execute(sql, params)


def fetch_all(cursor, sql, params=()):
    """Ejecutar SELECT y retornar todos los resultados"""
    execute_sql(cursor, sql, params)
    results = cursor.fetchall()
    
    if is_postgresql():
        # PostgreSQL ya retorna diccionarios por RealDictCursor
        return results
    else:
        # SQLite: convertir Row a dict
        return [dict(row) for row in results]


def fetch_one(cursor, sql, params=()):
    """Ejecutar SELECT y retornar un resultado - VERSIÓN MEJORADA"""
    execute_sql(cursor, sql, params)
    result = cursor.fetchone()
    
    if result:
        if is_postgresql():
            # PostgreSQL con RealDictCursor retorna diccionarios
            return dict(result) if hasattr(result, 'keys') else result
        else:
            # SQLite: convertir Row a dict
            return dict(result)
    return None


# =============================================================================
# INICIALIZACIÓN DE BASE DE DATOS
# =============================================================================

def init_db():
    """Inicializar base de datos"""
    print("🔧 INICIANDO INIT_DB - CREANDO ESQUEMA...")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Crear tablas
        _crear_tablas(cursor)
        print("✅ Tablas creadas/verificadas")
        
        # Insertar datos por defecto
        try:
            _insertar_datos_por_defecto(cursor)
            print("✅ Datos por defecto insertados")
        except Exception as e:
            print(f"⚠️ Error en datos por defecto: {e}")
        
        conn.commit()
        
        # Crear plantillas
        try:
            crear_plantillas_personalizadas_para_negocios()
            print("✅ Plantillas personalizadas creadas")
        except Exception as e:
            print(f"⚠️ Error creando plantillas: {e}")
        
        print("🎉 BASE DE DATOS INICIALIZADA COMPLETAMENTE")
        
    except Exception as e:
        print(f"❌ Error en init_db: {e}")
    finally:
        if conn:
            conn.close()


def _crear_tablas(cursor):
    """Crear todas las tablas necesarias"""
    postgres = is_postgresql()
    
    # Tabla negocios
    negocios_sql = '''
        CREATE TABLE IF NOT EXISTS negocios (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono_whatsapp TEXT UNIQUE NOT NULL,
            tipo_negocio TEXT DEFAULT 'general',
            emoji TEXT DEFAULT '👋',
            configuracion TEXT DEFAULT '{}',
            activo BOOLEAN DEFAULT TRUE,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''
    if postgres:
        negocios_sql = negocios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, negocios_sql)
    
    # Tabla usuarios
    usuarios_sql = '''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT DEFAULT 'propietario',
            activo BOOLEAN DEFAULT TRUE,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ultimo_login TIMESTAMP,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id)
        )
    '''
    if postgres:
        usuarios_sql = usuarios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, usuarios_sql)
    
    # Tabla plantillas_mensajes
    plantillas_sql = '''
        CREATE TABLE IF NOT EXISTS plantillas_mensajes (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER,
            nombre TEXT NOT NULL,
            plantilla TEXT NOT NULL,
            descripcion TEXT,
            variables_disponibles TEXT DEFAULT '[]',
            es_base BOOLEAN DEFAULT FALSE,
            activo BOOLEAN DEFAULT TRUE,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id),
            UNIQUE(negocio_id, nombre)
        )
    '''
    if postgres:
        plantillas_sql = plantillas_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, plantillas_sql)
    
    # Tabla profesionales
    profesionales_sql = '''
        CREATE TABLE IF NOT EXISTS profesionales (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            telefono TEXT,
            especialidad TEXT,
            pin TEXT,
            usuario_id INTEGER,
            activo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    '''
    if postgres:
        profesionales_sql = profesionales_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, profesionales_sql)
    
    # Tabla servicios
    servicios_sql = '''
        CREATE TABLE IF NOT EXISTS servicios (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            duracion INTEGER NOT NULL,
            precio DECIMAL(10,2) NOT NULL,
            descripcion TEXT,
            activo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id)
        )
    '''
    if postgres:
        servicios_sql = servicios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, servicios_sql)
    
    # Tabla citas
    citas_sql = '''
        CREATE TABLE IF NOT EXISTS citas (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            profesional_id INTEGER NOT NULL,
            cliente_telefono TEXT NOT NULL,
            cliente_nombre TEXT,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            servicio_id INTEGER NOT NULL,
            estado TEXT DEFAULT 'confirmado',
            recordatorio_24h_enviado BOOLEAN DEFAULT FALSE,
            recordatorio_1h_enviado BOOLEAN DEFAULT FALSE,
            notificado_profesional BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id),
            FOREIGN KEY (profesional_id) REFERENCES profesionales(id),
            FOREIGN KEY (servicio_id) REFERENCES servicios(id)
        )
    '''
    if postgres:
        citas_sql = citas_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, citas_sql)
    
    # Tabla configuracion
    configuracion_sql = '''
        CREATE TABLE IF NOT EXISTS configuracion (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            hora_inicio TEXT DEFAULT '09:00',
            hora_fin TEXT DEFAULT '19:00',
            almuerzo_inicio TEXT DEFAULT '13:00',
            almuerzo_fin TEXT DEFAULT '14:00',
            duracion_cita_base INTEGER DEFAULT 60,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id)
        )
    '''
    execute_sql(cursor, configuracion_sql)
    
    # Tabla configuracion_horarios
    config_horarios_sql = '''
        CREATE TABLE IF NOT EXISTS configuracion_horarios (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            dia_semana INTEGER NOT NULL,
            activo BOOLEAN DEFAULT TRUE,
            hora_inicio TIME NOT NULL,
            hora_fin TIME NOT NULL,
            almuerzo_inicio TIME,
            almuerzo_fin TIME,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id)
        )
    '''
    execute_sql(cursor, config_horarios_sql)
    
    # Tabla profesional_servicios
    prof_servicios_sql = '''
        CREATE TABLE IF NOT EXISTS profesional_servicios (
            id SERIAL PRIMARY KEY,
            profesional_id INTEGER NOT NULL,
            servicio_id INTEGER NOT NULL,
            FOREIGN KEY (profesional_id) REFERENCES profesionales (id) ON DELETE CASCADE,
            FOREIGN KEY (servicio_id) REFERENCES servicios (id) ON DELETE CASCADE,
            UNIQUE(profesional_id, servicio_id)
        )
    '''
    execute_sql(cursor, prof_servicios_sql)


def _insertar_datos_por_defecto(cursor):
    """Insertar datos por defecto en las tablas - VERSIÓN CORREGIDA"""
    postgres = is_postgresql()
    
    try:
        # Verificar si ya existe el negocio por defecto
        if postgres:
            cursor.execute('SELECT id FROM negocios WHERE id = 1')
        else:
            cursor.execute('SELECT id FROM negocios WHERE id = 1')
        
        negocio_existe = cursor.fetchone()
        
        if not negocio_existe:
            # Negocio por defecto - NO especificar ID para PostgreSQL
            if postgres:
                cursor.execute('''
                    INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion) 
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    'Negocio Premium', 
                    'whatsapp:+14155238886', 
                    'general', 
                    '👋',  # ✅ Agregar emoji
                    json.dumps({
                        "saludo_personalizado": "¡Hola! Soy tu asistente virtual para agendar citas",
                        "horario_atencion": "Lunes a Sábado 9:00 AM - 7:00 PM",
                        "direccion": "Calle Principal #123",
                        "telefono_contacto": "+573001234567",
                        "politica_cancelacion": "Puedes cancelar hasta 2 horas antes"
                    })
                ))
                result = cursor.fetchone()
                if hasattr(result, 'keys'):
                    negocio_id = result['id']
                else:
                    negocio_id = result[0] if result else None
                print(f"✅ Negocio por defecto creado con ID: {negocio_id}")
            else:
                cursor.execute('''
                    INSERT INTO negocios (id, nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion) 
                    VALUES (1, ?, ?, ?, ?, ?)
                ''', (
                    'Negocio Premium', 
                    'whatsapp:+14155238886', 
                    'general', 
                    '👋',  # ✅ Agregar emoji
                    json.dumps({
                        "saludo_personalizado": "¡Hola! Soy tu asistente virtual para agendar citas",
                        "horario_atencion": "Lunes a Sábado 9:00 AM - 7:00 PM",
                        "direccion": "Calle Principal #123",
                        "telefono_contacto": "+573001234567",
                        "politica_cancelacion": "Puedes cancelar hasta 2 horas antes"
                    })
                ))
        else:
            print("✅ Negocio por defecto ya existe")
        
        # Resto del código permanece igual...
        _insertar_usuarios_por_defecto(cursor)
        _insertar_plantillas_base(cursor)
        
        # Configuración
        if postgres:
            cursor.execute('SELECT id FROM configuracion WHERE negocio_id = 1')
            if not cursor.fetchone():
                cursor.execute('INSERT INTO configuracion (negocio_id) VALUES (1)')
        else:
            cursor.execute('INSERT OR IGNORE INTO configuracion (negocio_id) VALUES (1)')
        
        # Configuración de horarios
        _insertar_configuracion_horarios(cursor)
        
        # Profesionales por defecto
        _insertar_profesionales_por_defecto(cursor)
        
        # Servicios por defecto
        _insertar_servicios_por_defecto(cursor)
        
    except Exception as e:
        print(f"⚠️ Error insertando datos por defecto: {e}")
        import traceback
        traceback.print_exc()


def _insertar_usuarios_por_defecto(cursor):
    """Insertar usuarios por defecto"""
    postgres = is_postgresql()
    
    usuarios = [
        (1, 'Super Administrador', 'admin@negociobot.com', 'admin123', 'superadmin'),
        (1, 'Juan Propietario', 'juan@negocio.com', 'propietario123', 'propietario'),
        (1, 'Carlos Profesional', 'carlos@negocio.com', 'profesional123', 'profesional'),
        (1, 'Ana Profesional', 'ana@negocio.com', 'profesional123', 'profesional')
    ]
    
    for negocio_id, nombre, email, password, rol in usuarios:
        password_hash = generate_password_hash(password)
        
        if postgres:
            cursor.execute('SELECT id FROM usuarios WHERE email = %s', (email,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol) 
                    VALUES (%s, %s, %s, %s, %s)
                ''', (negocio_id, nombre, email, password_hash, rol))
        else:
            cursor.execute('''
                INSERT OR IGNORE INTO usuarios (negocio_id, nombre, email, password_hash, rol) 
                VALUES (?, ?, ?, ?, ?)
            ''', (negocio_id, nombre, email, password_hash, rol))


def _insertar_plantillas_base(cursor):
    """Insertar plantillas base del sistema"""
    postgres = is_postgresql()
    
    # Eliminar plantillas base existentes
    if postgres:
        cursor.execute('DELETE FROM plantillas_mensajes WHERE es_base = TRUE')
    else:
        cursor.execute('DELETE FROM plantillas_mensajes WHERE es_base = TRUE')
    
    plantillas_base = [
        ('saludo_inicial_nuevo', 
         '🤖 *Bienvenido a {nombre_negocio}* {emoji_negocio}\n\n{saludo_personalizado}\n\nPara comenzar, ¿cuál es tu nombre?\n\n💡 *Siempre puedes volver al menú principal con* *0*',
         'Saludo para clientes nuevos',
         '["nombre_negocio", "emoji_negocio", "saludo_personalizado"]'),
        
        ('saludo_inicial_existente',
         '👋 ¡Hola {cliente_nombre}!\n\n*{nombre_negocio}* - ¿En qué te puedo ayudar?\n\n*1* {emoji_servicio} - Agendar cita\n*2* 📋 - Ver mis reservas\n*3* ❌ - Cancelar reserva\n*4* 🆘 - Ayuda\n\n💡 *Siempre puedes volver al menú principal con* *0*',
         'Saludo para clientes existentes',
         '["cliente_nombre", "nombre_negocio", "emoji_servicio"]'),
        
        ('menu_principal',
         '*{nombre_negocio}* - ¿En qué te puedo ayudar?\n\n*1* {emoji_servicio} - Agendar cita\n*2* 📋 - Ver mis reservas\n*3* ❌ - Cancelar reserva\n*4* 🆘 - Ayuda\n\n💡 *Siempre puedes volver al menú principal con* *0*',
         'Menú principal de opciones',
         '["nombre_negocio", "emoji_servicio"]'),
        
        ('ayuda_general',
         '🆘 *AYUDA - {nombre_negocio}*\n\n*1* {emoji_servicio} - Agendar cita con {texto_profesional}\n*2* 📋 - Ver tus reservas activas\n*3* ❌ - Cancelar una reserva\n*4* 🆘 - Mostrar esta ayuda\n\n💡 *Siempre puedes volver al menú principal con* *0*',
         'Mensaje de ayuda general',
         '["nombre_negocio", "emoji_servicio", "texto_profesional"]'),
        
        ('error_generico',
         '❌ Ocurrió un error en {nombre_negocio}\n\nPor favor, intenta nuevamente o contacta a soporte.\n\n💡 *Vuelve al menú principal con* *0*',
         'Mensaje de error genérico',
         '["nombre_negocio"]'),
        
        ('cita_confirmada',
         '✅ *¡Cita confirmada!*\n\n👤 *Cliente:* {cliente_nombre}\n{emoji_profesional} *{texto_profesional_title}:* {profesional_nombre}\n💼 *Servicio:* {servicio_nombre}\n💰 *Precio:* {precio_formateado}\n📅 *Fecha:* {fecha}\n⏰ *Hora:* {hora}\n🎫 *ID:* #{cita_id}\n\n📍 *Dirección:* {direccion}\n📞 *Contacto:* {telefono_contacto}\n\nTe enviaremos recordatorios 24 horas y 1 hora antes de tu cita.',
         'Confirmación de cita agendada',
         '["cliente_nombre", "emoji_profesional", "texto_profesional_title", "profesional_nombre", "servicio_nombre", "precio_formateado", "fecha", "hora", "cita_id", "direccion", "telefono_contacto"]'),
        
        ('sin_citas',
         '📋 No tienes citas programadas en {nombre_negocio}.\n\n💡 *Vuelve al menú principal con* *0*',
         'Cuando el cliente no tiene citas',
         '["nombre_negocio"]'),
        
        ('cita_cancelada',
         '❌ *Cita cancelada*\n\nHola {cliente_nombre}, has cancelado tu cita del {fecha} a las {hora} en {nombre_negocio}.\n\nEsperamos verte pronto en otra ocasión.',
         'Confirmación de cancelación',
         '["cliente_nombre", "fecha", "hora", "nombre_negocio"]')
    ]
    
    for nombre, plantilla, descripcion, variables in plantillas_base:
        if postgres:
            cursor.execute('''
                INSERT INTO plantillas_mensajes 
                (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                VALUES (NULL, %s, %s, %s, %s, TRUE)
            ''', (nombre, plantilla, descripcion, variables))
        else:
            cursor.execute('''
                INSERT INTO plantillas_mensajes 
                (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                VALUES (NULL, ?, ?, ?, ?, TRUE)
            ''', (nombre, plantilla, descripcion, variables))


def _insertar_configuracion_horarios(cursor):
    """Insertar configuración de horarios por día - VERSIÓN CORREGIDA"""
    postgres = is_postgresql()
    
    dias_semana = [
        (1, '09:00', '19:00', '13:00', '14:00'),  # Lunes
        (2, '09:00', '19:00', '13:00', '14:00'),  # Martes
        (3, '09:00', '19:00', '13:00', '14:00'),  # Miércoles
        (4, '09:00', '19:00', '13:00', '14:00'),  # Jueves
        (5, '09:00', '19:00', '13:00', '14:00'),  # Viernes
        (6, '09:00', '19:00', '13:00', '14:00'),  # Sábado
        (7, '09:00', '13:00', None, None)         # Domingo
    ]
    
    # Para cada negocio existente
    if postgres:
        cursor.execute('SELECT id FROM negocios')
    else:
        cursor.execute('SELECT id FROM negocios')
    
    negocios = cursor.fetchall()
    
    for negocio in negocios:
        # ✅ CORRECCIÓN: Acceder correctamente al ID del negocio
        if hasattr(negocio, 'keys'):  # Es un diccionario (RealDictCursor)
            negocio_id = negocio['id']
        else:  # Es una tupla
            negocio_id = negocio[0]
            
        for dia in dias_semana:
            if postgres:
                cursor.execute('''
                    SELECT id FROM configuracion_horarios 
                    WHERE negocio_id = %s AND dia_semana = %s
                ''', (negocio_id, dia[0]))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO configuracion_horarios 
                        (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (negocio_id, dia[0], True, dia[1], dia[2], dia[3], dia[4]))
            else:
                cursor.execute('''
                    INSERT OR IGNORE INTO configuracion_horarios 
                    (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                ''', (negocio_id, dia[0], dia[1], dia[2], dia[3], dia[4]))


def _insertar_profesionales_por_defecto(cursor):
    """Insertar profesionales por defecto - VERSIÓN CORREGIDA"""
    postgres = is_postgresql()
    
    profesionales_data = [
        (1, 1, 'Carlos Profesional', 'Especialista en servicios clásicos', '1234', 3),
        (2, 1, 'Ana Profesional', 'Especialista en tratamientos', '5678', 4),
        (3, 1, 'María Profesional', 'Especialista unisex', '9012', None)
    ]
    
    for prof_data in profesionales_data:
        if postgres:
            cursor.execute('SELECT id FROM profesionales WHERE id = %s', (prof_data[0],))
            resultado = cursor.fetchone()
            if not resultado:
                cursor.execute('''
                    INSERT INTO profesionales (id, negocio_id, nombre, especialidad, pin, usuario_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', prof_data)
        else:
            cursor.execute('''
                INSERT OR IGNORE INTO profesionales (id, negocio_id, nombre, especialidad, pin, usuario_id) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', prof_data)


def _insertar_servicios_por_defecto(cursor):
    """Insertar servicios por defecto - VERSIÓN CORREGIDA"""
    postgres = is_postgresql()
    
    servicios_data = [
        (1, 1, 'Servicio Básico', 45, 15000, 'Servicio estándar'),
        (2, 1, 'Servicio Completo', 60, 20000, 'Servicio completo'),
        (3, 1, 'Servicio Premium', 75, 25000, 'Servicio premium'),
        (4, 1, 'Servicio Express', 30, 12000, 'Servicio rápido'),
        (5, 1, 'Servicio VIP', 90, 30000, 'Servicio exclusivo')
    ]
    
    for serv_data in servicios_data:
        if postgres:
            cursor.execute('SELECT id FROM servicios WHERE id = %s', (serv_data[0],))
            resultado = cursor.fetchone()
            if not resultado:
                cursor.execute('''
                    INSERT INTO servicios (id, negocio_id, nombre, duracion, precio, descripcion) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', serv_data)
        else:
            cursor.execute('''
                INSERT OR IGNORE INTO servicios (id, negocio_id, nombre, duracion, precio, descripcion) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', serv_data)


# =============================================================================
# SISTEMA DE PLANTILLAS
# =============================================================================

def obtener_plantilla(negocio_id, nombre_plantilla):
    """Obtener una plantilla específica"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Primero buscar plantilla personalizada
        sql = '''
            SELECT * FROM plantillas_mensajes 
            WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
        '''
        plantilla = fetch_one(cursor, sql, (negocio_id, nombre_plantilla))
        es_personalizada = True
        
        # Si no existe personalizada, usar la base
        if not plantilla:
            sql = '''
                SELECT * FROM plantillas_mensajes 
                WHERE nombre = ? AND es_base = TRUE
            '''
            plantilla = fetch_one(cursor, sql, (nombre_plantilla,))
            es_personalizada = False
        
        if plantilla:
            plantilla['es_personalizada'] = es_personalizada
            return plantilla
        else:
            return None
            
    except Exception as e:
        print(f"❌ Error en obtener_plantilla: {e}")
        return None
    finally:
        conn.close()


def obtener_plantillas_base():
    """Obtener SOLO las 8 plantillas base del sistema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = '''
        SELECT * FROM plantillas_mensajes 
        WHERE negocio_id IS NULL AND es_base = TRUE
        AND nombre IN (
            'saludo_inicial_nuevo', 'saludo_inicial_existente', 'menu_principal',
            'ayuda_general', 'error_generico', 'cita_confirmada', 
            'sin_citas', 'cita_cancelada'
        )
        ORDER BY 
            CASE nombre
                WHEN 'saludo_inicial_nuevo' THEN 1
                WHEN 'saludo_inicial_existente' THEN 2
                WHEN 'menu_principal' THEN 3
                WHEN 'ayuda_general' THEN 4
                WHEN 'error_generico' THEN 5
                WHEN 'cita_confirmada' THEN 6
                WHEN 'sin_citas' THEN 7
                WHEN 'cita_cancelada' THEN 8
                ELSE 9
            END
    '''
    
    plantillas = fetch_all(cursor, sql)
    conn.close()
    return plantillas


def obtener_plantillas_negocio(negocio_id):
    """Obtener todas las plantillas disponibles para un negocio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener nombres únicos de plantillas base
    sql = 'SELECT DISTINCT nombre FROM plantillas_mensajes WHERE es_base = TRUE'
    nombres_plantillas = [row['nombre'] for row in fetch_all(cursor, sql)]
    
    plantillas_resultado = []
    
    # Para cada nombre de plantilla, obtener la versión personalizada si existe
    for nombre in nombres_plantillas:
        plantilla = obtener_plantilla(negocio_id, nombre)
        if plantilla:
            plantillas_resultado.append(plantilla)
    
    conn.close()
    return plantillas_resultado


def guardar_plantilla_personalizada(negocio_id, nombre_plantilla, contenido, descripcion=''):
    """Guardar o actualizar plantilla personalizada"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si ya existe una personalizada
        sql = '''
            SELECT id FROM plantillas_mensajes 
            WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
        '''
        existe = fetch_one(cursor, sql, (negocio_id, nombre_plantilla))
        
        if existe:
            # Actualizar existente
            sql = '''
                UPDATE plantillas_mensajes 
                SET plantilla = ?, descripcion = ?
                WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
            '''
            execute_sql(cursor, sql, (contenido, descripcion, negocio_id, nombre_plantilla))
        else:
            # Crear nueva personalizada basada en la plantilla base
            sql = '''
                SELECT descripcion, variables_disponibles 
                FROM plantillas_mensajes 
                WHERE nombre = ? AND es_base = TRUE
            '''
            plantilla_base = fetch_one(cursor, sql, (nombre_plantilla,))
            
            descripcion_final = descripcion
            variables_disponibles = '[]'
            
            if plantilla_base:
                if not descripcion_final:
                    descripcion_final = plantilla_base['descripcion']
                variables_disponibles = plantilla_base['variables_disponibles']
            
            sql = '''
                INSERT INTO plantillas_mensajes 
                (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                VALUES (?, ?, ?, ?, ?, FALSE)
            '''
            execute_sql(cursor, sql, (negocio_id, nombre_plantilla, contenido, descripcion_final, variables_disponibles))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Error guardando plantilla: {e}")
        return False
    finally:
        conn.close()


def crear_plantillas_personalizadas_para_negocios():
    """Crear copias personalizadas de plantillas base para todos los negocios"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Obtener todos los negocios activos
        sql = "SELECT id FROM negocios WHERE activo = TRUE"
        negocios = fetch_all(cursor, sql)
        
        # Obtener plantillas base
        sql = "SELECT * FROM plantillas_mensajes WHERE es_base = TRUE"
        plantillas_base = fetch_all(cursor, sql)
        
        for negocio in negocios:
            negocio_id = negocio['id']
            
            for plantilla_base in plantillas_base:
                nombre = plantilla_base['nombre']
                
                # Verificar si ya existe plantilla personalizada
                sql = '''
                    SELECT id FROM plantillas_mensajes 
                    WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
                '''
                if not fetch_one(cursor, sql, (negocio_id, nombre)):
                    # Crear plantilla personalizada
                    sql = '''
                        INSERT INTO plantillas_mensajes 
                        (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                        VALUES (?, ?, ?, ?, ?, FALSE)
                    '''
                    execute_sql(cursor, sql, (
                        negocio_id, 
                        nombre, 
                        plantilla_base['plantilla'], 
                        plantilla_base['descripcion'], 
                        plantilla_base['variables_disponibles']
                    ))
        
        conn.commit()
        print("✅ Plantillas personalizadas creadas exitosamente")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creando plantillas personalizadas: {e}")
    finally:
        conn.close()


# =============================================================================
# GESTIÓN DE NEGOCIOS
# =============================================================================

def obtener_negocio_por_telefono(telefono_whatsapp):
    """Obtener un negocio por su número de WhatsApp"""
    conn = get_db_connection()
    sql = 'SELECT * FROM negocios WHERE telefono_whatsapp = ? AND activo = TRUE'
    negocio = fetch_one(conn.cursor(), sql, (telefono_whatsapp,))
    conn.close()
    return negocio


def obtener_negocio_por_id(negocio_id):
    """Obtener negocio por ID"""
    conn = get_db_connection()
    sql = 'SELECT * FROM negocios WHERE id = ?'
    negocio = fetch_one(conn.cursor(), sql, (negocio_id,))
    conn.close()
    return negocio


def obtener_todos_negocios():
    """Obtener todos los negocios - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    sql = 'SELECT * FROM negocios ORDER BY fecha_creacion DESC'
    negocios = fetch_all(conn.cursor(), sql)
    conn.close()
    
    # Procesar las fechas para la plantilla
    negocios_procesados = []
    for negocio in negocios:
        if not isinstance(negocio, dict):
            negocio_dict = dict(negocio)
        else:
            negocio_dict = negocio
        
        # Procesar fecha_creacion
        if negocio_dict.get('fecha_creacion'):
            if hasattr(negocio_dict['fecha_creacion'], 'strftime'):
                negocio_dict['fecha_creacion_str'] = negocio_dict['fecha_creacion'].strftime('%Y-%m-%d')
            else:
                negocio_dict['fecha_creacion_str'] = str(negocio_dict['fecha_creacion'])[:10]
        else:
            negocio_dict['fecha_creacion_str'] = '-'
        
        negocios_procesados.append(negocio_dict)
    
    return negocios_procesados


def crear_negocio(nombre, telefono_whatsapp, tipo_negocio='general', configuracion='{}', emoji='👋'):
    """Crear un nuevo negocio - VERSIÓN CORREGIDA PARA POSTGRESQL"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Para PostgreSQL, NO especificar el ID - dejar que la secuencia lo asigne automáticamente
        if is_postgresql():
            sql = '''
                INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            '''
            cursor.execute(sql, (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion))
            result = cursor.fetchone()
            # ✅ CORRECCIÓN: Acceder correctamente al resultado
            if hasattr(result, 'keys'):  # Es un diccionario (RealDictCursor)
                negocio_id = result['id']
            else:  # Es una tupla
                negocio_id = result[0] if result else None
        else:
            # Para SQLite
            sql = '''
                INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion)
                VALUES (?, ?, ?, ?, ?)
            '''
            execute_sql(cursor, sql, (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion))
            negocio_id = cursor.lastrowid
        
        if not negocio_id:
            print("❌ No se pudo obtener el ID del negocio creado")
            conn.rollback()
            return None
            
        print(f"✅ Negocio creado con ID: {negocio_id}")
        
        # Crear configuración por defecto
        sql = 'INSERT INTO configuracion (negocio_id) VALUES (?)'
        execute_sql(cursor, sql, (negocio_id,))
        
        # Crear configuración de horarios
        _insertar_configuracion_horarios_para_negocio(cursor, negocio_id)
        
        # Crear usuario propietario por defecto
        email_propietario = f"propietario{negocio_id}@negocio.com"
        sql = '''
            INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
            VALUES (?, ?, ?, ?, ?)
        '''
        execute_sql(cursor, sql, (
            negocio_id, 
            'Propietario', 
            email_propietario, 
            generate_password_hash('propietario123'), 
            'propietario'
        ))
        
        # Crear servicios por defecto
        _crear_servicios_por_defecto_negocio(cursor, negocio_id, tipo_negocio)
        
        # Crear profesional por defecto
        sql = '''
            INSERT INTO profesionales (negocio_id, nombre, especialidad, pin)
            VALUES (?, ?, ?, ?)
        '''
        execute_sql(cursor, sql, (negocio_id, 'Principal', 'Especialista', '0000'))
        
        conn.commit()
        
        # Crear plantillas personalizadas
        crear_plantillas_personalizadas_para_negocios()
        
        return negocio_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error al crear negocio: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()


def _insertar_configuracion_horarios_para_negocio(cursor, negocio_id):
    """Insertar configuración de horarios para un negocio específico - VERSIÓN CORREGIDA"""
    dias_semana = [
        (1, '09:00', '19:00', '13:00', '14:00'),  # Lunes
        (2, '09:00', '19:00', '13:00', '14:00'),  # Martes
        (3, '09:00', '19:00', '13:00', '14:00'),  # Miércoles
        (4, '09:00', '19:00', '13:00', '14:00'),  # Jueves
        (5, '09:00', '19:00', '13:00', '14:00'),  # Viernes
        (6, '09:00', '19:00', '13:00', '14:00'),  # Sábado
        (7, '09:00', '13:00', None, None)         # Domingo (medio día)
    ]
    
    for dia in dias_semana:
        if is_postgresql():
            sql = '''
                INSERT INTO configuracion_horarios 
                (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            '''
        else:
            sql = '''
                INSERT INTO configuracion_horarios 
                (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            '''
        
        execute_sql(cursor, sql, (
            negocio_id, 
            dia[0], 
            True,  # Activo por defecto
            dia[1], 
            dia[2], 
            dia[3],  # ✅ Almuerzo inicio
            dia[4]   # ✅ Almuerzo fin
        ))


def _crear_servicios_por_defecto_negocio(cursor, negocio_id, tipo_negocio):
    """Crear servicios por defecto según el tipo de negocio"""
    if tipo_negocio == 'barberia':
        servicios = [
            ('Corte Básico', 45, 15000, 'Corte de cabello estándar'),
            ('Corte Completo', 60, 20000, 'Corte + lavado + peinado'),
            ('Corte + Barba', 75, 25000, 'Corte completo + arreglo de barba')
        ]
    elif tipo_negocio == 'spa_unas':
        servicios = [
            ('Manicure Básica', 30, 18000, 'Limado y esmaltado básico'),
            ('Manicure Semi', 45, 25000, 'Incluye cutículas y hidratación'),
            ('Pedicure', 45, 22000, 'Cuidado completo de pies')
        ]
    else:
        servicios = [
            ('Servicio Básico', 60, 20000, 'Servicio estándar'),
            ('Servicio Completo', 90, 30000, 'Servicio premium')
        ]
    
    for nombre, duracion, precio, descripcion in servicios:
        sql = '''
            INSERT INTO servicios (negocio_id, nombre, duracion, precio, descripcion)
            VALUES (?, ?, ?, ?, ?)
        '''
        execute_sql(cursor, sql, (negocio_id, nombre, duracion, precio, descripcion))


def actualizar_negocio(negocio_id, nombre, telefono_whatsapp, tipo_negocio, activo, configuracion):
    """Actualizar un negocio existente"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        sql = '''
            UPDATE negocios 
            SET nombre = ?, telefono_whatsapp = ?, tipo_negocio = ?, activo = ?, configuracion = ?
            WHERE id = ?
        '''
        execute_sql(cursor, sql, (nombre, telefono_whatsapp, tipo_negocio, activo, configuracion, negocio_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error actualizando negocio: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# GESTIÓN DE PROFESIONALES Y SERVICIOS
# =============================================================================

def obtener_profesionales(negocio_id=1):
    """Obtener lista de todos los profesionales activos"""
    conn = get_db_connection()
    sql = '''
        SELECT id, nombre, especialidad, pin, telefono, activo
        FROM profesionales 
        WHERE negocio_id = ? AND activo = TRUE
        ORDER BY nombre
    '''
    profesionales = fetch_all(conn.cursor(), sql, (negocio_id,))
    conn.close()
    return profesionales


def obtener_servicios(negocio_id):
    """Obtener servicios activos de un negocio"""
    conn = get_db_connection()
    sql = '''
        SELECT id, nombre, duracion, precio 
        FROM servicios 
        WHERE negocio_id = ? AND activo = TRUE
        ORDER BY nombre
    '''
    servicios = fetch_all(conn.cursor(), sql, (negocio_id,))
    conn.close()
    return servicios


def obtener_servicio_por_id(servicio_id, negocio_id):
    """Obtener un servicio específico por ID"""
    conn = get_db_connection()
    sql = 'SELECT * FROM servicios WHERE id = ? AND negocio_id = ?'
    servicio = fetch_one(conn.cursor(), sql, (servicio_id, negocio_id))
    conn.close()
    return servicio


def obtener_nombre_profesional(negocio_id, profesional_id):
    """Obtener nombre de un profesional por ID"""
    conn = get_db_connection()
    sql = 'SELECT nombre FROM profesionales WHERE negocio_id = ? AND id = ?'
    resultado = fetch_one(conn.cursor(), sql, (negocio_id, profesional_id))
    conn.close()
    return resultado['nombre'] if resultado else 'Profesional no encontrado'


def obtener_nombre_servicio(negocio_id, servicio_id):
    """Obtener nombre de un servicio por ID"""
    conn = get_db_connection()
    sql = 'SELECT nombre FROM servicios WHERE negocio_id = ? AND id = ?'
    resultado = fetch_one(conn.cursor(), sql, (negocio_id, servicio_id))
    conn.close()
    return resultado['nombre'] if resultado else 'Servicio no encontrado'


def obtener_duracion_servicio(negocio_id, servicio_id):
    """Obtener duración de un servicio específico"""
    conn = get_db_connection()
    sql = 'SELECT duracion FROM servicios WHERE negocio_id = ? AND id = ?'
    resultado = fetch_one(conn.cursor(), sql, (negocio_id, servicio_id))
    conn.close()
    return resultado['duracion'] if resultado else None


# =============================================================================
# GESTIÓN DE CITAS
# =============================================================================

def agregar_cita(negocio_id, profesional_id, cliente_telefono, fecha, hora, servicio_id, cliente_nombre=""):
    """Agregar nueva cita a la base de datos"""
    print(f"🔍 [DEBUG agregar_cita] Iniciando inserción:")
    print(f"   - negocio_id: {negocio_id}")
    print(f"   - profesional_id: {profesional_id}")
    print(f"   - cliente_telefono: {cliente_telefono}")
    print(f"   - cliente_nombre: {cliente_nombre}")
    print(f"   - fecha: {fecha}")
    print(f"   - hora: {hora}")
    print(f"   - servicio_id: {servicio_id}")
    
    conn = get_db_connection()
    if not conn:
        print("❌ [DEBUG] No hay conexión a la BD")
        return 0
    
    cursor = conn.cursor()
    
    try:
        print("🔍 [DEBUG] Intentando INSERT...")
        
        # Para PostgreSQL con RealDictCursor
        sql = '''
            INSERT INTO citas (negocio_id, profesional_id, cliente_telefono, cliente_nombre, 
                             fecha, hora, servicio_id, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmado')
            RETURNING id
        '''
        
        cursor.execute(sql, (negocio_id, profesional_id, cliente_telefono, cliente_nombre, 
                           fecha, hora, servicio_id))
        
        # ✅ CORRECCIÓN: Acceder correctamente al resultado
        result = cursor.fetchone()
        
        # Si usas RealDictRow, accede por nombre de columna
        if hasattr(result, '__getitem__') and isinstance(result, dict):
            cita_id = result['id']
        else:
            # Si es una tupla normal
            cita_id = result[0] if result else 0
        
        conn.commit()
        
        print(f"✅ [DEBUG] ¡ÉXITO! Cita agregada con ID: {cita_id}")
        return cita_id
        
    except Exception as e:
        print(f"❌ [DEBUG] Error CRÍTICO al agregar cita: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        if conn:
            conn.close()
        print("🔍 [DEBUG] Conexión cerrada")


def obtener_citas_dia(negocio_id, profesional_id, fecha):
    """Obtener todas las citas de un profesional en un día específico - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    
    if is_postgresql():
        # ✅ CORRECCIÓN: Usar comparación directa con fecha convertida
        sql = '''
            SELECT c.hora, s.duracion 
            FROM citas c 
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s AND c.profesional_id = %s 
            AND c.fecha::DATE = %s::DATE 
            AND c.estado != 'cancelado'
            ORDER BY c.hora
        '''
    else:
        sql = '''
            SELECT c.hora, s.duracion 
            FROM citas c 
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = ? AND c.profesional_id = ? AND c.fecha = ? 
            AND c.estado != 'cancelado'
            ORDER BY c.hora
        '''
    
    citas = fetch_all(conn.cursor(), sql, (negocio_id, profesional_id, fecha))
    conn.close()
    return citas


def es_cliente_nuevo(telefono, negocio_id):
    """Verificar si es un cliente nuevo"""
    conn = get_db_connection()
    sql = '''
        SELECT COUNT(*) as count FROM citas 
        WHERE cliente_telefono = ? AND negocio_id = ?
    '''
    resultado = fetch_one(conn.cursor(), sql, (telefono, negocio_id))
    conn.close()
    count = resultado['count'] if resultado else 0
    return count == 0


def obtener_nombre_cliente(telefono, negocio_id):
    """Obtener nombre del cliente desde la base de datos - VERSIÓN CORREGIDA"""
    try:
        # Si el "teléfono" es un UUID (session_id), no buscar en BD
        if len(str(telefono)) > 15 or '-' in str(telefono):
            print(f"⚠️ [DB] Se recibió UUID/session_id como teléfono: {telefono}")
            return None
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        nombre_cliente = None
        
        # PRIMERO: Intentar buscar en la tabla de clientes
        try:
            cursor.execute('''
                SELECT nombre 
                FROM clientes 
                WHERE telefono = %s 
                AND negocio_id = %s 
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
            ''', (telefono, negocio_id))
            
            resultado = cursor.fetchone()
            
            if resultado:
                nombre = resultado[0]
                if nombre and len(str(nombre).strip()) >= 2:
                    nombre_cliente = str(nombre).strip()
                    print(f"✅ [DB] Nombre encontrado en tabla clientes: {nombre_cliente}")
            
        except Exception as e:
            print(f"⚠️ [DB] Error buscando en tabla clientes: {e}")
            # Continuamos
        
        # Si no encontramos en clientes, buscar en citas
        if not nombre_cliente:
            try:
                cursor.execute('''
                    SELECT cliente_nombre 
                    FROM citas 
                    WHERE cliente_telefono = %s 
                    AND negocio_id = %s 
                    AND cliente_nombre IS NOT NULL 
                    AND TRIM(cliente_nombre) != ''
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (telefono, negocio_id))
                
                resultado = cursor.fetchone()
                
                if resultado:
                    nombre = resultado[0]
                    if nombre and len(str(nombre).strip()) >= 2:
                        nombre_cliente = str(nombre).strip()
                        print(f"✅ [DB] Nombre encontrado en tabla citas: {nombre_cliente}")
                
            except Exception as e:
                print(f"⚠️ [DB] Error buscando en tabla citas: {e}")
        
        conn.close()
        return nombre_cliente
        
    except Exception as e:
        print(f"❌ Error general en obtener_nombre_cliente: {e}")
        return None


def obtener_citas_para_profesional(negocio_id, profesional_id, fecha):
    """Obtener citas de un profesional para una fecha específica - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    
    if is_postgresql():
        # ✅ CORRECCIÓN: Usar comparación directa con fecha convertida
        sql = '''
            SELECT c.*, s.nombre as servicio_nombre, s.precio, s.duracion
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s AND c.profesional_id = %s 
            AND c.fecha::DATE = %s::DATE
            ORDER BY c.hora
        '''
    else:
        sql = '''
            SELECT c.*, s.nombre as servicio_nombre, s.precio, s.duracion
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = ? AND c.profesional_id = ? AND c.fecha = ?
            ORDER BY c.hora
        '''
    
    citas = fetch_all(conn.cursor(), sql, (negocio_id, profesional_id, fecha))
    conn.close()
    return citas


# =============================================================================
# CONFIGURACIÓN DE HORARIOS
# =============================================================================

def obtener_horarios_por_dia(negocio_id, fecha):
    """Obtener horarios para un día específico - VERSIÓN CORREGIDA PARA POSTGRESQL"""
    try:
        # Convertir fecha a día de la semana (0=lunes, 6=domingo)
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        dia_semana_real = fecha_obj.weekday()  # 0=lunes, 1=martes, ..., 6=domingo
        
        # Convertir de 0-6 a 1-7 para buscar en la BD
        dia_semana_bd = dia_semana_real + 1  # 0→1, 1→2, ..., 6→7
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)  # ✅ Usar RealDictCursor
        sql = '''
            SELECT activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
            FROM configuracion_horarios
            WHERE negocio_id = %s AND dia_semana = %s
        '''
        cursor.execute(sql, (negocio_id, dia_semana_bd))  # ✅ Usar execute directo
        result = cursor.fetchone()
        conn.close()
        
        if result:
            # ✅ CORRECCIÓN: Convertir objetos time a strings
            hora_inicio = result['hora_inicio']
            hora_fin = result['hora_fin']
            almuerzo_inicio = result['almuerzo_inicio']
            almuerzo_fin = result['almuerzo_fin']
            
            return {
                'activo': bool(result['activo']),
                'hora_inicio': hora_inicio.strftime('%H:%M') if hasattr(hora_inicio, 'strftime') else str(hora_inicio),
                'hora_fin': hora_fin.strftime('%H:%M') if hasattr(hora_fin, 'strftime') else str(hora_fin),
                'almuerzo_inicio': almuerzo_inicio.strftime('%H:%M') if almuerzo_inicio and hasattr(almuerzo_inicio, 'strftime') else str(almuerzo_inicio) if almuerzo_inicio else None,
                'almuerzo_fin': almuerzo_fin.strftime('%H:%M') if almuerzo_fin and hasattr(almuerzo_fin, 'strftime') else str(almuerzo_fin) if almuerzo_fin else None
            }
        else:
            return {
                'activo': False,
                'hora_inicio': '09:00',
                'hora_fin': '18:00',
                'almuerzo_inicio': None,
                'almuerzo_fin': None
            }
            
    except Exception as e:
        print(f"❌ Error en obtener_horarios_por_dia: {e}")
        return {
            'activo': False,
            'hora_inicio': '09:00',
            'hora_fin': '18:00',
            'almuerzo_inicio': None,
            'almuerzo_fin': None
        }

def obtener_configuracion_horarios(negocio_id):
    """Obtener configuración de horarios por días"""
    conn = get_db_connection()
    sql = '''
        SELECT dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
        FROM configuracion_horarios 
        WHERE negocio_id = ?
        ORDER BY dia_semana
    '''
    resultados = fetch_all(conn.cursor(), sql, (negocio_id,))
    conn.close()
    
    dias_config = {}
    for row in resultados:
        dias_config[row['dia_semana']] = {
            'activo': bool(row['activo']),
            'hora_inicio': row['hora_inicio'],
            'hora_fin': row['hora_fin'],
            'almuerzo_inicio': row['almuerzo_inicio'],
            'almuerzo_fin': row['almuerzo_fin']
        }
    
    return dias_config


def actualizar_configuracion_horarios(negocio_id, configuraciones):
    """Actualizar configuración de horarios"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for dia_id, config in configuraciones.items():
            if is_postgresql():
                sql = '''
                    INSERT INTO configuracion_horarios 
                    (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (negocio_id, dia_semana) 
                    DO UPDATE SET 
                        activo = EXCLUDED.activo,
                        hora_inicio = EXCLUDED.hora_inicio,
                        hora_fin = EXCLUDED.hora_fin,
                        almuerzo_inicio = EXCLUDED.almuerzo_inicio,
                        almuerzo_fin = EXCLUDED.almuerzo_fin
                '''
            else:
                sql = '''
                    INSERT OR REPLACE INTO configuracion_horarios 
                    (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                '''
            
            execute_sql(cursor, sql, (
                negocio_id, dia_id, 
                config.get('activo', False),
                config.get('hora_inicio', '09:00'),
                config.get('hora_fin', '19:00'),
                config.get('almuerzo_inicio'),
                config.get('almuerzo_fin')
            ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error actualizando configuración de horarios: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# AUTENTICACIÓN DE USUARIOS
# =============================================================================

def crear_profesional(negocio_id, nombre, especialidad='', servicios_ids=None, activo=True):
    """Crear profesional - VERSIÓN SIMPLIFICADA SIN PIN"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print(f"🔧 DEBUG crear_profesional:")
        print(f"  - negocio_id: {negocio_id}")
        print(f"  - nombre: {nombre}")
        print(f"  - especialidad: {especialidad}")
        print(f"  - servicios_ids: {servicios_ids}")
        print(f"  - activo: {activo}")
        
        # Insertar profesional sin PIN
        cursor.execute('''
            INSERT INTO profesionales (negocio_id, nombre, especialidad, activo)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (negocio_id, nombre, especialidad, activo))
        
        result = cursor.fetchone()
        
        if not result:
            print(f"❌ Error: No se obtuvo ID del profesional insertado")
            conn.rollback()
            conn.close()
            return None
        
        # ✅ CORRECCIÓN: Acceder correctamente al ID
        if hasattr(result, 'keys'):  # Es un diccionario
            profesional_id = result['id']
        else:  # Es una tupla
            profesional_id = result[0]
        
        print(f"✅ Profesional creado con ID: {profesional_id}")
        
        # Asignar servicios solo si hay servicios seleccionados
        if servicios_ids:
            for servicio_id in servicios_ids:
                try:
                    servicio_id_int = int(servicio_id)
                    cursor.execute('''
                        INSERT INTO profesional_servicios (profesional_id, servicio_id)
                        VALUES (%s, %s)
                    ''', (profesional_id, servicio_id_int))
                    print(f"  - Servicio {servicio_id_int} asignado")
                except ValueError:
                    print(f"⚠️  ID de servicio inválido: {servicio_id}")
        else:
            print("ℹ️  No se seleccionaron servicios")
        
        conn.commit()
        return profesional_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ ERROR en crear_profesional: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()

def crear_usuario(negocio_id, nombre, email, password, rol='propietario'):
    """Crear usuario simple - VERSIÓN SIMPLIFICADA"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si el email ya existe
        if is_postgresql():
            cursor.execute('SELECT id FROM usuarios WHERE email = %s', (email,))
        else:
            cursor.execute('SELECT id FROM usuarios WHERE email = ?', (email,))
        
        if cursor.fetchone():
            print(f"❌ Email {email} ya está en uso")
            return None
        
        # Generar hash de la contraseña
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # Crear usuario
        if is_postgresql():
            cursor.execute('''
                INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (negocio_id, nombre, email, password_hash, rol))
            
            result = cursor.fetchone()
            if hasattr(result, 'keys'):
                usuario_id = result['id']
            else:
                usuario_id = result[0] if result else None
        else:
            cursor.execute('''
                INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
                VALUES (?, ?, ?, ?, ?)
            ''', (negocio_id, nombre, email, password_hash, rol))
            usuario_id = cursor.lastrowid
        
        # Si es profesional, crear también en la tabla profesionales
        if rol == 'profesional' and usuario_id:
            if is_postgresql():
                cursor.execute('''
                    INSERT INTO profesionales (negocio_id, nombre, especialidad, usuario_id, activo)
                    VALUES (%s, %s, %s, %s, TRUE)
                ''', (negocio_id, nombre, 'General', usuario_id))
            else:
                cursor.execute('''
                    INSERT INTO profesionales (negocio_id, nombre, especialidad, usuario_id, activo)
                    VALUES (?, ?, ?, ?, 1)
                ''', (negocio_id, nombre, 'General', usuario_id))
        
        conn.commit()
        print(f"✅ Usuario creado exitosamente: {email} (ID: {usuario_id}, Rol: {rol})")
        return usuario_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creando usuario: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()

def crear_profesional_con_usuario(negocio_id, nombre, email, password, especialidad='', 
                                  servicios_ids=None, telefono=None):
    """Crear profesional completo con usuario asociado - SIN PIN"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print(f"🔧 [DEBUG] Creando profesional con usuario:")
        print(f"  - negocio_id: {negocio_id}")
        print(f"  - nombre: {nombre}")
        print(f"  - email: {email}")
        print(f"  - especialidad: {especialidad}")
        print(f"  - servicios_ids: {servicios_ids}")
        
        # 1. Verificar si el email ya existe
        if is_postgresql():
            cursor.execute('SELECT id FROM usuarios WHERE email = %s', (email,))
        else:
            cursor.execute('SELECT id FROM usuarios WHERE email = ?', (email,))
        
        if cursor.fetchone():
            print(f"❌ Email {email} ya está en uso")
            conn.close()
            return None
        
        # 2. Generar hash de la contraseña
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # 3. Crear usuario
        if is_postgresql():
            cursor.execute('''
                INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (negocio_id, nombre, email, password_hash, 'profesional'))
            
            result = cursor.fetchone()
            if hasattr(result, 'keys'):
                usuario_id = result['id']
            else:
                usuario_id = result[0] if result else None
        else:
            cursor.execute('''
                INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
                VALUES (?, ?, ?, ?, ?)
            ''', (negocio_id, nombre, email, password_hash, 'profesional'))
            usuario_id = cursor.lastrowid
        
        if not usuario_id:
            print("❌ Error al crear usuario")
            conn.rollback()
            conn.close()
            return None
        
        print(f"✅ Usuario creado con ID: {usuario_id}")
        
        # 4. Crear profesional vinculado al usuario (sin PIN)
        if is_postgresql():
            cursor.execute('''
                INSERT INTO profesionales (negocio_id, nombre, especialidad, usuario_id, telefono, activo)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                RETURNING id
            ''', (negocio_id, nombre, especialidad, usuario_id, telefono))
            
            result = cursor.fetchone()
            if hasattr(result, 'keys'):
                profesional_id = result['id']
            else:
                profesional_id = result[0] if result else None
        else:
            cursor.execute('''
                INSERT INTO profesionales (negocio_id, nombre, especialidad, usuario_id, telefono, activo)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (negocio_id, nombre, especialidad, usuario_id, telefono))
            profesional_id = cursor.lastrowid
        
        print(f"✅ Profesional creado con ID: {profesional_id}")
        
        # 5. Asignar servicios si se proporcionaron
        if servicios_ids:
            for servicio_id in servicios_ids:
                try:
                    servicio_id_int = int(servicio_id)
                    cursor.execute('''
                        INSERT INTO profesional_servicios (profesional_id, servicio_id)
                        VALUES (%s, %s)
                    ''', (profesional_id, servicio_id_int))
                    print(f"  - Servicio {servicio_id_int} asignado")
                except ValueError:
                    print(f"⚠️  ID de servicio inválido: {servicio_id}")
        
        conn.commit()
        return {'usuario_id': usuario_id, 'profesional_id': profesional_id}
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creando profesional con usuario: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()


def verificar_usuario(email, password):
    """Verificar credenciales de usuario - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    
    if is_postgresql():
        sql = '''
            SELECT u.*, n.nombre as negocio_nombre 
            FROM usuarios u 
            JOIN negocios n ON u.negocio_id = n.id 
            WHERE u.email = %s AND u.activo = TRUE
        '''
    else:
        sql = '''
            SELECT u.*, n.nombre as negocio_nombre 
            FROM usuarios u 
            JOIN negocios n ON u.negocio_id = n.id 
            WHERE u.email = ? AND u.activo = TRUE
        '''
    
    usuario = fetch_one(conn.cursor(), sql, (email,))
    conn.close()
    
    if usuario:
        # SHA256
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if usuario['password_hash'] == password_hash:
            # Actualizar último login
            conn = get_db_connection()
            if is_postgresql():
                sql = 'UPDATE usuarios SET ultimo_login = %s WHERE id = %s'
            else:
                sql = 'UPDATE usuarios SET ultimo_login = ? WHERE id = ?'
            
            execute_sql(conn.cursor(), sql, (datetime.now(), usuario['id']))
            conn.commit()
            conn.close()
            
            return {
                'id': usuario['id'],
                'nombre': usuario['nombre'],
                'email': usuario['email'],
                'rol': usuario['rol'],
                'negocio_id': usuario['negocio_id'],
                'negocio_nombre': usuario['negocio_nombre']
            }
    return None


def obtener_usuarios_por_negocio(negocio_id):
    """Obtener todos los usuarios de un negocio - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    sql = '''
        SELECT u.*, n.nombre as negocio_nombre
        FROM usuarios u
        JOIN negocios n ON u.negocio_id = n.id
        WHERE u.negocio_id = %s
        ORDER BY u.fecha_creacion DESC
    '''
    usuarios = fetch_all(conn.cursor(), sql, (negocio_id,))
    conn.close()
    
    # Procesar los resultados para asegurar que son diccionarios
    usuarios_procesados = []
    for usuario in usuarios:
        if not isinstance(usuario, dict):
            usuario_dict = dict(usuario)
        else:
            usuario_dict = usuario
        
        # Asegurar que ultimo_login sea manejable
        if usuario_dict.get('ultimo_login') and hasattr(usuario_dict['ultimo_login'], 'strftime'):
            usuario_dict['ultimo_login_str'] = usuario_dict['ultimo_login'].strftime('%Y-%m-%d %H:%M')
        else:
            usuario_dict['ultimo_login_str'] = str(usuario_dict.get('ultimo_login', ''))[:16] if usuario_dict.get('ultimo_login') else 'Nunca'
        
        usuarios_procesados.append(usuario_dict)
    
    return usuarios_procesados


def obtener_usuarios_todos():
    """Obtener todos los usuarios del sistema"""
    conn = get_db_connection()
    sql = '''
        SELECT u.*, n.nombre as negocio_nombre
        FROM usuarios u
        JOIN negocios n ON u.negocio_id = n.id
        ORDER BY u.fecha_creacion DESC
    '''
    usuarios = fetch_all(conn.cursor(), sql)
    conn.close()
    return usuarios


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================
def resetear_secuencia_negocios():
    """Resetear la secuencia de IDs de negocios para PostgreSQL"""
    if not is_postgresql():
        print("ℹ️  Solo necesario para PostgreSQL")
        return True
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Obtener el máximo ID actual
        cursor.execute('SELECT COALESCE(MAX(id), 0) FROM negocios')
        max_id = cursor.fetchone()[0]
        
        # Resetear la secuencia al siguiente valor disponible
        cursor.execute(f'ALTER SEQUENCE negocios_id_seq RESTART WITH {max_id + 1}')
        
        conn.commit()
        print(f"✅ Secuencia resetada. Próximo ID: {max_id + 1}")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error resetando secuencia: {e}")
        return False
    finally:
        conn.close()

def actualizar_esquema_bd():
    """Actualizar esquema de base de datos existente"""
    # Esta función es principalmente para SQLite
    # En PostgreSQL, las columnas se crean automáticamente
    if not is_postgresql():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Verificar si existe la columna emoji en negocios
            cursor.execute("PRAGMA table_info(negocios)")
            columnas_negocios = cursor.fetchall()
            columnas_negocios_existentes = [col[1] for col in columnas_negocios]
            
            if 'emoji' not in columnas_negocios_existentes:
                cursor.execute('ALTER TABLE negocios ADD COLUMN emoji TEXT DEFAULT "👋"')
            
            conn.commit()
        except Exception as e:
            print(f"⚠️ Error actualizando esquema: {e}")
        finally:
            conn.close()


def actualizar_configuracion_completa(negocio_id, nombre, tipo_negocio, emoji, configuracion, horarios_actualizados):
    """Actualizar configuración completa del negocio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Actualizar información básica del negocio
        sql = '''
            UPDATE negocios 
            SET nombre = ?, tipo_negocio = ?, emoji = ?, configuracion = ?
            WHERE id = ?
        '''
        execute_sql(cursor, sql, (nombre, tipo_negocio, emoji, json.dumps(configuracion), negocio_id))
        
        # Actualizar horarios por día
        for horario in horarios_actualizados:
            almuerzo_inicio = horario['almuerzo_inicio'] if horario['almuerzo_inicio'] else None
            almuerzo_fin = horario['almuerzo_fin'] if horario['almuerzo_fin'] else None
            
            # Verificar si ya existe un registro para este día
            sql = '''
                SELECT id FROM configuracion_horarios 
                WHERE negocio_id = ? AND dia_semana = ?
            '''
            existe = fetch_one(cursor, sql, (negocio_id, horario['dia_id']))
            
            if existe:
                # Actualizar registro existente
                sql = '''
                    UPDATE configuracion_horarios 
                    SET activo = ?, hora_inicio = ?, hora_fin = ?, 
                        almuerzo_inicio = ?, almuerzo_fin = ?
                    WHERE negocio_id = ? AND dia_semana = ?
                '''
                execute_sql(cursor, sql, (
                    horario['activo'], 
                    horario['hora_inicio'], 
                    horario['hora_fin'],
                    almuerzo_inicio,
                    almuerzo_fin,
                    negocio_id, 
                    horario['dia_id']
                ))
            else:
                # Insertar nuevo registro
                sql = '''
                    INSERT INTO configuracion_horarios 
                    (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                '''
                execute_sql(cursor, sql, (
                    negocio_id, 
                    horario['dia_id'],
                    horario['activo'], 
                    horario['hora_inicio'], 
                    horario['hora_fin'],
                    almuerzo_inicio,
                    almuerzo_fin
                ))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error actualizando configuración: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# =============================================================================
# ESTADÍSTICAS
# =============================================================================

def obtener_estadisticas_mensuales(negocio_id, profesional_id=None, mes=None, año=None):
    """Obtener estadísticas mensuales - VERSIÓN CORREGIDA PARA POSTGRESQL"""
    if mes is None:
        mes = datetime.now().month
    if año is None:
        año = datetime.now().year
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Construir consulta base
    if is_postgresql():
        # ✅ CORRECCIÓN: Usar EXTRACT con CAST para convertir texto a fecha
        query = '''
            SELECT 
                COUNT(*) as total_citas,
                SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as citas_confirmadas,
                SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as citas_completadas,
                SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as citas_canceladas,
                SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) as citas_pendientes,
                SUM(CASE WHEN estado IN ('confirmado', 'completado') THEN s.precio ELSE 0 END) as ingresos_totales
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s 
            AND EXTRACT(MONTH FROM c.fecha::DATE) = %s 
            AND EXTRACT(YEAR FROM c.fecha::DATE) = %s
        '''
    else:
        # Para SQLite (código original)
        query = '''
            SELECT 
                COUNT(*) as total_citas,
                SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as citas_confirmadas,
                SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as citas_completadas,
                SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as citas_canceladas,
                SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) as citas_pendientes,
                SUM(CASE WHEN estado IN ('confirmado', 'completado') THEN s.precio ELSE 0 END) as ingresos_totales
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = ? AND strftime('%m', c.fecha) = ? AND strftime('%Y', c.fecha) = ?
        '''
    
    params = [negocio_id, mes, año]
    
    if profesional_id:
        query += ' AND c.profesional_id = ?'
        params.append(profesional_id)
    
    execute_sql(cursor, query, params)
    stats = cursor.fetchone()
    
    # ✅ CORRECCIÓN: Acceder correctamente a los valores según el tipo de cursor
    if hasattr(stats, 'keys'):  # Es un diccionario (RealDictCursor)
        total_citas = stats['total_citas'] or 0
        citas_confirmadas = stats['citas_confirmadas'] or 0
        citas_completadas = stats['citas_completadas'] or 0
        citas_canceladas = stats['citas_canceladas'] or 0
        citas_pendientes = stats['citas_pendientes'] or 0
        ingresos_totales = stats['ingresos_totales'] or 0
    else:  # Es una tupla
        total_citas = stats[0] or 0 if stats else 0
        citas_confirmadas = stats[1] or 0 if stats else 0
        citas_completadas = stats[2] or 0 if stats else 0
        citas_canceladas = stats[3] or 0 if stats else 0
        citas_pendientes = stats[4] or 0 if stats else 0
        ingresos_totales = stats[5] or 0 if stats else 0
    
    # Calcular tasa de éxito
    tasa_exito = (citas_completadas / total_citas * 100) if total_citas > 0 else 0
    
    estadisticas = {
        'resumen': {
            'total_citas': total_citas,
            'citas_confirmadas': citas_confirmadas,
            'citas_completadas': citas_completadas,
            'citas_canceladas': citas_canceladas,
            'citas_pendientes': citas_pendientes,
            'ingresos_totales': float(ingresos_totales),
            'tasa_exito': round(tasa_exito, 2)
        }
    }
    
    conn.close()
    return estadisticas


# =============================================================================
# FUNCIONES PARA RECORDATORIOS Y NOTIFICACIONES
# =============================================================================

def obtener_citas_proximas_recordatorio():
    """Obtener citas próximas para recordatorios - VERSIÓN POSTGRESQL"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Citas en 24 horas
    fecha_24h = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d')
    
    # ✅ CORRECCIÓN: Sintaxis PostgreSQL
    sql_24h = '''
        SELECT c.*, n.nombre as negocio_nombre, n.telefono_whatsapp, 
               p.nombre as profesional_nombre, s.nombre as servicio_nombre,
               s.duracion, s.precio
        FROM citas c
        JOIN negocios n ON c.negocio_id = n.id
        JOIN profesionales p ON c.profesional_id = p.id
        JOIN servicios s ON c.servicio_id = s.id
        WHERE c.fecha = %s 
        AND c.estado = 'confirmado' 
        AND c.recordatorio_24h_enviado = FALSE
        ORDER BY c.hora
    '''
    
    cursor.execute(sql_24h, (fecha_24h,))
    citas_24h = cursor.fetchall()
    
    # Citas en 1 hora (mismo día)
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    # ✅ CORRECCIÓN: Sintaxis PostgreSQL
    sql_1h = '''
        SELECT c.*, n.nombre as negocio_nombre, n.telefono_whatsapp,
               p.nombre as profesional_nombre, s.nombre as servicio_nombre,
               s.duracion, s.precio
        FROM citas c
        JOIN negocios n ON c.negocio_id = n.id
        JOIN profesionales p ON c.profesional_id = p.id
        JOIN servicios s ON c.servicio_id = s.id
        WHERE c.fecha = %s 
        AND c.estado = 'confirmado'
        AND c.recordatorio_1h_enviado = FALSE
        AND c.hora::time BETWEEN (NOW() + INTERVAL '55 minutes')::time 
                           AND (NOW() + INTERVAL '65 minutes')::time
        ORDER BY c.hora
    '''
    
    cursor.execute(sql_1h, (fecha_hoy,))
    citas_1h = cursor.fetchall()
    
    conn.close()
    
    # Convertir a lista de diccionarios
    return {
        'citas_24h': [dict(cita) for cita in citas_24h],
        'citas_1h': [dict(cita) for cita in citas_1h]
    }


def marcar_recordatorio_enviado(cita_id, tipo_recordatorio):
    """Marcar recordatorio como enviado - VERSIÓN POSTGRESQL"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if tipo_recordatorio == '24h':
            sql = 'UPDATE citas SET recordatorio_24h_enviado = TRUE WHERE id = %s'
        elif tipo_recordatorio == '1h':
            sql = 'UPDATE citas SET recordatorio_1h_enviado = TRUE WHERE id = %s'
        else:
            return False
        
        cursor.execute(sql, (cita_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error marcando recordatorio: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

