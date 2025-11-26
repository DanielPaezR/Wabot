# =============================================================================
# database.py - SISTEMA GENÉRICO DE CITAS
# =============================================================================
import os
import sqlite3
from datetime import datetime, timedelta
import json
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash


def get_db_connection():
    """Establecer conexión a la base de datos (SQLite o PostgreSQL) - VERSIÓN MEJORADA"""
    database_url = os.getenv('DATABASE_URL')
    
    print(f"🔧 [DEBUG] Intentando conectar a: {database_url}")
    
    # Si estamos en producción con PostgreSQL
    if database_url and database_url.startswith('postgresql://'):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            print("✅ Conectando a PostgreSQL...")
            
            # Convertir URL de PostgreSQL para psycopg2
            if database_url.startswith('postgresql://'):
                database_url = database_url.replace('postgresql://', 'postgres://')
            
            # Conectar con cursor que retorna diccionarios
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            print("✅ Conexión PostgreSQL exitosa")
            return conn
            
        except ImportError:
            print("⚠️ psycopg2 no instalado, usando SQLite")
            return sqlite3.connect('negocio.db')
        except Exception as e:
            print(f"❌ Error conectando a PostgreSQL: {e}")
            print("🔄 Fallback a SQLite...")
            return sqlite3.connect('negocio.db')
    else:
        # Desarrollo local con SQLite
        print("🔧 Usando SQLite local")
        conn = sqlite3.connect('negocio.db')
        conn.row_factory = sqlite3.Row
        return conn

# =============================================================================
# INICIALIZACIÓN DE BASE DE DATOS
# =============================================================================

def init_db():
    """Inicializar base de datos con manejo robusto de errores"""
    print("🔧 INICIANDO INIT_DB - CREANDO ESQUEMA...")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("✅ Conexión a BD establecida")
        
        # Detectar tipo de BD
        is_postgresql = os.getenv('DATABASE_URL', '').startswith('postgresql://')
        print(f"🔧 Usando {'PostgreSQL' if is_postgresql else 'SQLite'}")
        
        # Actualizar esquema primero
        actualizar_esquema_bd()
        
        # Crear tablas con sintaxis correcta
        _crear_tablas(cursor)
        print("✅ Tablas creadas/verificadas")
        
        # Insertar datos por defecto
        _insertar_datos_por_defecto(cursor)
        print("✅ Datos por defecto insertados")
        
        conn.commit()
        print("✅ Commit realizado")
        
        # Crear plantillas
        crear_plantillas_personalizadas_para_negocios()
        print("✅ Plantillas personalizadas creadas")
        
        print("🎉 BASE DE DATOS INICIALIZADA COMPLETAMENTE")
        
    except Exception as e:
        print(f"❌ Error en init_db: {e}")
        # En PostgreSQL, algunos errores son normales (tablas ya existen)
        if "already exists" not in str(e) and "duplicate" not in str(e) and "exists" not in str(e):
            print(f"🚨 ERROR CRÍTICO: {e}")
            # No relanzar el error, continuar con la aplicación
        else:
            print("⚠️ Error no crítico (tablas probablemente ya existen)")
    finally:
        if conn:
            conn.close()

def execute_query(query, params=()):
    """Ejecutar consulta compatible con SQLite y PostgreSQL"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Adaptar consultas para PostgreSQL si es necesario
        if hasattr(conn, 'cursor') and not isinstance(conn, sqlite3.Connection):
            # Estamos en PostgreSQL
            query = query.replace('?', '%s')
        
        cursor.execute(query, params)
        
        # Para SELECT, retornar resultados
        if query.strip().upper().startswith('SELECT'):
            results = cursor.fetchall()
            
            # Convertir a diccionarios si es PostgreSQL
            if hasattr(conn, 'cursor') and not isinstance(conn, sqlite3.Connection):
                columns = [desc[0] for desc in cursor.description]
                results = [dict(zip(columns, row)) for row in results]
            else:
                # SQLite ya retorna Row objects que se comportan como dicts
                results = [dict(row) for row in results]
                
            return results
        else:
            # Para INSERT, UPDATE, DELETE
            conn.commit()
            return cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error en consulta: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

def _crear_tablas(cursor):
    """Crear todas las tablas necesarias - VERSIÓN POSTGRESQL COMPATIBLE"""
    
    # Detectar si estamos en PostgreSQL
    is_postgresql = os.getenv('DATABASE_URL', '').startswith('postgresql://')
    
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
    if is_postgresql:
        negocios_sql = negocios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    cursor.execute(negocios_sql)
    
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
    if is_postgresql:
        usuarios_sql = usuarios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    cursor.execute(usuarios_sql)
    
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
    if is_postgresql:
        plantillas_sql = plantillas_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    cursor.execute(plantillas_sql)
    
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
    if is_postgresql:
        profesionales_sql = profesionales_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    cursor.execute(profesionales_sql)
    
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
    if is_postgresql:
        servicios_sql = servicios_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    cursor.execute(servicios_sql)
    
    # Tabla citas
    citas_sql = '''
        CREATE TABLE IF NOT EXISTS citas (
            id SERIAL PRIMARY KEY,
            negocio_id INTEGER NOT NULL,
            profesional_id INTEGER NOT NULL,
            cliente_telefono TEXT NOT NULL,
            cliente_nombre TEXT,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
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
    if is_postgresql:
        citas_sql = citas_sql.replace('CURRENT_TIMESTAMP', 'NOW()')
    cursor.execute(citas_sql)
    
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
    cursor.execute(configuracion_sql)
    
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
    cursor.execute(config_horarios_sql)
    
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
    cursor.execute(prof_servicios_sql)

def _insertar_datos_por_defecto(cursor):
    """Insertar datos por defecto en las tablas"""
    # Negocio por defecto
    cursor.execute('''
        INSERT OR IGNORE INTO negocios (id, nombre, telefono_whatsapp, tipo_negocio, configuracion) 
        VALUES (1, 'Negocio Premium', 'whatsapp:+14155238886', 'general', ?)
    ''', (json.dumps({
        "saludo_personalizado": "¡Hola! Soy tu asistente virtual para agendar citas",
        "horario_atencion": "Lunes a Sábado 9:00 AM - 7:00 PM",
        "direccion": "Calle Principal #123",
        "telefono_contacto": "+573001234567",
        "politica_cancelacion": "Puedes cancelar hasta 2 horas antes"
    }),))
    
    # Usuarios por defecto
    _insertar_usuarios_por_defecto(cursor)
    
    # Plantillas base
    _insertar_plantillas_base(cursor)
    
    # Configuración
    cursor.execute('INSERT OR IGNORE INTO configuracion (negocio_id) VALUES (1)')
    
    # Configuración de horarios
    _insertar_configuracion_horarios(cursor)
    
    # Profesionales por defecto
    _insertar_profesionales_por_defecto(cursor)
    
    # Servicios por defecto
    _insertar_servicios_por_defecto(cursor)

def _insertar_usuarios_por_defecto(cursor):
    """Insertar usuarios por defecto usando Werkzeug"""
    from werkzeug.security import generate_password_hash
    
    usuarios = [
        (1, 'Super Administrador', 'admin@negociobot.com', 'admin123', 'superadmin'),
        (1, 'Juan Propietario', 'juan@negocio.com', 'propietario123', 'propietario'),
        (1, 'Carlos Profesional', 'carlos@negocio.com', 'profesional123', 'profesional'),
        (1, 'Ana Profesional', 'ana@negocio.com', 'profesional123', 'profesional')
    ]
    
    for negocio_id, nombre, email, password, rol in usuarios:
        # ✅ USAR WERKZEUG (mismo que crear_usuario)
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT OR IGNORE INTO usuarios (negocio_id, nombre, email, password_hash, rol) 
            VALUES (?, ?, ?, ?, ?)
        ''', (negocio_id, nombre, email, password_hash, rol))

def migrar_hashes_automatico():
    """Migrar automáticamente los hashes al iniciar la app"""
    from werkzeug.security import generate_password_hash
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Lista de usuarios a migrar
        usuarios = [
            ('admin123', 'admin@negociobot.com'),
            ('propietario123', 'juan@negocio.com'), 
            ('profesional123', 'carlos@negocio.com'),
            ('profesional123', 'ana@negocio.com')
        ]
        
        for password, email in usuarios:
            nuevo_hash = generate_password_hash(password)
            cursor.execute('UPDATE usuarios SET password_hash = ? WHERE email = ?', 
                          (nuevo_hash, email))
        
        conn.commit()
        print("✅ Hashes migrados a Werkzeug automáticamente")
        
    except Exception as e:
        print(f"⚠️ Error en migración automática: {e}")
    finally:
        conn.close()

def adaptar_consultas_para_postgres(sql):
    """Adaptar consultas SQL de SQLite para PostgreSQL"""
    replacements = {
        'AUTOINCREMENT': 'SERIAL',
        'BOOLEAN DEFAULT 1': 'BOOLEAN DEFAULT TRUE',
        'BOOLEAN DEFAULT 0': 'BOOLEAN DEFAULT FALSE', 
        'INTEGER PRIMARY KEY AUTOINCREMENT': 'SERIAL PRIMARY KEY',
        'TIMESTAMP DEFAULT CURRENT_TIMESTAMP': 'TIMESTAMP DEFAULT NOW()',
        'BLOB': 'BYTEA',
        'INSERT OR IGNORE': 'INSERT ON CONFLICT DO NOTHING',
        'INSERT OR REPLACE': 'INSERT ON CONFLICT DO UPDATE SET'
    }
    
    for old, new in replacements.items():
        sql = sql.replace(old, new)
    
    return sql

def migrar_a_postgresql():
    """Migrar de SQLite a PostgreSQL"""
    print("🔄 MIGRANDO A POSTGRESQL...")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Eliminar tablas existentes (si las hay)
        print("🧹 Limpiando tablas existentes...")
        tablas = [
            'profesional_servicios', 'configuracion_horarios', 'configuracion',
            'citas', 'servicios', 'profesionales', 'plantillas_mensajes', 
            'usuarios', 'negocios'
        ]
        
        for tabla in tablas:
            try:
                cursor.execute(f'DROP TABLE IF EXISTS {tabla} CASCADE')
                print(f"✅ Tabla {tabla} eliminada")
            except Exception as e:
                print(f"⚠️ Error eliminando {tabla}: {e}")
        
        # Crear tablas con sintaxis PostgreSQL
        _crear_tablas(cursor)
        print("✅ Tablas creadas con sintaxis PostgreSQL")
        
        # Insertar datos por defecto
        _insertar_datos_por_defecto(cursor)
        print("✅ Datos por defecto insertados")
        
        conn.commit()
        print("🎉 MIGRACIÓN A POSTGRESQL COMPLETADA")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error en migración: {e}")
        raise e
    finally:
        conn.close()

def _insertar_plantillas_base(cursor):
    """Insertar SOLO las 8 plantillas base principales del sistema"""
    # Primero eliminar cualquier plantilla existente
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
        cursor.execute('''
            INSERT INTO plantillas_mensajes 
            (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
            VALUES (NULL, ?, ?, ?, ?, TRUE)
        ''', (nombre, plantilla, descripcion, variables))

def _insertar_configuracion_horarios(cursor):
    """Insertar configuración de horarios por día"""
    dias_semana = [
        (0, '09:00', '19:00', '13:00', '14:00'),  # Lunes
        (1, '09:00', '19:00', '13:00', '14:00'),  # Martes
        (2, '09:00', '19:00', '13:00', '14:00'),  # Miércoles
        (3, '09:00', '19:00', '13:00', '14:00'),  # Jueves
        (4, '09:00', '19:00', '13:00', '14:00'),  # Viernes
        (5, '09:00', '19:00', '13:00', '14:00'),  # Sábado
        (6, '09:00', '13:00', None, None)         # Domingo
    ]
    
    # Para cada negocio existente
    cursor.execute("SELECT id FROM negocios")
    negocios = cursor.fetchall()
    
    for negocio in negocios:
        negocio_id = negocio[0]
        for dia in dias_semana:
            cursor.execute('''
                INSERT OR IGNORE INTO configuracion_horarios 
                (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                VALUES (?, ?, 1, ?, ?, ?, ?)
            ''', (negocio_id, dia[0], dia[1], dia[2], dia[3], dia[4]))

def _insertar_profesionales_por_defecto(cursor):
    """Insertar profesionales por defecto"""
    cursor.execute('''
        INSERT OR IGNORE INTO profesionales (id, negocio_id, nombre, especialidad, pin, usuario_id) VALUES 
        (1, 1, 'Carlos Profesional', 'Especialista en servicios clásicos', '1234', 3),
        (2, 1, 'Ana Profesional', 'Especialista en tratamientos', '5678', 4),
        (3, 1, 'María Profesional', 'Especialista unisex', '9012', NULL)
    ''')

def _insertar_servicios_por_defecto(cursor):
    """Insertar servicios por defecto"""
    cursor.execute('''
        INSERT OR IGNORE INTO servicios (id, negocio_id, nombre, duracion, precio, descripcion) VALUES 
        (1, 1, 'Servicio Básico', 45, 15000, 'Servicio estándar'),
        (2, 1, 'Servicio Completo', 60, 20000, 'Servicio completo'),
        (3, 1, 'Servicio Premium', 75, 25000, 'Servicio premium'),
        (4, 1, 'Servicio Express', 30, 12000, 'Servicio rápido'),
        (5, 1, 'Servicio VIP', 90, 30000, 'Servicio exclusivo')
    ''')

# =============================================================================
# SISTEMA DE PLANTILLAS
# =============================================================================

def obtener_plantilla(negocio_id, nombre_plantilla):
    """Obtener una plantilla específica (personalizada si existe, sino base) - VERSIÓN CORREGIDA"""
    print(f"🔍 obtener_plantilla - negocio_id: {negocio_id}, nombre: {nombre_plantilla}")
    
    try:
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Primero buscar plantilla personalizada
        cursor.execute('''
            SELECT * FROM plantillas_mensajes 
            WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
        ''', (negocio_id, nombre_plantilla))
        
        plantilla = cursor.fetchone()
        es_personalizada = True
        
        # Si no existe personalizada, usar la base
        if not plantilla:
            cursor.execute('''
                SELECT * FROM plantillas_mensajes 
                WHERE nombre = ? AND es_base = TRUE
            ''', (nombre_plantilla,))
            plantilla = cursor.fetchone()
            es_personalizada = False
        
        conn.close()
        
        if plantilla:
            print(f"✅ Plantilla encontrada, tipo: {type(plantilla)}")
            
            # Convertir tupla a diccionario
            columnas = ['id', 'negocio_id', 'nombre', 'plantilla', 'descripcion', 'variables_disponibles', 'es_base', 'activo', 'created_at']
            plantilla_dict = dict(zip(columnas, plantilla))
            plantilla_dict['es_personalizada'] = es_personalizada
            
            print(f"✅ Retornando objeto completo de plantilla")
            return plantilla_dict  # ← ¡IMPORTANTE! Retornar el objeto completo
        else:
            print(f"❌ No se encontró plantilla: {nombre_plantilla}")
            return None
            
    except Exception as e:
        print(f"❌ Error en obtener_plantilla: {e}")
        return None

def obtener_plantillas_base():
    """Obtener SOLO las 8 plantillas base del sistema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Solo obtener las 8 plantillas base específicas
    cursor.execute('''
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
    ''')
    
    plantillas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return plantillas

def obtener_plantillas_negocio(negocio_id):
    """Obtener todas las plantillas disponibles para un negocio - VERSIÓN CORREGIDA"""
    print(f"🔍 obtener_plantillas_negocio - negocio_id: {negocio_id}")
    
    try:
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Obtener nombres únicos de plantillas base
        cursor.execute('''
            SELECT DISTINCT nombre FROM plantillas_mensajes 
            WHERE es_base = TRUE
        ''')
        nombres_plantillas = [row[0] for row in cursor.fetchall()]
        
        plantillas_resultado = []
        
        # Para cada nombre de plantilla, obtener la versión personalizada si existe
        for nombre in nombres_plantillas:
            plantilla = obtener_plantilla(negocio_id, nombre)
            if plantilla:
                plantillas_resultado.append(plantilla)
        
        conn.close()
        
        print(f"✅ Se encontraron {len(plantillas_resultado)} plantillas")
        return plantillas_resultado
        
    except Exception as e:
        print(f"❌ Error en obtener_plantillas_negocio: {e}")
        return []

def obtener_plantillas_unicas_negocio(negocio_id):
    """Obtener plantillas únicas para un negocio (personalizadas si existen, sino base)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM plantillas_mensajes 
        WHERE (negocio_id = ? AND es_base = FALSE) 
           OR (negocio_id IS NULL AND es_base = TRUE)
        ORDER BY nombre
    ''', (negocio_id,))
    
    todas_plantillas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Filtrar para mostrar solo una versión por nombre
    plantillas_unicas = {}
    for plantilla in todas_plantillas:
        nombre = plantilla['nombre']
        if nombre not in plantillas_unicas or plantilla.get('negocio_id') == negocio_id:
            plantillas_unicas[nombre] = plantilla
    
    return list(plantillas_unicas.values())

def procesar_plantilla(plantilla_texto, negocio_id, cliente_id=None, cita_id=None):
    """Procesar una plantilla reemplazando variables con valores reales"""
    try:
        print(f"🔍 Procesando plantilla para negocio {negocio_id}")
        
        # Obtener datos del negocio
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT nombre, emoji, saludo_personalizado FROM negocios WHERE id = ?', (negocio_id,))
        negocio = cursor.fetchone()
        
        if not negocio:
            return plantilla_texto
            
        nombre_negocio, emoji_negocio, saludo_personalizado = negocio
        
        # Reemplazar variables básicas del negocio
        plantilla_procesada = plantilla_texto
        plantilla_procesada = plantilla_procesada.replace('{nombre_negocio}', nombre_negocio or 'Nuestro Negocio')
        plantilla_procesada = plantilla_procesada.replace('{emoji_negocio}', emoji_negocio or '👋')
        plantilla_procesada = plantilla_procesada.replace('{saludo_personalizado}', saludo_personalizado or '¡Estamos aquí para ayudarte!')
        
        # Si hay cliente_id, obtener datos del cliente
        if cliente_id:
            cursor.execute('SELECT nombre FROM clientes WHERE id = ?', (cliente_id,))
            cliente = cursor.fetchone()
            if cliente:
                plantilla_procesada = plantilla_procesada.replace('{nombre_cliente}', cliente[0])
        
        # Si hay cita_id, obtener datos de la cita
        if cita_id:
            cursor.execute('''
                SELECT fecha, hora, servicios.nombre 
                FROM citas 
                JOIN servicios ON citas.servicio_id = servicios.id 
                WHERE citas.id = ?
            ''', (cita_id,))
            cita = cursor.fetchone()
            if cita:
                plantilla_procesada = plantilla_procesada.replace('{fecha_cita}', str(cita[0]))
                plantilla_procesada = plantilla_procesada.replace('{hora_cita}', str(cita[1]))
                plantilla_procesada = plantilla_procesada.replace('{servicio_cita}', cita[2] or 'Servicio')
        
        conn.close()
        
        print(f"✅ Plantilla procesada correctamente")
        return plantilla_procesada
        
    except Exception as e:
        print(f"❌ Error procesando plantilla: {e}")
        return plantilla_texto  # Retornar plantilla original en caso de error

def actualizar_plantilla_negocio(negocio_id, nombre_plantilla, nueva_plantilla, descripcion=None):
    """Actualizar o crear plantilla personalizada para un negocio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si ya existe una personalizada
        cursor.execute('''
            SELECT id FROM plantillas_mensajes 
            WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
        ''', (negocio_id, nombre_plantilla))
        
        existe = cursor.fetchone()
        
        if existe:
            # Actualizar existente
            cursor.execute('''
                UPDATE plantillas_mensajes 
                SET plantilla = ?, descripcion = ?
                WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
            ''', (nueva_plantilla, descripcion, negocio_id, nombre_plantilla))
        else:
            # Crear nueva personalizada
            cursor.execute('''
                SELECT descripcion, variables_disponibles 
                FROM plantillas_mensajes 
                WHERE nombre = ? AND es_base = TRUE
            ''', (nombre_plantilla,))
            
            plantilla_base = cursor.fetchone()
            
            if plantilla_base:
                cursor.execute('''
                    INSERT INTO plantillas_mensajes 
                    (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                    VALUES (?, ?, ?, ?, ?, FALSE)
                ''', (negocio_id, nombre_plantilla, nueva_plantilla, 
                      descripcion or plantilla_base[0], plantilla_base[1]))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error actualizando plantilla: {e}")
        return False
    finally:
        conn.close()

def crear_plantillas_personalizadas_para_negocios():
    """Crear copias personalizadas de plantillas base para todos los negocios"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM negocios WHERE activo = 1")
        negocios = cursor.fetchall()
        
        cursor.execute("SELECT * FROM plantillas_mensajes WHERE es_base = TRUE")
        plantillas_base = cursor.fetchall()
        
        for negocio in negocios:
            negocio_id = negocio[0]
            
            for plantilla_base in plantillas_base:
                nombre = plantilla_base['nombre']
                
                cursor.execute('''
                    SELECT id FROM plantillas_mensajes 
                    WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
                ''', (negocio_id, nombre))
                
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO plantillas_mensajes 
                        (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                        VALUES (?, ?, ?, ?, ?, FALSE)
                    ''', (negocio_id, nombre, plantilla_base['plantilla'], 
                          plantilla_base['descripcion'], plantilla_base['variables_disponibles']))
        
        conn.commit()
    except Exception as e:
        print(f"❌ Error creando plantillas personalizadas: {e}")
    finally:
        conn.close()

def guardar_plantilla_personalizada(negocio_id, nombre_plantilla, contenido, descripcion=''):
    """Guardar o actualizar plantilla personalizada"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si ya existe una personalizada
        cursor.execute('''
            SELECT id FROM plantillas_mensajes 
            WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
        ''', (negocio_id, nombre_plantilla))
        
        existe = cursor.fetchone()
        
        if existe:
            # Actualizar existente
            cursor.execute('''
                UPDATE plantillas_mensajes 
                SET plantilla = ?, descripcion = ?
                WHERE negocio_id = ? AND nombre = ? AND es_base = FALSE
            ''', (contenido, descripcion, negocio_id, nombre_plantilla))
        else:
            # Crear nueva personalizada basada en la plantilla base
            cursor.execute('''
                SELECT descripcion, variables_disponibles 
                FROM plantillas_mensajes 
                WHERE nombre = ? AND es_base = TRUE
            ''', (nombre_plantilla,))
            
            plantilla_base = cursor.fetchone()
            
            descripcion_final = descripcion
            variables_disponibles = '[]'
            
            if plantilla_base:
                if not descripcion_final:
                    descripcion_final = plantilla_base[0]
                variables_disponibles = plantilla_base[1]
            
            cursor.execute('''
                INSERT INTO plantillas_mensajes 
                (negocio_id, nombre, plantilla, descripcion, variables_disponibles, es_base)
                VALUES (?, ?, ?, ?, ?, FALSE)
            ''', (negocio_id, nombre_plantilla, contenido, descripcion_final, variables_disponibles))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Error guardando plantilla: {e}")
        return False
    finally:
        conn.close()


def actualizar_configuracion_negocio(negocio_id, nombre, tipo_negocio, emoji, saludo_personalizado,
                                   horario_atencion, direccion, telefono_contacto, politica_cancelacion):
    """Actualizar configuración del negocio"""
    try:
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Crear objeto de configuración
        configuracion = {
            'saludo_personalizado': saludo_personalizado or '¡Hola! Soy tu asistente virtual para agendar citas.',
            'horario_atencion': horario_atencion or 'Lunes a Sábado 9:00 AM - 7:00 PM',
            'direccion': direccion or 'Calle Principal #123',
            'telefono_contacto': telefono_contacto or '+573001234567',
            'politica_cancelacion': politica_cancelacion or 'Puedes cancelar hasta 2 horas antes'
        }
        
        # Actualizar negocio
        cursor.execute('''
            UPDATE negocios 
            SET nombre = ?, tipo_negocio = ?, emoji = ?, configuracion = ?
            WHERE id = ?
        ''', (nombre, tipo_negocio, emoji, json.dumps(configuracion), negocio_id))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error actualizando configuración: {e}")
        return False

def verificar_configuracion_negocio(negocio_id):
    """Verificar que el negocio tenga todos los datos necesarios para las plantillas"""
    try:
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT nombre, emoji, saludo_personalizado FROM negocios WHERE id = ?', (negocio_id,))
        negocio = cursor.fetchone()
        
        if not negocio:
            return False
            
        nombre, emoji, saludo = negocio
        
        # Si falta algún dato, usar valores por defecto
        needs_update = False
        if not nombre:
            nombre = "Mi Negocio"
            needs_update = True
        if not emoji:
            emoji = "👋"
            needs_update = True
        if not saludo:
            saludo = "¡Estamos aquí para ayudarte!"
            needs_update = True
            
        if needs_update:
            cursor.execute('''
                UPDATE negocios 
                SET nombre = ?, emoji = ?, saludo_personalizado = ?
                WHERE id = ?
            ''', (nombre, emoji, saludo, negocio_id))
            conn.commit()
            print(f"✅ Configuración actualizada para negocio {negocio_id}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error verificando configuración: {e}")
        return False
    
def actualizar_configuracion_completa(negocio_id, nombre, tipo_negocio, emoji, configuracion, horarios_actualizados):
    """Actualizar configuración completa del negocio - VERSIÓN CORREGIDA"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Actualizar información básica del negocio
        cursor.execute('''
            UPDATE negocios 
            SET nombre = ?, tipo_negocio = ?, emoji = ?, configuracion = ?
            WHERE id = ?
        ''', (nombre, tipo_negocio, emoji, json.dumps(configuracion), negocio_id))
        
        # Actualizar horarios por día
        for horario in horarios_actualizados:
            # ✅ CORRECCIÓN: Manejar valores vacíos para horarios de descanso
            almuerzo_inicio = horario['almuerzo_inicio'] if horario['almuerzo_inicio'] else None
            almuerzo_fin = horario['almuerzo_fin'] if horario['almuerzo_fin'] else None
            
            # Verificar si ya existe un registro para este día
            cursor.execute('''
                SELECT id FROM configuracion_horarios 
                WHERE negocio_id = ? AND dia_semana = ?
            ''', (negocio_id, horario['dia_id']))
            
            existe = cursor.fetchone()
            
            if existe:
                # Actualizar registro existente
                cursor.execute('''
                    UPDATE configuracion_horarios 
                    SET activo = ?, hora_inicio = ?, hora_fin = ?, 
                        almuerzo_inicio = ?, almuerzo_fin = ?
                    WHERE negocio_id = ? AND dia_semana = ?
                ''', (
                    horario['activo'], 
                    horario['hora_inicio'], 
                    horario['hora_fin'],
                    almuerzo_inicio,  # ✅ Puede ser None si está vacío
                    almuerzo_fin,     # ✅ Puede ser None si está vacío
                    negocio_id, 
                    horario['dia_id']
                ))
            else:
                # Insertar nuevo registro
                cursor.execute('''
                    INSERT INTO configuracion_horarios 
                    (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    negocio_id, 
                    horario['dia_id'],
                    horario['activo'], 
                    horario['hora_inicio'], 
                    horario['hora_fin'],
                    almuerzo_inicio,  # ✅ Puede ser None si está vacío
                    almuerzo_fin      # ✅ Puede ser None si está vacío
                ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error actualizando configuración: {e}")
        conn.rollback()
        conn.close()
        return False

# =============================================================================
# GESTIÓN DE NEGOCIOS
# =============================================================================

def obtener_negocio_por_telefono(telefono_whatsapp):
    """Obtener un negocio por su número de WhatsApp"""
    conn = get_db_connection()
    negocio = conn.execute(
        'SELECT * FROM negocios WHERE telefono_whatsapp = ? AND activo = 1',
        (telefono_whatsapp,)
    ).fetchone()
    conn.close()
    return negocio

def obtener_negocio_por_id(negocio_id):
    """Obtener negocio por ID - RETORNA DICCIONARIO"""
    try:
        conn = sqlite3.connect('negocio.db')
        conn.row_factory = sqlite3.Row  # Esto hace que retorne objetos Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM negocios WHERE id = ?', (negocio_id,))
        negocio_row = cursor.fetchone()
        conn.close()
        
        if negocio_row:
            # ✅ Convertir Row a diccionario
            return dict(negocio_row)
        return None
        
    except Exception as e:
        print(f"❌ Error obteniendo negocio: {e}")
        return None

def obtener_todos_negocios():
    """Obtener todos los negocios"""
    conn = get_db_connection()
    negocios = conn.execute(
        'SELECT * FROM negocios ORDER BY fecha_creacion DESC'
    ).fetchall()
    conn.close()
    return negocios

def crear_negocio(nombre, telefono_whatsapp, tipo_negocio='general', configuracion='{}'):
    """Crear un nuevo negocio"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, emoji, configuracion)
            VALUES (?, ?, ?, ?, ?)
        ''', (nombre, telefono_whatsapp, tipo_negocio, '👋', configuracion))  # ✅ EMOJI AGREGADO
        
        negocio_id = cursor.lastrowid
        
        # Crear configuración por defecto
        cursor.execute('INSERT INTO configuracion (negocio_id) VALUES (?)', (negocio_id,))
        
        # Crear configuración de horarios
        _insertar_configuracion_horarios_para_negocio(cursor, negocio_id)
        
        # Crear usuario propietario por defecto
        email_propietario = f"propietario{negocio_id}@negocio.com"
        cursor.execute('''
            INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol)
            VALUES (?, ?, ?, ?, ?)
        ''', (negocio_id, 'Propietario', email_propietario, generate_password_hash('propietario123'), 'propietario'))
        
        # Crear servicios por defecto
        _crear_servicios_por_defecto_negocio(cursor, negocio_id, tipo_negocio)
        
        # Crear profesional por defecto
        cursor.execute('''
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
        return None
    finally:
        conn.close()

def _insertar_configuracion_horarios_para_negocio(cursor, negocio_id):
    """Insertar configuración de horarios para un negocio específico"""
    dias_semana = [
        (0, '09:00', '19:00', '13:00', '14:00'),
        (1, '09:00', '19:00', '13:00', '14:00'),
        (2, '09:00', '19:00', '13:00', '14:00'),
        (3, '09:00', '19:00', '13:00', '14:00'),
        (4, '09:00', '19:00', '13:00', '14:00'),
        (5, '09:00', '19:00', '13:00', '14:00'),
        (6, '09:00', '13:00', None, None)
    ]
    
    for dia in dias_semana:
        cursor.execute('''
            INSERT INTO configuracion_horarios 
            (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
            VALUES (?, ?, 1, ?, ?, ?, ?)
        ''', (negocio_id, dia[0], dia[1], dia[2], dia[3], dia[4]))

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
        cursor.execute('''
            INSERT INTO servicios (negocio_id, nombre, duracion, precio, descripcion)
            VALUES (?, ?, ?, ?, ?)
        ''', (negocio_id, nombre, duracion, precio, descripcion))

def actualizar_negocio(negocio_id, nombre, telefono_whatsapp, tipo_negocio, activo, configuracion):
    """Actualizar un negocio existente"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE negocios 
            SET nombre = ?, telefono_whatsapp = ?, tipo_negocio = ?, activo = ?, configuracion = ?
            WHERE id = ?
        ''', (nombre, telefono_whatsapp, tipo_negocio, activo, configuracion, negocio_id))
        
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
    """Obtener lista de todos los profesionales activos - CORREGIDA"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, nombre, especialidad, pin, telefono, activo
        FROM profesionales 
        WHERE negocio_id = ? AND activo = TRUE
        ORDER BY nombre
    ''', (negocio_id,))
    
    profesionales = cursor.fetchall()
    conn.close()
    
    # ✅ CORRECCIÓN: Convertir a lista de diccionarios con estructura correcta
    resultado = []
    for p in profesionales:
        resultado.append({
            'id': p[0],
            'nombre': p[1],
            'especialidad': p[2] or 'General',
            'pin': p[3],
            'telefono': p[4],
            'activo': bool(p[5])
        })
    
    return resultado

def obtener_servicios(negocio_id):
    """Obtener servicios activos de un negocio"""
    try:
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, nombre, duracion, precio 
            FROM servicios 
            WHERE negocio_id = ? AND activo = 1
            ORDER BY nombre
        ''', (negocio_id,))
        
        servicios = []
        for row in cursor.fetchall():
            servicios.append({
                'id': row[0],
                'nombre': row[1],
                'duracion': row[2],
                'precio': row[3]
            })
        
        conn.close()
        return servicios
        
    except Exception as e:
        print(f"❌ Error en obtener_servicios: {e}")
        return []

def obtener_servicio_por_id(servicio_id, negocio_id):
    """Obtener un servicio específico por ID"""
    conn = sqlite3.connect('negocio.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM servicios 
        WHERE id = ? AND negocio_id = ?
    ''', (servicio_id, negocio_id))
    
    servicio = cursor.fetchone()
    conn.close()
    
    if servicio:
        return dict(servicio)
    return None

def obtener_servicios_negocio(negocio_id):
    """Obtener servicios activos de un negocio"""
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, nombre, duracion, precio 
        FROM servicios 
        WHERE negocio_id = ? AND activo = 1
        ORDER BY nombre
    ''', (negocio_id,))
    
    servicios = []
    for row in cursor.fetchall():
        servicios.append({
            'id': row[0],
            'nombre': row[1],
            'duracion': row[2],
            'precio': row[3]
        })
    
    conn.close()
    return servicios

def obtener_nombre_profesional(negocio_id, profesional_id):
    """Obtener nombre de un profesional por ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT nombre FROM profesionales WHERE negocio_id = ? AND id = ?', (negocio_id, profesional_id))
    resultado = cursor.fetchone()
    conn.close()
    
    return resultado[0] if resultado else 'Profesional no encontrado'

def obtener_nombre_servicio(negocio_id, servicio_id):
    """Obtener nombre de un servicio por ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT nombre FROM servicios WHERE negocio_id = ? AND id = ?', (negocio_id, servicio_id))
    resultado = cursor.fetchone()
    conn.close()
    
    return resultado[0] if resultado else 'Servicio no encontrado'

def obtener_duracion_servicio(negocio_id, servicio_id):
    """Obtener duración de un servicio específico"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT duracion FROM servicios WHERE negocio_id = ? AND id = ?', (negocio_id, servicio_id))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else None

def es_cliente_nuevo(telefono, negocio_id):
    """Verificar si es un cliente nuevo"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) FROM citas 
        WHERE cliente_telefono = ? AND negocio_id = ? AND cliente_nombre IS NOT NULL
    ''', (telefono, negocio_id))
    
    resultado = cursor.fetchone()
    conn.close()
    
    count = resultado[0] if resultado else 0
    return count == 0

def obtener_nombre_cliente(telefono, negocio_id):
    """Obtener el nombre del cliente"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT cliente_nombre FROM citas 
        WHERE cliente_telefono = ? AND negocio_id = ? 
        AND cliente_nombre IS NOT NULL 
        AND cliente_nombre != '' 
        AND cliente_nombre != 'Cliente'
        ORDER BY created_at DESC LIMIT 1
    ''', (telefono, negocio_id))
    
    resultado = cursor.fetchone()
    conn.close()
    
    return resultado[0] if resultado else None

def obtener_profesionales_por_negocio(negocio_id):
    """Obtener todos los profesionales de un negocio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, GROUP_CONCAT(s.nombre) as servicios_nombres
        FROM profesionales p
        LEFT JOIN profesional_servicios ps ON p.id = ps.profesional_id
        LEFT JOIN servicios s ON ps.servicio_id = s.id
        WHERE p.negocio_id = ?
        GROUP BY p.id
        ORDER BY p.nombre
    ''', (negocio_id,))
    
    profesionales = cursor.fetchall()
    conn.close()
    
    # Convertir a lista de diccionarios
    result = []
    for p in profesionales:
        profesional_dict = dict(p)
        # Procesar servicios
        servicios_nombres = profesional_dict.get('servicios_nombres', '').split(',') if profesional_dict.get('servicios_nombres') else []
        profesional_dict['servicios'] = [s.strip() for s in servicios_nombres if s.strip()]
        result.append(profesional_dict)
    
    return result

def obtener_profesional_por_id(profesional_id, negocio_id):
    """Obtener un profesional específico con sus servicios"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.*, GROUP_CONCAT(s.id) as servicios_ids, GROUP_CONCAT(s.nombre) as servicios_nombres
        FROM profesionales p
        LEFT JOIN profesional_servicios ps ON p.id = ps.profesional_id
        LEFT JOIN servicios s ON ps.servicio_id = s.id
        WHERE p.id = ? AND p.negocio_id = ?
        GROUP BY p.id
    ''', (profesional_id, negocio_id))
    
    profesional = cursor.fetchone()
    conn.close()
    
    if profesional:
        profesional_dict = dict(profesional)
        # Procesar servicios
        servicios_ids = profesional_dict.get('servicios_ids', '').split(',') if profesional_dict.get('servicios_ids') else []
        servicios_nombres = profesional_dict.get('servicios_nombres', '').split(',') if profesional_dict.get('servicios_nombres') else []
        
        profesional_dict['servicios_ids'] = [int(sid) for sid in servicios_ids if sid]
        profesional_dict['servicios'] = [s.strip() for s in servicios_nombres if s.strip()]
        
        return profesional_dict
    
    return None

def crear_profesional(negocio_id, nombre, especialidad, pin, servicios_ids, activo=True):
    """Crear un nuevo profesional"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insertar profesional
        cursor.execute('''
            INSERT INTO profesionales (negocio_id, nombre, especialidad, pin, activo)
            VALUES (?, ?, ?, ?, ?)
        ''', (negocio_id, nombre, especialidad, pin, activo))
        
        profesional_id = cursor.lastrowid
        
        # Asignar servicios
        for servicio_id in servicios_ids:
            cursor.execute('''
                INSERT INTO profesional_servicios (profesional_id, servicio_id)
                VALUES (?, ?)
            ''', (profesional_id, servicio_id))
        
        conn.commit()
        return profesional_id
        
    except Exception as e:
        conn.rollback()
        print(f"Error creando profesional: {e}")
        return None
    finally:
        conn.close()

def actualizar_profesional(profesional_id, nombre, especialidad, pin, servicios_ids, activo):
    """Actualizar un profesional existente"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Actualizar datos básicos
        cursor.execute('''
            UPDATE profesionales 
            SET nombre = ?, especialidad = ?, pin = ?, activo = ?
            WHERE id = ?
        ''', (nombre, especialidad, pin, activo, profesional_id))
        
        # Eliminar servicios anteriores
        cursor.execute('DELETE FROM profesional_servicios WHERE profesional_id = ?', (profesional_id,))
        
        # Agregar nuevos servicios
        for servicio_id in servicios_ids:
            cursor.execute('''
                INSERT INTO profesional_servicios (profesional_id, servicio_id)
                VALUES (?, ?)
            ''', (profesional_id, servicio_id))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Error actualizando profesional: {e}")
        return False
    finally:
        conn.close()

def eliminar_profesional(profesional_id, negocio_id):
    """Eliminar un profesional"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar que el profesional pertenece al negocio
        cursor.execute('SELECT id FROM profesionales WHERE id = ? AND negocio_id = ?', 
                      (profesional_id, negocio_id))
        
        if not cursor.fetchone():
            return False
        
        # Eliminar relaciones con servicios
        cursor.execute('DELETE FROM profesional_servicios WHERE profesional_id = ?', (profesional_id,))
        
        # Eliminar profesional
        cursor.execute('DELETE FROM profesionales WHERE id = ?', (profesional_id,))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Error eliminando profesional: {e}")
        return False
    finally:
        conn.close()

# =============================================================================
# GESTIÓN DE CITAS (antes turnos)
# =============================================================================

def agregar_cita(negocio_id, profesional_id, cliente_telefono, fecha, hora, servicio_id, cliente_nombre=""):
    """Agregar nueva cita a la base de datos"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO citas (negocio_id, profesional_id, cliente_telefono, cliente_nombre, fecha, hora, servicio_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (negocio_id, profesional_id, cliente_telefono, cliente_nombre, fecha, hora, servicio_id))
        
        conn.commit()
        cita_id = cursor.lastrowid
        return cita_id
    except Exception as e:
        print(f"❌ Error al agregar cita: {e}")
        return None
    finally:
        conn.close()

def obtener_citas_dia(negocio_id, profesional_id, fecha):
    """Obtener todas las citas de un profesional en un día específico"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.hora, s.duracion 
        FROM citas c 
        JOIN servicios s ON c.servicio_id = s.id
        WHERE c.negocio_id = ? AND c.profesional_id = ? AND c.fecha = ? AND c.estado != 'cancelado'
        ORDER BY c.hora
    ''', (negocio_id, profesional_id, fecha))
    
    citas = cursor.fetchall()
    conn.close()
    return citas

def es_cliente_nuevo(telefono, negocio_id):
    """Verificar si es un cliente nuevo"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM citas 
            WHERE cliente_telefono = ? AND negocio_id = ?
        ''', (telefono, negocio_id))
        
        resultado = cursor.fetchone()
        conn.close()
        
        count = resultado[0] if resultado else 0
        return count == 0
        
    except Exception as e:
        print(f"❌ ERROR en es_cliente_nuevo: {e}")
        return True

def obtener_nombre_cliente(telefono, negocio_id):
    """Obtener el nombre del cliente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT cliente_nombre FROM citas 
            WHERE cliente_telefono = ? AND negocio_id = ? 
            AND cliente_nombre IS NOT NULL 
            AND cliente_nombre != '' 
            AND cliente_nombre != 'Cliente'
            ORDER BY created_at DESC LIMIT 1
        ''', (telefono, negocio_id))
        
        resultado = cursor.fetchone()
        conn.close()
        
        return resultado[0] if resultado else None
        
    except Exception as e:
        print(f"❌ ERROR en obtener_nombre_cliente: {e}")
        return None

def obtener_citas_para_profesional(negocio_id, profesional_id, fecha):
    """Obtener citas de un profesional para una fecha específica"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.*, s.nombre as servicio_nombre, s.precio, s.duracion
        FROM citas c
        JOIN servicios s ON c.servicio_id = s.id
        WHERE c.negocio_id = ? AND c.profesional_id = ? AND c.fecha = ?
        ORDER BY c.hora
    ''', (negocio_id, profesional_id, fecha))
    
    citas = cursor.fetchall()
    conn.close()
    
    return [dict(cita) for cita in citas]

# =============================================================================
# CONFIGURACIÓN DE HORARIOS
# =============================================================================

def obtener_horarios_por_dia(negocio_id, fecha):
    """Obtener horarios para un día específico - SIEMPRE CONSULTAR BD"""
    try:
        # ✅ ELIMINAR CACHE - Siempre consultar base de datos fresca
        print(f"🔧 [DEBUG] CONSULTANDO BD para horarios - Negocio: {negocio_id}, Fecha: {fecha}")
        
        # Convertir fecha a día de la semana (0=lunes, 6=domingo)
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        dia_semana_real = fecha_obj.weekday()  # 0=lunes, 1=martes, ..., 6=domingo
        
        # Convertir de 0-6 a 1-7 para buscar en la BD
        dia_semana_bd = dia_semana_real + 1  # 0→1, 1→2, ..., 6→7
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
            FROM configuracion_horarios
            WHERE negocio_id = ? AND dia_semana = ?
        ''', (negocio_id, dia_semana_bd))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            horario = {
                'activo': bool(result[0]),
                'hora_inicio': result[1],
                'hora_fin': result[2],
                'almuerzo_inicio': result[3],
                'almuerzo_fin': result[4]
            }
            return horario
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
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
        FROM configuracion_horarios 
        WHERE negocio_id = ?
        ORDER BY dia_semana
    ''', (negocio_id,))
    
    resultados = cursor.fetchall()
    conn.close()
    
    dias_config = {}
    for row in resultados:
        dias_config[row[0]] = {
            'activo': bool(row[1]),
            'hora_inicio': row[2],
            'hora_fin': row[3],
            'almuerzo_inicio': row[4],
            'almuerzo_fin': row[5]
        }
    
    return dias_config

def actualizar_configuracion_horarios(negocio_id, configuraciones):
    """Actualizar configuración de horarios"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        for dia_id, config in configuraciones.items():
            cursor.execute('''
                INSERT OR REPLACE INTO configuracion_horarios 
                (negocio_id, dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
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

def notificar_cambio_horarios(negocio_id):
    """Notificar que hubo cambios en horarios - limpiar cache"""
    try:
        # Importar y limpiar conversaciones activas
        from whatsapp_handler import conversaciones_activas
        
        # Limpiar todas las conversaciones de este negocio
        claves_a_eliminar = []
        for clave in conversaciones_activas.keys():
            if clave.endswith(f"_{negocio_id}"):
                claves_a_eliminar.append(clave)
        
        for clave in claves_a_eliminar:
            del conversaciones_activas[clave]
        
        print(f"✅ Cache limpiado: {len(claves_a_eliminar)} conversaciones eliminadas para negocio {negocio_id}")
        return True
        
    except Exception as e:
        print(f"⚠️ No se pudo limpiar cache: {e}")
        return False

# =============================================================================
# AUTENTICACIÓN DE USUARIOS
# =============================================================================

def crear_usuario(negocio_id, nombre, email, password, rol):
    """Crear usuario usando SHA256 (consistente con el sistema actual)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar si el email ya existe
        cursor.execute('SELECT id FROM usuarios WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return None
        
        # ✅ USAR SHA256 (igual que usuarios existentes)
        import hashlib
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Insertar usuario
        cursor.execute(
            'INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol) VALUES (?, ?, ?, ?, ?)',
            (negocio_id, nombre, email, hashed_password, rol)
        )
        nuevo_usuario_id = cursor.lastrowid
        
        # Si es profesional, crear automáticamente en tabla profesionales
        if rol == 'profesional':
            cursor.execute(
                'SELECT id FROM profesionales WHERE nombre = ? AND negocio_id = ?',
                (nombre, negocio_id)
            )
            profesional_existente = cursor.fetchone()
            
            if not profesional_existente:
                cursor.execute(
                    'INSERT INTO profesionales (negocio_id, nombre, especialidad, pin, usuario_id, activo) VALUES (?, ?, ?, ?, ?, ?)',
                    (negocio_id, nombre, 'General', '0000', nuevo_usuario_id, True)
                )
        
        conn.commit()
        conn.close()
        return nuevo_usuario_id
        
    except Exception as e:
        print(f"❌ Error en crear_usuario: {e}")
        if conn:
            conn.close()
        return None

def verificar_usuario(email, password):
    """Verificar credenciales de usuario usando SHA256"""
    conn = get_db_connection()
    
    usuario = conn.execute('''
        SELECT u.*, n.nombre as negocio_nombre 
        FROM usuarios u 
        JOIN negocios n ON u.negocio_id = n.id 
        WHERE u.email = ? AND u.activo = 1
    ''', (email,)).fetchone()
    
    conn.close()
    
    if usuario:
        # ✅ SHA256 (consistente con crear_usuario)
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if usuario['password_hash'] == password_hash:
            # Actualizar último login
            conn = get_db_connection()
            conn.execute('UPDATE usuarios SET ultimo_login = ? WHERE id = ?', 
                        (datetime.now(), usuario['id']))
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
    """Obtener todos los usuarios de un negocio"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.*, n.nombre as negocio_nombre
        FROM usuarios u
        JOIN negocios n ON u.negocio_id = n.id
        WHERE u.negocio_id = ?
        ORDER BY u.fecha_creacion DESC
    ''', (negocio_id,))
    
    usuarios = cursor.fetchall()
    conn.close()
    
    return [dict(usuario) for usuario in usuarios]

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def actualizar_esquema_bd():
    """Actualizar esquema de base de datos existente de forma tolerante"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("🔧 ACTUALIZANDO ESQUEMA DE BD...")
        
        # Solo intentar alterar tablas si existen
        try:
            cursor.execute("SELECT 1 FROM negocios LIMIT 1")
            tabla_negocios_existe = True
        except:
            tabla_negocios_existe = False
        
        if tabla_negocios_existe:
            # ✅ VERIFICAR COLUMNA EMOJI EN NEGOCIOS
            try:
                cursor.execute("PRAGMA table_info(negocios)")
                columnas_negocios = cursor.fetchall()
                columnas_negocios_existentes = [col[1] for col in columnas_negocios]
                
                if 'emoji' not in columnas_negocios_existentes:
                    cursor.execute('ALTER TABLE negocios ADD COLUMN emoji TEXT DEFAULT "👋"')
                    print("✅ Columna 'emoji' agregada a tabla negocios")
            except Exception as e:
                print(f"⚠️ Error verificando columna emoji: {e}")
        
        # Para otras alteraciones, usar el mismo patrón...
        
        conn.commit()
        print("✅ Esquema de base de datos actualizado/verificado")
        
    except Exception as e:
        print(f"⚠️ Error actualizando esquema: {e}")
        # No hacer rollback, permitir que continúe
    finally:
        conn.close()

# =============================================================================
# FUNCIONES DE UTILIDAD PARA HORARIOS
# =============================================================================

def es_horario_almuerzo(hora, config):
    """Verificar si es horario de almuerzo"""
    if not config.get('almuerzo_inicio') or not config.get('almuerzo_fin'):
        return False
        
    almuerzo_ini = datetime.strptime(config['almuerzo_inicio'], '%H:%M')
    almuerzo_fin = datetime.strptime(config['almuerzo_fin'], '%H:%M')
    hora_time = hora.time()
    
    return almuerzo_ini.time() <= hora_time < almuerzo_fin.time()

def esta_disponible(hora_inicio, duracion_servicio, citas_ocupadas, config):
    """Verificar si un horario está disponible"""
    hora_fin_servicio = hora_inicio + timedelta(minutes=duracion_servicio)
    
    # Verificar que no se pase del horario de cierre
    hora_fin_jornada = datetime.strptime(config['hora_fin'], '%H:%M')
    if hora_fin_servicio.time() > hora_fin_jornada.time():
        return False
    
    # Verificar que no interfiera con horario de almuerzo
    if se_solapa_con_almuerzo(hora_inicio, hora_fin_servicio, config):
        return False
    
    # Verificar que no se solape con otras citas
    for cita_ocupada in citas_ocupadas:
        hora_cita = datetime.strptime(cita_ocupada[0], '%H:%M')
        duracion_cita = cita_ocupada[1]
        hora_fin_cita = hora_cita + timedelta(minutes=duracion_cita)
        
        if se_solapan(hora_inicio, hora_fin_servicio, hora_cita, hora_fin_cita):
            return False
    
    return True

def se_solapa_con_almuerzo(hora_inicio, hora_fin, config):
    """Verificar si un horario se solapa con el almuerzo"""
    if not config.get('almuerzo_inicio') or not config.get('almuerzo_fin'):
        return False
        
    almuerzo_ini = datetime.strptime(config['almuerzo_inicio'], '%H:%M')
    almuerzo_fin = datetime.strptime(config['almuerzo_fin'], '%H:%M')
    
    return (hora_inicio.time() < almuerzo_fin.time() and 
            hora_fin.time() > almuerzo_ini.time())

def se_solapan(inicio1, fin1, inicio2, fin2):
    """Verificar si dos intervalos de tiempo se solapan"""
    return (inicio1.time() < fin2.time() and 
            fin1.time() > inicio2.time())

# =============================================================================
# ESTADÍSTICAS
# =============================================================================

def obtener_estadisticas_mensuales(negocio_id, profesional_id=None, mes=None, año=None):
    """Obtener estadísticas mensuales"""
    if mes is None:
        mes = datetime.now().month
    if año is None:
        año = datetime.now().year
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Construir consulta base
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
    
    params = [negocio_id, f"{mes:02d}", str(año)]
    
    if profesional_id:
        query += ' AND c.profesional_id = ?'
        params.append(profesional_id)
    
    cursor.execute(query, params)
    stats = cursor.fetchone()
    
    # Calcular tasa de éxito
    total_citas = stats[0] or 0
    citas_completadas = stats[2] or 0
    tasa_exito = (citas_completadas / total_citas * 100) if total_citas > 0 else 0
    
    estadisticas = {
        'resumen': {
            'total_citas': total_citas,
            'citas_confirmadas': stats[1] or 0,
            'citas_completadas': citas_completadas,
            'citas_canceladas': stats[3] or 0,
            'citas_pendientes': stats[4] or 0,
            'ingresos_totales': float(stats[5] or 0),
            'tasa_exito': round(tasa_exito, 2)
        }
    }
    
    conn.close()
    return estadisticas

# =============================================================================
# FUNCIONES PARA RECORDATORIOS Y NOTIFICACIONES
# =============================================================================

def obtener_citas_proximas_recordatorio():
    """Obtener citas próximas para recordatorios"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Citas en 24 horas
    fecha_24h = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d')
    hora_actual = datetime.now().strftime('%H:%M')
    
    cursor.execute('''
        SELECT c.*, n.nombre as negocio_nombre, n.telefono_whatsapp, 
               p.nombre as profesional_nombre, s.nombre as servicio_nombre,
               s.duracion, s.precio
        FROM citas c
        JOIN negocios n ON c.negocio_id = n.id
        JOIN profesionales p ON c.profesional_id = p.id
        JOIN servicios s ON c.servicio_id = s.id
        WHERE c.fecha = ? AND c.estado = 'confirmado' 
        AND c.recordatorio_24h_enviado = FALSE
        ORDER BY c.hora
    ''', (fecha_24h,))
    
    citas_24h = [dict(row) for row in cursor.fetchall()]
    
    # Citas en 1 hora (mismo día)
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('''
        SELECT c.*, n.nombre as negocio_nombre, n.telefono_whatsapp,
               p.nombre as profesional_nombre, s.nombre as servicio_nombre,
               s.duracion, s.precio
        FROM citas c
        JOIN negocios n ON c.negocio_id = n.id
        JOIN profesionales p ON c.profesional_id = p.id
        JOIN servicios s ON c.servicio_id = s.id
        WHERE c.fecha = ? AND c.estado = 'confirmado'
        AND c.recordatorio_1h_enviado = FALSE
        AND TIME(c.hora) BETWEEN TIME('now', '+55 minutes') AND TIME('now', '+65 minutes')
        ORDER BY c.hora
    ''', (fecha_hoy,))
    
    citas_1h = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'citas_24h': citas_24h,
        'citas_1h': citas_1h
    }

def marcar_recordatorio_enviado(cita_id, tipo_recordatorio):
    """Marcar recordatorio como enviado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if tipo_recordatorio == '24h':
            cursor.execute('''
                UPDATE citas SET recordatorio_24h_enviado = TRUE 
                WHERE id = ?
            ''', (cita_id,))
        elif tipo_recordatorio == '1h':
            cursor.execute('''
                UPDATE citas SET recordatorio_1h_enviado = TRUE 
                WHERE id = ?
            ''', (cita_id,))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error marcando recordatorio: {e}")
        return False
    finally:
        conn.close()

# =============================================================================
# FUNCIONES PARA ADMINISTRADOR
# =============================================================================
def limpiar_registros_duplicados_horarios(negocio_id):
    """Eliminar registros duplicados en configuracion_horarios"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM configuracion_horarios 
            WHERE id NOT IN (
                SELECT MAX(id) 
                FROM configuracion_horarios 
                WHERE negocio_id = ? 
                GROUP BY dia_semana
            ) AND negocio_id = ?
        ''', (negocio_id, negocio_id))
        
        conn.commit()
        conn.close()
        print(f"✅ Registros duplicados eliminados para negocio {negocio_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error limpiando registros duplicados: {e}")
        return False

def obtener_usuarios_todos():
    """Obtener todos los usuarios del sistema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.*, n.nombre as negocio_nombre
        FROM usuarios u
        JOIN negocios n ON u.negocio_id = n.id
        ORDER BY u.fecha_creacion DESC
    ''')
    
    usuarios = cursor.fetchall()
    conn.close()
    
    return [dict(usuario) for usuario in usuarios]