# =============================================================================
# database.py - SISTEMA GENÉRICO DE CITAS - POSTGRESQL COMPLETO
# =============================================================================
import os
import logging
from datetime import datetime, timedelta
import re
import json
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3  # Para fallback
import localizacion

logger = logging.getLogger(__name__)


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

        # ✅ NUEVA: Crear tabla para suscripciones push
        crear_tabla_suscripciones_push()
        
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

    columnas_redes_negocio = ['instagram', 'facebook', 'tiktok', 'twitter', 'youtube', 'sitio_web']
    if postgres:
        for columna in columnas_redes_negocio:
            execute_sql(cursor, f'ALTER TABLE negocios ADD COLUMN IF NOT EXISTS {columna} TEXT')
    else:
        cursor.execute("PRAGMA table_info(negocios)")
        columnas_negocios = {row[1] for row in cursor.fetchall()}
        for columna in columnas_redes_negocio:
            if columna not in columnas_negocios:
                cursor.execute(f'ALTER TABLE negocios ADD COLUMN {columna} TEXT')
    
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
            tipo_precio VARCHAR(20) DEFAULT 'fijo',
            precio_maximo DECIMAL(10,2),
            foto_url TEXT,
            moneda VARCHAR(10) DEFAULT 'COP',
            FOREIGN KEY (negocio_id) REFERENCES negocios (id)
        )
    '''
    if postgres:
        servicios_sql = servicios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    execute_sql(cursor, servicios_sql)

    if postgres:
        execute_sql(cursor, 'ALTER TABLE servicios ADD COLUMN IF NOT EXISTS foto_url TEXT')
        execute_sql(cursor, "ALTER TABLE servicios ADD COLUMN IF NOT EXISTS moneda VARCHAR(10) DEFAULT 'COP'")
    else:
        cursor.execute("PRAGMA table_info(servicios)")
        columnas_servicios = {row[1] for row in cursor.fetchall()}
        if 'foto_url' not in columnas_servicios:
            cursor.execute('ALTER TABLE servicios ADD COLUMN foto_url TEXT')
        if 'moneda' not in columnas_servicios:
            cursor.execute("ALTER TABLE servicios ADD COLUMN moneda VARCHAR(10) DEFAULT 'COP'")
    
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
    """Insertar plantillas base del sistema - VERSIÓN ACTUALIZADA PARA WEB_CHAT_HANDLER"""
    postgres = is_postgresql()
    
    # Eliminar plantillas base existentes
    if postgres:
        cursor.execute('DELETE FROM plantillas_mensajes WHERE es_base = TRUE')
    else:
        cursor.execute('DELETE FROM plantillas_mensajes WHERE es_base = TRUE')
    
    plantillas_base = [
        # ============================================
        # PLANTILLAS PARA EL NUEVO FLUJO (web_chat_handler)
        # ============================================
        ('saludo_inicial',
         '¡Hola! 👋 Para comenzar, ingresa tu número de teléfono de 10 dígitos (debe empezar con 3, ejemplo: 3101234567):',
         'Saludo inicial para pedir teléfono',
         '["nombre_negocio"]'),
        
        ('telefono_validado_existente',
         '¡Hola {nombre_cliente}! 👋\n\nHe identificado tu número en nuestro sistema.\n\n¿En qué puedo ayudarte hoy?',
         'Cuando se reconoce un cliente existente',
         '["nombre_cliente"]'),
        
        ('solicitar_nombre_nuevo',
         '✅ Número registrado exitosamente.\n\n📝 **Ahora necesitamos tu nombre para completar tu registro.**\n\nPor favor, ingresa tu nombre completo:',
         'Solicitar nombre a cliente nuevo',
         '[]'),
        
        ('nombre_registrado_exitoso',
         '¡Perfecto {nombre_cliente}! ✅\n\nTu registro se ha completado exitosamente.\n\n¿En qué puedo ayudarte hoy?',
         'Confirmación de registro exitoso',
         '["nombre_cliente"]'),
        
        ('menu_principal',
         '¿En qué puedo ayudarte hoy?',
         'Menú principal de opciones',
         '[]'),
        
        ('lista_profesionales',
         '👨‍💼 **Selecciona un profesional:**',
         'Lista de profesionales disponibles',
         '[]'),
        
        ('lista_servicios',
         '📋 **Servicios con {profesional_nombre}:**',
         'Lista de servicios disponibles',
         '["profesional_nombre"]'),
        
        ('servicio_personalizado_opciones',
         '🌟 *SERVICIO PERSONALIZADO PARA TI* 🌟\n\n*{nombre_personalizado}*\n⏱️ Duración: {duracion_personalizada} min\n💵 Precio: ${precio_personalizado}\n\n🔢 *Responde con:*\n1️⃣ - Seleccionar mi servicio personalizado\n2️⃣ - Ver todos los servicios disponibles',
         'Opciones para servicio personalizado',
         '["nombre_personalizado", "duracion_personalizada", "precio_personalizado"]'),
        
        ('seleccion_fecha',
         '📅 **Selecciona una fecha:**',
         'Selección de fecha para cita',
         '[]'),
        
        ('seleccion_horario',
         '📅 **Horarios disponibles con {profesional_nombre} ({fecha_formateada}):**\n💼 Servicio: {servicio_nombre} - ${servicio_precio}',
         'Selección de horario para cita',
         '["profesional_nombre", "fecha_formateada", "servicio_nombre", "servicio_precio"]'),
        
        ('confirmacion_cita',
         '✅ **Confirmar cita**\n\nHola *{nombre_cliente}*, ¿confirmas tu cita?\n\n👨‍💼 **Profesional:** {profesional_nombre}\n💼 **Servicio:** {servicio_nombre}\n💰 **Precio:** ${servicio_precio}\n📅 **Fecha:** {fecha_formateada}\n⏰ **Hora:** {hora_seleccionada}\n\n**Selecciona una opción:**',
         'Confirmación de cita antes de agendar',
         '["nombre_cliente", "profesional_nombre", "servicio_nombre", "servicio_precio", "fecha_formateada", "hora_seleccionada"]'),
        
        ('cita_confirmada_exito',
         '✅ **Cita Confirmada**\n\nHola *{nombre_cliente}*, \n\nTu cita ha sido agendada exitosamente:\n\n• **Profesional:** {profesional_nombre}\n• **Servicio:** {servicio_nombre}  \n• **Precio:** ${servicio_precio}\n• **Fecha:** {fecha_formateada}\n• **Hora:** {hora_seleccionada}\n• **ID de cita:** #{cita_id}\n• **Teléfono:** {telefono_cliente}\n• **Duración:** {duracion_servicio} minutos\n\nRecibirás recordatorios por mensaje antes de tu cita.\n\n¡Te esperamos!',
         'Confirmación exitosa de cita agendada',
         '["nombre_cliente", "profesional_nombre", "servicio_nombre", "servicio_precio", "fecha_formateada", "hora_seleccionada", "cita_id", "telefono_cliente", "duracion_servicio"]'),
        
        ('mis_citas_lista',
         '📋 **Tus citas CONFIRMADAS - {nombre_cliente}:**',
         'Lista de citas del cliente',
         '["nombre_cliente"]'),
        
        ('sin_citas',
         '📋 **No tienes citas CONFIRMADAS programadas, {nombre_cliente}.**\n\nPara agendar una nueva cita, selecciona: *1*',
         'Cuando el cliente no tiene citas',
         '["nombre_cliente"]'),
        
        ('ayuda_general',
         'ℹ️ **Ayuda:**\n\nPara agendar una cita, responde: *1*\nPara ver tus citas, responde: *2*\nPara cancelar una cita, responde: *3*\n\nEn cualquier momento puedes escribir *0* para volver al menú principal.',
         'Mensaje de ayuda general',
         '[]'),
        
        ('error_generico',
         '❌ Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente.',
         'Mensaje de error genérico',
         '[]'),
        
        ('cita_cancelada_exito',
         '❌ **Cita cancelada exitosamente**\n\nHola {nombre_cliente}, has cancelado tu cita:\n\n📅 **Fecha:** {fecha_cita}\n⏰ **Hora:** {hora_cita}\n🎫 **ID de cita:** #{cita_id}\n\nEsperamos verte pronto en otra ocasión.',
         'Confirmación de cancelación exitosa',
         '["nombre_cliente", "fecha_cita", "hora_cita", "cita_id"]')
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
    """Obtener una plantilla específica - VERSIÓN CORREGIDA"""
    print(f"🔍 [DB] obtener_plantilla: negocio_id={negocio_id}, nombre={nombre_plantilla}")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # PRIMERO: Buscar plantilla personalizada del negocio
        sql_personalizada = '''
            SELECT *, TRUE as es_personalizada
            FROM plantillas_mensajes 
            WHERE negocio_id = %s 
            AND nombre = %s 
            AND es_base = FALSE
        '''
        cursor.execute(sql_personalizada, (negocio_id, nombre_plantilla))
        plantilla_personalizada = cursor.fetchone()
        
        if plantilla_personalizada:
            print(f"✅ [DB] Encontrada plantilla personalizada: {plantilla_personalizada}")
            conn.close()
            return dict(plantilla_personalizada)
        
        # SEGUNDO: Si no existe personalizada, buscar plantilla base
        sql_base = '''
            SELECT *, FALSE as es_personalizada
            FROM plantillas_mensajes 
            WHERE nombre = %s 
            AND es_base = TRUE
        '''
        cursor.execute(sql_base, (nombre_plantilla,))
        plantilla_base = cursor.fetchone()
        
        if plantilla_base:
            # Convertir plantilla base a formato de plantilla personalizada
            plantilla_dict = dict(plantilla_base)
            plantilla_dict['negocio_id'] = negocio_id  # Asignar ID del negocio
            plantilla_dict['es_personalizada'] = False
            print(f"✅ [DB] Encontrada plantilla base, convertida: {plantilla_dict}")
            conn.close()
            return plantilla_dict
        
        # Si no se encuentra ninguna
        print(f"❌ [DB] No se encontró plantilla: {nombre_plantilla}")
        conn.close()
        return None
        
    except Exception as e:
        print(f"❌ Error en obtener_plantilla: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return None


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
    """Obtener todas las plantillas disponibles para un negocio - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)  # ✅ Usar RealDictCursor
    
    try:
        print(f"🔍 [DB] Obteniendo plantillas para negocio {negocio_id}")
        
        # PRIMERO: Obtener todas las plantillas base del sistema
        sql_base = '''
            SELECT 
                NULL as negocio_id,
                nombre,
                plantilla,
                descripcion,
                variables_disponibles,
                TRUE as es_base,
                FALSE as es_personalizada,
                'system' as origen
            FROM plantillas_mensajes 
            WHERE es_base = TRUE
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
        cursor.execute(sql_base)
        plantillas_base = cursor.fetchall()
        print(f"✅ [DB] Plantillas base encontradas: {len(plantillas_base)}")
        
        # SEGUNDO: Obtener plantillas personalizadas de este negocio
        sql_personalizadas = '''
            SELECT 
                negocio_id,
                nombre,
                plantilla,
                descripcion,
                variables_disponibles,
                FALSE as es_base,
                TRUE as es_personalizada,
                'personalized' as origen
            FROM plantillas_mensajes 
            WHERE negocio_id = %s 
            AND es_base = FALSE
            ORDER BY nombre
        '''
        cursor.execute(sql_personalizadas, (negocio_id,))
        plantillas_personalizadas = cursor.fetchall()
        print(f"✅ [DB] Plantillas personalizadas encontradas: {len(plantillas_personalizadas)}")
        
        conn.close()
        
        # Combinar plantillas (prioridad: personalizadas sobre base)
        plantillas_final = []
        nombres_agregados = set()
        
        # 1. Agregar personalizadas primero
        for plantilla in plantillas_personalizadas:
            plantilla_dict = dict(plantilla)
            plantilla_dict['es_personalizada'] = True
            plantillas_final.append(plantilla_dict)
            nombres_agregados.add(plantilla_dict['nombre'])
        
        # 2. Agregar base solo si no hay personalizada
        for plantilla in plantillas_base:
            plantilla_dict = dict(plantilla)
            if plantilla_dict['nombre'] not in nombres_agregados:
                plantilla_dict['es_personalizada'] = False
                plantilla_dict['negocio_id'] = negocio_id  # Asignar ID para referencia
                plantillas_final.append(plantilla_dict)
        
        print(f"✅ [DB] Total plantillas a mostrar: {len(plantillas_final)}")
        
        # DEBUG: mostrar cada plantilla
        for i, p in enumerate(plantillas_final):
            print(f"🔍 Plantilla {i}: {p.get('nombre')} (Personalizada: {p.get('es_personalizada')})")
        
        return plantillas_final
        
    except Exception as e:
        print(f"❌ Error obteniendo plantillas del negocio: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return []


def guardar_plantilla_personalizada(negocio_id, nombre_plantilla, contenido, descripcion=''):
    """Guardar o actualizar plantilla personalizada - VERSIÓN CORREGIDA"""
    print(f"🔍 [DB] Guardando plantilla personalizada: {nombre_plantilla} para negocio {negocio_id}")
    print(f"📝 Contenido recibido: {contenido[:100]}...")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si ya existe una personalizada
        if is_postgresql():
            sql_check = '''
                SELECT id FROM plantillas_mensajes 
                WHERE negocio_id = %s AND nombre = %s AND es_base = FALSE
            '''
            cursor.execute(sql_check, (negocio_id, nombre_plantilla))
        else:
            sql_check = '''
                SELECT id FROM plantillas_mensajes 
                WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
            '''
            cursor.execute(sql_check, (negocio_id, nombre_plantilla))
        
        existe = cursor.fetchone()
        
        if existe:
            # Actualizar existente
            print(f"✅ [DB] Actualizando plantilla personalizada existente")
            if is_postgresql():
                sql_update = '''
                    UPDATE plantillas_mensajes 
                    SET plantilla = %s, descripcion = %s, es_base = FALSE
                    WHERE negocio_id = %s AND nombre = %s
                '''
                cursor.execute(sql_update, (contenido, descripcion, negocio_id, nombre_plantilla))
            else:
                sql_update = '''
                    UPDATE plantillas_mensajes 
                    SET plantilla = ?, descripcion = ?, es_base = FALSE
                    WHERE negocio_id = ? AND nombre = ?
                '''
                cursor.execute(sql_update, (contenido, descripcion, negocio_id, nombre_plantilla))
        else:
            # Crear nueva personalizada
            print(f"✅ [DB] Creando nueva plantilla personalizada")
            
            # Primero obtener datos de la plantilla base para copiar variables
            if is_postgresql():
                sql_base = '''
                    SELECT variables_disponibles 
                    FROM plantillas_mensajes 
                    WHERE nombre = %s AND es_base = TRUE
                    LIMIT 1
                '''
                cursor.execute(sql_base, (nombre_plantilla,))
            else:
                sql_base = '''
                    SELECT variables_disponibles 
                    FROM plantillas_mensajes 
                    WHERE nombre = ? AND es_base = TRUE
                    LIMIT 1
                '''
                cursor.execute(sql_base, (nombre_plantilla,))
            
            base_data = cursor.fetchone()
            variables_disponibles = '[]'
            
            if base_data:
                if hasattr(base_data, 'keys'):
                    variables_disponibles = base_data['variables_disponibles']
                else:
                    variables_disponibles = base_data[0]
            
            # Crear nueva plantilla personalizada
            if is_postgresql():
                sql_insert = '''
                    INSERT INTO plantillas_mensajes 
                    (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                    VALUES (%s, %s, %s, %s, %s, FALSE)
                '''
                cursor.execute(sql_insert, (negocio_id, nombre_plantilla, contenido, descripcion, variables_disponibles))
            else:
                sql_insert = '''
                    INSERT INTO plantillas_mensajes 
                    (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                    VALUES (?, ?, ?, ?, ?, FALSE)
                '''
                cursor.execute(sql_insert, (negocio_id, nombre_plantilla, contenido, descripcion, variables_disponibles))
        
        conn.commit()
        print(f"✅ [DB] Plantilla '{nombre_plantilla}' guardada exitosamente")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error guardando plantilla: {e}")
        import traceback
        traceback.print_exc()
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

def obtener_negocio_por_id(negocio_id):
    """Obtener negocio por ID con todos los campos"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor if is_postgresql() else None)
    
    try:
        if is_postgresql():
            cursor.execute('''
                SELECT id, nombre, telefono_whatsapp, tipo_negocio, emoji, 
                       configuracion, activo, fecha_creacion, latitud, longitud, direccion
                FROM negocios 
                WHERE id = %s
            ''', (negocio_id,))
        else:
            cursor.execute('''
                SELECT id, nombre, telefono_whatsapp, tipo_negocio, emoji, 
                       configuracion, activo, fecha_creacion, latitud, longitud, direccion
                FROM negocios 
                WHERE id = ?
            ''', (negocio_id,))
        
        return cursor.fetchone()
    except Exception as e:
        print(f"❌ Error obteniendo negocio: {e}")
        return None
    finally:
        conn.close()


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


def crear_negocio(nombre, telefono_whatsapp, tipo_negocio='general', configuracion='{}', emoji='👋', latitud=None, longitud=None, direccion=None):
    """Crear un nuevo negocio - CON COORDENADAS Y DIRECCIÓN"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Para PostgreSQL
        if is_postgresql():
            sql = '''
                INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion, latitud, longitud, direccion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            '''
            cursor.execute(sql, (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion, latitud, longitud, direccion))
            result = cursor.fetchone()
            # Acceder correctamente al resultado
            if hasattr(result, 'keys'):  # Es un diccionario (RealDictCursor)
                negocio_id = result['id']
            else:  # Es una tupla
                negocio_id = result[0] if result else None
        else:
            # Para SQLite
            sql = '''
                INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion, latitud, longitud, direccion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            '''
            execute_sql(cursor, sql, (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion, latitud, longitud, direccion))
            negocio_id = cursor.lastrowid
        
        if not negocio_id:
            print("❌ No se pudo obtener el ID del negocio creado")
            conn.rollback()
            return None
            
        print(f"✅ Negocio creado con ID: {negocio_id}")
        
        # Crear configuración por defecto
        if is_postgresql():
            cursor.execute('INSERT INTO configuracion (negocio_id) VALUES (%s)', (negocio_id,))
        else:
            execute_sql(cursor, 'INSERT INTO configuracion (negocio_id) VALUES (?)', (negocio_id,))
        
        # Crear configuración de horarios
        _insertar_configuracion_horarios_para_negocio(cursor, negocio_id)
        
        # Crear usuario propietario por defecto
        email_propietario = f"propietario{negocio_id}@negocio.com"
        if is_postgresql():
            cursor.execute('''
                INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
                VALUES (%s, %s, %s, %s, %s)
            ''', (negocio_id, 'Propietario', email_propietario, generate_password_hash('propietario123'), 'propietario'))
        else:
            execute_sql(cursor, '''
                INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
                VALUES (?, ?, ?, ?, ?)
            ''', (negocio_id, 'Propietario', email_propietario, generate_password_hash('propietario123'), 'propietario'))
        
        # Crear servicios por defecto
        _crear_servicios_por_defecto_negocio(cursor, negocio_id, tipo_negocio)
        
        # Crear profesional por defecto
        if is_postgresql():
            cursor.execute('''
                INSERT INTO profesionales (negocio_id, nombre, especialidad, pin)
                VALUES (%s, %s, %s, %s)
            ''', (negocio_id, 'Principal', 'Especialista', '0000'))
        else:
            execute_sql(cursor, '''
                INSERT INTO profesionales (negocio_id, nombre, especialidad, pin)
                VALUES (?, ?, ?, ?)
            ''', (negocio_id, 'Principal', 'Especialista', '0000'))
        
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


def actualizar_negocio(negocio_id, nombre=None, telefono_whatsapp=None, tipo_negocio=None, emoji=None, activo=None, configuracion=None, latitud=None, longitud=None, direccion=None):
    """Actualizar un negocio existente - CON COORDENADAS Y DIRECCIÓN"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        campos = []
        valores = []
        
        if nombre is not None:
            campos.append("nombre = %s" if is_postgresql() else "nombre = ?")
            valores.append(nombre)
        if telefono_whatsapp is not None:
            campos.append("telefono_whatsapp = %s" if is_postgresql() else "telefono_whatsapp = ?")
            valores.append(telefono_whatsapp)
        if tipo_negocio is not None:
            campos.append("tipo_negocio = %s" if is_postgresql() else "tipo_negocio = ?")
            valores.append(tipo_negocio)
        if emoji is not None:
            campos.append("emoji = %s" if is_postgresql() else "emoji = ?")
            valores.append(emoji)
        if activo is not None:
            campos.append("activo = %s" if is_postgresql() else "activo = ?")
            valores.append(activo)
        if configuracion is not None:
            campos.append("configuracion = %s" if is_postgresql() else "configuracion = ?")
            valores.append(configuracion)
        if latitud is not None:
            campos.append("latitud = %s" if is_postgresql() else "latitud = ?")
            valores.append(latitud)
        if longitud is not None:
            campos.append("longitud = %s" if is_postgresql() else "longitud = ?")
            valores.append(longitud)
        if direccion is not None:
            campos.append("direccion = %s" if is_postgresql() else "direccion = ?")
            valores.append(direccion)
        
        if campos:
            valores.append(negocio_id)
            query = f"UPDATE negocios SET {', '.join(campos)} WHERE id = %s" if is_postgresql() else f"UPDATE negocios SET {', '.join(campos)} WHERE id = ?"
            
            if is_postgresql():
                cursor.execute(query, valores)
            else:
                execute_sql(cursor, query, valores)
            
            conn.commit()
            print(f"✅ Negocio {negocio_id} actualizado: {campos}")
            return True
        else:
            print(f"⚠️ No hay campos para actualizar en negocio {negocio_id}")
            return False
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error actualizando negocio: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()




# =============================================================================
# GESTIÓN DE PROFESIONALES Y SERVICIOS
# =============================================================================

def obtener_profesionales(negocio_id):
    """Obtener profesionales de un negocio - SOLO LOS QUE TIENEN HORARIOS DISPONIBLES"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Obtener TODOS los profesionales activos
        cur.execute("""
            SELECT 
                id, 
                nombre, 
                telefono,
                especialidad, 
                foto_url,
                pin,
                usuario_id,
                activo,
                created_at,
                negocio_id
            FROM profesionales 
            WHERE negocio_id = %s AND activo = TRUE
            ORDER BY nombre
        """, (negocio_id,))
        
        profesionales = cur.fetchall()
        cur.close()
        conn.close()
        
        # Aquí podríamos filtrar pero es más complejo porque necesitamos fecha/horario
        # Por ahora, devolvemos todos y el filtro se hará en web_chat_handler
        
        print(f"📊 [DB] Obtenidos {len(profesionales)} profesionales para negocio {negocio_id}")
        
        return profesionales
        
    except Exception as e:
        print(f"❌ Error obteniendo profesionales: {str(e)}")
        return []


def obtener_servicios(negocio_id):
    """Obtener servicios activos de un negocio - CON TIPO DE PRECIO Y PRECIO MÁXIMO"""
    conn = get_db_connection()
    
    if is_postgresql():
        sql = '''
            SELECT id, nombre, duracion, precio, descripcion, activo, created_at,
                   tipo_precio, precio_maximo, foto_url
            FROM servicios 
            WHERE negocio_id = %s AND activo = TRUE
            ORDER BY nombre
        '''
        servicios = fetch_all(conn.cursor(), sql, (negocio_id,))
    else:
        sql = '''
            SELECT id, nombre, duracion, precio, descripcion, activo, created_at,
                   tipo_precio, precio_maximo, foto_url
            FROM servicios 
            WHERE negocio_id = ? AND activo = TRUE
            ORDER BY nombre
        '''
        servicios = fetch_all(conn.cursor(), sql, (negocio_id,))
    
    conn.close()
    
    # Procesar resultados para asegurar que todos los campos están presentes
    servicios_procesados = []
    for servicio in servicios:
        if isinstance(servicio, dict):
            # Si ya es diccionario, asegurar campos por defecto
            if 'tipo_precio' not in servicio:
                servicio['tipo_precio'] = 'fijo'
            if 'precio_maximo' not in servicio:
                servicio['precio_maximo'] = None
            if 'foto_url' not in servicio:
                servicio['foto_url'] = None
            servicios_procesados.append(servicio)
        else:
            # Si es tupla, convertir a diccionario
            servicios_procesados.append({
                'id': servicio[0],
                'nombre': servicio[1],
                'duracion': servicio[2],
                'precio': servicio[3],
                'descripcion': servicio[4] if len(servicio) > 4 else '',
                'activo': servicio[5] if len(servicio) > 5 else True,
                'created_at': servicio[6] if len(servicio) > 6 else None,
                'tipo_precio': servicio[7] if len(servicio) > 7 else 'fijo',
                'precio_maximo': servicio[8] if len(servicio) > 8 else None,
                'foto_url': servicio[9] if len(servicio) > 9 else None
            })
    
    return servicios_procesados


def obtener_servicio_por_id(servicio_id, negocio_id):
    """Obtener un servicio específico por ID - CON TIPO DE PRECIO Y PRECIO MÁXIMO"""
    conn = get_db_connection()
    
    if is_postgresql():
        sql = 'SELECT * FROM servicios WHERE id = %s AND negocio_id = %s'
        servicio = fetch_one(conn.cursor(), sql, (servicio_id, negocio_id))
    else:
        sql = 'SELECT * FROM servicios WHERE id = ? AND negocio_id = ?'
        servicio = fetch_one(conn.cursor(), sql, (servicio_id, negocio_id))
    
    conn.close()
    
    if servicio:
        # Asegurar que los campos existen
        if 'tipo_precio' not in servicio:
            servicio['tipo_precio'] = 'fijo'
        if 'precio_maximo' not in servicio:
            servicio['precio_maximo'] = None
    
    return servicio

def guardar_servicio(negocio_id, servicio_id, nombre, duracion, precio, descripcion, activo=True, tipo_precio='fijo', precio_maximo=None, foto_url=None, moneda='COP'):
    """Guardar o actualizar servicio - CON FOTO Y MONEDA"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if servicio_id:
            # Actualizar existente
            if foto_url is not None:
                cursor.execute('''
                    UPDATE servicios 
                    SET nombre = %s, duracion = %s, precio = %s, descripcion = %s, 
                        activo = %s, tipo_precio = %s, precio_maximo = %s, foto_url = %s, moneda = %s
                    WHERE id = %s AND negocio_id = %s
                ''', (nombre, duracion, precio, descripcion, activo, tipo_precio, precio_maximo, foto_url, moneda, servicio_id, negocio_id))
            else:
                cursor.execute('''
                    UPDATE servicios 
                    SET nombre = %s, duracion = %s, precio = %s, descripcion = %s, 
                        activo = %s, tipo_precio = %s, precio_maximo = %s, moneda = %s
                    WHERE id = %s AND negocio_id = %s
                ''', (nombre, duracion, precio, descripcion, activo, tipo_precio, precio_maximo, moneda, servicio_id, negocio_id))
            conn.commit()
            return {'success': True, 'id': servicio_id, 'message': 'Servicio actualizado correctamente'}
        else:
            # Crear nuevo
            cursor.execute('''
                INSERT INTO servicios 
                (negocio_id, nombre, duracion, precio, descripcion, activo, tipo_precio, precio_maximo, foto_url, moneda)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (negocio_id, nombre, duracion, precio, descripcion, activo, tipo_precio, precio_maximo, foto_url, moneda))
            
            result = cursor.fetchone()
            
            if result:
                if isinstance(result, tuple):
                    nuevo_id = result[0]
                elif isinstance(result, dict):
                    nuevo_id = result.get('id')
                else:
                    nuevo_id = result
            else:
                cursor.execute('SELECT LASTVAL()')
                last_result = cursor.fetchone()
                if last_result:
                    nuevo_id = last_result[0] if isinstance(last_result, tuple) else last_result.get('lastval')
                else:
                    nuevo_id = None
            
            conn.commit()
            
            if nuevo_id:
                return {'success': True, 'id': nuevo_id, 'message': 'Servicio creado correctamente'}
            else:
                return {'success': False, 'error': 'No se pudo obtener el ID del servicio'}
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error guardando servicio: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


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

def normalizar_hora(hora_str):
    """Convierte cualquier formato de hora a HH:MM (24h)"""
    if not hora_str:
        return hora_str
    
    try:
        # Si ya está en formato 24h (ej: "16:00")
        if ':' in hora_str and not ('AM' in hora_str or 'PM' in hora_str):
            partes = hora_str.split(':')
            if len(partes) >= 2:
                hora = int(partes[0])
                minuto = partes[1][:2]
                return f"{hora:02d}:{minuto}"
        
        # Si está en formato 12h (ej: "3:00 PM")
        if 'AM' in hora_str or 'PM' in hora_str:
            from datetime import datetime
            hora_limpia = hora_str.strip()
            hora_obj = datetime.strptime(hora_limpia, '%I:%M %p')
            return hora_obj.strftime('%H:%M')
        
        return hora_str
    except Exception as e:
        print(f"⚠️ Error normalizando hora '{hora_str}': {e}")
        return hora_str

def verificar_disponibilidad(profesional_id, fecha, hora, duracion_minutos):
    """
    Verifica si un profesional está disponible en una fecha y hora específicas.
    Reemplaza la función inexistente que llama ia_agendar_cita()
    """
    from datetime import datetime, timedelta
    
    try:
        # Obtener citas del día
        citas = obtener_citas_dia(None, profesional_id, fecha)  # None para negocio_id
        
        if not citas:
            return True  # No hay citas, está disponible
        
        # Convertir hora a datetime para comparar
        hora_inicio = datetime.strptime(hora, '%H:%M')
        hora_fin = hora_inicio + timedelta(minutes=int(duracion_minutos))
        
        # Verificar solapamiento con cada cita existente
        for cita in citas:
            cita_hora_str = cita.get('hora', '')
            cita_duracion = cita.get('duracion', 0)
            cita_estado = cita.get('estado', '')
            
            # Ignorar citas canceladas
            if cita_estado and cita_estado.lower() in ['cancelado', 'cancelada']:
                continue
            
            try:
                # Normalizar hora de la cita
                if 'AM' in cita_hora_str or 'PM' in cita_hora_str:
                    cita_hora_obj = datetime.strptime(cita_hora_str.strip(), '%I:%M %p')
                    cita_hora_str = cita_hora_obj.strftime('%H:%M')
                
                cita_hora = datetime.strptime(cita_hora_str, '%H:%M')
                cita_fin = cita_hora + timedelta(minutes=int(cita_duracion))
                
                # Verificar solapamiento
                if (hora_inicio.time() < cita_fin.time() and 
                    hora_fin.time() > cita_hora.time()):
                    print(f"❌ Conflicto: {hora} solapa con cita {cita_hora_str}")
                    return False
                    
            except Exception as e:
                print(f"⚠️ Error procesando cita {cita_hora_str}: {e}")
                continue
        
        return True
        
    except Exception as e:
        print(f"❌ Error en verificar_disponibilidad: {e}")
        # En caso de error, mejor prevenir y decir que NO está disponible
        return False


def agregar_cita(negocio_id, profesional_id, cliente_telefono, fecha, hora, servicio_id, cliente_nombre="", fecha_fin=None):
    """Agregar nueva cita a la base de datos.

    ``fecha_fin`` (opcional, 'YYYY-MM-DD'): renta de varios días. El profesional (vehículo) queda ocupado TODOS los días
    de ``fecha`` a ``fecha_fin``, y una cita normal tampoco puede caer dentro de una renta ya existente.
    """
    logger.debug("agregar_cita: negocio_id=%s, profesional_id=%s, fecha=%s, hora=%s, servicio_id=%s, fecha_fin=%s",
                 negocio_id, profesional_id, fecha, hora, servicio_id, fecha_fin)

    # ✅ NORMALIZAR LA HORA (convertir de 12h a 24h si es necesario)
    hora_normalizada = normalizar_hora(hora)

    conn = get_db_connection()
    if not conn:
        print("❌ [DEBUG] No hay conexión a la BD")
        return 0

    cursor = conn.cursor()
    cita_id = 0

    try:
        if is_postgresql():
            import disponibilidad
            # ✅ Lock de asesoramiento por profesional: serializa el chequeo de solapamiento y el INSERT, evitando que
            # dos solicitudes casi simultáneas (flujo IA y flujo de menú, o dos clientes) pasen ambas la verificación
            # de disponibilidad antes de que cualquiera confirme su cita (doble-reserva). Es por profesional (no por
            # fecha) porque una renta de varios días abarca muchas fechas.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"cita_prof_{profesional_id}",))

            cursor.execute('SELECT duracion FROM servicios WHERE id = %s', (servicio_id,))
            fila_duracion = cursor.fetchone()
            if fila_duracion:
                duracion_nueva = fila_duracion['duracion'] if isinstance(fila_duracion, dict) else fila_duracion[0]
            else:
                duracion_nueva = 0

            if fecha_fin:
                # Renta de varios días: no puede haber NINGUNA reserva, bloqueo ni otra renta en ese rango
                cursor.execute("""
                    SELECT 1 FROM citas
                    WHERE profesional_id = %s AND estado NOT IN ('cancelado', 'cancelada')
                      AND fecha <= %s AND COALESCE(fecha_fin, fecha) >= %s
                    LIMIT 1
                """, (profesional_id, fecha_fin, fecha))
                if cursor.fetchone():
                    print(f"❌ [DEBUG] El vehículo no está libre entre {fecha} y {fecha_fin}")
                    conn.rollback()
                    return 0
            else:
                # Citas del día (incluye las rentas de varios días que cubren esta fecha, como día completo)
                cursor.execute("""
                    SELECT CASE WHEN c.fecha_fin IS NOT NULL AND c.fecha <> %s THEN '00:00' ELSE c.hora END AS hora,
                           CASE WHEN c.fecha_fin IS NOT NULL THEN 1440 ELSE COALESCE(c.duracion_minutos, s.duracion, 0) END AS duracion
                    FROM citas c
                    JOIN servicios s ON c.servicio_id = s.id
                    WHERE c.profesional_id = %s AND c.estado NOT IN ('cancelado', 'cancelada')
                      AND (c.fecha = %s OR (c.fecha_fin IS NOT NULL AND c.fecha <= %s AND c.fecha_fin >= %s))
                """, (fecha, profesional_id, fecha, fecha, fecha))
                inicio_nuevo = disponibilidad.a_minutos(hora_normalizada)
                fin_nuevo = inicio_nuevo + max(int(duracion_nueva or 0), disponibilidad.DURACION_MINIMA)
                for cita_existente in cursor.fetchall():
                    if isinstance(cita_existente, dict):
                        cita_hora_str, cita_duracion = cita_existente['hora'], cita_existente['duracion']
                    else:
                        cita_hora_str, cita_duracion = cita_existente[0], cita_existente[1]
                    inicio = disponibilidad.a_minutos(cita_hora_str)
                    if inicio is None:
                        continue
                    fin = inicio + max(int(cita_duracion or 0), disponibilidad.DURACION_MINIMA)
                    if inicio_nuevo < fin and fin_nuevo > inicio:
                        print(f"❌ [DEBUG] Conflicto detectado al confirmar (carrera evitada): {hora_normalizada} solapa con {cita_hora_str}")
                        conn.rollback()
                        return 0

                # Bloqueos recurrentes (p. ej. "martes 15:00-17:30"): también impiden reservar en esa franja
                try:
                    for b_ini, b_fin in disponibilidad.intervalos_bloqueo_recurrente(
                            obtener_bloqueos_recurrentes(negocio_id, profesional_id), fecha):
                        if inicio_nuevo < b_fin and fin_nuevo > b_ini:
                            print(f"❌ [DEBUG] La cita cae dentro de un bloqueo recurrente ({disponibilidad.a_hhmm(b_ini)}-{disponibilidad.a_hhmm(b_fin)})")
                            conn.rollback()
                            return 0
                except Exception as e:
                    print(f"⚠️ No se pudo verificar bloqueos recurrentes: {e}")

        print("🔍 [DEBUG] Intentando INSERT...")

        if fecha_fin:
            cursor.execute('''
                INSERT INTO citas (negocio_id, profesional_id, cliente_telefono, cliente_nombre,
                                 fecha, hora, servicio_id, estado, fecha_fin)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmado', %s)
                RETURNING id
            ''', (negocio_id, profesional_id, cliente_telefono, cliente_nombre, fecha, hora_normalizada, servicio_id, fecha_fin))
        else:
            cursor.execute('''
                INSERT INTO citas (negocio_id, profesional_id, cliente_telefono, cliente_nombre,
                                 fecha, hora, servicio_id, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmado')
                RETURNING id
            ''', (negocio_id, profesional_id, cliente_telefono, cliente_nombre, fecha, hora_normalizada, servicio_id))

        result = cursor.fetchone()
        if hasattr(result, '__getitem__') and isinstance(result, dict):
            cita_id = result['id']
        else:
            cita_id = result[0] if result else 0

        conn.commit()

        print(f"✅ [DEBUG] ¡ÉXITO! Cita agregada con ID: {cita_id}")
        print(f"   - Hora guardada en BD: {hora_normalizada}")

        return cita_id

    except Exception as e:
        print(f"❌ [DEBUG] Error CRÍTICO al agregar cita: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            conn.close()
        print("🔍 [DEBUG] Conexión cerrada")

# Añade esta función en database.py, después de agregar_cita:

def profesional_libre_en_rango(profesional_id, fecha_ini, fecha_fin):
    """True si el profesional (vehículo) no tiene ninguna cita, bloqueo ni renta entre ``fecha_ini`` y ``fecha_fin`` (ambas incluidas)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM citas
            WHERE profesional_id = %s AND estado NOT IN ('cancelado', 'cancelada')
              AND fecha::DATE <= %s::DATE AND COALESCE(fecha_fin, fecha)::DATE >= %s::DATE
            LIMIT 1
        """, (profesional_id, fecha_fin, fecha_ini))
        return cursor.fetchone() is None
    finally:
        conn.close()


def _hora_hhmm(valor):
    """La columna citas.hora es TIME en PostgreSQL (llega como datetime.time): siempre se devuelve 'HH:MM'."""
    if valor is None:
        return None
    if hasattr(valor, 'strftime'):
        return valor.strftime('%H:%M')
    return str(valor)[:5]


def obtener_citas_dia(negocio_id, profesional_id, fecha):
    """Obtener todas las citas de un profesional en un día específico - INCLUYENDO BLOQUEOS"""
    print(f"\n📋 [DB-DIAGNÓSTICO] obtener_citas_dia llamado con:")
    print(f"   negocio_id: {negocio_id}")
    print(f"   profesional_id: {profesional_id}")
    print(f"   fecha: {fecha}")
    
    conn = get_db_connection()
    
    if is_postgresql():
        sql = '''
            SELECT CASE WHEN c.fecha_fin IS NOT NULL AND c.fecha::DATE < %s::DATE THEN '00:00' ELSE c.hora END AS hora,
                   CASE WHEN c.fecha_fin IS NOT NULL THEN 1440 ELSE COALESCE(c.duracion_minutos, s.duracion) END AS duracion,
                   c.estado
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s AND c.profesional_id = %s
            AND (c.fecha::DATE = %s::DATE
                 OR (c.fecha_fin IS NOT NULL AND c.fecha::DATE <= %s::DATE AND c.fecha_fin::DATE >= %s::DATE))
            AND c.estado IN ('confirmado', 'confirmada', 'completado', 'bloqueado')  /* ← INCLUIR BLOQUEADOS */
            ORDER BY 1
        '''
        params = (fecha, negocio_id, profesional_id, fecha, fecha, fecha)
    else:
        sql = '''
            SELECT c.hora, s.duracion, c.estado
            FROM citas c 
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = ? AND c.profesional_id = ? AND c.fecha = ? 
            AND c.estado IN ('confirmado', 'completado', 'bloqueado')
            ORDER BY c.hora
        '''
        params = (negocio_id, profesional_id, fecha)
    
    if negocio_id is None:
        if is_postgresql():
            sql = '''
                SELECT CASE WHEN c.fecha_fin IS NOT NULL AND c.fecha::DATE < %s::DATE THEN '00:00' ELSE c.hora END AS hora,
                       CASE WHEN c.fecha_fin IS NOT NULL THEN 1440 ELSE COALESCE(c.duracion_minutos, s.duracion) END AS duracion,
                       c.estado
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.profesional_id = %s
                AND (c.fecha::DATE = %s::DATE
                     OR (c.fecha_fin IS NOT NULL AND c.fecha::DATE <= %s::DATE AND c.fecha_fin::DATE >= %s::DATE))
                AND c.estado IN ('confirmado', 'confirmada', 'completado', 'bloqueado')
                ORDER BY 1
            '''
        else:
            sql = '''
                SELECT c.hora, s.duracion, c.estado
                FROM citas c 
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.profesional_id = ? AND c.fecha = ? 
                AND c.estado IN ('confirmado', 'completado', 'bloqueado')
                ORDER BY c.hora
            '''
        params = (fecha, profesional_id, fecha, fecha, fecha) if is_postgresql() else (profesional_id, fecha)

    cursor = conn.cursor()
    cursor.execute(sql, params)

    resultados = cursor.fetchall()
    conn.close()
    
    # Convertir resultados a formato consistente
    citas = []
    for row in resultados:
        if isinstance(row, dict):
            citas.append({
                'hora': _hora_hhmm(row.get('hora')),
                'duracion': row.get('duracion', 0),
                'estado': row.get('estado', 'confirmado')
            })
        elif isinstance(row, (list, tuple)):
            cita_dict = {
                'hora': _hora_hhmm(row[0]) if len(row) > 0 else None,
                'duracion': row[1] if len(row) > 1 else 0,
                'estado': row[2] if len(row) > 2 else 'confirmado'
            }
            citas.append(cita_dict)
    
    print(f"📋 Citas procesadas para retornar: {len(citas)}")
    for c in citas:
        print(f"   - {c['hora']} (dur. {c['duracion']} min, estado: {c['estado']})")
    
    return citas


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
    """Obtener citas ACTIVAS de un profesional para una fecha específica"""
    conn = get_db_connection()
    
    print(f"🔍 [DB] Buscando citas para profesional {profesional_id} en fecha {fecha}")
    
    sql = '''
        SELECT c.*, s.nombre as servicio_nombre, s.precio, COALESCE(c.duracion_minutos, s.duracion) AS duracion,
               CASE 
                   WHEN c.estado = 'bloqueado' THEN 'Horario Bloqueado'
                   ELSE s.nombre 
               END as display_nombre
        FROM citas c
        LEFT JOIN servicios s ON c.servicio_id = s.id
        WHERE c.negocio_id = %s AND c.profesional_id = %s 
        AND c.fecha = %s
        AND c.estado IN ('confirmado', 'bloqueado')
        ORDER BY c.hora
    '''
    
    citas = fetch_all(conn.cursor(), sql, (negocio_id, profesional_id, fecha))
    conn.close()
    
    # ✅ NORMALIZAR HORAS para comparación
    for cita in citas:
        if isinstance(cita, dict) and 'hora' in cita:
            # Normalizar para mostrar en el dashboard
            hora_original = cita['hora']
            try:
                if 'AM' in hora_original or 'PM' in hora_original:
                    from datetime import datetime
                    hora_obj = datetime.strptime(hora_original.strip(), '%I:%M %p')
                    cita['hora_display'] = hora_obj.strftime('%I:%M %p').lstrip('0')
                else:
                    cita['hora_display'] = hora_original
            except:
                cita['hora_display'] = hora_original
    
    logger.debug("Encontradas %d citas activas", len(citas))
    
    # Procesar citas para marcar bloqueos
    for cita in citas:
        if cita['estado'] == 'bloqueado':
            cita['es_bloqueo'] = True
            cita['clase_css'] = 'bg-warning'
        else:
            cita['es_bloqueo'] = False
            cita['clase_css'] = ''
    
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
        password_hash = generate_password_hash(password)
        
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
        logger.info("Usuario creado: ID=%s, Rol=%s", usuario_id, rol)
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
        logger.debug("Creando profesional con usuario: negocio_id=%s, especialidad=%s, servicios=%s",
                     negocio_id, especialidad, servicios_ids)

        # 1. Verificar si el email ya existe
        if is_postgresql():
            cursor.execute('SELECT id FROM usuarios WHERE email = %s', (email,))
        else:
            cursor.execute('SELECT id FROM usuarios WHERE email = ?', (email,))

        if cursor.fetchone():
            logger.warning("Email ya está en uso al crear profesional")
            conn.close()
            return None

        # 2. Generar hash de la contraseña
        password_hash = generate_password_hash(password)
        
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
    try:
        conn = get_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        
        # Buscar usuario por email
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
        
        cursor.execute(sql, (email,))
        
        # Obtener resultado
        if is_postgresql() and hasattr(cursor, 'fetchone'):
            usuario = cursor.fetchone()
        else:
            usuario = cursor.fetchone()
        
        if not usuario:
            conn.close()
            return None
        
        # Convertir a diccionario si es necesario
        if hasattr(usuario, 'keys'):  # Es un diccionario (RealDictCursor)
            usuario_dict = dict(usuario)
        else:  # Es una tupla
            usuario_dict = {
                'id': usuario[0],
                'negocio_id': usuario[1],
                'nombre': usuario[2],
                'email': usuario[3],
                'password_hash': usuario[4],
                'rol': usuario[5],
                'activo': usuario[6],
                'created_at': usuario[7],
                'ultimo_login': usuario[8],
                'negocio_nombre': usuario[9] if len(usuario) > 9 else 'Negocio'
            }
        
        # Verificar contraseña — werkzeug primero, SHA256 como fallback para hashes legacy
        stored_hash = usuario_dict['password_hash']
        password_ok = check_password_hash(stored_hash, password)
        if not password_ok:
            # Fallback: hash SHA256 sin salt (hashes creados antes de la migración)
            import hashlib
            sha256_hash = hashlib.sha256(password.encode()).hexdigest()
            if stored_hash != sha256_hash:
                conn.close()
                return None
            # Contraseña correcta con hash legacy — upgrade transparente a werkzeug
            nuevo_hash = generate_password_hash(password)
            try:
                if is_postgresql():
                    cursor.execute('UPDATE usuarios SET password_hash = %s WHERE id = %s',
                                   (nuevo_hash, usuario_dict['id']))
                else:
                    cursor.execute('UPDATE usuarios SET password_hash = ? WHERE id = ?',
                                   (nuevo_hash, usuario_dict['id']))
                conn.commit()
            except Exception:
                conn.rollback()

        # Actualizar último login
        try:
            if is_postgresql():
                update_sql = 'UPDATE usuarios SET ultimo_login = %s WHERE id = %s'
            else:
                update_sql = 'UPDATE usuarios SET ultimo_login = ? WHERE id = ?'

            cursor.execute(update_sql, (datetime.now(), usuario_dict['id']))
            conn.commit()

        except Exception as e:
            print(f"⚠️ Error actualizando último login: {e}")
            conn.rollback()
        
        conn.close()
        
        # Retornar solo datos necesarios
        return {
            'id': usuario_dict['id'],
            'nombre': usuario_dict['nombre'],
            'email': usuario_dict['email'],
            'rol': usuario_dict['rol'],
            'negocio_id': usuario_dict['negocio_id'],
            'negocio_nombre': usuario_dict['negocio_nombre']
        }
        
    except Exception as e:
        print(f"❌ Error en verificar_usuario: {e}")
        import traceback
        traceback.print_exc()
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

def actualizar_configuracion_completa(negocio_id, nombre, tipo_negocio, emoji, configuracion, horarios_actualizados):
    """Actualizar configuración completa del negocio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Conservar las claves que este formulario no maneja (color de acento, etc.)
        actual = fetch_one(cursor, 'SELECT configuracion FROM negocios WHERE id = ?', (negocio_id,))
        valor = (actual.get('configuracion') if isinstance(actual, dict) else (actual[0] if actual else None)) if actual else None
        try:
            previa = json.loads(valor) if isinstance(valor, str) and valor else (valor if isinstance(valor, dict) else {})
        except ValueError:
            previa = {}
        configuracion = {**previa, **(configuracion or {})}

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
    ahora_negocio = localizacion.ahora_en(negocio_id)
    if mes is None:
        mes = ahora_negocio.month
    if año is None:
        año = ahora_negocio.year
    
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

def obtener_servicio_personalizado_cliente(telefono, negocio_id):
    """Obtener servicio personalizado de un cliente"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Buscar cliente por teléfono
        cursor.execute('''
            SELECT id FROM clientes 
            WHERE telefono = %s AND negocio_id = %s
        ''', (telefono, negocio_id))
        
        cliente = cursor.fetchone()
        
        if not cliente:
            return None
        
        cliente_id = cliente['id']
        
        # Buscar servicio personalizado activo para este cliente
        cursor.execute('''
            SELECT 
                sp.id,
                sp.nombre_personalizado,
                sp.descripcion,
                sp.precio_personalizado,
                sp.duracion_personalizada,
                sp.servicio_base_id,
                sp.profesional_id,
                s.nombre as servicio_base_nombre,
                p.nombre as profesional_nombre
            FROM servicios_personalizados sp
            LEFT JOIN servicios s ON sp.servicio_base_id = s.id
            LEFT JOIN profesionales p ON sp.profesional_id = p.id
            WHERE sp.cliente_id = %s 
            AND sp.negocio_id = %s
            AND sp.activo = true
            ORDER BY sp.fecha_actualizacion DESC
            LIMIT 1
        ''', (cliente_id, negocio_id))
        
        servicio_personalizado = cursor.fetchone()
        
        if not servicio_personalizado:
            return None
        
        # Obtener servicios adicionales si existen
        cursor.execute('''
            SELECT 
                s.id as servicio_id,
                s.nombre,
                s.descripcion,
                s.precio,
                s.duracion,
                sac.incluido_por_defecto
            FROM servicios_adicionales_cliente sac
            JOIN servicios s ON sac.servicio_id = s.id
            WHERE sac.servicio_personalizado_id = %s
        ''', (servicio_personalizado['id'],))
        
        servicios_adicionales = cursor.fetchall()
        
        servicio_personalizado['servicios_adicionales'] = servicios_adicionales
        
        return dict(servicio_personalizado)
        
    except Exception as e:
        print(f"❌ Error obteniendo servicio personalizado: {e}")
        return None
    finally:
        conn.close()

# =============================================================================
# BLOQUEO DE HORARIOS POR PROFESIONALES
# =============================================================================

def bloquear_horario_profesional(negocio_id, profesional_id, fecha, hora_inicio, 
                                 duracion_minutos=60, motivo="", sobreescribir=False):
    """
    Bloquear un horario para un profesional - CANCELA TODAS LAS CITAS AFECTADAS
    """
    print(f"🔒 [BLOQUEO] Bloqueando {fecha} {hora_inicio} por {duracion_minutos} minutos")
    print(f"📝 Motivo: {motivo}")
    print(f"🔄 Sobreescribir: {sobreescribir}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Verificar si ya hay bloqueo exactamente en ese horario
        cursor.execute('''
            SELECT id FROM citas 
            WHERE negocio_id = %s AND profesional_id = %s 
            AND fecha = %s AND hora = %s
            AND estado = 'bloqueado'
        ''', (negocio_id, profesional_id, fecha, hora_inicio))
        
        if cursor.fetchone():
            conn.close()
            return {'success': False, 'error': 'Ya existe un bloqueo en ese horario'}

        # 2. Calcular rango del bloqueo
        hora_obj = datetime.strptime(str(hora_inicio)[:5], '%H:%M')
        hora_fin_bloqueo = hora_obj + timedelta(minutes=duracion_minutos)

        # 2b. No se permite un bloqueo que se solape con otro bloqueo existente
        cursor.execute('''
            SELECT c.hora, COALESCE(c.duracion_minutos, s.duracion, 60) AS duracion
            FROM citas c
            LEFT JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s AND c.profesional_id = %s AND c.fecha = %s AND c.estado = 'bloqueado'
        ''', (negocio_id, profesional_id, fecha))
        for otro in cursor.fetchall():
            otro_hora, otro_dur = (otro['hora'], otro['duracion']) if hasattr(otro, 'keys') else (otro[0], otro[1])
            otro_ini = datetime.strptime(str(otro_hora)[:5], '%H:%M')
            otro_fin = otro_ini + timedelta(minutes=int(otro_dur))
            if hora_obj < otro_fin and hora_fin_bloqueo > otro_ini:
                conn.close()
                return {'success': False, 'error': f'Ya hay un bloqueo entre {otro_ini.strftime("%H:%M")} y {otro_fin.strftime("%H:%M")} que se solapa con este'}

        print(f"⏰ Rango bloqueo: {hora_inicio} a {hora_fin_bloqueo.strftime('%H:%M')}")
        
        # 3. Obtener TODAS las citas del día CON SU DURACIÓN
        cursor.execute('''
            SELECT c.id, c.hora, s.duracion, c.estado, c.cliente_nombre
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s AND c.profesional_id = %s 
            AND c.fecha = %s
            AND c.estado IN ('confirmado', 'confirmada', 'completado')
            ORDER BY c.hora
        ''', (negocio_id, profesional_id, fecha))
        
        citas_activas = cursor.fetchall()
        print(f"📋 Citas activas encontradas: {len(citas_activas)}")
        
        # 4. Identificar TODAS las citas que se solapan
        citas_a_cancelar = []
        
        for cita in citas_activas:
            # Extraer datos según formato
            if hasattr(cita, 'keys'):  # Diccionario
                cita_id = cita['id']
                cita_hora = cita['hora']
                cita_duracion = cita['duracion']
                cita_estado = cita['estado']
                cita_cliente = cita.get('cliente_nombre', 'Cliente')
            else:  # Tupla
                cita_id = cita[0]
                cita_hora = cita[1]
                cita_duracion = cita[2]
                cita_estado = cita[3]
                cita_cliente = cita[4] if len(cita) > 4 else 'Cliente'
            
            # Calcular rango de la cita
            cita_hora_obj = datetime.strptime(str(cita_hora)[:5], '%H:%M')
            cita_fin_obj = cita_hora_obj + timedelta(minutes=int(cita_duracion))
            
            # ✅ VERIFICAR SOLAPAMIENTO COMPLETO
            # Una cita se solapa si:
            # - Empieza antes y termina después del inicio del bloqueo
            # - Empieza dentro del bloqueo
            # - Termina dentro del bloqueo
            se_solapa = (
                (cita_hora_obj.time() < hora_fin_bloqueo.time() and 
                 cita_fin_obj.time() > hora_obj.time())
            )
            
            if se_solapa:
                print(f"⚠️ Conflicto con cita {cita_hora}-{cita_fin_obj.strftime('%H:%M')} (cliente: {cita_cliente})")
                
                if sobreescribir:
                    citas_a_cancelar.append(cita_id)
                    print(f"   → Se cancelará (sobreescribir=True)")
                else:
                    print(f"   → NO se puede bloquear (sobreescribir=False)")
                    conn.close()
                    return {
                        'success': False,
                        'error': f'El bloqueo se solapa con cita de {cita_hora} (cliente: {cita_cliente})',
                        'needs_override': True,
                        'cita_conflicto': {
                            'id': cita_id,
                            'hora': cita_hora,
                            'cliente': cita_cliente
                        }
                    }
        
        # 5. Si hay citas para cancelar y sobreescribir=True, cancelarlas TODAS
        if sobreescribir and citas_a_cancelar:
            print(f"🔄 Cancelando {len(citas_a_cancelar)} cita(s): {citas_a_cancelar}")
            
            # Cancelar cada cita individualmente (para tener registro)
            for cita_id in citas_a_cancelar:
                cursor.execute('''
                    UPDATE citas 
                    SET estado = 'cancelado' 
                    WHERE id = %s
                ''', (cita_id,))
                print(f"   ✅ Cita {cita_id} cancelada")
        
        # 6. Crear el bloqueo
        # Obtener un servicio_id válido
        cursor.execute('''
            SELECT id FROM servicios 
            WHERE negocio_id = %s AND activo = TRUE 
            LIMIT 1
        ''', (negocio_id,))
        
        servicio_result = cursor.fetchone()
        if not servicio_result:
            conn.close()
            return {'success': False, 'error': 'No hay servicios activos'}
        
        servicio_id = servicio_result[0] if isinstance(servicio_result, tuple) else servicio_result['id']
        
        # Crear el bloqueo
        cursor.execute('''
            INSERT INTO citas (
                negocio_id, profesional_id, cliente_telefono, cliente_nombre,
                fecha, hora, servicio_id, estado, created_at, duracion_minutos
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'bloqueado', NOW(), %s)
            RETURNING id
        ''', (
            negocio_id,
            profesional_id,
            'BLOQUEO_SISTEMA',
            f"Bloqueado: {motivo}" if motivo else "Horario no disponible",
            fecha,
            hora_inicio,
            servicio_id,
            int(duracion_minutos)
        ))
        
        result = cursor.fetchone()
        bloqueo_id = result[0] if isinstance(result, tuple) else result['id']
        
        conn.commit()
        
        # 7. Preparar mensaje de respuesta
        if citas_a_cancelar:
            mensaje = f'✅ Horario bloqueado: {fecha} {hora_inicio} por {duracion_minutos} minutos\n'
            mensaje += f'   Se cancelaron {len(citas_a_cancelar)} cita(s) afectada(s)'
        else:
            mensaje = f'✅ Horario bloqueado: {fecha} {hora_inicio} por {duracion_minutos} minutos'
        
        print(mensaje)
        
        return {
            'success': True,
            'bloqueo_id': bloqueo_id,
            'message': mensaje,
            'citas_canceladas': len(citas_a_cancelar),
            'citas_canceladas_ids': citas_a_cancelar
        }
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error en bloqueo: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def obtener_bloqueos_profesional(negocio_id, profesional_id, fecha=None):
    """
    Obtener todos los horarios bloqueados de un profesional
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        sql = '''
            SELECT c.id, c.fecha, c.hora, c.cliente_nombre as motivo, c.created_at
            FROM citas c
            WHERE c.negocio_id = %s 
            AND c.profesional_id = %s 
            AND c.estado = 'bloqueado'
            AND c.cliente_telefono = 'BLOQUEO_SISTEMA'
        '''
        
        params = [negocio_id, profesional_id]
        
        if fecha:
            sql += ' AND c.fecha = %s'
            params.append(fecha)
        
        sql += ' ORDER BY c.fecha, c.hora'
        
        cursor.execute(sql, params)
        bloqueos = cursor.fetchall()
        
        return [dict(bloqueo) for bloqueo in bloqueos]
        
    except Exception as e:
        print(f"❌ Error obteniendo bloqueos: {e}")
        return []
    finally:
        conn.close()

def desbloquear_horario(bloqueo_id, profesional_id=None, negocio_id=None):
    """
    Eliminar un bloqueo de horario
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar permisos
        sql = 'SELECT negocio_id, profesional_id FROM citas WHERE id = %s AND estado = %s'
        cursor.execute(sql, (bloqueo_id, 'bloqueado'))
        
        bloqueo = cursor.fetchone()
        
        if not bloqueo:
            conn.close()
            return {'success': False, 'error': 'Bloqueo no encontrado'}
        
        # Si se proporcionan profesional_id o negocio_id, verificar que coincidan
        if profesional_id:
            bloqueo_profesional_id = bloqueo[1] if isinstance(bloqueo, tuple) else bloqueo['profesional_id']
            if bloqueo_profesional_id != profesional_id:
                conn.close()
                return {'success': False, 'error': 'No tienes permiso para desbloquear este horario'}
        
        # Eliminar el bloqueo
        sql_delete = 'DELETE FROM citas WHERE id = %s AND estado = %s'
        cursor.execute(sql_delete, (bloqueo_id, 'bloqueado'))
        
        rows_affected = cursor.rowcount
        
        if rows_affected > 0:
            conn.commit()
            return {'success': True, 'message': 'Horario desbloqueado exitosamente'}
        else:
            conn.rollback()
            return {'success': False, 'error': 'No se pudo eliminar el bloqueo'}
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error desbloqueando horario: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def crear_tabla_suscripciones_push():
    """Crear tabla para suscripciones push si no existe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = '''
        CREATE TABLE IF NOT EXISTS suscripciones_push (
            id SERIAL PRIMARY KEY,
            profesional_id INTEGER NOT NULL,
            subscription_json TEXT NOT NULL,
            dispositivo_info TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            activa BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (profesional_id) REFERENCES profesionales (id) ON DELETE CASCADE,
            UNIQUE(profesional_id, subscription_json)
        )
    '''
    
    if is_postgresql():
        sql = sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    
    execute_sql(cursor, sql)
    conn.commit()
    conn.close()
    print("✅ Tabla suscripciones_push creada/verificada")

def obtener_suscripciones_profesional(profesional_id):
    """Obtener todas las suscripciones push activas de un profesional"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        sql = '''
            SELECT subscription_json, dispositivo_info
            FROM suscripciones_push
            WHERE profesional_id = %s AND activa = TRUE
        '''
        
        if is_postgresql():
            cursor.execute(sql, (profesional_id,))
        else:
            sql = sql.replace('%s', '?')
            cursor.execute(sql, (profesional_id,))
        
        suscripciones = cursor.fetchall()
        
        resultado = []
        for suscripcion in suscripciones:
            try:
                sub_json = json.loads(suscripcion['subscription_json'])
                resultado.append({
                    'subscription': sub_json,
                    'dispositivo': suscripcion.get('dispositivo_info', '')
                })
            except:
                continue
        
        return resultado
    except Exception as e:
        print(f"❌ Error obteniendo suscripciones: {e}")
        return []
    finally:
        conn.close()

# =============================================================================
# BLOQUEOS RECURRENTES (SEMANALES)
# =============================================================================

def crear_tabla_bloqueos_recurrentes():
    """Crear tabla para bloqueos recurrentes si no existe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = '''
        CREATE TABLE IF NOT EXISTS bloqueos_recurrentes (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            profesional_id INTEGER NOT NULL,
            dias_semana TEXT NOT NULL,  -- JSON array de días [1,2,3] (1=lunes, 7=domingo)
            hora_inicio TIME NOT NULL,
            hora_fin TIME NOT NULL,
            motivo TEXT,
            fecha_inicio DATE,
            fecha_fin DATE,
            activo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (negocio_id) REFERENCES negocios (id) ON DELETE CASCADE,
            FOREIGN KEY (profesional_id) REFERENCES profesionales (id) ON DELETE CASCADE
        )
    '''
    
    if is_postgresql():
        sql = sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    
    execute_sql(cursor, sql)
    conn.commit()
    conn.close()
    print("✅ Tabla bloqueos_recurrentes creada/verificada")

def crear_bloqueo_recurrente(negocio_id, profesional_id, dias_semana, hora_inicio, 
                            hora_fin, motivo='', fecha_inicio=None, fecha_fin=None):
    """
    Crear un bloqueo recurrente (semanal)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Validar que los días estén en el rango correcto
        dias_validos = [int(d) for d in dias_semana if 1 <= int(d) <= 7]
        if not dias_validos:
            return {'success': False, 'error': 'Debe seleccionar al menos un día válido'}
        
        # Convertir lista de días a JSON string
        dias_json = json.dumps(dias_validos)
        print(f"📝 [DB] Guardando días: {dias_json}")
        
        # Insertar bloqueo recurrente
        if is_postgresql():
            sql = '''
                INSERT INTO bloqueos_recurrentes 
                (negocio_id, profesional_id, dias_semana, hora_inicio, hora_fin, 
                 motivo, fecha_inicio, fecha_fin, activo, created_at, updated_at)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())
                RETURNING id
            '''
            cursor.execute(sql, (
                negocio_id, profesional_id, dias_json, hora_inicio, hora_fin,
                motivo, fecha_inicio if fecha_inicio else None, 
                fecha_fin if fecha_fin else None
            ))
            
            result = cursor.fetchone()
            if hasattr(result, 'keys'):
                bloqueo_id = result['id']
            else:
                bloqueo_id = result[0] if result else None
        else:
            sql = '''
                INSERT INTO bloqueos_recurrentes 
                (negocio_id, profesional_id, dias_semana, hora_inicio, hora_fin, 
                 motivo, fecha_inicio, fecha_fin, activo, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            '''
            cursor.execute(sql, (
                negocio_id, profesional_id, dias_json, hora_inicio, hora_fin,
                motivo, fecha_inicio if fecha_inicio else None, 
                fecha_fin if fecha_fin else None
            ))
            bloqueo_id = cursor.lastrowid
        
        conn.commit()
        print(f"✅ [DB] Bloqueo recurrente creado con ID: {bloqueo_id}")
        
        # Los bloqueos recurrentes se aplican en vivo (disponibilidad.py y agregar_cita), sin copiar filas por fecha.
        return {'success': True, 'id': bloqueo_id, 'message': 'Bloqueo recurrente creado'}
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creando bloqueo recurrente: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def obtener_bloqueos_recurrentes(negocio_id, profesional_id=None, solo_activos=True):
    """
    Obtener todos los bloqueos recurrentes de un profesional o negocio
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        sql = '''
            SELECT 
                id,
                negocio_id,
                profesional_id,
                dias_semana,
                hora_inicio,
                hora_fin,
                motivo,
                fecha_inicio,
                fecha_fin,
                activo,
                created_at,
                updated_at
            FROM bloqueos_recurrentes
            WHERE negocio_id = %s
        '''
        
        params = [negocio_id]
        
        if profesional_id:
            sql += ' AND profesional_id = %s'
            params.append(profesional_id)
        
        if solo_activos:
            sql += ' AND activo = TRUE'
        
        sql += ' ORDER BY created_at DESC'
        
        print(f"🔍 [DB] Ejecutando consulta: {sql}")
        print(f"🔍 [DB] Parámetros: {params}")
        
        cursor.execute(sql, params)
        bloqueos = cursor.fetchall()
        
        print(f"🔍 [DB] Encontrados {len(bloqueos)} bloqueos recurrentes")
        
        resultado = []
        for i, bloqueo in enumerate(bloqueos):
            print(f"🔍 [DB] Procesando bloqueo #{i+1}")
            bloqueo_dict = dict(bloqueo)
            
            # Parsear días_semana de JSON string a lista
            try:
                if isinstance(bloqueo_dict['dias_semana'], str):
                    bloqueo_dict['dias_semana_lista'] = json.loads(bloqueo_dict['dias_semana'])
                else:
                    bloqueo_dict['dias_semana_lista'] = bloqueo_dict['dias_semana']
                
                print(f"  📅 Días parseados: {bloqueo_dict['dias_semana_lista']}")
                
            except Exception as e:
                print(f"  ⚠️ Error parseando días: {e}")
                bloqueo_dict['dias_semana_lista'] = []
            
            # Crear una versión legible de los días
            dias_nombres = []
            nombres = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
            
            for dia_num in bloqueo_dict['dias_semana_lista']:
                try:
                    dia_int = int(dia_num)
                    if 1 <= dia_int <= 7:
                        dias_nombres.append(nombres[dia_int-1])
                except (ValueError, TypeError):
                    continue
            
            bloqueo_dict['dias_legibles'] = ', '.join(dias_nombres)
            
            # Convertir horas a strings si son objetos time
            if bloqueo_dict['hora_inicio']:
                if hasattr(bloqueo_dict['hora_inicio'], 'strftime'):
                    bloqueo_dict['hora_inicio'] = bloqueo_dict['hora_inicio'].strftime('%H:%M')
            
            if bloqueo_dict['hora_fin']:
                if hasattr(bloqueo_dict['hora_fin'], 'strftime'):
                    bloqueo_dict['hora_fin'] = bloqueo_dict['hora_fin'].strftime('%H:%M')
            
            # Convertir fechas a strings
            if bloqueo_dict['fecha_inicio']:
                if hasattr(bloqueo_dict['fecha_inicio'], 'strftime'):
                    bloqueo_dict['fecha_inicio'] = bloqueo_dict['fecha_inicio'].strftime('%Y-%m-%d')
            
            if bloqueo_dict['fecha_fin']:
                if hasattr(bloqueo_dict['fecha_fin'], 'strftime'):
                    bloqueo_dict['fecha_fin'] = bloqueo_dict['fecha_fin'].strftime('%Y-%m-%d')
            
            resultado.append(bloqueo_dict)
        
        print(f"✅ [DB] Retornando {len(resultado)} bloqueos procesados")
        return resultado
        
    except Exception as e:
        print(f"❌ Error obteniendo bloqueos recurrentes: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        conn.close()

def eliminar_bloqueo_recurrente(bloqueo_id, profesional_id=None, negocio_id=None):
    """
    Eliminar un bloqueo recurrente y todos los bloqueos puntuales asociados
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar permisos
        sql_verificar = '''
            SELECT negocio_id, profesional_id, dias_semana 
            FROM bloqueos_recurrentes 
            WHERE id = %s
        '''
        
        if is_postgresql():
            cursor.execute(sql_verificar, (bloqueo_id,))
        else:
            sql_verificar = sql_verificar.replace('%s', '?')
            cursor.execute(sql_verificar, (bloqueo_id,))
        
        bloqueo = cursor.fetchone()
        
        if not bloqueo:
            return {'success': False, 'error': 'Bloqueo recurrente no encontrado'}
        
        # Si se proporcionan profesional_id o negocio_id, verificar que coincidan
        if profesional_id:
            bloqueo_profesional_id = bloqueo[1] if isinstance(bloqueo, tuple) else bloqueo['profesional_id']
            if bloqueo_profesional_id != profesional_id:
                return {'success': False, 'error': 'No tienes permiso para eliminar este bloqueo'}
        
        # Eliminar TODOS los bloqueos puntuales asociados a este recurrente
        # Buscamos por el patrón en cliente_nombre: 'Recurrente ID:{bloqueo_id}'
        patron_busqueda = f'Recurrente ID:{bloqueo_id}'
        
        cursor.execute('''
            DELETE FROM citas 
            WHERE cliente_telefono = 'BLOQUEO_RECURRENTE'
            AND cliente_nombre LIKE %s
            AND estado = 'bloqueado'
        ''', (f'%{patron_busqueda}%',))
        
        puntuales_eliminados = cursor.rowcount
        print(f"🗑️ Eliminados {puntuales_eliminados} bloqueos puntuales asociados")
        
        # Eliminar el bloqueo recurrente
        cursor.execute('''
            DELETE FROM bloqueos_recurrentes 
            WHERE id = %s
        ''', (bloqueo_id,))
        
        conn.commit()
        
        return {
            'success': True, 
            'message': 'Bloqueo recurrente eliminado',
            'puntuales_eliminados': puntuales_eliminados
        }
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error eliminando bloqueo recurrente: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

def actualizar_bloqueo_recurrente(bloqueo_id, dias_semana=None, hora_inicio=None, 
                                 hora_fin=None, motivo=None, fecha_inicio=None, 
                                 fecha_fin=None, activo=None):
    """
    Actualizar un bloqueo recurrente existente
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        update_fields = []
        params = []
        
        if dias_semana is not None:
            update_fields.append('dias_semana = %s')
            params.append(json.dumps(dias_semana))
        
        if hora_inicio is not None:
            update_fields.append('hora_inicio = %s')
            params.append(hora_inicio)
        
        if hora_fin is not None:
            update_fields.append('hora_fin = %s')
            params.append(hora_fin)
        
        if motivo is not None:
            update_fields.append('motivo = %s')
            params.append(motivo)
        
        if fecha_inicio is not None:
            update_fields.append('fecha_inicio = %s')
            params.append(fecha_inicio if fecha_inicio else None)
        
        if fecha_fin is not None:
            update_fields.append('fecha_fin = %s')
            params.append(fecha_fin if fecha_fin else None)
        
        if activo is not None:
            update_fields.append('activo = %s')
            params.append(activo)
        
        update_fields.append('updated_at = NOW()')
        
        if not update_fields:
            return {'success': False, 'error': 'No hay campos para actualizar'}
        
        params.append(bloqueo_id)
        
        sql = f'''
            UPDATE bloqueos_recurrentes 
            SET {', '.join(update_fields)}
            WHERE id = %s
        '''
        
        if is_postgresql():
            cursor.execute(sql, params)
        else:
            sql = sql.replace('%s', '?')
            cursor.execute(sql, params)
        
        conn.commit()
        
        return {'success': True, 'message': 'Bloqueo recurrente actualizado'}
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error actualizando bloqueo recurrente: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()

# Ejecutar al iniciar para asegurar que la tabla existe
try:
    crear_tabla_bloqueos_recurrentes()
except Exception as e:
    print(f"⚠️ Error creando tabla de bloqueos recurrentes: {e}")


def asegurar_columnas_localizacion():
    """Columnas pais y zona_horaria en negocios (NULL = Colombia, el comportamiento histórico)."""
    if not is_postgresql():
        return
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE negocios ADD COLUMN IF NOT EXISTS pais TEXT")
        cursor.execute("ALTER TABLE negocios ADD COLUMN IF NOT EXISTS zona_horaria TEXT")
        cursor.execute("ALTER TABLE negocios ADD COLUMN IF NOT EXISTS prompt_ia TEXT")
        # Tareas periódicas que deben ejecutarse una sola vez aunque haya varios procesos (p. ej. el resumen diario)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_ejecuciones (
                clave TEXT PRIMARY KEY,
                creada TIMESTAMP DEFAULT NOW()
            )
        """)
        # Duración propia de los bloqueos (antes usaban la del primer servicio activo y quedaban muy cortos)
        cursor.execute("ALTER TABLE citas ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER")
        # Rentas de varios días (renta de autos): último día de la reserva (la devolución). NULL en las citas normales.
        cursor.execute("ALTER TABLE citas ADD COLUMN IF NOT EXISTS fecha_fin TEXT")
# Relación número de WhatsApp (n8n) -> negocio; el alta de negocios la consulta
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS numeros_whatsapp_negocio (
                id SERIAL PRIMARY KEY,
                negocio_id INTEGER NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
                numero_whatsapp VARCHAR(20) NOT NULL UNIQUE,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ Error asegurando columnas de localización: {e}")
    finally:
        conn.close()

    # Relleno (una sola vez) de la duración de los bloqueos recurrentes ya creados: dura lo que dice su regla
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE citas c
            SET duracion_minutos = GREATEST(15, (EXTRACT(EPOCH FROM (br.hora_fin - br.hora_inicio)) / 60)::int)
            FROM bloqueos_recurrentes br
            WHERE c.estado = 'bloqueado' AND c.duracion_minutos IS NULL
              AND c.cliente_telefono = 'BLOQUEO_RECURRENTE'
              AND br.id = NULLIF(substring(c.cliente_nombre from 'Recurrente ID:([0-9]+)'), '')::int
        """)
        conn.commit()
    except Exception as e:
        conn.rollback()  # la tabla de bloqueos recurrentes puede no existir todavía
    finally:
        conn.close()


def guardar_numero_whatsapp_negocio(negocio_id, numero):
    """Asocia el número de la API de WhatsApp a un negocio (uno por negocio).
    Devuelve 'ok', o 'duplicado' si el número ya pertenece a otro negocio."""
    ph = '%s' if is_postgresql() else '?'
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f'SELECT 1 FROM numeros_whatsapp_negocio WHERE numero_whatsapp = {ph} AND negocio_id != {ph}', (numero, negocio_id))
        if cursor.fetchone():
            return 'duplicado'
        cursor.execute(f'UPDATE numeros_whatsapp_negocio SET numero_whatsapp = {ph} WHERE negocio_id = {ph}', (numero, negocio_id))
        if cursor.rowcount == 0:
            cursor.execute(f'INSERT INTO numeros_whatsapp_negocio (negocio_id, numero_whatsapp) VALUES ({ph}, {ph})', (negocio_id, numero))
        conn.commit()
        return 'ok'
    finally:
        conn.close()


def eliminar_numero_whatsapp_negocio(negocio_id):
    ph = '%s' if is_postgresql() else '?'
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM numeros_whatsapp_negocio WHERE negocio_id = {ph}', (negocio_id,))
        conn.commit()
    finally:
        conn.close()


def negocio_id_por_numero_whatsapp(numero):
    """negocio_id del negocio activo dueño de ese número de WhatsApp, o None.

    Coincidencia EXACTA de dígitos (primero la tabla de números de la API, luego el teléfono del negocio). Si el
    número solo coincide por sus últimos 10 dígitos (p. ej. guardado sin indicativo de país) se acepta únicamente
    cuando hay un solo negocio candidato; con varios es ambiguo y no se asigna a ninguno.
    """
    digitos = re.sub(r'[^0-9]', '', str(numero or ''))
    if not digitos:
        return None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.negocio_id FROM numeros_whatsapp_negocio w
            JOIN negocios n ON n.id = w.negocio_id
            WHERE w.numero_whatsapp = %s AND w.activo = TRUE AND n.activo = TRUE
        """, (digitos,))
        fila = cursor.fetchone()
        if fila:
            return fila['negocio_id'] if hasattr(fila, 'keys') else fila[0]
        cursor.execute("""
            SELECT id FROM negocios
            WHERE activo = TRUE
              AND regexp_replace(telefono_whatsapp, '[^0-9]', '', 'g') = %s
        """, (digitos,))
        filas = cursor.fetchall()
        if len(filas) == 1:
            return filas[0]['id'] if hasattr(filas[0], 'keys') else filas[0][0]
        if len(filas) > 1:
            return None
        if len(digitos) >= 7:
            cursor.execute("""
                SELECT id FROM negocios
                WHERE activo = TRUE
                  AND RIGHT(regexp_replace(telefono_whatsapp, '[^0-9]', '', 'g'), 10) = RIGHT(%s, 10)
            """, (digitos,))
            filas = cursor.fetchall()
            if len(filas) == 1:
                return filas[0]['id'] if hasattr(filas[0], 'keys') else filas[0][0]
            if len(filas) > 1:
                print(f"⚠️ [WHATSAPP] El número {digitos} coincide con varios negocios; no se asigna a ninguno")
        return None
    finally:
        conn.close()


def reclamar_ejecucion(clave):
    """True si ESTE proceso es el primero en reclamar la tarea ``clave`` (p. ej. 'resumen_America/Bogota_2026-11-13').

    Con varios procesos/hilos del programador solo uno obtiene True; los demás reciben False y no repiten el trabajo.
    Sin PostgreSQL (desarrollo local) siempre devuelve True.
    """
    if not is_postgresql():
        return True
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scheduler_ejecuciones WHERE creada < NOW() - INTERVAL '30 days'")
        cursor.execute("INSERT INTO scheduler_ejecuciones (clave) VALUES (%s) ON CONFLICT (clave) DO NOTHING", (clave,))
        reclamada = cursor.rowcount == 1
        conn.commit()
        return reclamada
    except Exception as e:
        conn.rollback()
        print(f"⚠️ No se pudo reclamar la tarea {clave}: {e}")
        return True  # ante un fallo de la BD es preferible enviar a no enviar
    finally:
        conn.close()


try:
    asegurar_columnas_localizacion()
except Exception as e:
    print(f"⚠️ Error asegurando columnas de localización: {e}")
