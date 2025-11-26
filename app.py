# =============================================================================
# ARCHIVO COMPLETO - app.py SISTEMA GENÉRICO DE CITAS - POSTGRESQL
# =============================================================================

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import secrets
from datetime import datetime, timedelta
import database as db
from whatsapp_handler import whatsapp_bp
import os
from dotenv import load_dotenv
import threading
from scheduler import iniciar_scheduler
import json
from functools import wraps
from database import get_db_connection
import psycopg2
from psycopg2.extras import RealDictCursor

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'negocio-secret-key')

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
        return datetime.now()
    return dict(now=now)

# Registrar blueprint de WhatsApp
app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')

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
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/test-simple')
def test_simple():
    """Ruta simple sin dependencias"""
    return "✅ Ruta básica OK"

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
    """Login para todos los usuarios"""
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
            
            # Manejar profesional
            if usuario['rol'] == 'profesional':
                if 'profesional_id' in session:
                    del session['profesional_id']
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT id, nombre FROM profesionales WHERE usuario_id = %s AND negocio_id = %s', 
                    (usuario['id'], usuario['negocio_id'])
                )
                profesional = cursor.fetchone()
                
                if profesional:
                    session['profesional_id'] = profesional[0]
                    print(f"✅ PROFESIONAL ENCONTRADO: {profesional[1]} (ID: {profesional[0]})")
                else:
                    cursor.execute(
                        'SELECT id, nombre FROM profesionales WHERE nombre = %s AND negocio_id = %s', 
                        (usuario['nombre'], usuario['negocio_id'])
                    )
                    profesional = cursor.fetchone()
                    
                    if profesional:
                        session['profesional_id'] = profesional[0]
                    else:
                        cursor.execute(
                            'SELECT id FROM profesionales WHERE negocio_id = %s AND activo = TRUE LIMIT 1', 
                            (usuario['negocio_id'],)
                        )
                        profesional_fallback = cursor.fetchone()
                        if profesional_fallback:
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
        
        # Configuración por defecto
        configuracion = {
            "saludo_personalizado": f"¡Hola! Soy tu asistente virtual para agendar citas",
            "horario_atencion": "Lunes a Sábado 9:00 AM - 7:00 PM",
            "direccion": "Calle Principal #123",
            "telefono_contacto": telefono_whatsapp.replace('whatsapp:', ''),
            "politica_cancelacion": "Puedes cancelar hasta 2 horas antes"
        }
        
        if not telefono_whatsapp.startswith('whatsapp:'):
            telefono_whatsapp = f'whatsapp:{telefono_whatsapp}'
        
        negocio_id = db.crear_negocio(nombre, telefono_whatsapp, tipo_negocio, json.dumps(configuracion))
        
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

@app.route('/admin/usuarios')
@role_required(['superadmin'])
def admin_usuarios():
    """Gestión de usuarios"""
    usuarios = []
    for negocio in db.obtener_todos_negocios():
        usuarios_negocio = db.obtener_usuarios_por_negocio(negocio['id'])
        usuarios.extend(usuarios_negocio)
    
    return render_template('admin/usuarios.html', usuarios=usuarios)

@app.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_nuevo_usuario():
    """Crear nuevo usuario"""
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
        
        if not all([negocio_id, nombre, email, password]):
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('admin_nuevo_usuario'))
        
        usuario_id = db.crear_usuario(negocio_id, nombre, email, password, rol)
        
        if usuario_id:
            if rol == 'profesional':
                flash(f'Usuario profesional "{nombre}" creado exitosamente', 'success')
            else:
                flash('Usuario creado exitosamente', 'success')
            return redirect(url_for('admin_usuarios'))
        else:
            flash('Error al crear usuario. El email puede estar en uso.', 'error')
    
    negocios = db.obtener_todos_negocios()
    return render_template('admin/nuevo_usuario.html', negocios=negocios)

@app.route('/admin/usuarios/<int:usuario_id>/toggle', methods=['POST'])
@role_required(['superadmin'])
def admin_toggle_usuario(usuario_id):
    """Activar o desactivar un usuario"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_usuarios'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Obtener estado actual del usuario
        cursor.execute('SELECT activo FROM usuarios WHERE id = %s', (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('❌ Usuario no encontrado', 'error')
            return redirect(url_for('admin_usuarios'))
        
        nuevo_estado = not usuario[0]  # Invertir estado
        
        # Actualizar estado
        cursor.execute('''
            UPDATE usuarios 
            SET activo = %s 
            WHERE id = %s
        ''', (nuevo_estado, usuario_id))
        
        conn.commit()
        
        if nuevo_estado:
            flash('✅ Usuario activado exitosamente', 'success')
        else:
            flash('✅ Usuario desactivado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error cambiando estado de usuario: {e}")
        flash('❌ Error al cambiar el estado del usuario', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/<int:usuario_id>/eliminar', methods=['POST'])
@role_required(['superadmin'])
def admin_eliminar_usuario(usuario_id):
    """Eliminar un usuario (solo superadmin)"""
    # Validar CSRF
    if not validate_csrf_token(request.form.get('csrf_token', '')):
        flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
        return redirect(url_for('admin_usuarios'))
    
    # Prevenir eliminación del superadmin principal
    if usuario_id == 1:
        flash('❌ No se puede eliminar el superadministrador principal', 'error')
        return redirect(url_for('admin_usuarios'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si el usuario existe
        cursor.execute('SELECT rol FROM usuarios WHERE id = %s', (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('❌ Usuario no encontrado', 'error')
            return redirect(url_for('admin_usuarios'))
        
        # Si es profesional, también eliminar de la tabla profesionales
        if usuario[0] == 'profesional':
            cursor.execute('''
                DELETE FROM profesionales 
                WHERE usuario_id = %s
            ''', (usuario_id,))
        
        # Eliminar usuario
        cursor.execute('DELETE FROM usuarios WHERE id = %s', (usuario_id,))
        
        conn.commit()
        flash('✅ Usuario eliminado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error eliminando usuario: {e}")
        flash('❌ Error al eliminar el usuario', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@role_required(['superadmin'])
def admin_editar_usuario(usuario_id):
    """Editar un usuario existente"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Obtener usuario actual
    cursor.execute('''
        SELECT u.*, n.nombre as negocio_nombre 
        FROM usuarios u 
        JOIN negocios n ON u.negocio_id = n.id 
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
        negocio_id = request.form.get('negocio_id')
        activo = request.form.get('activo') == 'on'
        
        try:
            # Actualizar usuario
            cursor.execute('''
                UPDATE usuarios 
                SET nombre = %s, email = %s, rol = %s, negocio_id = %s, activo = %s
                WHERE id = %s
            ''', (nombre, email, rol, negocio_id, activo, usuario_id))
            
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
                        SET nombre = %s
                        WHERE usuario_id = %s
                    ''', (nombre, usuario_id))
                else:
                    # Crear nuevo profesional
                    cursor.execute('''
                        INSERT INTO profesionales (negocio_id, nombre, especialidad, pin, usuario_id, activo)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    ''', (negocio_id, nombre, 'General', '0000', usuario_id, activo))
            
            conn.commit()
            flash('✅ Usuario actualizado exitosamente', 'success')
            return redirect(url_for('admin_usuarios'))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error actualizando usuario: {e}")
            flash('❌ Error al actualizar el usuario', 'error')
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
    """Panel principal del negocio"""
    if session.get('usuario_rol') == 'superadmin':
        return redirect(url_for('negocio_estadisticas'))
    
    negocio_id = session.get('negocio_id', 1)
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    stats = db.obtener_estadisticas_mensuales(negocio_id, mes=datetime.now().month, año=datetime.now().year)
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT c.id, c.cliente_nombre, c.hora, s.nombre as servicio, p.nombre as profesional, c.estado
        FROM citas c
        JOIN servicios s ON c.servicio_id = s.id
        JOIN profesionales p ON c.profesional_id = p.id
        WHERE c.negocio_id = %s AND c.fecha = %s AND c.estado != 'cancelado'
        ORDER BY c.hora
        LIMIT 10
    ''', (negocio_id, fecha_hoy))
    
    citas_hoy = cursor.fetchall()
    conn.close()
    
    return render_template('negocio/dashboard.html',
                         stats=stats['resumen'],
                         citas_hoy=citas_hoy,
                         fecha_hoy=fecha_hoy)

@app.route('/negocio/citas')
@role_required(['propietario', 'superadmin'])
def negocio_citas():
    """Gestión de citas del negocio"""
    negocio_id = session.get('negocio_id', 1)
    fecha = request.args.get('fecha', datetime.now().strftime('%Y-%m-%d'))
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
            fecha = datetime.now().strftime('%Y-%m-%d')
        
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
    """API para obtener estadísticas del negocio"""
    try:
        profesional_id = request.args.get('profesional_id', '')
        mes = request.args.get('mes', datetime.now().month)
        año = request.args.get('año', datetime.now().year)
        
        negocio_id = session.get('negocio_id', 1)
        
        try:
            mes = int(mes)
            año = int(año)
            if profesional_id:
                profesional_id = int(profesional_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Parámetros inválidos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Estadísticas básicas del negocio
        query_resumen = '''
            SELECT 
                COUNT(*) as total_citas,
                SUM(CASE WHEN estado = 'confirmada' THEN 1 ELSE 0 END) as citas_confirmadas,
                SUM(CASE WHEN estado = 'completada' THEN 1 ELSE 0 END) as citas_completadas,
                SUM(CASE WHEN estado = 'cancelada' THEN 1 ELSE 0 END) as citas_canceladas,
                COALESCE(SUM(s.precio), 0) as ingresos_totales
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s 
            AND EXTRACT(MONTH FROM c.fecha) = %s 
            AND EXTRACT(YEAR FROM c.fecha) = %s
        '''
        
        params_resumen = [negocio_id, mes, año]
        
        if profesional_id:
            query_resumen += ' AND c.profesional_id = %s'
            params_resumen.append(profesional_id)
        
        cursor.execute(query_resumen, params_resumen)
        resumen = cursor.fetchone()
        
        # Top profesionales
        query_profesionales = '''
            SELECT p.nombre, COUNT(*) as total_citas
            FROM citas c
            JOIN profesionales p ON c.profesional_id = p.id
            WHERE c.negocio_id = %s
            AND EXTRACT(MONTH FROM c.fecha) = %s 
            AND EXTRACT(YEAR FROM c.fecha) = %s
        '''
        
        params_profesionales = [negocio_id, mes, año]
        
        if profesional_id:
            query_profesionales += ' AND c.profesional_id = %s'
            params_profesionales.append(profesional_id)
        
        query_profesionales += ' GROUP BY p.id, p.nombre ORDER BY total_citas DESC LIMIT 5'
        
        cursor.execute(query_profesionales, params_profesionales)
        profesionales_top = cursor.fetchall()
        
        # Top servicios
        query_servicios = '''
            SELECT s.nombre, COUNT(*) as total_citas
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.negocio_id = %s 
            AND EXTRACT(MONTH FROM c.fecha) = %s 
            AND EXTRACT(YEAR FROM c.fecha) = %s
        '''
        
        params_servicios = [negocio_id, mes, año]
        
        if profesional_id:
            query_servicios += ' AND c.profesional_id = %s'
            params_servicios.append(profesional_id)
        
        query_servicios += ' GROUP BY s.id, s.nombre ORDER BY total_citas DESC LIMIT 5'
        
        cursor.execute(query_servicios, params_servicios)
        servicios_top = cursor.fetchall()
        
        # Tendencia mensual (últimos 6 meses)
        meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        tendencia_meses = []
        tendencia_ingresos = []
        
        for i in range(5, -1, -1):  # Últimos 6 meses
            mes_tendencia = mes - i
            año_tendencia = año
            
            if mes_tendencia <= 0:
                mes_tendencia += 12
                año_tendencia -= 1
            
            query_tendencia = '''
                SELECT COALESCE(SUM(s.precio), 0) as ingresos
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.negocio_id = %s 
                AND EXTRACT(MONTH FROM c.fecha) = %s 
                AND EXTRACT(YEAR FROM c.fecha) = %s
                AND c.estado != 'cancelada'
            '''
            
            params_tendencia = [negocio_id, mes_tendencia, año_tendencia]
            
            if profesional_id:
                query_tendencia += ' AND c.profesional_id = %s'
                params_tendencia.append(profesional_id)
            
            cursor.execute(query_tendencia, params_tendencia)
            ingresos_mes = cursor.fetchone()[0]
            
            tendencia_meses.append(f"{meses_nombres[mes_tendencia-1]} {año_tendencia}")
            tendencia_ingresos.append(float(ingresos_mes))
        
        conn.close()
        
        # Calcular tasa de éxito
        total_citas = resumen[0] if resumen else 0
        citas_exitosas = (resumen[1] if resumen else 0) + (resumen[2] if resumen else 0)
        tasa_exito = round((citas_exitosas / total_citas * 100), 2) if total_citas > 0 else 0
        
        estadisticas = {
            'resumen': {
                'total_citas': total_citas,
                'citas_confirmadas': resumen[1] if resumen else 0,
                'citas_completadas': resumen[2] if resumen else 0,
                'citas_canceladas': resumen[3] if resumen else 0,
                'ingresos_totales': float(resumen[4]) if resumen else 0,
                'tasa_exito': tasa_exito
            },
            'profesionales_top': [
                {'nombre': p[0], 'total_citas': p[1]} for p in profesionales_top
            ],
            'servicios_top': [
                {'nombre': s[0], 'total_citas': s[1]} for s in servicios_top
            ],
            'tendencia_mensual': {
                'meses': tendencia_meses,
                'ingresos': tendencia_ingresos
            }
        }
        
        return jsonify(estadisticas)
        
    except Exception as e:
        print(f"❌ Error en negocio_api_estadisticas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    
@app.route('/negocio/api/citas/recientes')
@role_required(['propietario', 'superadmin'])
def negocio_api_citas_recientes():
    """API para obtener citas recientes del negocio"""
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
            params.append(profesional_id)
        
        query += ' ORDER BY c.fecha DESC, c.hora DESC LIMIT %s'
        params.append(int(limit))
        
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        
        return jsonify([
            {
                'cliente_nombre': c['cliente_nombre'],
                'servicio_nombre': c['servicio_nombre'],
                'profesional_nombre': c['profesional_nombre'],
                'fecha': c['fecha'].strftime('%Y-%m-%d') if c['fecha'] else '',
                'hora': c['hora'],
                'estado': c['estado']
            } for c in citas
        ])
        
    except Exception as e:
        print(f"❌ Error en negocio_api_citas_recientes: {e}")
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
    
    # ✅ CORRECCIÓN: Obtener datos REALES de la base de datos
    dias_semana = []
    nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    
    for dia_id in range(1, 8):
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
                FROM configuracion_horarios 
                WHERE negocio_id = %s AND dia_semana = %s
            ''', (negocio_id, dia_id))
            
            resultado = cursor.fetchone()
            conn.close()
            
            if resultado:
                dia_config = {
                    'activo': bool(resultado[0]),
                    'hora_inicio': resultado[1] or '09:00',
                    'hora_fin': resultado[2] or '19:00',
                    'almuerzo_inicio': resultado[3] or '',
                    'almuerzo_fin': resultado[4] or ''
                }
            else:
                dia_config = {
                    'activo': False,  # ✅ Por defecto INACTIVO
                    'hora_inicio': '09:00',
                    'hora_fin': '19:00',
                    'almuerzo_inicio': '',
                    'almuerzo_fin': ''
                }
                
            dias_semana.append({
                'id': dia_id,
                'nombre': nombres_dias[dia_id-1],
                'config': dia_config
            })
            
        except Exception as e:
            print(f"⚠️ Error cargando día {dia_id}: {e}")
            dias_semana.append({
                'id': dia_id,
                'nombre': nombres_dias[dia_id-1],
                'config': {
                    'activo': False,  # ✅ Por defecto INACTIVO
                    'hora_inicio': '09:00',
                    'hora_fin': '19:00',
                    'almuerzo_inicio': '',
                    'almuerzo_fin': ''
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
                # ✅ CORRECCIÓN CRÍTICA: Los checkboxes solo se envían cuando están CHECKED
                # Si no está en el request.form, significa que está DESACTIVADO
                activo = f'dia_{dia_id}_activo' in request.form
                hora_inicio = request.form.get(f'dia_{dia_id}_inicio', '09:00')
                hora_fin = request.form.get(f'dia_{dia_id}_fin', '19:00')
                almuerzo_inicio = request.form.get(f'dia_{dia_id}_descanso_inicio', '')
                almuerzo_fin = request.form.get(f'dia_{dia_id}_descanso_fin', '')
                
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
                print(f"  Día {h['dia_id']} ({nombres_dias[h['dia_id']-1]}): {h['activo']} - {h['hora_inicio']} a {h['hora_fin']}")
            
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
    """Editar servicio del negocio"""
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_servicios'))
    
    servicio = db.obtener_servicio_por_id(servicio_id, session['negocio_id'])
    if not servicio:
        flash('Servicio no encontrado', 'error')
        return redirect(url_for('negocio_servicios'))
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        duracion = int(request.form['duracion'])
        precio = float(request.form['precio'])
        descripcion = request.form.get('descripcion', '')
        activo = 'activo' in request.form
        
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
    """Editar plantilla del negocio"""
    negocio_id = session['negocio_id']
    
    # ✅ USAR LA FUNCIÓN CORREGIDA
    plantilla_actual = db.obtener_plantilla(negocio_id, nombre_plantilla)
    
    print(f"🔍 EDITAR PLANTILLA - plantilla_actual recibida: {plantilla_actual}")
    print(f"🔍 EDITAR PLANTILLA - tipo: {type(plantilla_actual)}")
    
    if not plantilla_actual:
        flash('❌ Error: Nombre de plantilla inválido. Por favor, contacta al administrador.', 'error')
        return redirect(url_for('negocio_plantillas'))
    
    # Verificar que tenemos un diccionario completo
    if not isinstance(plantilla_actual, dict) or 'plantilla' not in plantilla_actual:
        print(f"❌ EDITAR PLANTILLA - plantilla_actual no es un diccionario válido: {plantilla_actual}")
        flash('❌ Error: Estructura de plantilla inválida.', 'error')
        return redirect(url_for('negocio_plantillas'))
    
    if request.method == 'POST':
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_plantillas'))
        
        nueva_plantilla = request.form.get('plantilla')
        descripcion = request.form.get('descripcion', '')
        
        # Guardar plantilla personalizada
        if db.guardar_plantilla_personalizada(negocio_id, nombre_plantilla, nueva_plantilla, descripcion):
            flash('✅ Plantilla actualizada exitosamente', 'success')
            return redirect(url_for('negocio_plantillas'))
        else:
            flash('❌ Error al actualizar la plantilla', 'error')
    
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
    """Crear nuevo profesional"""
    if session['usuario_rol'] != 'propietario':
        return redirect(url_for('login'))
    
    servicios = obtener_servicios_por_negocio(session['negocio_id'])
    
    if request.method == 'POST':
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('negocio_nuevo_profesional'))
        
        nombre = request.form['nombre']
        especialidad = request.form.get('especialidad', '')
        pin = request.form['pin']
        servicios_seleccionados = request.form.getlist('servicios')
        activo = 'activo' in request.form
        
        # Crear profesional
        profesional_id = crear_profesional(
            negocio_id=session['negocio_id'],
            nombre=nombre,
            especialidad=especialidad,
            pin=pin,
            servicios_ids=servicios_seleccionados,
            activo=activo
        )
        
        if profesional_id:
            flash('Profesional creado exitosamente', 'success')
            return redirect(url_for('negocio_profesionales'))
        else:
            flash('Error al crear el profesional', 'error')
    
    return render_template('negocio/nuevo_profesional.html', servicios=servicios)

@app.route('/negocio/profesionales/editar/<int:profesional_id>', methods=['GET', 'POST'])
@login_required
def negocio_editar_profesional(profesional_id):
    """Editar profesional existente"""
    if session['usuario_rol'] != 'propietario':
        return redirect(url_for('login'))
    
    profesional = obtener_profesional_por_id(profesional_id, session['negocio_id'])
    servicios = obtener_servicios_por_negocio(session['negocio_id'])
    
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
        pin = request.form['pin']
        servicios_seleccionados = request.form.getlist('servicios')
        activo = 'activo' in request.form
        
        # Actualizar profesional
        if actualizar_profesional(
            profesional_id=profesional_id,
            nombre=nombre,
            especialidad=especialidad,
            pin=pin,
            servicios_ids=servicios_seleccionados,
            activo=activo
        ):
            flash('Profesional actualizado exitosamente', 'success')
            return redirect(url_for('negocio_profesionales'))
        else:
            flash('Error al actualizar el profesional', 'error')
    
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
        fecha = request.args.get('fecha', datetime.now().strftime('%Y-%m-%d'))
        
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
                            fecha=datetime.now().strftime('%Y-%m-%d'))
    
@app.route('/profesional/estadisticas')
@role_required(['profesional', 'propietario', 'superadmin'])
def profesional_estadisticas():
    """Estadísticas del profesional"""
    try:
        negocio_id = session.get('negocio_id', 1)
        profesional_id = request.args.get('profesional_id', session.get('profesional_id'))
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        # Obtener estadísticas del profesional
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Estadísticas básicas
        cursor.execute('''
            SELECT COUNT(*) as total_citas,
                   SUM(CASE WHEN estado = 'completada' THEN 1 ELSE 0 END) as completadas,
                   SUM(CASE WHEN estado = 'confirmada' THEN 1 ELSE 0 END) as confirmadas,
                   SUM(CASE WHEN estado = 'cancelada' THEN 1 ELSE 0 END) as canceladas,
                   COALESCE(SUM(s.precio), 0) as ingresos_totales
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.profesional_id = %s AND c.negocio_id = %s
        ''', (profesional_id, negocio_id))
        
        stats = cursor.fetchone()
        
        # Citas de esta semana
        cursor.execute('''
            SELECT COUNT(*) 
            FROM citas 
            WHERE profesional_id = %s AND negocio_id = %s 
            AND fecha >= CURRENT_DATE - INTERVAL '7 days'
        ''', (profesional_id, negocio_id))
        
        citas_semana = cursor.fetchone()[0]
        
        # Servicios más populares
        cursor.execute('''
            SELECT s.nombre, COUNT(*) as cantidad
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.profesional_id = %s AND c.negocio_id = %s
            GROUP BY s.id, s.nombre
            ORDER BY cantidad DESC
            LIMIT 5
        ''', (profesional_id, negocio_id))
        
        servicios_populares = cursor.fetchall()
        
        conn.close()
        
        estadisticas = {
            'total_citas': stats[0] if stats else 0,
            'completadas': stats[1] if stats else 0,
            'confirmadas': stats[2] if stats else 0,
            'canceladas': stats[3] if stats else 0,
            'ingresos_totales': float(stats[4]) if stats else 0,
            'citas_semana': citas_semana,
            'servicios_populares': [{'nombre': s[0], 'cantidad': s[1]} for s in servicios_populares],
            'tasa_exito': round((stats[1] / stats[0] * 100), 2) if stats and stats[0] > 0 else 0
        }
        
        return render_template('profesional/estadisticas.html',
                            estadisticas=estadisticas,
                            profesional_id=profesional_id)
        
    except Exception as e:
        print(f"❌ Error en profesional_estadisticas: {e}")
        flash('Error al cargar las estadísticas', 'error')
        return redirect(url_for('profesional_dashboard'))
    
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
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
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
    """Crear cita desde el panel del profesional"""
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
        
        if not all([cliente_nombre, cliente_telefono, servicio_id, fecha, hora, profesional_id]):
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('profesional_agendar'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar disponibilidad
        cursor.execute('''
            SELECT id FROM citas 
            WHERE profesional_id = %s AND fecha = %s AND hora = %s AND estado != 'cancelada'
        ''', (profesional_id, fecha, hora))
        
        cita_existente = cursor.fetchone()
        if cita_existente:
            flash('❌ Ya existe una cita en ese horario', 'error')
            conn.close()
            return redirect(url_for('profesional_agendar'))
        
        # Crear la cita
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmada', CURRENT_TIMESTAMP)
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
        
        cita_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        
        flash('✅ Cita agendada exitosamente', 'success')
        return redirect(url_for('profesional_dashboard'))
        
    except Exception as e:
        print(f"❌ Error creando cita: {e}")
        flash('❌ Error al agendar la cita', 'error')
        return redirect(url_for('profesional_agendar'))

@app.route('/profesional/completar-cita/<int:cita_id>', methods=['POST'])
@role_required(['profesional', 'propietario', 'superadmin'])
def completar_cita(cita_id):
    """Marcar cita como completada desde el panel del profesional"""
    try:
        # Validar CSRF
        if not validate_csrf_token(request.form.get('csrf_token', '')):
            flash('Error de seguridad. Por favor, intenta nuevamente.', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar que la cita pertenece al profesional
        cursor.execute('''
            SELECT id FROM citas 
            WHERE id = %s AND profesional_id = %s AND negocio_id = %s
        ''', (cita_id, profesional_id, negocio_id))
        
        if not cursor.fetchone():
            flash('❌ Cita no encontrada', 'error')
            conn.close()
            return redirect(url_for('profesional_dashboard'))
        
        # Actualizar estado a completada
        cursor.execute('''
            UPDATE citas 
            SET estado = 'completada' 
            WHERE id = %s
        ''', (cita_id,))
        
        conn.commit()
        conn.close()
        
        flash('✅ Cita marcada como completada', 'success')
        return redirect(url_for('profesional_dashboard') + '?completed=true')
        
    except Exception as e:
        print(f"❌ Error completando cita: {e}")
        flash('❌ Error al completar la cita', 'error')
        return redirect(url_for('profesional_dashboard'))

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
        fecha = datetime.now().strftime('%Y-%m-%d')
    
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
    
    return jsonify([{
        'id': c['id'],
        'cliente_nombre': c['cliente_nombre'] or 'No especificado',
        'cliente_telefono': c['cliente_telefono'],
        'fecha': c['fecha'].strftime('%Y-%m-%d') if c['fecha'] else '',
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
        mes = request.args.get('mes', datetime.now().month)
        año = request.args.get('año', datetime.now().year)
        
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
    """API para obtener horarios disponibles"""
    try:
        profesional_id = request.args.get('profesional_id')
        fecha = request.args.get('fecha')
        servicio_id = request.args.get('servicio_id')
        
        if not all([profesional_id, fecha, servicio_id]):
            return jsonify({'error': 'Parámetros incompletos'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Obtener duración del servicio
        cursor.execute('SELECT duracion FROM servicios WHERE id = %s', (servicio_id,))
        servicio = cursor.fetchone()
        
        if not servicio:
            conn.close()
            return jsonify({'error': 'Servicio no encontrado'}), 404
        
        duracion = servicio[0]
        
        # Generar horarios disponibles (de 8:00 a 20:00)
        horarios_disponibles = []
        hora_actual = 8  # 8:00 AM
        hora_fin = 20    # 8:00 PM
        
        while hora_actual < hora_fin:
            hora_str = f"{hora_actual:02d}:00"
            
            # Verificar disponibilidad usando columnas separadas fecha y hora
            cursor.execute('''
                SELECT id FROM citas 
                WHERE profesional_id = %s AND fecha = %s AND hora = %s AND estado != 'cancelada'
            ''', (profesional_id, fecha, hora_str))
            
            if not cursor.fetchone():
                horarios_disponibles.append(hora_str)
            
            hora_actual += 1
        
        conn.close()
        
        return jsonify({
            'horarios': horarios_disponibles,
            'duracion': duracion
        })
        
    except Exception as e:
        print(f"❌ Error en api_horarios_disponibles: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

# =============================================================================
# RUTAS DE DEBUG Y TEST
# =============================================================================

@app.route('/debug-session')
def debug_session():
    """Debug de la sesión actual"""
    return jsonify(dict(session))

# =============================================================================
# RUTA SIMPLE DE DEBUG PARA CONTRASEÑAS
# =============================================================================

@app.route('/debug/passwords')
def debug_passwords():
    """Ruta simple para ver estado de contraseñas"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, email, password, nombre FROM usuarios")
        usuarios = cursor.fetchall()
        conn.close()
        
        resultados = []
        
        for usuario in usuarios:
            usuario_id, email, password, nombre = usuario
            
            if not password:
                estado = "❌ VACÍA"
            elif password.startswith('$5$') or password.startswith('$6$'):
                estado = "✅ SHA256_CRYPT"
            elif password.startswith('pbkdf2:sha256:'):
                estado = "🔀 WERKZEUG"
            elif len(password) < 60:
                estado = "🔓 TEXTO PLANO"
            else:
                estado = "❓ DESCONOCIDO"
            
            resultados.append(f"{estado} - {email}: {password[:30]}...")
        
        return f"""
        <h1>🔧 Estado de Contraseñas</h1>
        <p><strong>Total usuarios:</strong> {len(usuarios)}</p>
        <hr>
        <pre>{chr(10).join(resultados)}</pre>
        <hr>
        <p><strong>Usuarios con TEXTO PLANO necesitan migración</strong></p>
        """
        
    except Exception as e:
        return f"❌ Error: {str(e)}"

@app.route('/debug/reset-password/<int:usuario_id>')
def debug_reset_password(usuario_id):
    """Resetear contraseña de usuario específico a '123456' con sha256_crypt"""
    try:
        # Clave simple de seguridad
        auth_key = request.args.get('key', '')
        if auth_key != 'reset2024':
            return "❌ No autorizado. Usa: /debug/reset-password/USUARIO_ID?key=reset2024"
        
        # Generar hash sha256_crypt manualmente (sin passlib)
        import hashlib
        import secrets
        
        # Crear un hash similar a sha256_crypt
        salt = secrets.token_hex(8)
        password_plain = "123456"
        
        # Hash simple (esto es temporal, deberías instalar passlib después)
        hash_obj = hashlib.sha256()
        hash_obj.update(f"{password_plain}{salt}".encode())
        password_hash = f"sha256${salt}${hash_obj.hexdigest()}"
        
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Verificar que el usuario existe
        cursor.execute("SELECT email, nombre FROM usuarios WHERE id = %s", (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            conn.close()
            return f"❌ Usuario {usuario_id} no encontrado"
        
        email, nombre = usuario
        
        # Actualizar contraseña
        cursor.execute(
            "UPDATE usuarios SET password = %s WHERE id = %s",
            (password_hash, usuario_id)
        )
        
        conn.commit()
        conn.close()
        
        return f"""
        <h1>✅ Contraseña Reseteada</h1>
        <p><strong>Usuario:</strong> {nombre} ({email})</p>
        <p><strong>Nueva contraseña:</strong> 123456</p>
        <p><strong>Hash generado:</strong> {password_hash[:50]}...</p>
        <hr>
        <p><a href="/debug/passwords">← Volver al estado</a></p>
        """
        
    except Exception as e:
        return f"❌ Error: {str(e)}"

@app.route('/debug/simple-fix')
def debug_simple_fix():
    """Solución simple: resetear todas las contraseñas problemáticas"""
    try:
        auth_key = request.args.get('key', '')
        if auth_key != 'fix2024':
            return "❌ No autorizado. Usa: /debug/simple-fix?key=fix2024"
        
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, email, password, nombre FROM usuarios")
        usuarios = cursor.fetchall()
        
        resultados = []
        reseteados = 0
        
        for usuario in usuarios:
            usuario_id, email, password, nombre = usuario
            
            # Si no tiene contraseña o es texto plano, resetear
            if not password or (len(password) < 60 and not password.startswith('$')):
                # Generar hash simple
                import hashlib
                import secrets
                
                salt = secrets.token_hex(8)
                password_plain = "123456"
                hash_obj = hashlib.sha256()
                hash_obj.update(f"{password_plain}{salt}".encode())
                password_hash = f"sha256${salt}${hash_obj.hexdigest()}"
                
                # Actualizar
                cursor.execute(
                    "UPDATE usuarios SET password = %s WHERE id = %s",
                    (password_hash, usuario_id)
                )
                
                reseteados += 1
                resultados.append(f"✅ {email}: Reset a '123456'")
            else:
                resultados.append(f"✅ {email}: OK ({password[:20]}...)")
        
        conn.commit()
        conn.close()
        
        return f"""
        <h1>🔧 Fix Simple Completado</h1>
        <p><strong>Total usuarios:</strong> {len(usuarios)}</p>
        <p><strong>Contraseñas reseteadas:</strong> {reseteados}</p>
        <hr>
        <h3>Resultados:</h3>
        <pre>{chr(10).join(resultados)}</pre>
        <hr>
        <p><strong>Todas las contraseñas reseteadas son: 123456</strong></p>
        <p><a href="/login">→ Ir al login</a></p>
        """
        
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =============================================================================
# INICIALIZACIÓN - EJECUTAR SIEMPRE
# =============================================================================

def initialize_app():
    """Inicializar la aplicación - EJECUTAR SIEMPRE"""
    print("🚀 INICIALIZANDO APLICACIÓN...")
    
    try:
        db.init_db()
        print("✅ Base de datos inicializada")
    except Exception as e:
        print(f"⚠️ Error en init_db: {e}")

    try:
        scheduler_thread = threading.Thread(target=iniciar_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        print("✅ Scheduler iniciado")
    except Exception as e:
        print(f"⚠️ Error en scheduler: {e}")

# ✅ INICIALIZAR SIEMPRE - SIN IMPORTAR CÓMO SE CARGUE EL MÓDULO
print("🔧 INICIALIZANDO APLICACIÓN FLASK...")
initialize_app()

# ✅ SALTO DE LÍNEA OBLIGATORIO AQUÍ
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🎯 INICIANDO SERVIDOR EN PUERTO {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)