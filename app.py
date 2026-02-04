# =============================================================================
# ARCHIVO COMPLETO - app.py SISTEMA GENÉRICO DE CITAS - POSTGRESQL
# =============================================================================

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory
import pywebpush
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import secrets
from datetime import datetime, timedelta
import database as db
from web_chat_handler import web_chat_bp
import os
from dotenv import load_dotenv
import threading
import threading
import json
from functools import wraps
from database import get_db_connection
import pytz
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid 
from notification_system import notification_system
from push_notifications import push_bp, enviar_notificacion_cita_creada
import scheduler

# Cargar variables de entorno
load_dotenv()

tz_colombia = pytz.timezone('America/Bogota')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'negocio-secret-key')
app.register_blueprint(push_bp, url_prefix='/push')

def enviar_notificacion_push_profesional(profesional_id, titulo, mensaje, cita_id=None):
    """Enviar notificación push a todos los dispositivos del profesional"""
    try:
        print(f"🔔 [PUSH] Enviando notificación push para profesional {profesional_id}")
        
        # Configurar webpush
        VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
        VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
        VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', 'mailto:admin@tuapp.com')
        
        if not all([VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT]):
            print("⚠️ [PUSH] Variables VAPID no configuradas")
            return False
        
        # Configurar claims VAPID
        vapid_claims = {
            "sub": VAPID_SUBJECT,
            "exp": (datetime.utcnow() + timedelta(hours=12)).isoformat()
        }
        
        # Obtener suscripciones del profesional - TABLA SIMPLIFICADA
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT subscription_json 
            FROM suscripciones_push 
            WHERE profesional_id = %s AND activa = TRUE
        ''', (profesional_id,))
        
        suscripciones = cursor.fetchall()
        conn.close()
        
        if not suscripciones:
            print(f"⚠️ [PUSH] Profesional {profesional_id} no tiene suscripciones push")
            return False
        
        # Preparar payload de notificación
        payload = {
            'title': titulo,
            'body': mensaje,
            'icon': '/static/icons/icon-192x192.png',
            'badge': '/static/icons/icon-72x72.png',
            'url': f'/profesional?cita={cita_id}' if cita_id else '/profesional',
            'citaId': cita_id,
            'timestamp': datetime.now().isoformat()
        }
        
        # Enviar a cada suscripción
        exitos = 0
        for suscripcion in suscripciones:
            try:
                subscription_json = suscripcion[0] if isinstance(suscripcion, tuple) else suscripcion['subscription_json']
                subscription = json.loads(subscription_json)
                
                pywebpush.send_notification(
                    subscription,
                    json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims
                )
                exitos += 1
                print(f"✅ [PUSH] Notificación enviada a suscripción #{exitos}")
            except Exception as e:
                print(f"⚠️ [PUSH] Error enviando push: {e}")
                # Si el error es de suscripción expirada, marcarla como inactiva
                if "expired" in str(e).lower() or "gone" in str(e).lower():
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE suscripciones_push 
                            SET activa = FALSE 
                            WHERE profesional_id = %s AND subscription_json = %s
                        ''', (profesional_id, subscription_json))
                        conn.commit()
                        conn.close()
                        print(f"⚠️ [PUSH] Suscripción marcada como inactiva (expiró)")
                    except:
                        pass
        
        print(f"✅ [PUSH] Total notificaciones enviadas: {exitos}/{len(suscripciones)}")
        return exitos > 0
        
    except Exception as e:
        print(f"❌ [PUSH] Error general en notificación push: {e}")
        return False

# =============================================================================
# CONFIGURACIÓN MANUAL DE CSRF (SIN FLASK-WTF)
# =============================================================================

def generate_csrf_token():
    """Generar token CSRF manualmente"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf_token(token_from_form):
    """Validar token CSRF manualmente"""
    if 'csrf_token' not in session:
        return False
    return secrets.compare_digest(session['csrf_token'], token_from_form)

# Context processor para agregar CSRF a todas las templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf_token)

# =============================================================================
# DECORADORES DE AUTENTICACIÓN
# =============================================================================

def login_required(f):
    """Decorador para requerir login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    """Decorador para requerir roles específicos"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario_id' not in session:
                return redirect(url_for('login'))
            
            usuario_rol = session.get('usuario_rol')
            if usuario_rol not in roles:
                flash('No tienes permisos para acceder a esta página', 'error')
                return redirect(url_for(get_redirect_url_by_role(usuario_rol)))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_redirect_url_by_role(rol):
    """Obtener URL de redirección según el rol"""
    if rol == 'superadmin':
        return 'admin_dashboard'
    elif rol == 'propietario':
        return 'negocio_dashboard'
    elif rol == 'profesional':
        return 'profesional_dashboard'
    else:
        return 'login'
    
# =============================================================================
# FUNCIÓN PARA CHAT WEB - AGREGAR ESTO
# =============================================================================

def obtener_negocio_por_id(negocio_id):
    """Obtener información del negocio para el chat"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT n.*, 
               COALESCE(c.configuracion, '{}') as config_json
        FROM negocios n
        LEFT JOIN (
            SELECT negocio_id, json_agg(json_build_object(
                'dia_semana', dia_semana,
                'activo', activo,
                'hora_inicio', hora_inicio,
                'hora_fin', hora_fin,
                'almuerzo_inicio', almuerzo_inicio,
                'almuerzo_fin', almuerzo_fin
            )) as configuracion
            FROM configuracion_horarios
            GROUP BY negocio_id
        ) c ON n.id = c.negocio_id
        WHERE n.id = %s
    ''', (negocio_id,))
    
    negocio = cursor.fetchone()
    conn.close()
    
    if negocio:
        # Parsear configuración JSON
        if negocio.get('config_json'):
            try:
                config_parsed = json.loads(negocio['config_json'])
                negocio['configuracion_horarios'] = config_parsed
            except:
                negocio['configuracion_horarios'] = []
        else:
            negocio['configuracion_horarios'] = []
        
        # Parsear configuración general
        if negocio.get('configuracion'):
            try:
                config_general = json.loads(negocio['configuracion'])
                negocio['config_general'] = config_general
            except:
                negocio['config_general'] = {}
        else:
            negocio['config_general'] = {}
    
    return negocio

# =============================================================================
# FILTROS PERSONALIZADOS PARA JINJA2
# =============================================================================

@app.template_filter('fromjson')
def fromjson_filter(value):
    """Filtro para convertir string JSON a objeto Python"""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

@app.template_filter('tojson')
def tojson_filter(value):
    """Filtro para convertir objeto Python a JSON string"""
    return json.dumps(value)

# =============================================================================
# CONTEXT PROCESSORS
# =============================================================================

@app.context_processor
def utility_processor():
    """Agregar funciones útiles a todos los templates"""
    def now():
        return datetime.now(tz_colombia)
    return dict(now=now)

# Registrar blueprint de WhatsApp
app.register_blueprint(web_chat_bp, url_prefix='/web_chat')

# =============================================================================
# RUTAS BÁSICAS - AGREGAR AL PRINCIPIO
# =============================================================================

@app.route('/')
def index():
    """Página principal - MÍNIMA"""
    return "✅ ¡App Funcionando! Ve a /login para acceder al sistema."

@app.route('/health')
def health_check():
    """Health check para Railway"""
    return jsonify({"status": "healthy", "timestamp": datetime.now(tz_colombia).isoformat()})

@app.route('/test-simple')
def test_simple():
    """Ruta simple sin dependencias"""
    return "✅ Ruta básica OK"

# =============================================================================
# RUTAS DEL CHAT WEB
# =============================================================================

@app.route('/cliente/<int:negocio_id>')
def chat_index(negocio_id):
    """Página principal del chat web para un negocio."""
    # Verificar que el negocio exista y esté activo
    negocio = obtener_negocio_por_id(negocio_id)
    if not negocio or not negocio['activo']:
        return "Negocio no disponible", 404
    
    # Inicializar sesión de chat si no existe
    if 'chat_session_id' not in session:
        session['chat_session_id'] = str(uuid.uuid4())
        session['negocio_id'] = negocio_id
        session['chat_step'] = 'inicio'
        session['datos_agendamiento'] = {}
    
    return render_template('cliente/index.html', 
                          negocio=negocio,
                          session_id=session['chat_session_id'])

@app.route('/cliente/send', methods=['POST'])
def chat_send():
    """Recibir mensaje del usuario en el chat web."""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        negocio_id = data.get('negocio_id')
        
        if not user_message:
            return jsonify({'error': 'Mensaje vacío'}), 400
        
        # Importar aquí para evitar dependencia circular
        from web_chat_handler import procesar_mensaje_chat
        response = procesar_mensaje_chat(
            user_message=user_message,
            session_id=session_id,
            negocio_id=negocio_id,
            session=session
        )
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Error en chat_send: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'message': '❌ Ocurrió un error al procesar tu mensaje. Por favor, intenta de nuevo.',
            'step': 'error'
        })

@app.route('/cliente/reset', methods=['POST'])
def chat_reset():
    """Reiniciar la sesión del chat."""
    session.clear()
    return jsonify({'status': 'sesion_reiniciada'})

@app.route('/cliente/guardar-telefono', methods=['POST'])
def guardar_telefono_cliente():
    """Guardar teléfono del cliente para notificaciones"""
    try:
        data = request.json
        session_id = data.get('session_id')
        negocio_id = data.get('negocio_id')
        telefono = data.get('telefono')
        
        if not all([session_id, negocio_id, telefono]):
            return jsonify({'error': 'Datos incompletos'}), 400
        
        # Guardar en la base de datos
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO cliente_telefonos (session_id, negocio_id, telefono, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (session_id, negocio_id) 
            DO UPDATE SET telefono = %s, updated_at = NOW()
        ''', (session_id, negocio_id, telefono, telefono))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Error guardando teléfono: {e}")
        return jsonify({'error': 'Error interno'}), 500

# =============================================================================
# FUNCIONES PARA GESTIÓN DE PROFESIONALES
# =============================================================================

def obtener_profesionales_por_negocio(negocio_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT p.*, string_agg(s.nombre, ', ') as servicios_nombres
        FROM profesionales p
        LEFT JOIN profesional_servicios ps ON p.id = ps.profesional_id
        LEFT JOIN servicios s ON ps.servicio_id = s.id
        WHERE p.negocio_id = %s
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

def obtener_servicios_por_negocio(negocio_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT * FROM servicios 
        WHERE negocio_id = %s AND activo = TRUE
        ORDER BY nombre
    ''', (negocio_id,))
    
    servicios = [dict(servicio) for servicio in cursor.fetchall()]
    conn.close()
    return servicios

def obtener_profesional_por_id(profesional_id, negocio_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT p.*, string_agg(s.id::text, ',') as servicios_ids, string_agg(s.nombre, ',') as servicios_nombres
        FROM profesionales p
        LEFT JOIN profesional_servicios ps ON p.id = ps.profesional_id
        LEFT JOIN servicios s ON ps.servicio_id = s.id
        WHERE p.id = %s AND p.negocio_id = %s
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insertar profesional
        cursor.execute('''
            INSERT INTO profesionales (negocio_id, nombre, especialidad, pin, activo)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (negocio_id, nombre, especialidad, pin, activo))
        
        profesional_id = cursor.fetchone()[0]
        
        # Asignar servicios
        for servicio_id in servicios_ids:
            cursor.execute('''
                INSERT INTO profesional_servicios (profesional_id, servicio_id)
                VALUES (%s, %s)
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Actualizar datos básicos
        cursor.execute('''
            UPDATE profesionales 
            SET nombre = %s, especialidad = %s, pin = %s, activo = %s
            WHERE id = %s
        ''', (nombre, especialidad, pin, activo, profesional_id))
        
        # Eliminar servicios anteriores
        cursor.execute('DELETE FROM profesional_servicios WHERE profesional_id = %s', (profesional_id,))
        
        # Agregar nuevos servicios
        for servicio_id in servicios_ids:
            cursor.execute('''
                INSERT INTO profesional_servicios (profesional_id, servicio_id)
                VALUES (%s, %s)
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar que el profesional pertenece al negocio
        cursor.execute('SELECT id FROM profesionales WHERE id = %s AND negocio_id = %s', 
                      (profesional_id, negocio_id))
        
        if not cursor.fetchone():
            return False
        
        # Eliminar relaciones con servicios
        cursor.execute('DELETE FROM profesional_servicios WHERE profesional_id = %s', (profesional_id,))
        
        # Eliminar profesional
        cursor.execute('DELETE FROM profesionales WHERE id = %s', (profesional_id,))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Error eliminando profesional: {e}")
        return False
    finally:
        conn.close()

# =============================================================================
# RUTAS DE AUTENTICACIÓN
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login para todos los usuarios - VERSIÓN CORREGIDA"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        usuario = db.verificar_usuario(email, password)
        
        if usuario:
            session['usuario_id'] = usuario['id']
            session['usuario_nombre'] = usuario['nombre']
            session['usuario_email'] = usuario['email']
            session['usuario_rol'] = usuario['rol']
            session['negocio_id'] = usuario['negocio_id']
            session['negocio_nombre'] = usuario['negocio_nombre']
            
            print(f"🔐 LOGIN: {usuario['nombre']} (Rol: {usuario['rol']})")
            
            # Manejar profesional - VERSIÓN CORREGIDA
            if usuario['rol'] == 'profesional':
                if 'profesional_id' in session:
                    del session['profesional_id']
                
                session['needs_push_subscription'] = True

                conn = db.get_db_connection()
                cursor = conn.cursor()
                
                if db.is_postgresql():
                    cursor.execute(
                        'SELECT id, nombre FROM profesionales WHERE usuario_id = %s AND negocio_id = %s', 
                        (usuario['id'], usuario['negocio_id'])
                    )
                else:
                    cursor.execute(
                        'SELECT id, nombre FROM profesionales WHERE usuario_id = ? AND negocio_id = ?', 
                        (usuario['id'], usuario['negocio_id'])
                    )
                
                profesional = cursor.fetchone()
                
                if profesional:
                    # ✅ CORRECCIÓN: Acceder correctamente a los valores según el tipo de cursor
                    if hasattr(profesional, 'keys'):  # Es un diccionario (RealDictCursor)
                        session['profesional_id'] = profesional['id']
                        print(f"✅ PROFESIONAL ENCONTRADO: {profesional['nombre']} (ID: {profesional['id']})")
                    else:  # Es una tupla
                        session['profesional_id'] = profesional[0]
                        print(f"✅ PROFESIONAL ENCONTRADO: {profesional[1]} (ID: {profesional[0]})")
                else:
                    # Buscar por nombre si no se encuentra por usuario_id
                    if db.is_postgresql():
                        cursor.execute(
                            'SELECT id, nombre FROM profesionales WHERE nombre = %s AND negocio_id = %s', 
                            (usuario['nombre'], usuario['negocio_id'])
                        )
                    else:
                        cursor.execute(
                            'SELECT id, nombre FROM profesionales WHERE nombre = ? AND negocio_id = ?', 
                            (usuario['nombre'], usuario['negocio_id'])
                        )
                    
                    profesional = cursor.fetchone()
                    
                    if profesional:
                        if hasattr(profesional, 'keys'):  # Es un diccionario
                            session['profesional_id'] = profesional['id']
                        else:  # Es una tupla
                            session['profesional_id'] = profesional[0]
                    else:
                        # Fallback: primer profesional activo del negocio
                        if db.is_postgresql():
                            cursor.execute(
                                'SELECT id FROM profesionales WHERE negocio_id = %s AND activo = TRUE LIMIT 1', 
                                (usuario['negocio_id'],)
                            )
                        else:
                            cursor.execute(
                                'SELECT id FROM profesionales WHERE negocio_id = ? AND activo = TRUE LIMIT 1', 
                                (usuario['negocio_id'],)
                            )
                        
                        profesional_fallback = cursor.fetchone()
                        if profesional_fallback:
                            if hasattr(profesional_fallback, 'keys'):  # Es un diccionario
                                session['profesional_id'] = profesional_fallback['id']
                            else:  # Es una tupla
                                session['profesional_id'] = profesional_fallback[0]
                
                conn.close()
            
            # Redirigir según el rol
            if usuario['rol'] == 'superadmin':
                return redirect(url_for('admin_dashboard'))
            elif usuario['rol'] == 'propietario':
                return redirect(url_for('negocio_dashboard'))
            elif usuario['rol'] == 'profesional':
                return redirect(url_for('profesional_dashboard'))
        else:
            flash('Credenciales incorrectas', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout para todos los usuarios"""
    session.clear()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('login'))

@app.route('/api/profesional/needs-push')
@login_required
def check_needs_push():
    """Verificar si el profesional necesita suscripción push"""
    try:
        profesional_id = session.get('profesional_id')
        
        if not profesional_id:
            return jsonify({'needsPush': False})
        
        # Verificar si ya tiene suscripciones activas
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) 
            FROM suscripciones_push 
            WHERE profesional_id = %s AND activa = TRUE
        ''', (profesional_id,))
        
        tiene_suscripciones = cursor.fetchone()[0] > 0
        conn.close()
        
        # Si ya tiene suscripciones, no necesita más
        if tiene_suscripciones:
            return jsonify({'needsPush': False})
        
        # Verificar si la sesión indica que necesita push
        needs_push = session.get('needs_push_subscription', False)
        
        # Limpiar la sesión después de verificar
        if 'needs_push_subscription' in session:
            session.pop('needs_push_subscription')
        
        return jsonify({'needsPush': needs_push})
        
    except Exception as e:
        print(f"❌ Error check_needs_push: {e}")
        return jsonify({'needsPush': False})
# =============================================================================
# RUTAS DEL PANEL ADMINISTRADOR
# =============================================================================

@app.route('/admin')
@role_required(['superadmin'])
def admin_dashboard():
    """Panel principal de administración"""
    negocios = db.obtener_todos_negocios()
    total_negocios = len(negocios)
    negocios_activos = sum(1 for n in negocios if n['activo'])
    
    usuarios_recientes = db.obtener_usuarios_todos()[:8]
    
    return render_template('admin/dashboard.html', 
                         negocios=negocios,
                         total_negocios=total_negocios,
                         negocios_activos=negocios_activos,
                         usuarios_recientes=usuarios_recientes)

@app.route('/admin/negocios')
@role_required(['superadmin'])
def admin_negocios():
    """Gestión de negocios"""
    negocios = db.obtener_todos_negocios()
    return render_template('admin/negocios.html', negocios=negocios)

@app.route('/admin/negocios/nuevo', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_nuevo_negocio():
    """Crear nuevo negocio"""
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('admin_nuevo_negocio'))
        
        nombre = request.form.get('nombre')
        telefono_whatsapp = request.form.get('telefono_whatsapp')
        tipo_negocio = request.form.get('tipo_negocio', 'general')
        emoji = request.form.get('emoji', '👋')  # ✅ NUEVO: Obtener el emoji
        
        # Configuración por defecto
        configuracion = {
            "saludo_personalizado": request.form.get('saludo_personalizado', f"¡Hola! Soy tu asistente virtual para agendar citas"),
            "horario_atencion": "Lunes a Sábado 9:00 AM - 7:00 PM",
            "direccion": "Calle Principal #123",
            "telefono_contacto": telefono_whatsapp.replace('whatsapp:', ''),
            "politica_cancelacion": "Puedes cancelar hasta 2 horas antes"
        }
        
        if not telefono_whatsapp.startswith('whatsapp:'):
            telefono_whatsapp = f'whatsapp:{telefono_whatsapp}'
        
        negocio_id = db.crear_negocio(nombre, telefono_whatsapp, tipo_negocio, json.dumps(configuracion), emoji)
        
        if negocio_id:
            flash('Negocio creado exitosamente', 'success')
            return redirect(url_for('admin_negocios'))
        else:
            flash('Error al crear el negocio. Verifica que el número no esté en uso.', 'error')
    
    return render_template('admin/nuevo_negocio.html')

@app.route('/admin/negocios/<int:negocio_id>/editar', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_editar_negocio(negocio_id):
    """Editar negocio existente"""
    negocio = db.obtener_negocio_por_id(negocio_id)
    
    if not negocio:
        flash('Negocio no encontrado', 'error')
        return redirect(url_for('admin_negocios'))
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('admin_editar_negocio', negocio_id=negocio_id))
        
        nombre = request.form.get('nombre')
        telefono_whatsapp = request.form.get('telefono_whatsapp')
        tipo_negocio = request.form.get('tipo_negocio')
        activo = request.form.get('activo') == 'on'
        
        configuracion = {
            "saludo_personalizado": request.form.get('saludo_personalizado', ''),
            "horario_atencion": request.form.get('horario_atencion', ''),
            "direccion": request.form.get('direccion', ''),
            "telefono_contacto": request.form.get('telefono_contacto', ''),
            "politica_cancelacion": request.form.get('politica_cancelacion', '')
        }
        
        if not telefono_whatsapp.startswith('whatsapp:'):
            telefono_whatsapp = f'whatsapp:{telefono_whatsapp}'
        
        db.actualizar_negocio(
            negocio_id, 
            nombre=nombre, 
            telefono_whatsapp=telefono_whatsapp, 
            tipo_negocio=tipo_negocio,
            activo=activo,
            configuracion=json.dumps(configuracion)
        )
        
        flash('Negocio actualizado exitosamente', 'success')
        return redirect(url_for('admin_negocios'))
    
    config = json.loads(negocio['configuracion'] if negocio['configuracion'] else '{}')
    return render_template('admin/editar_negocio.html', negocio=negocio, config=config)

# =============================================================================
# RUTAS PARA ELIMINAR NEGOCIOS
# =============================================================================

@app.route('/admin/negocios/<int:negocio_id>/eliminar', methods=['POST'])
@role_required(['superadmin'])
def admin_eliminar_negocio(negocio_id):
    """Eliminar un negocio (desactivar)"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_negocios'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # En lugar de eliminar, desactivamos el negocio
        cursor.execute('''
            UPDATE negocios 
            SET activo = FALSE 
            WHERE id = %s
        ''', (negocio_id,))
        
        # También desactivamos los usuarios asociados
        cursor.execute('''
            UPDATE usuarios 
            SET activo = FALSE 
            WHERE negocio_id = %s
        ''', (negocio_id,))
        
        conn.commit()
        flash('✅ Negocio desactivado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error eliminando negocio: {e}")
        flash('❌ Error al eliminar el negocio', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_negocios'))

@app.route('/admin/negocios/<int:negocio_id>/activar', methods=['POST'])
@role_required(['superadmin'])
def admin_activar_negocio(negocio_id):
    """Activar un negocio previamente desactivado"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_negocios'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Reactivar el negocio
        cursor.execute('''
            UPDATE negocios 
            SET activo = TRUE 
            WHERE id = %s
        ''', (negocio_id,))
        
        # También reactivar los usuarios asociados
        cursor.execute('''
            UPDATE usuarios 
            SET activo = TRUE 
            WHERE negocio_id = %s
        ''', (negocio_id,))
        
        conn.commit()
        flash('✅ Negocio activado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error activando negocio: {e}")
        flash('❌ Error al activar el negocio', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_negocios'))

# =============================================================================
# RUTAS PARA GESTIÓN DE USUARIOS
# =============================================================================

# =============================================================================
# CORRECCIÓN PARA LA RUTA admin_usuarios
# =============================================================================

@app.route('/admin/usuarios')
@role_required(['superadmin'])
def admin_usuarios():
    """Gestión de usuarios - VERSIÓN CORREGIDA"""
    try:
        usuarios = []
        for negocio in db.obtener_todos_negocios():
            usuarios_negocio = db.obtener_usuarios_por_negocio(negocio['id'])
            usuarios.extend(usuarios_negocio)
        
        # Procesar los datos para la plantilla
        usuarios_procesados = []
        for usuario in usuarios:
            usuario_dict = dict(usuario) if not isinstance(usuario, dict) else usuario
            
            # Convertir datetime a string para la plantilla
            if usuario_dict.get('ultimo_login'):
                if hasattr(usuario_dict['ultimo_login'], 'strftime'):
                    # Es un objeto datetime, convertirlo a string
                    usuario_dict['ultimo_login_str'] = usuario_dict['ultimo_login'].strftime('%Y-%m-%d %H:%M')
                else:
                    # Ya es string
                    usuario_dict['ultimo_login_str'] = str(usuario_dict['ultimo_login'])[:16]
            else:
                usuario_dict['ultimo_login_str'] = 'Nunca'
            
            usuarios_procesados.append(usuario_dict)
        
        return render_template('admin/usuarios.html', usuarios=usuarios_procesados)
        
    except Exception as e:
        print(f"❌ Error en admin_usuarios: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al cargar la página de usuarios', 'error')
        return redirect(url_for('admin_dashboard'))
    
@app.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_nuevo_usuario():
    """Crear nuevo usuario - VERSIÓN CORREGIDA"""
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
        
        negocio_id = request.form.get('negocio_id')
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        password = request.form.get('password')
        rol = request.form.get('rol', 'propietario')
        especialidad = request.form.get('especialidad', '')
        
        print(f"🔧 Datos del formulario: negocio_id={negocio_id}, nombre={nombre}, email={email}, rol={rol}")
        
        # Validaciones
        if not all([nombre, email, password]):
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
        
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
        
        # Si es superadmin y no se seleccionó negocio, usar negocio por defecto
        if rol == 'superadmin' and (not negocio_id or negocio_id == ''):
            negocio_id = 1
        
        # Validar que se haya seleccionado negocio para roles que lo requieren
        if rol != 'superadmin' and (not negocio_id or negocio_id == ''):
            flash('Debes seleccionar un negocio para este rol', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
        
        try:
            # Convertir negocio_id a entero
            if negocio_id:
                negocio_id = int(negocio_id)
            
            usuario_id = db.crear_usuario(negocio_id, nombre, email, password, rol)
            
            if usuario_id:
                if rol == 'profesional':
                    # Si es profesional y se proporcionó especialidad, actualizarla
                    if especialidad:
                        conn = db.get_db_connection()
                        cursor = conn.cursor()
                        if db.is_postgresql():
                            cursor.execute('''
                                UPDATE profesionales 
                                SET especialidad = %s 
                                WHERE usuario_id = %s
                            ''', (especialidad, usuario_id))
                        else:
                            cursor.execute('''
                                UPDATE profesionales 
                                SET especialidad = ? 
                                WHERE usuario_id = ?
                            ''', (especialidad, usuario_id))
                        conn.commit()
                        conn.close()
                    
                    flash(f'Usuario profesional "{nombre}" creado exitosamente', 'success')
                else:
                    flash('Usuario creado exitosamente', 'success')
                return redirect(url_for('admin_usuarios'))
            else:
                flash('Error al crear usuario. El email puede estar en uso o hay un problema con los datos.', 'error')
                return redirect(url_for('admin_nuevo_usuario'))
                
        except ValueError:
            flash('ID de negocio inválido', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
        except Exception as e:
            print(f"❌ Error creando usuario: {e}")
            flash('Error interno al crear el usuario', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
    
    negocios = db.obtener_todos_negocios()
    return render_template('admin/nuevo_usuario.html', negocios=negocios)

@app.route('/admin/usuarios/<int:usuario_id>/toggle', methods=['POST'])
@role_required(['superadmin'])
def admin_toggle_usuario(usuario_id):
    """Activar o desactivar un usuario - VERSIÓN CORREGIDA"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_usuarios'))
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Obtener estado actual del usuario
        if db.is_postgresql():
            cursor.execute('SELECT activo FROM usuarios WHERE id = %s', (usuario_id,))
        else:
            cursor.execute('SELECT activo FROM usuarios WHERE id = ?', (usuario_id,))
        
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('❌ Usuario no encontrado', 'error')
            return redirect(url_for('admin_usuarios'))
        
        # Acceder correctamente a los valores
        if hasattr(usuario, 'keys'):  # Es un diccionario
            activo_actual = usuario['activo']
        else:  # Es una tupla
            activo_actual = usuario[0]
        
        nuevo_estado = not activo_actual  # Invertir estado
        
        # Actualizar estado
        if db.is_postgresql():
            cursor.execute('UPDATE usuarios SET activo = %s WHERE id = %s', (nuevo_estado, usuario_id))
        else:
            cursor.execute('UPDATE usuarios SET activo = ? WHERE id = ?', (nuevo_estado, usuario_id))
        
        conn.commit()
        
        if nuevo_estado:
            flash('✅ Usuario activado exitosamente', 'success')
        else:
            flash('✅ Usuario desactivado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error cambiando estado de usuario: {str(e)}")
        flash('❌ Error al cambiar el estado del usuario', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/<int:usuario_id>/eliminar', methods=['POST'])
@role_required(['superadmin'])
def admin_eliminar_usuario(usuario_id):
    """Eliminar un usuario (solo superadmin) - VERSIÓN CORREGIDA"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_usuarios'))
    
    # Prevenir eliminación del superadmin principal
    if usuario_id == 1:
        flash('❌ No se puede eliminar el superadministrador principal', 'error')
        return redirect(url_for('admin_usuarios'))
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si el usuario existe
        cursor.execute('SELECT rol, email FROM usuarios WHERE id = %s', (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('❌ Usuario no encontrado', 'error')
            return redirect(url_for('admin_usuarios'))
        
        # Acceder correctamente a los valores según el tipo de cursor
        if hasattr(usuario, 'keys'):  # Es un diccionario (RealDictCursor)
            usuario_rol = usuario['rol']
            usuario_email = usuario['email']
        else:  # Es una tupla
            usuario_rol = usuario[0]
            usuario_email = usuario[1]
        
        print(f"🔧 Eliminando usuario: {usuario_email} (ID: {usuario_id}, Rol: {usuario_rol})")
        
        # Si es profesional, también eliminar de la tabla profesionales
        if usuario_rol == 'profesional':
            if db.is_postgresql():
                cursor.execute('DELETE FROM profesionales WHERE usuario_id = %s', (usuario_id,))
            else:
                cursor.execute('DELETE FROM profesionales WHERE usuario_id = ?', (usuario_id,))
            print(f"✅ Relaciones de profesional eliminadas para usuario {usuario_id}")
        
        # Eliminar usuario
        if db.is_postgresql():
            cursor.execute('DELETE FROM usuarios WHERE id = %s', (usuario_id,))
        else:
            cursor.execute('DELETE FROM usuarios WHERE id = ?', (usuario_id,))
        
        conn.commit()
        flash('✅ Usuario eliminado exitosamente', 'success')
        print(f"✅ Usuario {usuario_email} eliminado correctamente")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error eliminando usuario: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('❌ Error al eliminar el usuario', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_editar_usuario(usuario_id):
    """Editar un usuario existente - VERSIÓN CON CAMBIO DE CONTRASEÑA"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Obtener usuario actual
    cursor.execute('''
        SELECT u.*, n.nombre as negocio_nombre 
        FROM usuarios u 
        LEFT JOIN negocios n ON u.negocio_id = n.id 
        WHERE u.id = %s
    ''', (usuario_id,))
    
    usuario = cursor.fetchone()
    
    if not usuario:
        flash('❌ Usuario no encontrado', 'error')
        conn.close()
        return redirect(url_for('admin_usuarios'))
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
        
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        rol = request.form.get('rol')
        activo = request.form.get('activo') == 'on'
        nueva_password = request.form.get('nueva_password')
        only_password = request.form.get('only_password') == 'true'
        
        # Obtener negocio_id según el rol
        if rol == 'superadmin':
            # Para Super Admin, usar el primer negocio o uno específico
            cursor.execute('SELECT id FROM negocios LIMIT 1')
            negocio_por_defecto = cursor.fetchone()
            negocio_id = negocio_por_defecto['id'] if negocio_por_defecto else 1
        else:
            negocio_id = request.form.get('negocio_id')
            if not negocio_id:
                flash('❌ Debes seleccionar un negocio para este rol', 'error')
                conn.close()
                return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
        
        # Obtener campos adicionales para profesionales
        especialidad = request.form.get('especialidad', '')
        telefono = request.form.get('telefono', '')
        
        try:
            if only_password:
                # Solo cambiar contraseña
                if nueva_password:
                    import hashlib
                    hashed_password = hashlib.sha256(nueva_password.encode()).hexdigest()
                    
                    cursor.execute('''
                        UPDATE usuarios 
                        SET password_hash = %s
                        WHERE id = %s
                    ''', (hashed_password, usuario_id))
                    
                    conn.commit()
                    flash('✅ Contraseña actualizada exitosamente', 'success')
                else:
                    flash('❌ No se proporcionó una nueva contraseña', 'error')
                    
            else:
                # Actualizar todos los datos del usuario
                update_query = '''
                    UPDATE usuarios 
                    SET nombre = %s, email = %s, rol = %s, negocio_id = %s, activo = %s
                '''
                params = [nombre, email, rol, negocio_id, activo]
                
                # Si se proporciona nueva contraseña, incluirla en la actualización
                if nueva_password:
                    import hashlib
                    hashed_password = hashlib.sha256(nueva_password.encode()).hexdigest()
                    update_query += ', password_hash = %s'
                    params.append(hashed_password)
                
                update_query += ' WHERE id = %s'
                params.append(usuario_id)
                
                cursor.execute(update_query, params)
                
                # Si es profesional, actualizar también en la tabla profesionales
                if rol == 'profesional':
                    cursor.execute('''
                        SELECT id FROM profesionales WHERE usuario_id = %s
                    ''', (usuario_id,))
                    
                    profesional = cursor.fetchone()
                    
                    if profesional:
                        # Actualizar profesional existente
                        cursor.execute('''
                            UPDATE profesionales 
                            SET nombre = %s, 
                                especialidad = COALESCE(%s, 'General'),
                                telefono = %s,
                                negocio_id = %s,
                                activo = %s
                            WHERE usuario_id = %s
                        ''', (nombre, especialidad, telefono, negocio_id, activo, usuario_id))
                    else:
                        # Crear nuevo profesional
                        cursor.execute('''
                            INSERT INTO profesionales (negocio_id, nombre, especialidad, telefono, pin, usuario_id, activo)
                            VALUES (%s, %s, COALESCE(%s, 'General'), %s, %s, %s, %s)
                        ''', (negocio_id, nombre, especialidad, telefono, '0000', usuario_id, activo))
                else:
                    # Si cambia de profesional a otro rol, eliminar de la tabla profesionales
                    cursor.execute('''
                        DELETE FROM profesionales WHERE usuario_id = %s
                    ''', (usuario_id,))
                
                conn.commit()
                flash('✅ Usuario actualizado exitosamente', 'success')
            
            return redirect(url_for('admin_usuarios'))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error actualizando usuario: {e}")
            flash(f'❌ Error al actualizar el usuario: {str(e)}', 'error')
            return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
        finally:
            conn.close()
    else:
        # Obtener lista de negocios para el formulario
        cursor.execute('SELECT id, nombre FROM negocios ORDER BY nombre')
        negocios = cursor.fetchall()
        conn.close()
        
        return render_template('admin/editar_usuario.html', 
                             usuario=dict(usuario), 
                             negocios=negocios)
    
@app.route('/admin/reset-db')
def admin_reset_db():
    """Ruta de emergencia para resetear la base de datos (SOLO DESARROLLO)"""
    if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('PYTHONANYWHERE_SITE'):
        return "❌ No disponible en producción"
    
    try:
        # Reinicializar base de datos
        db.init_db()
        
        # Resetear secuencia si es PostgreSQL
        if db.is_postgresql():
            db.resetear_secuencia_negocios()
        
        return """
        <h1>✅ Base de datos reseteada</h1>
        <p>La base de datos ha sido reinicializada correctamente.</p>
        <p><a href="/admin/negocios">→ Ir a gestión de negocios</a></p>
        <p><a href="/admin/negocios/nuevo">→ Crear nuevo negocio</a></p>
        """
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =============================================================================
# RUTAS PARA PLANTILLAS DEL ADMINISTRADOR
# =============================================================================

@app.route('/admin/plantillas')
@role_required(['superadmin'])
def admin_plantillas():
    """Gestión de plantillas base del sistema"""
    plantillas = db.obtener_plantillas_base()
    
    # Definir las 8 plantillas base principales
    plantillas_principales = [
        'saludo_inicial_nuevo',
        'saludo_inicial_existente', 
        'menu_principal',
        'ayuda_general',
        'error_generico',
        'cita_confirmada',
        'sin_citas',
        'cita_cancelada'
    ]
    
    # Filtrar solo las plantillas principales
    plantillas_filtradas = [p for p in plantillas if p['nombre'] in plantillas_principales]
    
    return render_template('admin/plantillas.html', 
                         plantillas=plantillas_filtradas)

@app.route('/admin/plantillas/<nombre_plantilla>/editar', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_editar_plantilla(nombre_plantilla):
    """Editar plantilla base del sistema"""
    plantilla_actual = None
    plantillas_base = db.obtener_plantillas_base()
    
    for plantilla in plantillas_base:
        if plantilla['nombre'] == nombre_plantilla:
            plantilla_actual = plantilla
            break
    
    if not plantilla_actual:
        flash('Plantilla no encontrada', 'error')
        return redirect(url_for('admin_plantillas'))
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('admin_editar_plantilla', nombre_plantilla=nombre_plantilla))
        
        nueva_plantilla = request.form.get('plantilla')
        descripcion = request.form.get('descripcion')
        
        # Actualizar plantilla base
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE plantillas_mensajes 
                SET plantilla = %s, descripcion = %s
                WHERE nombre = %s AND es_base = TRUE
            ''', (nueva_plantilla, descripcion, nombre_plantilla))
            
            conn.commit()
            flash('✅ Plantilla base actualizada exitosamente', 'success')
            return redirect(url_for('admin_plantillas'))
        except Exception as e:
            conn.rollback()
            flash('❌ Error al actualizar la plantilla', 'error')
        finally:
            conn.close()
    
    return render_template('admin/editar_plantilla.html', 
                         plantilla=plantilla_actual,
                         es_base=True)

@app.route('/admin/limpiar-plantillas')
@role_required(['superadmin'])
def admin_limpiar_plantillas():
    """Limpiar plantillas duplicadas (ruta temporal)"""
    # Validar CSRF
    if not validate_csrf_token(request.args.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_plantillas'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Eliminar todas las plantillas existentes
        cursor.execute('DELETE FROM plantillas_mensajes')
        
        # 2. Insertar solo las 8 plantillas base
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
                VALUES (NULL, %s, %s, %s, %s, TRUE)
            ''', (nombre, plantilla, descripcion, variables))
        
        conn.commit()
        flash('✅ Plantillas limpiadas correctamente. Solo quedan las 8 plantillas base.', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error limpiando plantillas: {e}")
        flash('❌ Error al limpiar las plantillas', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_plantillas'))

# =============================================================================
# RUTAS DEL PANEL NEGOCIO
# =============================================================================

@app.route('/negocio')
@role_required(['propietario', 'superadmin'])
def negocio_dashboard():
    """Panel principal del negocio - VERSIÓN CORREGIDA"""
    if session.get('usuario_rol') == 'superadmin':
        return redirect(url_for('negocio_estadisticas'))
    
    negocio_id = session.get('negocio_id', 1)
    
    # Formatear fecha para mostrar
    fecha_hoy_str = datetime.now(tz_colombia).strftime('%d/%m/%Y')
    fecha_hoy_db = datetime.now(tz_colombia).strftime('%Y-%m-%d')
    
    # Obtener estadísticas del mes actual
    stats = db.obtener_estadisticas_mensuales(
        negocio_id, 
        mes=datetime.now(tz_colombia).month, 
        año=datetime.now(tz_colombia).year
    )
    
    # Obtener citas de hoy
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute('''
            SELECT 
                c.id, 
                c.cliente_nombre, 
                c.hora, 
                s.nombre as servicio, 
                p.nombre as profesional, 
                c.estado,
                c.cliente_telefono,
                s.precio
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.negocio_id = %s 
            AND c.fecha = %s 
            AND c.estado != 'cancelado'
            ORDER BY c.hora
            LIMIT 10
        ''', (negocio_id, fecha_hoy_db))
        
        citas_hoy = cursor.fetchall()
        
        # Obtener número de profesionales activos
        cursor.execute('''
            SELECT COUNT(*) as total_profesionales 
            FROM profesionales 
            WHERE negocio_id = %s AND activo = true
        ''', (negocio_id,))
        
        profesionales_result = cursor.fetchone()
        total_profesionales = profesionales_result['total_profesionales'] if profesionales_result else 0
        
    except Exception as e:
        print(f"❌ Error obteniendo datos del dashboard: {e}")
        stats = {'resumen': {}}
        citas_hoy = []
        total_profesionales = 0
    finally:
        conn.close()
    
    # Procesar estadísticas para la plantilla
    resumen = stats.get('resumen', {}) if stats else {}
    
    stats_formateadas = {
        'total_turnos': resumen.get('total_citas', 0),
        'turnos_confirmados': resumen.get('citas_confirmadas', 0),
        'ingresos_totales': f"{resumen.get('ingresos_totales', 0):,.0f}".replace(',', '.'),
        'total_profesionales': total_profesionales,
        'nuevos_profesionales': 0,  # Puedes calcular esto si tienes fecha de creación
        'tasa_exito': resumen.get('tasa_exito', 0)
    }
    
    # Procesar citas de hoy para la plantilla
    citas_procesadas = []
    for cita in citas_hoy:
        # Formatear hora (de 'HH:MM:SS' a 'HH:MM')
        hora_str = str(cita['hora'])
        if ':' in hora_str:
            hora_formateada = hora_str[:5]
        else:
            hora_formateada = hora_str
        
        citas_procesadas.append({
            'id': cita['id'],
            'cliente_nombre': cita['cliente_nombre'] or 'Cliente',
            'hora': hora_formateada,
            'servicio': cita['servicio'] or 'Servicio',
            'profesional': cita['profesional'] or 'Profesional',
            'estado': cita['estado'] or 'confirmado',
            'cliente_telefono': cita.get('cliente_telefono', ''),
            'precio': float(cita.get('precio', 0))
        })
    
    return render_template('negocio/dashboard.html',
                         stats=stats_formateadas,
                         citas_hoy=citas_procesadas,
                         fecha_hoy=fecha_hoy_str,
                         mes_actual=datetime.now(tz_colombia).strftime('%B %Y'))

@app.route('/negocio/citas')
@role_required(['propietario', 'superadmin'])
def negocio_citas():
    """Gestión de citas del negocio"""
    negocio_id = session.get('negocio_id', 1)
    fecha = request.args.get('fecha', datetime.now(tz_colombia).strftime('%Y-%m-%d'))
    profesional_id = request.args.get('profesional_id', '')
    
    profesionales = db.obtener_profesionales(negocio_id)
    
    return render_template('negocio/citas.html', 
                         fecha_seleccionada=fecha, 
                         profesional_id=profesional_id,
                         negocio_id=negocio_id,
                         profesionales=profesionales)

@app.route('/negocio/api/citas')
@role_required(['propietario', 'superadmin'])
def negocio_api_citas():
    """API para obtener citas del negocio (para el panel de negocio)"""
    try:
        fecha = request.args.get('fecha', '')
        profesional_id = request.args.get('profesional_id', '')
        estado = request.args.get('estado', '')
        
        if not fecha:
            fecha = datetime.now(tz_colombia).strftime('%Y-%m-%d')
        
        negocio_id = session.get('negocio_id', 1)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = '''
            SELECT c.id, c.cliente_nombre, c.cliente_telefono, c.fecha, c.hora, 
                   s.nombre as servicio_nombre, c.estado, p.nombre as profesional_nombre
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.negocio_id = %s AND c.fecha = %s
        '''
        
        params = [negocio_id, fecha]
        
        if profesional_id and profesional_id != '':
            query += ' AND c.profesional_id = %s'
            params.append(profesional_id)
        
        if estado and estado != '':
            query += ' AND c.estado = %s'
            params.append(estado)
        
        query += ' ORDER BY c.hora'
        
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        
        return jsonify([{
            'id': c['id'],
            'cliente_nombre': c['cliente_nombre'] or 'Cliente',
            'cliente_telefono': c['cliente_telefono'] or 'N/A',
            'fecha': c['fecha'],
            'hora': c['hora'],
            'servicio_nombre': c['servicio_nombre'],
            'estado': c['estado'],
            'profesional_nombre': c['profesional_nombre']
        } for c in citas])
        
    except Exception as e:
        print(f"❌ Error en negocio_api_citas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/negocio/estadisticas')
@role_required(['propietario', 'superadmin'])
def negocio_estadisticas():
    """Estadísticas del negocio"""
    if session.get('usuario_rol') == 'propietario':
        negocio_id = session.get('negocio_id', 1)
        negocios = []
    else:
        negocios = db.obtener_todos_negocios()
        negocio_seleccionado = request.args.get('negocio_id')
        
        if negocio_seleccionado:
            negocio_id = int(negocio_seleccionado)
        else:
            negocio_id = negocios[0]['id'] if negocios else 1
    
    profesionales = db.obtener_profesionales(negocio_id)
    
    negocio_nombre = "Mi Negocio"
    for negocio in negocios:
        if negocio['id'] == negocio_id:
            negocio_nombre = negocio['nombre']
            break
    
    return render_template('negocio/estadisticas.html', 
                         negocio_id=negocio_id,
                         negocios=negocios,
                         negocio_nombre=negocio_nombre,
                         profesionales=profesionales)

@app.route('/negocio/api/estadisticas')
@role_required(['propietario', 'superadmin'])
def negocio_api_estadisticas():
    """API para obtener estadísticas del negocio - VERSIÓN SIMPLIFICADA SIN TENDENCIA"""
    try:
        profesional_id = request.args.get('profesional_id', '')
        mes = request.args.get('mes', datetime.now(tz_colombia).month)
        año = request.args.get('año', datetime.now(tz_colombia).year)
        
        negocio_id = session.get('negocio_id', 1)
        
        try:
            mes = int(mes)
            año = int(año)
            mes_str = f"{mes:02d}"
            año_str = str(año)
            
            if profesional_id:
                profesional_id = int(profesional_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Parámetros inválidos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Estadísticas básicas del negocio
        if db.is_postgresql():
            query_resumen = '''
                SELECT 
                    COUNT(*) as total_citas,
                    SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as citas_confirmadas,
                    SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as citas_completadas,
                    SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as citas_canceladas,
                    COALESCE(SUM(CASE WHEN estado IN ('confirmado', 'completado') THEN s.precio ELSE 0 END), 0) as ingresos_totales
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = %s 
                AND c.fecha LIKE %s
            '''
            fecha_pattern = f"{año_str}-{mes_str}-%"
        else:
            query_resumen = '''
                SELECT 
                    COUNT(*) as total_citas,
                    SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as citas_confirmadas,
                    SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as citas_completadas,
                    SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as citas_canceladas,
                    COALESCE(SUM(CASE WHEN estado IN ('confirmado', 'completado') THEN s.precio ELSE 0 END), 0) as ingresos_totales
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = ? 
                AND substr(c.fecha, 1, 7) = ?
            '''
            fecha_pattern = f"{año_str}-{mes_str}"
        
        params_resumen = [negocio_id, fecha_pattern]
        
        if profesional_id:
            query_resumen += ' AND c.profesional_id = %s' if db.is_postgresql() else ' AND c.profesional_id = ?'
            params_resumen.append(profesional_id)
        
        cursor.execute(query_resumen, params_resumen)
        resumen = cursor.fetchone()
        
        # Función auxiliar para acceder a valores
        def get_value(row, key_or_index, default=0):
            if hasattr(row, 'keys') and isinstance(row, dict):
                value = row.get(key_or_index, default)
                return value if value is not None else default
            elif hasattr(row, '__getitem__'):
                try:
                    value = row[key_or_index]
                    return value if value is not None else default
                except (IndexError, TypeError):
                    return default
            return default
        
        total_citas = get_value(resumen, 'total_citas', 0)
        citas_confirmadas = get_value(resumen, 'citas_confirmadas', 0)
        citas_completadas = get_value(resumen, 'citas_completadas', 0)
        citas_canceladas = get_value(resumen, 'citas_canceladas', 0)
        ingresos_totales = get_value(resumen, 'ingresos_totales', 0)
        
        # 2. Top profesionales
        if db.is_postgresql():
            query_profesionales = '''
                SELECT p.nombre, COUNT(*) as total_citas
                FROM citas c
                JOIN profesionales p ON c.profesional_id = p.id
                WHERE c.negocio_id = %s
                AND c.fecha LIKE %s
                AND c.estado != 'cancelado'
            '''
        else:
            query_profesionales = '''
                SELECT p.nombre, COUNT(*) as total_citas
                FROM citas c
                JOIN profesionales p ON c.profesional_id = p.id
                WHERE c.negocio_id = ?
                AND substr(c.fecha, 1, 7) = ?
                AND c.estado != 'cancelado'
            '''
        
        params_profesionales = [negocio_id, fecha_pattern]
        
        if profesional_id:
            query_profesionales += ' AND c.profesional_id = %s' if db.is_postgresql() else ' AND c.profesional_id = ?'
            params_profesionales.append(profesional_id)
            query_profesionales += ' GROUP BY p.id, p.nombre'
        else:
            query_profesionales += ' GROUP BY p.id, p.nombre ORDER BY total_citas DESC LIMIT 5'
        
        cursor.execute(query_profesionales, params_profesionales)
        profesionales_top_rows = cursor.fetchall()
        
        # Convertir profesionales_top
        profesionales_top = []
        for row in profesionales_top_rows:
            if hasattr(row, 'keys') and isinstance(row, dict):
                profesionales_top.append({
                    'nombre': row.get('nombre', ''),
                    'total_citas': row.get('total_citas', 0)
                })
            elif hasattr(row, '__len__'):
                if len(row) >= 2:
                    profesionales_top.append({
                        'nombre': row[0] if row[0] is not None else '',
                        'total_citas': row[1] if row[1] is not None else 0
                    })
        
        # 3. Top servicios
        if db.is_postgresql():
            query_servicios = '''
                SELECT s.nombre, COUNT(*) as total_citas
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = %s 
                AND c.fecha LIKE %s
                AND c.estado != 'cancelado'
            '''
        else:
            query_servicios = '''
                SELECT s.nombre, COUNT(*) as total_citas
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = ? 
                AND substr(c.fecha, 1, 7) = ?
                AND c.estado != 'cancelado'
            '''
        
        params_servicios = [negocio_id, fecha_pattern]
        
        if profesional_id:
            query_servicios += ' AND c.profesional_id = %s' if db.is_postgresql() else ' AND c.profesional_id = ?'
            params_servicios.append(profesional_id)
        
        query_servicios += ' GROUP BY s.id, s.nombre ORDER BY total_citas DESC LIMIT 5'
        
        cursor.execute(query_servicios, params_servicios)
        servicios_top_rows = cursor.fetchall()
        
        # Convertir servicios_top
        servicios_top = []
        for row in servicios_top_rows:
            if hasattr(row, 'keys') and isinstance(row, dict):
                servicios_top.append({
                    'nombre': row.get('nombre', ''),
                    'total_citas': row.get('total_citas', 0)
                })
            elif hasattr(row, '__len__'):
                if len(row) >= 2:
                    servicios_top.append({
                        'nombre': row[0] if row[0] is not None else '',
                        'total_citas': row[1] if row[1] is not None else 0
                    })
        
        conn.close()
        
        # Calcular tasa de éxito
        citas_exitosas = citas_confirmadas + citas_completadas
        tasa_exito = round((citas_exitosas / total_citas * 100), 2) if total_citas > 0 else 0
        
        # Preparar respuesta final SIN tendencia mensual
        estadisticas = {
            'resumen': {
                'total_citas': int(total_citas),
                'citas_confirmadas': int(citas_confirmadas),
                'citas_completadas': int(citas_completadas),
                'citas_canceladas': int(citas_canceladas),
                'ingresos_totales': float(ingresos_totales),
                'tasa_exito': tasa_exito,
                'filtro_profesional': 'Sí' if profesional_id else 'No'
            },
            'profesionales_top': profesionales_top,
            'servicios_top': servicios_top
            # ❌ REMOVIDO: 'tendencia_mensual' y 'distribucion_dias'
        }
        
        print(f"✅ Estadísticas simplificadas generadas: {estadisticas['resumen']}")
        
        return jsonify(estadisticas)
        
    except Exception as e:
        print(f"❌ Error en negocio_api_estadisticas: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error interno del servidor'}), 500
    
@app.route('/negocio/api/citas/recientes')
@role_required(['propietario', 'superadmin'])
def negocio_api_citas_recientes():
    """API para obtener citas recientes del negocio - VERSIÓN CORREGIDA"""
    try:
        limit = request.args.get('limit', 10)
        profesional_id = request.args.get('profesional_id', '')
        
        negocio_id = session.get('negocio_id', 1)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = '''
            SELECT c.cliente_nombre, s.nombre as servicio_nombre, 
                   p.nombre as profesional_nombre, c.fecha, c.hora, c.estado
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.negocio_id = %s
        '''
        
        params = [negocio_id]
        
        if profesional_id:
            query += ' AND c.profesional_id = %s'
            params.append(int(profesional_id))
        
        query += ' ORDER BY c.fecha DESC, c.hora DESC LIMIT %s'
        params.append(int(limit))
        
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        
        # ✅ CORRECCIÓN: Manejar fecha como string
        citas_procesadas = []
        for c in citas:
            # Formatear fecha (ya es string en formato 'YYYY-MM-DD')
            fecha_str = c['fecha']
            
            # Si fecha es None o vacía
            if not fecha_str:
                fecha_formateada = ''
            else:
                # Intentar convertir a formato más amigable
                try:
                    # Si es un objeto datetime
                    if hasattr(fecha_str, 'strftime'):
                        fecha_formateada = fecha_str.strftime('%d/%m/%Y')
                    # Si es un string en formato 'YYYY-MM-DD'
                    elif '-' in fecha_str:
                        fecha_dt = datetime.strptime(str(fecha_str), '%Y-%m-%d')
                        fecha_formateada = fecha_dt.strftime('%d/%m/%Y')
                    # Si es otro formato
                    else:
                        fecha_formateada = str(fecha_str)[:10]  # Tomar primeros 10 caracteres
                except:
                    fecha_formateada = str(fecha_str)[:10]  # Fallback
            
            citas_procesadas.append({
                'cliente_nombre': c['cliente_nombre'],
                'servicio_nombre': c['servicio_nombre'],
                'profesional_nombre': c['profesional_nombre'],
                'fecha': fecha_formateada,
                'hora': str(c['hora'])[:5] if c['hora'] else '',  # Formatear hora a HH:MM
                'estado': c['estado']
            })
        
        return jsonify(citas_procesadas)
        
    except Exception as e:
        print(f"❌ Error en negocio_api_citas_recientes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error interno del servidor'}), 500


@app.route('/negocio/configuracion', methods=['GET', 'POST'])
@login_required
def negocio_configuracion():
    """Configuración del negocio - HORARIOS + INFORMACIÓN - VERSIÓN CORREGIDA"""
    negocio_id = session['negocio_id']
    
    # Obtener datos actuales del negocio
    negocio_row = db.obtener_negocio_por_id(negocio_id)
    negocio = dict(negocio_row) if negocio_row else {}
    
    # Parsear configuración existente
    config_actual = {}
    if negocio and negocio.get('configuracion'):
        try:
            config_actual = json.loads(negocio['configuracion'])
        except:
            config_actual = {}
    
    # ✅ CORRECCIÓN MEJORADA: Obtener datos REALES de la base de datos
    dias_semana = []
    nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    
    for dia_id in range(1, 8):
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            
            if db.is_postgresql():
                cursor.execute('''
                    SELECT activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
                    FROM configuracion_horarios 
                    WHERE negocio_id = %s AND dia_semana = %s
                ''', (negocio_id, dia_id))
            else:
                cursor.execute('''
                    SELECT activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
                    FROM configuracion_horarios 
                    WHERE negocio_id = ? AND dia_semana = ?
                ''', (negocio_id, dia_id))
            
            resultado = cursor.fetchone()
            conn.close()
            
            if resultado:
                # ✅ CORRECCIÓN: Acceder correctamente a los valores según el tipo de cursor
                if hasattr(resultado, 'keys'):  # Es un diccionario (RealDictCursor)
                    dia_config = {
                        'activo': bool(resultado['activo']),
                        'hora_inicio': resultado['hora_inicio'] or '09:00',
                        'hora_fin': resultado['hora_fin'] or '19:00',
                        'almuerzo_inicio': resultado['almuerzo_inicio'] or '13:00',  # ✅ Valor por defecto
                        'almuerzo_fin': resultado['almuerzo_fin'] or '14:00'         # ✅ Valor por defecto
                    }
                else:  # Es una tupla
                    dia_config = {
                        'activo': bool(resultado[0]),
                        'hora_inicio': resultado[1] or '09:00',
                        'hora_fin': resultado[2] or '19:00',
                        'almuerzo_inicio': resultado[3] or '13:00',  # ✅ Valor por defecto
                        'almuerzo_fin': resultado[4] or '14:00'      # ✅ Valor por defecto
                    }
            else:
                # ✅ CORRECCIÓN: Valores por defecto más realistas
                dia_config = {
                    'activo': dia_id <= 6,  # ✅ Lunes a Sábado activos por defecto
                    'hora_inicio': '09:00',
                    'hora_fin': '19:00',
                    'almuerzo_inicio': '13:00',  # ✅ Valor por defecto
                    'almuerzo_fin': '14:00'      # ✅ Valor por defecto
                }
                
            dias_semana.append({
                'id': dia_id,
                'nombre': nombres_dias[dia_id-1],
                'config': dia_config
            })
            
        except Exception as e:
            print(f"⚠️ Error cargando día {dia_id}: {e}")
            # ✅ CORRECCIÓN: Valores por defecto en caso de error
            dias_semana.append({
                'id': dia_id,
                'nombre': nombres_dias[dia_id-1],
                'config': {
                    'activo': dia_id <= 6,  # ✅ Lunes a Sábado activos por defecto
                    'hora_inicio': '09:00',
                    'hora_fin': '19:00',
                    'almuerzo_inicio': '13:00',  # ✅ Valor por defecto
                    'almuerzo_fin': '14:00'      # ✅ Valor por defecto
                }
            })

    if request.method == 'POST':
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_configuracion'))
        
        try:
            # ===== PROCESAR INFORMACIÓN DEL NEGOCIO =====
            nombre = request.form.get('nombre')
            tipo_negocio = request.form.get('tipo_negocio')
            emoji = request.form.get('emoji')
            saludo_personalizado = request.form.get('saludo_personalizado')
            horario_atencion = request.form.get('horario_atencion')
            direccion = request.form.get('direccion')
            telefono_contacto = request.form.get('telefono_contacto')
            politica_cancelacion = request.form.get('politica_cancelacion')
            
            if not nombre or not tipo_negocio:
                flash('❌ El nombre y tipo de negocio son obligatorios', 'error')
                return redirect(url_for('negocio_configuracion'))
            
            nueva_configuracion = {
                'saludo_personalizado': saludo_personalizado or '¡Hola! Soy tu asistente virtual para agendar citas.',
                'horario_atencion': horario_atencion or 'Lunes a Sábado 9:00 AM - 7:00 PM',
                'direccion': direccion or '',
                'telefono_contacto': telefono_contacto or '',
                'politica_cancelacion': politica_cancelacion or 'Puedes cancelar hasta 2 horas antes'
            }
            
            # ===== PROCESAR HORARIOS =====
            horarios_actualizados = []
            for dia_id in range(1, 8):
                # ✅ CORRECCIÓN: Los checkboxes solo se envían cuando están CHECKED
                activo = f'dia_{dia_id}_activo' in request.form
                hora_inicio = request.form.get(f'dia_{dia_id}_inicio', '09:00')
                hora_fin = request.form.get(f'dia_{dia_id}_fin', '19:00')
                almuerzo_inicio = request.form.get(f'dia_{dia_id}_descanso_inicio', '13:00')  # ✅ Valor por defecto
                almuerzo_fin = request.form.get(f'dia_{dia_id}_descanso_fin', '14:00')        # ✅ Valor por defecto
                
                print(f"🔍 Día {dia_id}: activo={activo}, inicio={hora_inicio}, fin={hora_fin}, almuerzo={almuerzo_inicio}-{almuerzo_fin}")
                
                # ✅ CORRECCIÓN: Validar horarios solo si el día está activo
                if activo:
                    if not hora_inicio or not hora_fin:
                        flash(f'❌ El {nombres_dias[dia_id-1]} necesita horario de inicio y fin', 'error')
                        return redirect(url_for('negocio_configuracion'))
                    
                    if hora_inicio >= hora_fin:
                        flash(f'❌ En {nombres_dias[dia_id-1]}, la hora de inicio debe ser anterior a la hora de fin', 'error')
                        return redirect(url_for('negocio_configuracion'))
                
                horarios_actualizados.append({
                    'dia_id': dia_id,
                    'activo': activo,  # ✅ Esto ahora refleja correctamente el estado
                    'hora_inicio': hora_inicio,
                    'hora_fin': hora_fin,
                    'almuerzo_inicio': almuerzo_inicio,
                    'almuerzo_fin': almuerzo_fin
                })
            
            # ✅ CORRECCIÓN: Verificar que al menos un día esté activo
            dias_activos = sum(1 for h in horarios_actualizados if h['activo'])
            if dias_activos == 0:
                flash('❌ Debe haber al menos un día activo para atención', 'error')
                return redirect(url_for('negocio_configuracion'))
            
            print(f"🔍 DEBUG - Guardando configuración:")
            for h in horarios_actualizados:
                print(f"  Día {h['dia_id']} ({nombres_dias[h['dia_id']-1]}): {h['activo']} - {h['hora_inicio']} a {h['hora_fin']} - Descanso: {h['almuerzo_inicio']} a {h['almuerzo_fin']}")
            
            # Guardar TODO en la base de datos
            if db.actualizar_configuracion_completa(
                negocio_id, nombre, tipo_negocio, emoji, nueva_configuracion, horarios_actualizados
            ):
                flash('✅ Configuración actualizada exitosamente', 'success')
            else:
                flash('❌ Error al actualizar la configuración', 'error')
                
        except Exception as e:
            print(f"❌ Error en configuración: {e}")
            import traceback
            traceback.print_exc()
            flash(f'❌ Error al procesar la configuración: {str(e)}', 'error')
    
    return render_template('negocio/configuracion.html', 
                         negocio=negocio, 
                         dias_semana=dias_semana,
                         config_actual=config_actual)

@app.route('/actualizar-cache/<int:negocio_id>')
def actualizar_cache(negocio_id):
    """Forzar actualización de cache para un negocio"""
    from database import notificar_cambio_horarios
    
    if notificar_cambio_horarios(negocio_id):
        return f"✅ Cache actualizado para negocio {negocio_id}"
    else:
        return f"❌ Error actualizando cache para negocio {negocio_id}"
    
# Ruta para personalizar servicio desde el panel de negocio
@app.route('/negocio/personalizar_servicio/<int:cita_id>', methods=['GET', 'POST'])
def negocio_personalizar_servicio(cita_id):
    """Personalizar servicio para un cliente específico"""
    # Verificar sesión
    if 'usuario_id' not in session or session.get('usuario_rol') != 'propietario':
        return redirect('/login')
    
    negocio_id = session.get('negocio_id')
    usuario_id = session.get('usuario_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Obtener datos de la cita
        cursor.execute('''
            SELECT c.*, cl.nombre as cliente_nombre, cl.telefono, 
                   s.nombre as servicio_nombre, s.duracion, s.precio, s.descripcion,
                   p.nombre as profesional_nombre
            FROM citas c
            LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono AND cl.negocio_id = c.negocio_id
            LEFT JOIN servicios s ON c.servicio_id = s.id
            LEFT JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.id = %s AND c.negocio_id = %s
        ''', (cita_id, negocio_id))
        
        cita = cursor.fetchone()
        
        if not cita:
            flash('Cita no encontrada', 'error')
            return redirect('/negocio/citas')
        
        # Convertir a diccionario si es necesario
        if hasattr(cita, 'keys'):
            cita_dict = dict(cita)
        else:
            cita_dict = {
                'id': cita[0],
                'negocio_id': cita[1],
                'profesional_id': cita[2],
                'cliente_telefono': cita[3],
                'cliente_nombre': cita[4] if cita[4] else 'Cliente',
                'fecha': cita[5],
                'hora': cita[6],
                'servicio_id': cita[7],
                'estado': cita[8],
                'servicio_nombre': cita[12] if len(cita) > 12 else 'Servicio',
                'duracion': cita[13] if len(cita) > 13 else 30,
                'precio': cita[14] if len(cita) > 14 else 0,
                'telefono': cita[10] if len(cita) > 10 else cita[3]
            }
        
        if request.method == 'POST':
            # Procesar la personalización
            nombre_personalizado = request.form.get('nombre_personalizado')
            duracion = request.form.get('duracion')
            precio = request.form.get('precio')
            descripcion = request.form.get('descripcion')
            
            # Servicios adicionales seleccionados
            servicios_adicionales = request.form.getlist('servicios_adicionales')
            incluidos_por_defecto = request.form.getlist('incluidos_por_defecto')
            
            # 1. Primero obtener o crear cliente en tabla clientes
            cursor.execute('''
                SELECT id FROM clientes 
                WHERE telefono = %s AND negocio_id = %s
            ''', (cita_dict['cliente_telefono'], negocio_id))
            
            cliente = cursor.fetchone()
            
            if cliente:
                cliente_id = cliente[0] if isinstance(cliente, (list, tuple)) else cliente['id']
            else:
                # Crear cliente si no existe
                cursor.execute('''
                    INSERT INTO clientes (negocio_id, telefono, nombre, created_at)
                    VALUES (%s, %s, %s, NOW())
                    RETURNING id
                ''', (negocio_id, cita_dict['cliente_telefono'], cita_dict['cliente_nombre']))
                
                cliente_result = cursor.fetchone()
                cliente_id = cliente_result[0] if cliente_result else None
            
            if not cliente_id:
                flash('Error al obtener/crear cliente', 'error')
                return redirect(f'/negocio/personalizar_servicio/{cita_id}')
            
            # 2. Crear o actualizar servicio personalizado
            # Primero verificar si ya existe
            cursor.execute('''
                SELECT id FROM servicios_personalizados 
                WHERE cliente_id = %s AND negocio_id = %s
            ''', (cliente_id, negocio_id))
            
            servicio_personalizado_existente = cursor.fetchone()
            
            if servicio_personalizado_existente:
                # Actualizar existente
                cursor.execute('''
                    UPDATE servicios_personalizados 
                    SET nombre_personalizado = %s,
                        duracion_personalizada = %s,
                        precio_personalizado = %s,
                        descripcion = %s,
                        profesional_id = %s,
                        servicio_base_id = %s,
                        fecha_actualizacion = NOW()
                    WHERE id = %s
                ''', (
                    nombre_personalizado, duracion, precio, descripcion,
                    cita_dict['profesional_id'], cita_dict['servicio_id'],
                    servicio_personalizado_existente[0] if isinstance(servicio_personalizado_existente, tuple) else servicio_personalizado_existente['id']
                ))
                
                servicio_personalizado_id = servicio_personalizado_existente[0] if isinstance(servicio_personalizado_existente, tuple) else servicio_personalizado_existente['id']
            else:
                # Crear nuevo
                cursor.execute('''
                    INSERT INTO servicios_personalizados 
                    (cliente_id, negocio_id, profesional_id, servicio_base_id,
                     nombre_personalizado, duracion_personalizada, precio_personalizado, descripcion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    cliente_id, negocio_id, cita_dict['profesional_id'], 
                    cita_dict['servicio_id'], nombre_personalizado, 
                    duracion, precio, descripcion
                ))
                
                servicio_personalizado_result = cursor.fetchone()
                servicio_personalizado_id = servicio_personalizado_result[0] if servicio_personalizado_result else None
            
            # 3. Limpiar servicios adicionales anteriores y agregar nuevos
            if servicio_personalizado_id:
                cursor.execute('''
                    DELETE FROM servicios_adicionales_cliente 
                    WHERE servicio_personalizado_id = %s
                ''', (servicio_personalizado_id,))
                
                # Agregar nuevos servicios adicionales
                for servicio_id in servicios_adicionales:
                    try:
                        servicio_id_int = int(servicio_id)
                        incluido = servicio_id in incluidos_por_defecto
                        
                        cursor.execute('''
                            INSERT INTO servicios_adicionales_cliente 
                            (servicio_personalizado_id, servicio_id, incluido_por_defecto)
                            VALUES (%s, %s, %s)
                        ''', (servicio_personalizado_id, servicio_id_int, incluido))
                    except ValueError:
                        continue
            
            conn.commit()
            flash('✅ Servicio personalizado guardado exitosamente', 'success')
            return redirect('/negocio/citas')
        
        # Obtener servicios disponibles del negocio (excluyendo el servicio actual)
        cursor.execute('''
            SELECT * FROM servicios 
            WHERE negocio_id = %s AND activo = true 
            AND id != %s
            ORDER BY nombre
        ''', (negocio_id, cita_dict.get('servicio_id', 0)))
        
        servicios = cursor.fetchall()
        
        # Verificar si ya existe personalización previa
        # Primero obtener cliente_id
        cursor.execute('''
            SELECT id FROM clientes 
            WHERE telefono = %s AND negocio_id = %s
        ''', (cita_dict['cliente_telefono'], negocio_id))
        
        cliente = cursor.fetchone()
        personalizacion_existente = None
        
        if cliente:
            cliente_id = cliente[0] if isinstance(cliente, tuple) else cliente['id']
            
            cursor.execute('''
                SELECT sp.* 
                FROM servicios_personalizados sp
                WHERE sp.cliente_id = %s AND sp.negocio_id = %s
            ''', (cliente_id, negocio_id))
            
            personalizacion = cursor.fetchone()
            
            if personalizacion:
                # Obtener servicios adicionales
                cursor.execute('''
                    SELECT sac.servicio_id, sac.incluido_por_defecto
                    FROM servicios_adicionales_cliente sac
                    WHERE sac.servicio_personalizado_id = %s
                ''', (personalizacion[0] if isinstance(personalizacion, tuple) else personalizacion['id'],))
                
                servicios_adicionales = cursor.fetchall()
                
                personalizacion_existente = {
                    'id': personalizacion[0] if isinstance(personalizacion, tuple) else personalizacion['id'],
                    'nombre_personalizado': personalizacion[4] if len(personalizacion) > 4 else '',
                    'duracion_personalizada': personalizacion[5] if len(personalizacion) > 5 else 0,
                    'precio_personalizado': personalizacion[6] if len(personalizacion) > 6 else 0,
                    'descripcion': personalizacion[7] if len(personalizacion) > 7 else '',
                    'servicios_adicionales_ids': [sa[0] for sa in servicios_adicionales] if servicios_adicionales else [],
                    'incluidos_default': [sa[0] for sa in servicios_adicionales if sa[1]] if servicios_adicionales else []
                }
        
        conn.close()
        
        return render_template('profesional/personalizar_servicio.html',
                             cita=cita_dict,
                             servicios=servicios,
                             personalizacion=personalizacion_existente)
        
    except Exception as e:
        print(f"❌ Error en personalizar_servicio: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al procesar la solicitud', 'error')
        return redirect('/negocio/citas')

# =============================================================================
# RUTAS PARA GESTIÓN DE SERVICIOS Y PLANTILLAS
# =============================================================================

@app.route('/negocio/servicios')
@role_required(['propietario', 'superadmin'])
def negocio_servicios():
    """Gestión de servicios del negocio"""
    negocio_id = session.get('negocio_id', 1)
    servicios = db.obtener_servicios(negocio_id)
    
    return render_template('negocio/servicios.html', 
                         servicios=servicios,
                         negocio_id=negocio_id)

@app.route('/negocio/servicios/nuevo', methods=['GET', 'POST'])
@role_required(['propietario', 'superadmin'])
def negocio_nuevo_servicio():
    """Crear nuevo servicio para el negocio"""
    if session['usuario_rol'] == 'propietario':
        negocio_id = session['negocio_id']
    else:
        negocio_id = request.args.get('negocio_id', session.get('negocio_id', 1))
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_nuevo_servicio'))
        
        nombre = request.form['nombre']
        duracion = int(request.form['duracion'])
        precio = float(request.form['precio'])
        descripcion = request.form.get('descripcion', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO servicios (negocio_id, nombre, duracion, precio, descripcion)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (negocio_id, nombre, duracion, precio, descripcion))
            
            conn.commit()
            flash('✅ Servicio creado exitosamente', 'success')
            return redirect(url_for('negocio_servicios'))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error creando servicio: {e}")
            flash('❌ Error al crear el servicio', 'error')
        finally:
            conn.close()
    
    return render_template('negocio/nuevo_servicio.html', negocio_id=negocio_id)

@app.route('/negocio/servicios/<int:servicio_id>/editar', methods=['GET', 'POST'])
@login_required
def negocio_editar_servicio(servicio_id):
    """Editar servicio del negocio - VERSIÓN CORREGIDA"""
    servicio = db.obtener_servicio_por_id(servicio_id, session['negocio_id'])
    if not servicio:
        flash('Servicio no encontrado', 'error')
        return redirect(url_for('negocio_servicios'))
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_servicios'))
        
        nombre = request.form['nombre']
        duracion = int(request.form['duracion'])
        precio = float(request.form['precio'])
        descripcion = request.form.get('descripcion', '')
        # ✅ CORRECCIÓN: Por defecto activo si no se especifica
        activo = request.form.get('activo', 'off') == 'on'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE servicios 
                SET nombre = %s, duracion = %s, precio = %s, descripcion = %s, activo = %s
                WHERE id = %s AND negocio_id = %s
            ''', (nombre, duracion, precio, descripcion, activo, servicio_id, session['negocio_id']))
            
            conn.commit()
            flash('✅ Servicio actualizado exitosamente', 'success')
            return redirect(url_for('negocio_servicios'))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error actualizando servicio: {e}")
            flash('❌ Error al actualizar el servicio', 'error')
        finally:
            conn.close()
    
    # Convertir a diccionario si es necesario
    if hasattr(servicio, '_asdict'):
        servicio_dict = servicio._asdict()
    elif isinstance(servicio, dict):
        servicio_dict = servicio
    else:
        servicio_dict = {
            'id': servicio.id,
            'nombre': servicio.nombre,
            'precio': servicio.precio,
            'duracion': servicio.duracion,
            'descripcion': servicio.descripcion,
            'activo': servicio.activo
        }
    
    return render_template('negocio/editar_servicio.html', 
                         servicio=servicio_dict,
                         negocio_id=session['negocio_id'])

@app.route('/negocio/servicios/<int:servicio_id>/eliminar', methods=['POST'])
@role_required(['propietario', 'superadmin'])
def negocio_eliminar_servicio(servicio_id):
    """Eliminar servicio"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('negocio_servicios'))
    
    if session['usuario_rol'] == 'propietario':
        negocio_id = session['negocio_id']
    else:
        negocio_id = request.args.get('negocio_id', session.get('negocio_id', 1))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar que el servicio pertenece al negocio
        cursor.execute('SELECT id FROM servicios WHERE id = %s AND negocio_id = %s', 
                      (servicio_id, negocio_id))
        
        if not cursor.fetchone():
            flash('❌ Servicio no encontrado', 'error')
            return redirect(url_for('negocio_servicios'))
        
        # Eliminar relaciones con profesionales primero
        cursor.execute('DELETE FROM profesional_servicios WHERE servicio_id = %s', (servicio_id,))
        
        # Eliminar servicio
        cursor.execute('DELETE FROM servicios WHERE id = %s', (servicio_id,))
        
        conn.commit()
        flash('✅ Servicio eliminado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error eliminando servicio: {e}")
        flash('❌ Error al eliminar el servicio', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('negocio_servicios'))

@app.route('/negocio/plantillas')
@login_required
def negocio_plantillas():
    """Página principal de plantillas del negocio"""
    negocio_id = session['negocio_id']
    
    # ✅ USAR LA FUNCIÓN CORREGIDA
    plantillas = db.obtener_plantillas_negocio(negocio_id)
    
    print(f"🔍 PLANTILLAS PRINCIPAL - plantillas recibidas: {len(plantillas)}")
    
    # Debug: mostrar información de cada plantilla
    for i, plantilla in enumerate(plantillas):
        print(f"🔍 Plantilla {i}: {plantilla.get('nombre')} - tipo: {type(plantilla)}")
    
    return render_template('negocio/plantillas.html', plantillas=plantillas)

@app.route('/negocio/plantillas/<nombre_plantilla>/editar', methods=['GET', 'POST'])
@login_required
def negocio_editar_plantilla(nombre_plantilla):
    """Editar plantilla del negocio - VERSIÓN CORREGIDA"""
    negocio_id = session['negocio_id']
    
    print(f"🔍 [APP] EDITAR PLANTILLA: negocio_id={negocio_id}, nombre={nombre_plantilla}")
    
    # Obtener la plantilla actual
    plantilla_actual = db.obtener_plantilla(negocio_id, nombre_plantilla)
    
    if not plantilla_actual:
        print(f"❌ [APP] Plantilla '{nombre_plantilla}' no encontrada")
        flash('❌ Plantilla no encontrada', 'error')
        return redirect(url_for('negocio_plantillas'))
    
    print(f"✅ [APP] Plantilla obtenida: {plantilla_actual.get('nombre')}")
    print(f"✅ [APP] Es personalizada: {plantilla_actual.get('es_personalizada', False)}")
    
    if request.method == 'POST':
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_plantillas'))
        
        nueva_plantilla = request.form.get('plantilla')
        descripcion = request.form.get('descripcion', '')
        
        print(f"🔍 [APP] Guardando plantilla '{nombre_plantilla}'")
        print(f"📝 Contenido recibido (primeros 100 chars): {nueva_plantilla[:100]}")
        
        # Guardar plantilla personalizada
        if db.guardar_plantilla_personalizada(negocio_id, nombre_plantilla, nueva_plantilla, descripcion):
            flash('✅ Plantilla actualizada exitosamente', 'success')
            return redirect(url_for('negocio_plantillas'))
        else:
            flash('❌ Error al actualizar la plantilla', 'error')
            return redirect(url_for('negocio_editar_plantilla', nombre_plantilla=nombre_plantilla))
    
    # Para GET, preparar datos para la template
    return render_template('negocio/editar_plantilla.html',
                         plantilla=plantilla_actual,
                         nombre_plantilla=nombre_plantilla,
                         es_personalizada=plantilla_actual.get('es_personalizada', False))

def guardar_plantilla_personalizada(negocio_id, nombre_plantilla, contenido, descripcion=''):
    """Guardar o actualizar plantilla personalizada"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar si ya existe una personalizada
        cursor.execute('''
            SELECT id FROM plantillas_mensajes 
            WHERE negocio_id = %s AND nombre = %s AND es_base = FALSE
        ''', (negocio_id, nombre_plantilla))
        
        existe = cursor.fetchone()
        
        if existe:
            # Actualizar existente
            cursor.execute('''
                UPDATE plantillas_mensajes 
                SET plantilla = %s, descripcion = %s
                WHERE negocio_id = %s AND nombre = %s AND es_base = FALSE
            ''', (contenido, descripcion, negocio_id, nombre_plantilla))
        else:
            # Crear nueva personalizada
            cursor.execute('''
                INSERT INTO plantillas_mensajes 
                (negocio_id, nombre, plantilla, descripcion, es_base)
                VALUES (%s, %s, %s, %s, FALSE)
                RETURNING id
            ''', (negocio_id, nombre_plantilla, contenido, descripcion))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error guardando plantilla: {e}")
        return False

# =============================================================================
# RUTAS PARA GESTIÓN DE PROFESIONALES
# =============================================================================

@app.route('/negocio/profesionales')
@login_required
def negocio_profesionales():
    """Gestión de profesionales del negocio"""
    if session['usuario_rol'] != 'propietario':
        return redirect(url_for('login'))
    
    # Obtener profesionales del negocio actual
    profesionales = obtener_profesionales_por_negocio(session['negocio_id'])
    return render_template('negocio/profesionales.html', profesionales=profesionales)


@app.route('/negocio/profesionales/nuevo', methods=['GET', 'POST'])
@login_required
def negocio_nuevo_profesional():
    """Crear nuevo profesional con usuario - VERSIÓN CORREGIDA"""
    if session['usuario_rol'] != 'propietario':
        flash('No tienes permisos para acceder a esta página', 'error')
        return redirect(url_for('login'))
    
    negocio_id = session.get('negocio_id', 1)
    servicios = obtener_servicios_por_negocio(negocio_id)
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_nuevo_profesional'))
        
        print(f"🔍 DEBUG FORM DATA:")
        for key, value in request.form.items():
            print(f"  {key}: {value}")
        
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        especialidad = request.form.get('especialidad', '').strip()
        servicios_seleccionados = request.form.getlist('servicios')
        activo = 'activo' in request.form
        
        # Validaciones
        if not nombre:
            flash('El nombre es requerido', 'error')
            return redirect(url_for('negocio_nuevo_profesional'))
        
        if not email:
            flash('El email es requerido', 'error')
            return redirect(url_for('negocio_nuevo_profesional'))
        
        if not password or len(password) < 6:
            flash('La contraseña es requerida y debe tener al menos 6 caracteres', 'error')
            return redirect(url_for('negocio_nuevo_profesional'))
        
        print(f"🔍 DEBUG - Datos procesados:")
        print(f"  - negocio_id: {negocio_id}")
        print(f"  - nombre: {nombre}")
        print(f"  - email: {email}")
        print(f"  - especialidad: {especialidad}")
        print(f"  - servicios_seleccionados: {servicios_seleccionados}")
        print(f"  - activo: {activo}")
        
        # ✅ USAR LA FUNCIÓN NUEVA para crear profesional con usuario
        resultado = db.crear_profesional_con_usuario(
            negocio_id=negocio_id,
            nombre=nombre,
            email=email,
            password=password,
            especialidad=especialidad,
            servicios_ids=servicios_seleccionados
        )
        
        if resultado:
            flash('✅ Profesional creado exitosamente con acceso al sistema', 'success')
            return redirect(url_for('negocio_profesionales'))
        else:
            flash('❌ Error al crear el profesional. El email puede estar en uso.', 'error')
    
    return render_template('negocio/nuevo_profesional.html', 
                         servicios=servicios,
                         negocio_id=negocio_id)

@app.route('/negocio/profesionales/editar/<int:profesional_id>', methods=['GET', 'POST'])
@login_required
def negocio_editar_profesional(profesional_id):
    """Editar profesional existente"""
    if session['usuario_rol'] != 'propietario':
        return redirect(url_for('login'))
    
    negocio_id = session.get('negocio_id', 1)
    profesional = obtener_profesional_por_id(profesional_id, negocio_id)
    servicios = obtener_servicios_por_negocio(negocio_id)
    
    if not profesional:
        flash('Profesional no encontrado', 'error')
        return redirect(url_for('negocio_profesionales'))
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_editar_profesional', profesional_id=profesional_id))
        
        nombre = request.form['nombre']
        especialidad = request.form.get('especialidad', '')
        servicios_seleccionados = request.form.getlist('servicios')
        activo = 'activo' in request.form
        
        # Actualizar profesional
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Actualizar datos básicos
            cursor.execute('''
                UPDATE profesionales 
                SET nombre = %s, especialidad = %s, activo = %s
                WHERE id = %s AND negocio_id = %s
            ''', (nombre, especialidad, activo, profesional_id, negocio_id))
            
            # Eliminar servicios anteriores
            cursor.execute('DELETE FROM profesional_servicios WHERE profesional_id = %s', (profesional_id,))
            
            # Agregar nuevos servicios
            for servicio_id in servicios_seleccionados:
                cursor.execute('''
                    INSERT INTO profesional_servicios (profesional_id, servicio_id)
                    VALUES (%s, %s)
                ''', (profesional_id, servicio_id))
            
            conn.commit()
            flash('✅ Profesional actualizado exitosamente', 'success')
            return redirect(url_for('negocio_profesionales'))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error actualizando profesional: {e}")
            flash('❌ Error al actualizar el profesional', 'error')
        finally:
            conn.close()
    
    return render_template('negocio/editar_profesional.html', 
                         profesional=profesional, 
                         servicios=servicios)

@app.route('/negocio/profesionales/eliminar/<int:profesional_id>', methods=['POST'])
@login_required
def negocio_eliminar_profesional(profesional_id):
    """Eliminar profesional"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('negocio_profesionales'))
    
    if session['usuario_rol'] != 'propietario':
        return redirect(url_for('login'))
    
    if eliminar_profesional(profesional_id, session['negocio_id']):
        flash('Profesional eliminado exitosamente', 'success')
    else:
        flash('Error al eliminar el profesional', 'error')
    
    return redirect(url_for('negocio_profesionales'))

# =============================================================================
# RUTAS DEL PANEL PROFESIONAL
# =============================================================================

@app.route('/profesional')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_dashboard():
    """Dashboard móvil para profesionales"""
    try:
        negocio_id = session.get('negocio_id', 1)
        fecha = request.args.get('fecha', datetime.now(tz_colombia).strftime('%Y-%m-%d'))
        
        profesional_id = session.get('profesional_id')
        
        print(f"🔍 DEBUG - profesional_dashboard: negocio_id={negocio_id}, fecha={fecha}, profesional_id={profesional_id}")
        
        if not profesional_id:
            usuario_id = session.get('usuario_id')
            if usuario_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM profesionales WHERE usuario_id = %s AND negocio_id = %s', 
                             (usuario_id, negocio_id))
                profesional = cursor.fetchone()
                conn.close()
                
                if profesional:
                    profesional_id = profesional[0]
                    session['profesional_id'] = profesional_id
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return render_template('profesional/dashboard.html', 
                                citas=[], 
                                total_citas=0, 
                                ganancia_estimada=0,
                                profesional_id=None,
                                fecha=fecha)

        # Obtener citas del profesional
        citas = db.obtener_citas_para_profesional(negocio_id, profesional_id, fecha)
        
        total_citas = len(citas)
        ganancia_estimada = sum(cita.get('precio', 0) for cita in citas if cita.get('estado') != 'cancelado')
        
        usuario_nombre = session.get('usuario_nombre', 'Profesional')
        
        return render_template('profesional/dashboard.html',
                            citas=citas,
                            total_citas=total_citas,
                            ganancia_estimada=ganancia_estimada,
                            profesional_nombre=usuario_nombre,
                            fecha=fecha,
                            profesional_id=profesional_id)
                            
    except Exception as e:
        print(f"❌ Error en profesional_dashboard: {e}")
        import traceback
        traceback.print_exc()
        return render_template('profesional/dashboard.html', 
                            citas=[], 
                            total_citas=0, 
                            ganancia_estimada=0,
                            profesional_id=None,
                            fecha=datetime.now(tz_colombia).strftime('%Y-%m-%d'))
    
@app.route('/profesional/estadisticas')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_estadisticas():
    """Estadísticas del profesional - CON FILTRO DE MES/AÑO"""
    try:
        negocio_id = session.get('negocio_id', 1)
        profesional_id = request.args.get('profesional_id', session.get('profesional_id'))
        
        # Obtener mes y año de los parámetros o usar actual
        mes = request.args.get('mes', datetime.now(tz_colombia).month, type=int)
        año = request.args.get('año', datetime.now(tz_colombia).year, type=int)
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        # Obtener información del profesional
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT nombre, especialidad FROM profesionales WHERE id = %s', (profesional_id,))
        profesional_info = cursor.fetchone()
        conn.close()
        
        if not profesional_info:
            flash('Profesional no encontrado', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        # Obtener estadísticas del profesional (con filtro mes/año)
        estadisticas = obtener_estadisticas_profesional(negocio_id, profesional_id, mes, año)
        
        return render_template('profesional/estadisticas.html',
                            estadisticas=estadisticas,
                            profesional_id=profesional_id,
                            profesional_nombre=profesional_info['nombre'],
                            profesional_especialidad=profesional_info['especialidad'],
                            mes_seleccionado=mes,
                            año_seleccionado=año)
        
    except Exception as e:
        print(f"❌ Error en profesional_estadisticas: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al cargar las estadísticas', 'error')
        return redirect(url_for('profesional_dashboard'))

def obtener_estadisticas_profesional(negocio_id, profesional_id, mes, año):
    """Obtener estadísticas de un profesional para un mes y año específicos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Construir fecha pattern para LIKE
        mes_str = f"{mes:02d}"
        fecha_pattern = f"{año}-{mes_str}-%"
        
        # 1. Estadísticas básicas del mes
        if db.is_postgresql():
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_citas,
                    SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as citas_confirmadas,
                    SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as citas_completadas,
                    SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as citas_canceladas,
                    COALESCE(SUM(CASE WHEN estado IN ('confirmado', 'completado') THEN s.precio ELSE 0 END), 0) as ingresos_totales
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = %s 
                AND c.profesional_id = %s
                AND c.fecha LIKE %s
            ''', (negocio_id, profesional_id, fecha_pattern))
        else:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_citas,
                    SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as citas_confirmadas,
                    SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as citas_completadas,
                    SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as citas_canceladas,
                    COALESCE(SUM(CASE WHEN estado IN ('confirmado', 'completado') THEN s.precio ELSE 0 END), 0) as ingresos_totales
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = ? 
                AND c.profesional_id = ?
                AND substr(c.fecha, 1, 7) = ?
            ''', (negocio_id, profesional_id, f"{año}-{mes_str}"))
        
        stats = cursor.fetchone()
        
        # 2. Servicios más populares del mes
        if db.is_postgresql():
            cursor.execute('''
                SELECT s.nombre, COUNT(*) as cantidad
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = %s 
                AND c.profesional_id = %s
                AND c.fecha LIKE %s
                AND c.estado != 'cancelado'
                GROUP BY s.id, s.nombre
                ORDER BY cantidad DESC
                LIMIT 5
            ''', (negocio_id, profesional_id, fecha_pattern))
        else:
            cursor.execute('''
                SELECT s.nombre, COUNT(*) as cantidad
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = ? 
                AND c.profesional_id = ?
                AND substr(c.fecha, 1, 7) = ?
                AND c.estado != 'cancelado'
                GROUP BY s.id, s.nombre
                ORDER BY cantidad DESC
                LIMIT 5
            ''', (negocio_id, profesional_id, f"{año}-{mes_str}"))
        
        servicios_populares_rows = cursor.fetchall()
        
        conn.close()
        
        # Función para acceder a valores
        def get_value(row, key, default=0):
            if row and key in row:
                return row[key] or default
            return default
        
        # Procesar estadísticas
        total_citas = get_value(stats, 'total_citas', 0)
        citas_confirmadas = get_value(stats, 'citas_confirmadas', 0)
        citas_completadas = get_value(stats, 'citas_completadas', 0)
        citas_canceladas = get_value(stats, 'citas_canceladas', 0)
        ingresos_totales = get_value(stats, 'ingresos_totales', 0)
        
        # Procesar servicios populares
        servicios_populares = []
        for row in servicios_populares_rows:
            if hasattr(row, 'keys'):
                servicios_populares.append({
                    'nombre': row.get('nombre', ''),
                    'cantidad': row.get('cantidad', 0)
                })
            elif hasattr(row, '__len__') and len(row) >= 2:
                servicios_populares.append({
                    'nombre': row[0] if row[0] is not None else '',
                    'cantidad': row[1] if row[1] is not None else 0
                })
        
        # Calcular tasa de éxito
        citas_exitosas = citas_completadas + citas_confirmadas
        tasa_exito = round((citas_exitosas / total_citas * 100), 2) if total_citas > 0 else 0
        
        return {
            'total_citas': int(total_citas),
            'confirmadas': int(citas_confirmadas),
            'completadas': int(citas_completadas),
            'canceladas': int(citas_canceladas),
            'ingresos_totales': float(ingresos_totales),
            'servicios_populares': servicios_populares,
            'tasa_exito': tasa_exito,
            'mes': mes,
            'año': año
        }
        
    except Exception as e:
        print(f"❌ Error obteniendo estadísticas del profesional: {e}")
        # Retornar estadísticas vacías en caso de error
        return {
            'total_citas': 0,
            'confirmadas': 0,
            'completadas': 0,
            'canceladas': 0,
            'ingresos_totales': 0,
            'servicios_populares': [],
            'tasa_exito': 0,
            'mes': mes,
            'año': año
        }
    
@app.route('/profesional/todas-citas')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_todas_citas():
    """Todas las citas del profesional (no solo las de hoy)"""
    try:
        negocio_id = session.get('negocio_id', 1)
        profesional_id = session.get('profesional_id')
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Obtener todas las citas del profesional
        cursor.execute('''
            SELECT c.*, s.nombre as servicio_nombre, s.precio
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.profesional_id = %s AND c.negocio_id = %s
            ORDER BY c.fecha DESC, c.hora DESC
        ''', (profesional_id, negocio_id))
        
        citas = cursor.fetchall()
        conn.close()
        
        return render_template('profesional/todas_citas.html',
                            citas=citas,
                            profesional_id=profesional_id)
        
    except Exception as e:
        print(f"❌ Error en profesional_todas_citas: {e}")
        flash('Error al cargar las citas', 'error')
        return redirect(url_for('profesional_dashboard'))
    
@app.route('/profesional/agendar')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_agendar():
    """Página para que el profesional agende citas"""
    try:
        negocio_id = session.get('negocio_id', 1)
        profesional_id = session.get('profesional_id')
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        # Obtener servicios del negocio
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT id, nombre, duracion, precio 
            FROM servicios 
            WHERE negocio_id = %s AND activo = TRUE
            ORDER BY nombre
        ''', (negocio_id,))
        
        servicios = cursor.fetchall()
        
        conn.close()
        
        # Fecha de hoy para el mínimo del datepicker
        fecha_hoy = datetime.now(tz_colombia).strftime('%Y-%m-%d')
        
        return render_template('profesional/agendar_cita.html',
                            servicios=servicios,
                            profesional_id=profesional_id,
                            fecha_hoy=fecha_hoy)
        
    except Exception as e:
        print(f"❌ Error en profesional_agendar: {e}")
        flash('Error al cargar la página de agendamiento', 'error')
        return redirect(url_for('profesional_dashboard'))
    
@app.route('/profesional/crear-cita', methods=['POST'])
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_crear_cita():
    """Crear cita desde el panel del profesional - VERSIÓN COMPLETA CORREGIDA"""
    try:
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('profesional_agendar'))
        
        cliente_nombre = request.form.get('cliente_nombre')
        cliente_telefono = request.form.get('cliente_telefono')
        servicio_id = request.form.get('servicio_id')
        fecha = request.form.get('fecha')
        hora = request.form.get('hora')
        
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        
        print(f"🔍 DEBUG crear-cita: cliente_nombre={cliente_nombre}, telefono={cliente_telefono}, servicio={servicio_id}, fecha={fecha}, hora={hora}, profesional={profesional_id}, negocio={negocio_id}")
        
        if not all([cliente_nombre, cliente_telefono, servicio_id, fecha, hora, profesional_id, negocio_id]):
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('profesional_agendar'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ✅ 1. PRIMERO: Crear o actualizar cliente en tabla `clientes`
        print(f"🔍 [CLIENTE] Verificando/creando cliente con teléfono: {cliente_telefono}")
        
        try:
            # Verificar si el cliente ya existe
            cursor.execute('''
                SELECT id, nombre FROM clientes 
                WHERE telefono = %s AND negocio_id = %s
                LIMIT 1
            ''', (cliente_telefono, negocio_id))
            
            cliente_existente = cursor.fetchone()
            
            if cliente_existente:
                # ✅ Cliente existe - actualizar si es necesario
                if hasattr(cliente_existente, 'keys'):  # Diccionario
                    cliente_id = cliente_existente['id']
                    nombre_actual = cliente_existente['nombre']
                else:  # Tupla
                    cliente_id = cliente_existente[0]
                    nombre_actual = cliente_existente[1]
                
                print(f"✅ [CLIENTE] Cliente existente encontrado: ID={cliente_id}, Nombre actual: '{nombre_actual}'")
                
                # Actualizar nombre si es diferente
                if nombre_actual != cliente_nombre:
                    cursor.execute('''
                        UPDATE clientes 
                        SET nombre = %s, updated_at = NOW()
                        WHERE id = %s
                    ''', (cliente_nombre, cliente_id))
                    print(f"✅ [CLIENTE] Nombre actualizado: '{nombre_actual}' -> '{cliente_nombre}'")
                else:
                    print(f"✅ [CLIENTE] Manteniendo nombre existente: '{nombre_actual}'")
            else:
                # ✅ Cliente nuevo - crear registro
                cursor.execute('''
                    INSERT INTO clientes (
                        negocio_id, 
                        telefono, 
                        nombre, 
                        created_at, 
                        updated_at
                    ) VALUES (%s, %s, %s, NOW(), NOW())
                    RETURNING id
                ''', (negocio_id, cliente_telefono, cliente_nombre))
                
                cliente_result = cursor.fetchone()
                if hasattr(cliente_result, 'keys'):
                    cliente_id = cliente_result['id']
                else:
                    cliente_id = cliente_result[0]
                
                print(f"✅ [CLIENTE] Nuevo cliente creado: ID={cliente_id}, Nombre='{cliente_nombre}'")
                
        except Exception as e:
            print(f"⚠️ [CLIENTE] Error procesando cliente: {e}")
            # Continuamos aunque falle, la cita se puede crear igual
        
        # ✅ 2. Verificar disponibilidad
        cursor.execute('''
            SELECT id FROM citas 
            WHERE profesional_id = %s AND fecha = %s AND hora = %s AND estado != 'cancelada'
        ''', (profesional_id, fecha, hora))
        
        cita_existente = cursor.fetchone()
        if cita_existente:
            flash('❌ Ya existe una cita en ese horario', 'error')
            conn.close()
            return redirect(url_for('profesional_agendar'))
        
        # ✅ 3. Crear la cita
        cursor.execute('''
            INSERT INTO citas (
                negocio_id, 
                profesional_id, 
                cliente_telefono, 
                cliente_nombre, 
                fecha, 
                hora, 
                servicio_id, 
                estado, 
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmada', NOW())
            RETURNING id
        ''', (
            negocio_id, 
            profesional_id, 
            cliente_telefono, 
            cliente_nombre, 
            fecha, 
            hora, 
            servicio_id
        ))
        
        result = cursor.fetchone()
        if result:
            if hasattr(result, 'keys'):
                cita_id = result['id']
            else:
                cita_id = result[0]
            
            print(f"✅ [CITA] Cita creada exitosamente. ID: {cita_id}")
            
            # ✅ 4. OPCIONAL: Notificación (puedes activarlo después)
            try:
                # Aquí podrías enviar notificación al cliente
                # enviar_notificacion_cita(cita_id, cliente_telefono, cliente_nombre, fecha, hora)
                pass
            except Exception as e:
                print(f"⚠️ [NOTIFICACIÓN] Error enviando notificación: {e}")
        
        else:
            flash('❌ Error al crear la cita en la base de datos', 'error')
            conn.rollback()
            conn.close()
            return redirect(url_for('profesional_agendar'))
        
        conn.commit()
        try:
            mensaje_push = f"{cliente_nombre} - {fecha} {hora}"
            enviar_notificacion_push_profesional(
                profesional_id=profesional_id,
                titulo="📅 Nueva Cita Agendada",
                mensaje=mensaje_push,
                cita_id=cita_id
            )
            print("✅ Notificación push enviada")
        except Exception as push_error:
            print(f"⚠️ Error enviando push: {push_error}")

        conn.close()
        
        flash('✅ Cita agendada exitosamente', 'success')
        return redirect(url_for('profesional_dashboard'))
        
    except Exception as e:
        print(f"❌ Error creando cita: {e}")
        import traceback
        traceback.print_exc()
        flash('❌ Error al agendar la cita', 'error')
        return redirect(url_for('profesional_agendar'))

@app.route('/profesional/completar-cita/<int:cita_id>', methods=['POST'])
@role_required(['profesional', 'propietario', 'superadmin'])
def completar_cita(cita_id):
    """Marcar cita como completada desde el panel del profesional"""
    conn = None
    try:
        print(f"🔍 [COMPLETAR_CITA] Iniciando para cita #{cita_id}")
        
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            print("❌ [COMPLETAR_CITA] CSRF inválido")
            return redirect(url_for('profesional_dashboard'))
        
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        
        print(f"🔍 [COMPLETAR_CITA] profesional_id={profesional_id}, negocio_id={negocio_id}")
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            print("❌ [COMPLETAR_CITA] Sin profesional_id")
            return redirect(url_for('profesional_dashboard'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Primero obtener info de la cita actual
        cursor.execute('''
            SELECT id, cliente_nombre, estado, servicio_id 
            FROM citas 
            WHERE id = %s AND profesional_id = %s AND negocio_id = %s
        ''', (cita_id, profesional_id, negocio_id))
        
        cita_actual = cursor.fetchone()
        
        if not cita_actual:
            flash('❌ Cita no encontrada', 'error')
            print(f"❌ [COMPLETAR_CITA] Cita {cita_id} no encontrada para profesional {profesional_id}")
            conn.close()
            return redirect(url_for('profesional_dashboard'))
        
        print(f"✅ [COMPLETAR_CITA] Cita encontrada: {cita_actual}")
        print(f"   Estado actual: {cita_actual['estado']}")
        
        # 2. Actualizar estado a 'completado' (MASCULINO, no 'completada')
        cursor.execute('''
            UPDATE citas 
            SET estado = 'completado', 
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, estado, cliente_nombre
        ''', (cita_id,))
        
        resultado_update = cursor.fetchone()
        print(f"✅ [COMPLETAR_CITA] Resultado UPDATE: {resultado_update}")
        
        if resultado_update:
            # 3. Opcional: Registrar en historial
            try:
                cursor.execute('''
                    INSERT INTO historial_citas 
                    (cita_id, negocio_id, profesional_id, accion, detalles)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (
                    cita_id,
                    negocio_id,
                    profesional_id,
                    'completada',
                    f'Cita marcada como completada por profesional'
                ))
                print(f"📝 [COMPLETAR_CITA] Historial registrado")
            except Exception as hist_error:
                print(f"⚠️ [COMPLETAR_CITA] Error en historial (no crítico): {hist_error}")
            
            # 4. Crear notificación
            try:
                cursor.execute('''
                    INSERT INTO notificaciones 
                    (negocio_id, profesional_id, tipo, titulo, mensaje, fecha_creacion, leido)
                    VALUES (%s, %s, %s, %s, %s, NOW(), false)
                ''', (
                    negocio_id, 
                    profesional_id,
                    'success',
                    '✅ Servicio Completado',
                    f'Has completado el servicio para {resultado_update["cliente_nombre"]}'
                ))
                print(f"📢 [COMPLETAR_CITA] Notificación creada")
            except Exception as notif_error:
                print(f"⚠️ [COMPLETAR_CITA] Error en notificación (no crítico): {notif_error}")
            
            conn.commit()
            print(f"✅ [COMPLETAR_CITA] Commit exitoso")
            
            flash(f'✅ Cita completada para {resultado_update["cliente_nombre"]}', 'success')
            
        else:
            print(f"❌ [COMPLETAR_CITA] UPDATE no devolvió resultado")
            flash('❌ Error al actualizar la cita', 'error')
            conn.rollback()
        
    except Exception as e:
        print(f"❌ [COMPLETAR_CITA] Error: {e}")
        import traceback
        traceback.print_exc()
        
        if conn:
            conn.rollback()
            print("🔄 [COMPLETAR_CITA] Rollback realizado")
        
        flash('❌ Error al completar la cita', 'error')
        
    finally:
        if conn:
            conn.close()
            print("🔒 [COMPLETAR_CITA] Conexión cerrada")
    
    # Redirigir con parámetro para notificación
    return redirect(url_for('profesional_dashboard', fecha=request.args.get('fecha', ''), completed='true'))
    

@app.route('/profesional/cambiar-password', methods=['POST'])
@role_required(['profesional'])
def cambiar_password():
    """Permite a un profesional cambiar su contraseña"""
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        return jsonify({'success': False, 'message': 'Error de seguridad'})
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'Todos los campos son requeridos'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'La nueva contraseña debe tener al menos 6 caracteres'})
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Obtener usuario actual
        usuario_id = session.get('usuario_id')
        cursor.execute('SELECT * FROM usuarios WHERE id = %s', (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            return jsonify({'success': False, 'message': 'Usuario no encontrado'})
        
        # Verificar contraseña actual
        import hashlib
        current_hash = hashlib.sha256(current_password.encode()).hexdigest()
        
        if current_hash != usuario['password_hash']:
            return jsonify({'success': False, 'message': 'Contraseña actual incorrecta'})
        
        # Actualizar contraseña
        new_hash = hashlib.sha256(new_password.encode()).hexdigest()
        cursor.execute('''
            UPDATE usuarios 
            SET password_hash = %s
            WHERE id = %s
        ''', (new_hash, usuario_id))
        
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Contraseña actualizada correctamente'})
        
    except Exception as e:
        conn.rollback()
        print(f"Error cambiando contraseña: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'})
        
    finally:
        conn.close()

@app.route('/profesional/personalizar_servicio/<int:cita_id>', methods=['GET', 'POST'])
def profesional_personalizar_servicio(cita_id):
    """Permitir a profesionales personalizar servicios para sus clientes"""
    print(f"🔍 [PERSONALIZAR] Iniciando para cita #{cita_id}")
    
    if 'usuario_id' not in session:
        print("❌ No hay sesión")
        return redirect('/login')
    
    if session.get('usuario_rol') != 'profesional':
        print("❌ Usuario no es profesional")
        flash('Solo los profesionales pueden acceder a esta función', 'error')
        return redirect('/login')
    
    negocio_id = session.get('negocio_id')
    profesional_id = session.get('profesional_id') or session.get('usuario_id')
    
    print(f"🔍 [PERSONALIZAR] negocio_id={negocio_id}, profesional_id={profesional_id}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Verificar que la cita existe
        cursor.execute('''
            SELECT c.*, s.nombre as servicio_nombre, s.duracion, s.precio,
                   cl.nombre as cliente_nombre, cl.telefono as cliente_telefono
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            LEFT JOIN clientes cl ON c.cliente_telefono = cl.telefono AND cl.negocio_id = c.negocio_id
            WHERE c.id = %s AND c.negocio_id = %s AND c.profesional_id = %s
        ''', (cita_id, negocio_id, profesional_id))
        
        cita = cursor.fetchone()
        
        if not cita:
            print(f"❌ [PERSONALIZAR] Cita {cita_id} no encontrada")
            flash('Cita no encontrada o no tienes permiso para acceder', 'error')
            return redirect('/profesional')
        
        print(f"✅ [PERSONALIZAR] Cita encontrada: {cita}")
        
        if request.method == 'POST':
            print("📝 [PERSONALIZAR] Procesando formulario POST")
            
            # Procesar formulario
            nombre_personalizado = request.form.get('nombre_personalizado', '').strip()
            duracion_personalizada = request.form.get('duracion', 0)
            precio_personalizado = request.form.get('precio', 0)
            descripcion = request.form.get('descripcion', '').strip()
            
            servicios_adicionales = request.form.getlist('servicios_adicionales[]')
            incluidos_por_defecto = request.form.getlist('incluidos_por_defecto[]')
            
            print(f"📝 [PERSONALIZAR] Datos recibidos:")
            print(f"   Nombre: {nombre_personalizado}")
            print(f"   Duración: {duracion_personalizada}")
            print(f"   Precio: {precio_personalizado}")
            print(f"   Servicios adicionales: {servicios_adicionales}")
            print(f"   Incluidos por defecto: {incluidos_por_defecto}")
            
            # 1. Buscar o crear cliente
            cursor.execute('''
                SELECT id FROM clientes 
                WHERE telefono = %s AND negocio_id = %s
            ''', (cita['cliente_telefono'], negocio_id))
            
            cliente_existente = cursor.fetchone()
            cliente_id = None
            
            if cliente_existente:
                cliente_id = cliente_existente['id']
                print(f"✅ [PERSONALIZAR] Cliente existente encontrado: ID {cliente_id}")
            else:
                cursor.execute('''
                    INSERT INTO clientes (negocio_id, telefono, nombre, created_at, updated_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    RETURNING id
                ''', (negocio_id, cita['cliente_telefono'], cita['cliente_nombre']))
                
                cliente_result = cursor.fetchone()
                cliente_id = cliente_result['id']
                print(f"✅ [PERSONALIZAR] Nuevo cliente creado: ID {cliente_id}")
            
            if not cliente_id:
                print("❌ [PERSONALIZAR] Error al obtener/crear cliente")
                flash('Error al obtener/crear cliente', 'error')
                return redirect(f'/profesional/personalizar_servicio/{cita_id}')
            
            # 2. Crear o actualizar servicio personalizado
            cursor.execute('''
                SELECT id FROM servicios_personalizados 
                WHERE cliente_id = %s AND negocio_id = %s AND profesional_id = %s
            ''', (cliente_id, negocio_id, profesional_id))
            
            servicio_personalizado_existente = cursor.fetchone()
            servicio_personalizado_id = None
            
            if servicio_personalizado_existente:
                # Actualizar existente
                cursor.execute('''
                    UPDATE servicios_personalizados 
                    SET nombre_personalizado = %s,
                        duracion_personalizada = %s,
                        precio_personalizado = %s,
                        descripcion = %s,
                        servicio_base_id = %s,
                        fecha_actualizacion = NOW(),
                        activo = true
                    WHERE id = %s
                ''', (
                    nombre_personalizado or f'Personalizado para {cita["cliente_nombre"]}',
                    duracion_personalizada or cita['duracion'],
                    precio_personalizado or cita['precio'],
                    descripcion or f'Servicio personalizado para {cita["cliente_nombre"]}',
                    cita['servicio_id'],
                    servicio_personalizado_existente['id']
                ))
                
                servicio_personalizado_id = servicio_personalizado_existente['id']
                print(f"✅ [PERSONALIZAR] Servicio personalizado actualizado: ID {servicio_personalizado_id}")
            else:
                # Crear nuevo
                cursor.execute('''
                    INSERT INTO servicios_personalizados 
                    (cliente_id, negocio_id, profesional_id, servicio_base_id,
                     nombre_personalizado, duracion_personalizada, precio_personalizado, 
                     descripcion, activo, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, NOW())
                    RETURNING id
                ''', (
                    cliente_id, negocio_id, profesional_id, cita['servicio_id'],
                    nombre_personalizado or f'Personalizado para {cita["cliente_nombre"]}',
                    duracion_personalizada or cita['duracion'],
                    precio_personalizado or cita['precio'],
                    descripcion or f'Servicio personalizado para {cita["cliente_nombre"]}'
                ))
                
                servicio_personalizado_result = cursor.fetchone()
                servicio_personalizado_id = servicio_personalizado_result['id']
                print(f"✅ [PERSONALIZAR] Nuevo servicio personalizado creado: ID {servicio_personalizado_id}")
            
            # 3. Guardar servicios adicionales
            if servicio_personalizado_id:
                # Limpiar servicios adicionales anteriores
                cursor.execute('''
                    DELETE FROM servicios_adicionales_cliente 
                    WHERE servicio_personalizado_id = %s
                ''', (servicio_personalizado_id,))
                
                # Agregar nuevos servicios adicionales
                for servicio_id in servicios_adicionales:
                    try:
                        servicio_id_int = int(servicio_id)
                        incluido = servicio_id in incluidos_por_defecto
                        
                        cursor.execute('''
                            INSERT INTO servicios_adicionales_cliente 
                            (servicio_personalizado_id, servicio_id, incluido_por_defecto)
                            VALUES (%s, %s, %s)
                        ''', (servicio_personalizado_id, servicio_id_int, incluido))
                    except ValueError:
                        continue
            
            conn.commit()
            print("✅ [PERSONALIZAR] Personalización guardada exitosamente")
            
            flash('✅ Servicio personalizado guardado exitosamente', 'success')
            return redirect('/profesional')
        
        # ========== GET REQUEST ==========
        print("📋 [PERSONALIZAR] Mostrando formulario (GET)")
        
        # Obtener servicios disponibles
        cursor.execute('''
            SELECT * FROM servicios 
            WHERE negocio_id = %s AND activo = true 
            AND id != %s
            ORDER BY nombre
        ''', (negocio_id, cita['servicio_id']))
        
        servicios = cursor.fetchall()
        
        # Verificar si ya existe personalización
        cursor.execute('''
            SELECT id FROM clientes 
            WHERE telefono = %s AND negocio_id = %s
        ''', (cita['cliente_telefono'], negocio_id))
        
        cliente = cursor.fetchone()
        personalizacion_existente = None
        
        if cliente:
            cursor.execute('''
                SELECT * FROM servicios_personalizados 
                WHERE cliente_id = %s AND negocio_id = %s AND profesional_id = %s
                AND activo = true
            ''', (cliente['id'], negocio_id, profesional_id))
            
            personalizacion = cursor.fetchone()
            
            if personalizacion:
                # Obtener servicios adicionales
                cursor.execute('''
                    SELECT sac.servicio_id, sac.incluido_por_defecto
                    FROM servicios_adicionales_cliente sac
                    WHERE sac.servicio_personalizado_id = %s
                ''', (personalizacion['id'],))
                
                servicios_adicionales = cursor.fetchall()
                
                personalizacion_existente = {
                    'id': personalizacion['id'],
                    'nombre_personalizado': personalizacion['nombre_personalizado'],
                    'duracion_personalizada': personalizacion['duracion_personalizada'],
                    'precio_personalizado': personalizacion['precio_personalizado'],
                    'descripcion': personalizacion['descripcion'],
                    'servicios_adicionales_ids': [sa['servicio_id'] for sa in servicios_adicionales] if servicios_adicionales else [],
                    'incluidos_default': [sa['servicio_id'] for sa in servicios_adicionales if sa['incluido_por_defecto']] if servicios_adicionales else []
                }
        
        conn.close()
        
        return render_template('profesional/personalizar_servicio.html',
                             cita=cita,
                             servicios=servicios,
                             personalizacion=personalizacion_existente)
        
    except Exception as e:
        print(f"❌ [PERSONALIZAR] Error: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al procesar la solicitud', 'error')
        return redirect('/profesional')
    finally:
        if conn:
            conn.close()
# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/citas', methods=['GET'])
@login_required
def obtener_citas():
    """Obtener todas las citas para una fecha y profesional"""
    fecha = request.args.get('fecha', '')
    profesional_id = request.args.get('profesional_id', '')
    negocio_id = request.args.get('negocio_id', session.get('negocio_id', 1))
    limit = request.args.get('limit', '')
    
    if not fecha:
        fecha = datetime.now(tz_colombia).strftime('%Y-%m-%d')
    
    if session.get('usuario_rol') == 'profesional':
        profesional_id = session.get('profesional_id')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = '''
        SELECT c.id, c.cliente_nombre, c.cliente_telefono, c.fecha, c.hora, 
               s.nombre as servicio, c.estado, p.nombre as profesional_nombre
        FROM citas c
        JOIN servicios s ON c.servicio_id = s.id
        JOIN profesionales p ON c.profesional_id = p.id
        WHERE c.negocio_id = %s AND c.fecha = %s
    '''
    
    params = [negocio_id, fecha]
    
    if profesional_id and profesional_id != '':
        query += ' AND c.profesional_id = %s'
        params.append(profesional_id)
    
    query += ' ORDER BY c.hora'
    
    if limit:
        query += ' LIMIT %s'
        params.append(int(limit))
    
    cursor.execute(query, params)
    citas = cursor.fetchall()
    conn.close()

    # Para debug - ver qué está devolviendo la BD
    if citas and len(citas) > 0:
        primera_cita = citas[0]
        print(f"🔍 DEBUG primera cita fecha: {primera_cita['fecha']}")
        print(f"🔍 DEBUG tipo fecha: {type(primera_cita['fecha'])}")
        print(f"🔍 DEBUG tiene strftime?: {hasattr(primera_cita['fecha'], 'strftime')}")
    
    return jsonify([{
        'id': c['id'],
        'cliente_nombre': c['cliente_nombre'] or 'No especificado',
        'cliente_telefono': c['cliente_telefono'],
        'fecha': c['fecha'].strftime('%Y-%m-%d') if c['fecha'] and hasattr(c['fecha'], 'strftime') else str(c['fecha']) if c['fecha'] else '',
        'hora': c['hora'],
        'servicio': c['servicio'],
        'estado': c['estado'],
        'profesional_nombre': c['profesional_nombre']
    } for c in citas])

@app.route('/api/estadisticas/mensuales')
@login_required
def obtener_estadisticas_mensuales():
    """Obtener estadísticas mensuales avanzadas"""
    try:
        profesional_id = request.args.get('profesional_id')
        mes = request.args.get('mes', datetime.now(tz_colombia).month)
        año = request.args.get('año', datetime.now(tz_colombia).year)
        
        if session.get('usuario_rol') == 'superadmin':
            negocio_id = request.args.get('negocio_id', 1)
        else:
            negocio_id = session.get('negocio_id', 1)
        
        if session.get('usuario_rol') == 'profesional':
            profesional_id = session.get('profesional_id')
        
        try:
            mes = int(mes)
            año = int(año)
            negocio_id = int(negocio_id)
            if profesional_id:
                profesional_id = int(profesional_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Parámetros inválidos'}), 400
        
        estadisticas = db.obtener_estadisticas_mensuales(
            negocio_id=negocio_id,
            profesional_id=profesional_id,
            mes=mes,
            año=año
        )
        return jsonify(estadisticas)
        
    except Exception as e:
        print(f"❌ Error obteniendo estadísticas mensuales: {e}")
        return jsonify({
            'resumen': {
                'total_citas': 0,
                'citas_confirmadas': 0,
                'citas_completadas': 0,
                'citas_canceladas': 0,
                'citas_pendientes': 0,
                'ingresos_totales': 0,
                'tasa_exito': 0
            },
            'profesionales_top': [],
            'servicios_top': [],
            'tendencia_mensual': {
                'meses': [],
                'ingresos': []
            }
        })

@app.route('/api/cita/<int:cita_id>/completar', methods=['POST'])
@login_required
def marcar_cita_completada(cita_id):
    """Marcar cita como completada"""
    usuario_rol = session.get('usuario_rol')
    profesional_id = session.get('profesional_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if usuario_rol == 'profesional':
        cursor.execute('SELECT profesional_id FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita or cita[0] != profesional_id:
            conn.close()
            return jsonify({'error': 'No autorizado'}), 403
    
    cursor.execute('UPDATE citas SET estado = %s WHERE id = %s', ('completada', cita_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/horarios_disponibles')
def api_horarios_disponibles():
    """API para obtener horarios disponibles - VERSIÓN CON ZONA HORARIA CORREGIDA"""
    try:
        profesional_id = request.args.get('profesional_id')
        fecha = request.args.get('fecha')
        servicio_id = request.args.get('servicio_id')
        
        print(f"🔍 DEBUG api_horarios_disponibles: profesional_id={profesional_id}, fecha={fecha}, servicio_id={servicio_id}")
        
        if not all([profesional_id, fecha, servicio_id]):
            return jsonify({'error': 'Parámetros incompletos'}), 400
        
        # ✅ CORRECCIÓN: Configurar zona horaria de Colombia
        tz_colombia = pytz.timezone('America/Bogota')
        fecha_actual_colombia = datetime.now(tz_colombia)
        
        print(f"🔍 Hora UTC del servidor: {datetime.utcnow()}")
        print(f"🔍 Hora Colombia: {fecha_actual_colombia}")
        
        # Obtener negocio_id del profesional
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('SELECT negocio_id FROM profesionales WHERE id = %s', (profesional_id,))
        profesional = cursor.fetchone()
        if not profesional:
            conn.close()
            return jsonify({'error': 'Profesional no encontrado'}), 404
        
        negocio_id = profesional['negocio_id']
        
        cursor.execute('SELECT duracion FROM servicios WHERE id = %s', (servicio_id,))
        servicio = cursor.fetchone()
        
        if not servicio:
            conn.close()
            return jsonify({'error': 'Servicio no encontrado'}), 404
        
        duracion_minutos = servicio['duracion']
        print(f"🔍 Duración del servicio: {duracion_minutos} minutos, Negocio ID: {negocio_id}")
        
        horarios_config = db.obtener_horarios_por_dia(negocio_id, fecha)
        print(f"🔍 Configuración de horarios obtenida: {horarios_config}")
        
        if not horarios_config or not horarios_config['activo']:
            conn.close()
            return jsonify({'error': 'El negocio no trabaja este día'}), 400
        
        hora_inicio_str = horarios_config['hora_inicio']
        hora_fin_str = horarios_config['hora_fin']
        almuerzo_inicio_str = horarios_config.get('almuerzo_inicio')
        almuerzo_fin_str = horarios_config.get('almuerzo_fin')
        
        print(f"🔍 Horario configurado: {hora_inicio_str} a {hora_fin_str}, Almuerzo: {almuerzo_inicio_str} a {almuerzo_fin_str}")
        
        fecha_solicitada = datetime.strptime(fecha, '%Y-%m-%d').date()
        es_hoy = fecha_solicitada == fecha_actual_colombia.date()
        
        print(f"🔍 Fecha actual Colombia: {fecha_actual_colombia}")
        print(f"🔍 Fecha solicitada: {fecha_solicitada}")
        print(f"🔍 ¿Es hoy en Colombia?: {es_hoy}")
        print(f"🔍 Hora actual en Colombia: {fecha_actual_colombia.strftime('%H:%M')}")
        
        # ✅ CORRECCIÓN: Si es HOY, verificar si ya pasó la hora de cierre
        if es_hoy:
            hora_fin_hoy_colombia = tz_colombia.localize(
                datetime.combine(fecha_solicitada, datetime.strptime(hora_fin_str, '%H:%M').time())
            )
            print(f"🔍 Hora de cierre hoy en Colombia: {hora_fin_hoy_colombia.strftime('%Y-%m-%d %H:%M')}")
            
            if fecha_actual_colombia >= hora_fin_hoy_colombia:
                print(f"⏰ EL NEGOCIO YA CERRÓ HOY EN COLOMBIA ({hora_fin_str}). No hay horarios disponibles.")
                conn.close()
                return jsonify({
                    'horarios': [],
                    'mensaje': f'El negocio ya cerró hoy a las {hora_fin_str}. No hay horarios disponibles para hoy.'
                })
        
        # Convertir strings a datetime para cálculos
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M')
        hora_fin = datetime.strptime(hora_fin_str, '%H:%M')
        
        almuerzo_inicio = None
        almuerzo_fin = None
        if almuerzo_inicio_str and almuerzo_fin_str:
            try:
                almuerzo_inicio = datetime.strptime(almuerzo_inicio_str, '%H:%M')
                almuerzo_fin = datetime.strptime(almuerzo_fin_str, '%H:%M')
            except ValueError:
                print("⚠️ Error parseando horario de almuerzo, ignorando...")
        
        # Obtener citas ya agendadas
        cursor.execute('''
            SELECT hora FROM citas 
            WHERE profesional_id = %s 
            AND fecha = %s 
            AND estado NOT IN ('cancelada', 'cancelado')
            ORDER BY hora
        ''', (profesional_id, fecha))
        
        citas_ocupadas_result = cursor.fetchall()
        citas_ocupadas = [cita['hora'] for cita in citas_ocupadas_result]
        print(f"🔍 Citas ocupadas: {citas_ocupadas}")
        
        conn.close()
        
        # ✅ CORRECCIÓN: Si es HOY, empezar desde la hora actual + margen
        if es_hoy:
            # Calcular la hora mínima para agendar (hora actual + 30 minutos)
            hora_minima_colombia = fecha_actual_colombia + timedelta(minutes=30)
            hora_minima_time = hora_minima_colombia.time()
            
            print(f"🔍 Hora actual Colombia: {fecha_actual_colombia.strftime('%H:%M')}")
            print(f"🔍 Hora mínima para agendar hoy (Colombia): {hora_minima_colombia.strftime('%H:%M')}")
            
            # Si la hora mínima es después del horario de cierre, no hay horarios
            if hora_minima_time >= datetime.strptime(hora_fin_str, '%H:%M').time():
                print(f"⏰ La hora mínima ({hora_minima_colombia.strftime('%H:%M')}) es después del cierre ({hora_fin_str})")
                return jsonify({
                    'horarios': [],
                    'mensaje': 'No hay horarios disponibles para hoy en el horario laboral restante.'
                })
            
            # ✅ CORRECCIÓN: Redondear correctamente a intervalos de 30 minutos
            hora_minima_dt = datetime.combine(fecha_solicitada, hora_minima_time)
            hora_inicio_dt = datetime.combine(fecha_solicitada, hora_inicio.time())
            
            hora_actual = max(hora_minima_dt, hora_inicio_dt)
            
            # ✅ CORRECCIÓN DEL ERROR: Redondear minutos correctamente
            minutos = hora_actual.minute
            if minutos % 30 != 0:
                # Calcular los minutos redondeados
                minutos_redondeados = ((minutos // 30) + 1) * 30
                
                # ✅ CORRECCIÓN: Si minutos_redondeados es 60, ajustar a 0 y sumar 1 hora
                if minutos_redondeados == 60:
                    hora_actual = hora_actual.replace(
                        hour=hora_actual.hour + 1,
                        minute=0,
                        second=0,
                        microsecond=0
                    )
                else:
                    hora_actual = hora_actual.replace(
                        minute=minutos_redondeados,
                        second=0,
                        microsecond=0
                    )
            
            print(f"🔍 Hora actual ajustada para hoy (Colombia): {hora_actual.strftime('%H:%M')}")
        else:
            # Para días futuros, empezar desde la hora de apertura normal
            hora_actual = datetime.combine(fecha_solicitada, hora_inicio.time())
        
        # Convertir hora_fin a datetime completo para comparación
        hora_fin_completa = datetime.combine(fecha_solicitada, hora_fin.time())
        
        # Generar slots
        intervalos_disponibles = []
        
        while hora_actual < hora_fin_completa:
            hora_fin_slot = hora_actual + timedelta(minutes=duracion_minutos)
            
            # Si el slot se pasa del horario de fin, no es válido
            if hora_fin_slot > hora_fin_completa:
                break
            
            # Verificar si está dentro del horario de almuerzo
            dentro_almuerzo = False
            if almuerzo_inicio and almuerzo_fin:
                hora_actual_time = hora_actual.time()
                almuerzo_ini_time = almuerzo_inicio.time()
                almuerzo_fin_time = almuerzo_fin.time()
                
                if (almuerzo_ini_time <= hora_actual_time < almuerzo_fin_time or
                    almuerzo_ini_time < hora_fin_slot.time() <= almuerzo_fin_time or
                    (hora_actual_time <= almuerzo_ini_time and hora_fin_slot.time() >= almuerzo_fin_time)):
                    dentro_almuerzo = True
            
            if not dentro_almuerzo:
                # Verificar si el slot está ocupado
                hora_str = hora_actual.strftime('%H:%M')
                ocupado = False
                
                for cita_hora in citas_ocupadas:
                    cita_hora_str = str(cita_hora)
                    if ':' in cita_hora_str:
                        cita_hora_str = cita_hora_str[:5]
                    
                    if cita_hora_str == hora_str:
                        ocupado = True
                        break
                
                if not ocupado:
                    # ✅ CORRECCIÓN: Si es HOY, verificar margen con hora de Colombia
                    if es_hoy:
                        horario_colombia = tz_colombia.localize(hora_actual)
                        tiempo_hasta_horario = horario_colombia - fecha_actual_colombia
                        margen_minimo = 30 * 60  # segundos
                        
                        if tiempo_hasta_horario.total_seconds() < margen_minimo:
                            print(f"⏰ Horario {hora_str} omitido (faltan {int(tiempo_hasta_horario.total_seconds()/60)} minutos, mínimo 30 requeridos)")
                        else:
                            intervalos_disponibles.append(hora_str)
                            print(f"✅ Horario {hora_str} DISPONIBLE (faltan {int(tiempo_hasta_horario.total_seconds()/60)} minutos)")
                    else:
                        intervalos_disponibles.append(hora_str)
                        print(f"✅ Horario {hora_str} DISPONIBLE (día futuro)")
            
            # Avanzar al siguiente slot (30 minutos)
            hora_actual += timedelta(minutes=30)
        
        print(f"🔍 Horarios disponibles encontrados: {len(intervalos_disponibles)}: {intervalos_disponibles}")
        
        if not intervalos_disponibles:
            mensaje = 'No hay horarios disponibles para esta fecha'
            if es_hoy:
                mensaje = 'No hay horarios disponibles para hoy con el margen requerido'
            
            return jsonify({
                'horarios': [],
                'mensaje': mensaje,
                'hora_actual_colombia': fecha_actual_colombia.strftime('%H:%M'),
                'hora_minima_requerida': (fecha_actual_colombia + timedelta(minutes=30)).strftime('%H:%M') if es_hoy else None
            })
        
        return jsonify({
            'horarios': intervalos_disponibles,
            'duracion': duracion_minutos,
            'hora_actual_colombia': fecha_actual_colombia.strftime('%H:%M') if es_hoy else None,
            'horario_laboral': {
                'inicio': hora_inicio_str,
                'fin': hora_fin_str,
                'almuerzo': f"{almuerzo_inicio_str} - {almuerzo_fin_str}" if almuerzo_inicio_str and almuerzo_fin_str else None
            }
        })
        
    except Exception as e:
        print(f"❌ Error en api_horarios_disponibles: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error interno del servidor'}), 500


   
# =============================================================================
# RUTAS DE notificaciones
# =============================================================================

@app.route('/api/profesional/notificaciones', methods=['GET'])
def get_professional_notifications():
    """API para obtener notificaciones del profesional"""
    if 'profesional_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    profesional_id = session['profesional_id']
    notificaciones = notification_system.get_professional_notifications(profesional_id)
    
    return jsonify({
        'success': True,
        'notificaciones': notificaciones,
        'total_no_leidas': notification_system.get_unread_count(profesional_id)
    })

@app.route('/api/profesional/notificaciones/<int:notif_id>/leer', methods=['POST'])
def mark_notification_read(notif_id):
    """API para marcar notificación como leída"""
    if notification_system.mark_as_read(notif_id):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/api/profesional/notificaciones/leer-todas', methods=['POST'])
def mark_all_notifications_read():
    """API para marcar todas las notificaciones como leídas"""
    if 'profesional_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    profesional_id = session['profesional_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Actualizar todas las notificaciones no leídas del profesional
        cursor.execute('''
            UPDATE notificaciones_profesional 
            SET leida = TRUE, fecha_leida = NOW()
            WHERE profesional_id = %s AND leida = FALSE
        ''', (profesional_id,))
        
        conn.commit()
        
        rows_updated = cursor.rowcount
        
        return jsonify({
            'success': True,
            'message': f'Se marcaron {rows_updated} notificaciones como leídas'
        })
        
    except Exception as e:
        print(f"❌ Error marcando todas como leídas: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# =============================================================================
# RUTAS PARA NOTIFICACIONES PUSH
# =============================================================================

@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def subscribe_push():
    """Registrar dispositivo para notificaciones push - VERSIÓN SIMPLIFICADA"""
    try:
        data = request.json
        subscription = data.get('subscription')
        profesional_id = session.get('profesional_id')
        
        if not subscription or not profesional_id:
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        
        print(f"📱 Suscribiendo profesional {profesional_id} a notificaciones push")
        
        # Guardar en base de datos
        conn = get_db_connection()
        cursor = conn.cursor()
        
        dispositivo_info = request.headers.get('User-Agent', 'Dispositivo móvil')[:500]
        
        cursor.execute('''
            INSERT INTO suscripciones_push (profesional_id, subscription_json, dispositivo_info, activa)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (profesional_id, subscription_json) 
            DO UPDATE SET activa = TRUE
        ''', (profesional_id, json.dumps(subscription), dispositivo_info))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Suscripto a notificaciones push'})
        
    except Exception as e:
        print(f"❌ Error en subscribe_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

@app.route('/api/push/test', methods=['POST'])
@login_required
def test_push():
    """Probar notificaciones push"""
    profesional_id = session.get('profesional_id')
    
    # Llamar a la función auxiliar que ya creaste
    if enviar_notificacion_push_profesional(
        profesional_id=profesional_id,
        titulo="🔔 Test Push",
        mensaje="¡Las notificaciones push funcionan correctamente!",
        cita_id=None
    ):
        return jsonify({'success': True, 'message': 'Notificación de prueba enviada'})
    else:
        return jsonify({'success': False, 'message': 'No hay suscripciones activas'})

# =============================================================================
# RUTAS DE DEBUG PARA CONTRASEÑAS - VERSIÓN CORREGIDA
# =============================================================================
@app.route('/test_personalizar')
def test_personalizar():
    """Ruta de prueba para verificar que la personalización funciona"""
    return "✅ Ruta de personalización funciona correctamente"

@app.route('/api/debug/recreate-push-table', methods=['GET', 'POST'])
def recreate_push_table():
    """Recrear tabla de suscripciones push correctamente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("🗑️ Eliminando tabla existente...")
        cursor.execute('DROP TABLE IF EXISTS suscripciones_push')
        
        print("🔧 Creando nueva tabla...")
        cursor.execute('''
            CREATE TABLE suscripciones_push (
                id SERIAL PRIMARY KEY,
                profesional_id INTEGER NOT NULL,
                subscription_json TEXT NOT NULL,
                dispositivo_info TEXT,
                activa BOOLEAN DEFAULT TRUE,
                UNIQUE(profesional_id, subscription_json)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Tabla recreada con constraint UNIQUE'})
        
    except Exception as e:
        print(f"❌ Error recreando tabla: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# MANIFEST ÚNICO - DETECTA AUTOMÁTICAMENTE
# =============================================================================

@app.route('/manifest.json')
def manifest_final():
    referer = request.headers.get('Referer', '')
    
    # Detectar negocio
    negocio_id = 1
    if referer and '/cliente/' in referer:
        import re
        match = re.search(r'/cliente/(\d+)', referer)
        if match:
            negocio_id = match.group(1)
    
    base_url = 'https://wabot-production-d544.up.railway.app'
    
    manifest = {
        "name": "WaBot",
        "short_name": "WaBot",
        "description": "Agendar citas",
        "start_url": f"{base_url}/cliente/{negocio_id}",
        "display": "standalone",
        "background_color": "#007bff",
        "theme_color": "#007bff",
        "orientation": "portrait",
        "scope": f"{base_url}/",
        "lang": "es",
        
        # 🔥 CLAVE: "any maskable" para iconos adaptables
        "icons": [
            {
                "src": f"{base_url}/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"  # 🔥 ESTA LÍNEA ES CLAVE
            },
            {
                "src": f"{base_url}/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png", 
                "purpose": "any maskable"  # 🔥 ESTA LÍNEA ES CLAVE
            }
        ],
        
        # 🔥 OPCIONAL: Agrega este shortcut simplificado
        "shortcuts": [
            {
                "name": "Agendar",
                "url": f"{base_url}/cliente/{negocio_id}"
            }
        ]
    }
    
    response = jsonify(manifest)
    response.headers['Cache-Control'] = 'no-store, no-cache'
    return response

def crear_manifest_default():
    """Manifest por defecto (redirige a /app que decide inteligentemente)"""
    return {
        "name": "WaBot",
        "short_name": "WaBot",
        "description": "Sistema de agendamiento",
        "start_url": "/app",  # Ruta INTELIGENTE que decide
        "display": "standalone",
        "background_color": "#007bff",
        "theme_color": "#007bff",
        "orientation": "portrait-primary",
        "scope": "/",
        "lang": "es",
        "icons": [
            {
                "src": "/static/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/icons/icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/icons/icon-128x128.png",
                "sizes": "128x128",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ],
        "categories": ["business", "productivity", "utilities"],
        "shortcuts": [
            {
                "name": "WaBot",
                "short_name": "WaBot",
                "description": "Sistema de agendamiento",
                "url": "/app",
                "icons": [
                    {
                        "src": "/static/icons/icon-96x96.png",
                        "sizes": "96x96",
                        "type": "image/png"
                    }
                ]
            }
        ]
    }

@app.route('/manifest-login.json')
def manifest_login():
    """Manifest específico para la página de login"""
    
    manifest = {
        "name": "WaBot Login",
        "short_name": "WaBot Login",
        "description": "Acceso a la plataforma WaBot",
        "start_url": "/login",
        "display": "standalone",
        "background_color": "#667eea",
        "theme_color": "#667eea",
        "orientation": "portrait",
        "scope": "/",
        "lang": "es",
        "icons": [
            {
                "src": "/static/icons/icon-login-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-login-512.png", 
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }
    
    response = jsonify(manifest)
    response.headers['Cache-Control'] = 'no-store, no-cache'
    return response

@app.route('/app')
def app_redirect():
    """Redirección inteligente según el tipo de usuario"""
    # 1. Si hay sesión de trabajador
    if 'usuario_id' in session:
        rol = session.get('usuario_rol')
        if rol == 'superadmin':
            return redirect(url_for('admin_dashboard'))
        elif rol == 'propietario':
            return redirect(url_for('negocio_dashboard'))
        elif rol == 'profesional':
            return redirect(url_for('profesional_dashboard'))
        else:
            return redirect(url_for('login'))
    
    # 2. Si NO hay sesión (cliente)
    else:
        # Intentar detectar de dónde venía
        referer = request.headers.get('Referer', '')
        if '/cliente/' in referer:
            import re
            match = re.search(r'/cliente/(\d+)', referer)
            if match:
                return redirect(url_for('chat_index', negocio_id=match.group(1)))
        
        # Por defecto: primer negocio activo
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT id FROM negocios WHERE activo = TRUE LIMIT 1')
        negocio = cursor.fetchone()
        conn.close()
        
        return redirect(url_for('chat_index', negocio_id=negocio['id'] if negocio else 1))

# =============================================================================
# RUTAS PARA BLOQUEO DE HORARIOS POR PROFESIONALES
# =============================================================================

@app.route('/profesional/bloqueos')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_bloqueos():
    """Página principal para gestión de horarios bloqueados"""
    try:
        negocio_id = session.get('negocio_id', 1)
        profesional_id = session.get('profesional_id')
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        # Fecha por defecto: hoy
        fecha = request.args.get('fecha', datetime.now(tz_colombia).strftime('%Y-%m-%d'))
        
        # Obtener bloqueos del profesional
        from database import obtener_bloqueos_profesional
        bloqueos = obtener_bloqueos_profesional(negocio_id, profesional_id, fecha)
        
        # Obtener información del profesional
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT nombre, especialidad FROM profesionales WHERE id = %s', (profesional_id,))
        profesional_info = cursor.fetchone()
        conn.close()
        
        return render_template('profesional/bloqueos.html',
                            bloqueos=bloqueos,
                            fecha_seleccionada=fecha,
                            profesional_id=profesional_id,
                            profesional_nombre=profesional_info['nombre'])
        
    except Exception as e:
        print(f"❌ Error en profesional_bloqueos: {e}")
        flash('Error al cargar la página de bloqueos', 'error')
        return redirect(url_for('profesional_dashboard'))

@app.route('/profesional/bloquear-horario', methods=['POST'])
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_bloquear_horario():
    """Bloquear un horario específico"""
    try:
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            return jsonify({'success': False, 'error': 'Error de seguridad'})
        
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        
        fecha = request.form.get('fecha')
        hora = request.form.get('hora')
        duracion = request.form.get('duracion', 60)
        motivo = request.form.get('motivo', '')
        sobreescribir_cita = request.form.get('sobreescribir_cita', 'false').lower() == 'true'
        
        
        if not all([fecha, hora]):
            return jsonify({'success': False, 'error': 'Fecha y hora son requeridos'})
        
        print(f"🔒 Bloqueando horario: {fecha} {hora} por profesional {profesional_id}")
        
        # Llamar a la función de bloqueo
        from database import bloquear_horario_profesional
        resultado = bloquear_horario_profesional(
            negocio_id=negocio_id,
            profesional_id=profesional_id,
            fecha=fecha,
            hora_inicio=hora,
            duracion_minutos=int(duracion),
            motivo=motivo,
            sobreescribir=sobreescribir_cita
        )
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Error bloqueando horario: {e}")
        return jsonify({'success': False, 'error': 'Error interno del servidor'})

@app.route('/profesional/desbloquear-horario/<int:bloqueo_id>', methods=['POST'])
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_desbloquear_horario(bloqueo_id):
    """Desbloquear un horario previamente bloqueado"""
    try:
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad', 'error')
            return redirect(url_for('profesional_bloqueos'))
        
        profesional_id = session.get('profesional_id')
        
        from database import desbloquear_horario
        resultado = desbloquear_horario(bloqueo_id, profesional_id)
        
        if resultado['success']:
            flash('✅ Horario desbloqueado exitosamente', 'success')
        else:
            flash(f"❌ {resultado.get('error', 'Error al desbloquear')}", 'error')
        
        return redirect(url_for('profesional_bloqueos'))
        
    except Exception as e:
        print(f"❌ Error desbloqueando horario: {e}")
        flash('Error al desbloquear el horario', 'error')
        return redirect(url_for('profesional_bloqueos'))

@app.route('/profesional/api/horarios-disponibles')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_api_horarios_disponibles():
    """API para obtener horarios disponibles (para el formulario de bloqueo)"""
    try:
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        fecha = request.args.get('fecha', datetime.now(tz_colombia).strftime('%Y-%m-%d'))
        
        # Reutilizar la misma lógica que usan los clientes
        from web_chat_handler import generar_horarios_disponibles_actualizado
        
        # Necesitamos un servicio_id para la función, usamos el primero
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM servicios WHERE negocio_id = %s AND activo = TRUE LIMIT 1', (negocio_id,))
        servicio = cursor.fetchone()
        conn.close()
        
        if not servicio:
            return jsonify({'horarios': [], 'error': 'No hay servicios configurados'})
        
        servicio_id = servicio[0] if isinstance(servicio, tuple) else servicio['id']
        
        # Generar horarios disponibles (ya excluye los bloqueados automáticamente)
        horarios = generar_horarios_disponibles_actualizado(negocio_id, profesional_id, fecha, servicio_id)
        
        # Obtener horarios ya bloqueados para marcarlos
        from database import obtener_bloqueos_profesional
        bloqueos = obtener_bloqueos_profesional(negocio_id, profesional_id, fecha)
        
        # Formatear respuesta
        horarios_formateados = []
        for hora in horarios:
            # Verificar si está bloqueado
            bloqueado = False
            motivo = ""
            for bloqueo in bloqueos:
                if bloqueo['hora'].startswith(hora):
                    bloqueado = True
                    motivo = bloqueo.get('motivo', '')
                    break
            
            horarios_formateados.append({
                'hora': hora,
                'bloqueado': bloqueado,
                'motivo': motivo if bloqueado else None
            })
        
        return jsonify({
            'success': True,
            'horarios': horarios_formateados,
            'fecha': fecha
        })
        
    except Exception as e:
        print(f"❌ Error en profesional_api_horarios_disponibles: {e}")
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/api/horarios/configuracion', methods=['GET'])
@login_required
def obtener_configuracion_horarios():
    """Obtener configuración de horarios para una fecha específica"""
    fecha = request.args.get('fecha', '')
    if not fecha:
        fecha = datetime.now().strftime('%Y-%m-%d')
    
    negocio_id = session.get('negocio_id', 1)
    
    # Usar la función que ya tienes en database.py
    config = db.obtener_horarios_por_dia(negocio_id, fecha)
    
    return jsonify(config)

@app.route('/api/push/public-key')
def get_public_key():
    """Obtener clave pública VAPID para notificaciones push"""
    try:
        VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
        
        # DEBUG: Mostrar qué hay en la variable
        print(f"🔑 [DEBUG] VAPID_PUBLIC_KEY: {VAPID_PUBLIC_KEY[:50]}...")
        print(f"🔑 [DEBUG] Longitud: {len(VAPID_PUBLIC_KEY)}")
        print(f"🔑 [DEBUG] Tipo: {type(VAPID_PUBLIC_KEY)}")
        
        if not VAPID_PUBLIC_KEY:
            return jsonify({'error': 'VAPID no configurado'}), 500
        
        # Verificar que sea string Base64 válido
        import base64
        try:
            # Intentar decodificar para verificar
            if '=' in VAPID_PUBLIC_KEY:
                # Tiene padding, verificar
                test = base64.urlsafe_b64decode(VAPID_PUBLIC_KEY + '=' * (4 - len(VAPID_PUBLIC_KEY) % 4))
            else:
                # Sin padding
                test = base64.urlsafe_b64decode(VAPID_PUBLIC_KEY + '=' * (4 - len(VAPID_PUBLIC_KEY) % 4))
            print(f"✅ Clave válida, longitud decodificada: {len(test)}")
        except Exception as decode_error:
            print(f"❌ Clave inválida: {decode_error}")
            return jsonify({'error': 'Clave VAPID inválida'}), 500
        
        return jsonify({
            'success': True,
            'publicKey': VAPID_PUBLIC_KEY
        })
    except Exception as e:
        print(f"❌ Error get_public_key: {e}")
        return jsonify({'error': 'Error interno'}), 500

@app.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def unsubscribe_push():
    """Eliminar suscripción push"""
    try:
        data = request.json
        subscription = data.get('subscription')
        profesional_id = session.get('profesional_id')
        
        if not subscription or not profesional_id:
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Marcar suscripción como inactiva
        cursor.execute('''
            UPDATE suscripciones_push 
            SET activa = FALSE, fecha_eliminacion = NOW()
            WHERE profesional_id = %s 
            AND subscription_json LIKE %s
        ''', (profesional_id, f'%{subscription["endpoint"][-20:]}%'))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Suscripción eliminada'})
        
    except Exception as e:
        print(f"❌ Error unsubscribe_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500
    
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

# =============================================================================
# EJECUCIÓN PRINCIPAL - SOLO AL EJECUTAR DIRECTAMENTE
# =============================================================================
try:
    scheduler_thread = scheduler.iniciar_scheduler_en_segundo_plano()
    if scheduler_thread:
        print("✅ Scheduler iniciado exitosamente")
except Exception as e:
    print(f"⚠️ No se pudo iniciar scheduler automáticamente: {e}")

if __name__ == '__main__':
    print("🏠 MODO DESARROLLO LOCAL")
    
    # Para desarrollo local: Iniciar scheduler
    try:
        scheduler.iniciar_scheduler_en_segundo_plano()
        print("✅ Scheduler iniciado para desarrollo local")
    except Exception as e:
        print(f"⚠️ Error iniciando scheduler local: {e}")
    
    # Iniciar Flask
    port = int(os.environ.get('PORT', 5000))
    print(f"🎯 INICIANDO SERVIDOR EN PUERTO {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)