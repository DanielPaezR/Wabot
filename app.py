# =============================================================================
# ARCHIVO COMPLETO - app.py SISTEMA GENÉRICO DE CITAS
# =============================================================================

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta
import database as db
from whatsapp_handler import whatsapp_bp
import os
from dotenv import load_dotenv
import threading
from scheduler import iniciar_scheduler
import json
from functools import wraps

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'negocio-secret-key')

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
# FUNCIONES PARA GESTIÓN DE PROFESIONALES
# =============================================================================

def obtener_profesionales_por_negocio(negocio_id):
    """Obtener todos los profesionales de un negocio"""
    conn = sqlite3.connect('negocio.db')
    conn.row_factory = sqlite3.Row
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

def obtener_servicios_por_negocio(negocio_id):
    """Obtener todos los servicios de un negocio"""
    conn = sqlite3.connect('negocio.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM servicios 
        WHERE negocio_id = ? AND activo = 1
        ORDER BY nombre
    ''', (negocio_id,))
    
    servicios = [dict(servicio) for servicio in cursor.fetchall()]
    conn.close()
    return servicios

def obtener_profesional_por_id(profesional_id, negocio_id):
    """Obtener un profesional específico con sus servicios"""
    conn = sqlite3.connect('negocio.db')
    conn.row_factory = sqlite3.Row
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
    conn = sqlite3.connect('negocio.db')
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
    conn = sqlite3.connect('negocio.db')
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
    conn = sqlite3.connect('negocio.db')
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
            if usuario['rol'] == 'profesional':  # ✅ Ahora es 'profesional'
                if 'profesional_id' in session:
                    del session['profesional_id']
                
                conn = sqlite3.connect('negocio.db')
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT id, nombre FROM profesionales WHERE usuario_id = ? AND negocio_id = ?', 
                    (usuario['id'], usuario['negocio_id'])
                )
                profesional = cursor.fetchone()
                
                if profesional:
                    session['profesional_id'] = profesional[0]
                    print(f"✅ PROFESIONAL ENCONTRADO: {profesional[1]} (ID: {profesional[0]})")
                else:
                    cursor.execute(
                        'SELECT id, nombre FROM profesionales WHERE nombre = ? AND negocio_id = ?', 
                        (usuario['nombre'], usuario['negocio_id'])
                    )
                    profesional = cursor.fetchone()
                    
                    if profesional:
                        session['profesional_id'] = profesional[0]
                    else:
                        cursor.execute(
                            'SELECT id FROM profesionales WHERE negocio_id = ? AND activo = TRUE LIMIT 1', 
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
            elif usuario['rol'] == 'profesional':  # ✅ Ahora es 'profesional'
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
    
    usuarios_recientes = db.obtener_usuarios_todos()[:8]  # Solo los primeros 8
    
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
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    try:
        # En lugar de eliminar, desactivamos el negocio
        cursor.execute('''
            UPDATE negocios 
            SET activo = FALSE 
            WHERE id = ?
        ''', (negocio_id,))
        
        # También desactivamos los usuarios asociados
        cursor.execute('''
            UPDATE usuarios 
            SET activo = FALSE 
            WHERE negocio_id = ?
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
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    try:
        # Reactivar el negocio
        cursor.execute('''
            UPDATE negocios 
            SET activo = TRUE 
            WHERE id = ?
        ''', (negocio_id,))
        
        # También reactivar los usuarios asociados
        cursor.execute('''
            UPDATE usuarios 
            SET activo = TRUE 
            WHERE negocio_id = ?
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

# =============================================================================
# RUTAS PARA GESTIÓN DE USUARIOS (ACTIVAR/DESACTIVAR)
# =============================================================================

@app.route('/admin/usuarios/<int:usuario_id>/toggle', methods=['POST'])
@role_required(['superadmin'])
def admin_toggle_usuario(usuario_id):
    """Activar o desactivar un usuario"""
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    try:
        # Obtener estado actual del usuario
        cursor.execute('SELECT activo FROM usuarios WHERE id = ?', (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('❌ Usuario no encontrado', 'error')
            return redirect(url_for('admin_usuarios'))
        
        nuevo_estado = not usuario[0]  # Invertir estado
        
        # Actualizar estado
        cursor.execute('''
            UPDATE usuarios 
            SET activo = ? 
            WHERE id = ?
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
    # Prevenir eliminación del superadmin principal
    if usuario_id == 1:  # ID del superadmin principal
        flash('❌ No se puede eliminar el superadministrador principal', 'error')
        return redirect(url_for('admin_usuarios'))
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    try:
        # Verificar si el usuario existe
        cursor.execute('SELECT rol FROM usuarios WHERE id = ?', (usuario_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('❌ Usuario no encontrado', 'error')
            return redirect(url_for('admin_usuarios'))
        
        # Si es profesional, también eliminar de la tabla profesionales
        if usuario[0] == 'profesional':
            cursor.execute('''
                DELETE FROM profesionales 
                WHERE usuario_id = ?
            ''', (usuario_id,))
        
        # Eliminar usuario
        cursor.execute('DELETE FROM usuarios WHERE id = ?', (usuario_id,))
        
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
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    # Obtener usuario actual
    cursor.execute('''
        SELECT u.*, n.nombre as negocio_nombre 
        FROM usuarios u 
        JOIN negocios n ON u.negocio_id = n.id 
        WHERE u.id = ?
    ''', (usuario_id,))
    
    usuario = cursor.fetchone()
    
    if not usuario:
        flash('❌ Usuario no encontrado', 'error')
        conn.close()
        return redirect(url_for('admin_usuarios'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        rol = request.form.get('rol')
        negocio_id = request.form.get('negocio_id')
        activo = request.form.get('activo') == 'on'
        
        try:
            # Actualizar usuario
            cursor.execute('''
                UPDATE usuarios 
                SET nombre = ?, email = ?, rol = ?, negocio_id = ?, activo = ?
                WHERE id = ?
            ''', (nombre, email, rol, negocio_id, activo, usuario_id))
            
            # Si es profesional, actualizar también en la tabla profesionales
            if rol == 'profesional':
                cursor.execute('''
                    SELECT id FROM profesionales WHERE usuario_id = ?
                ''', (usuario_id,))
                
                profesional = cursor.fetchone()
                
                if profesional:
                    # Actualizar profesional existente
                    cursor.execute('''
                        UPDATE profesionales 
                        SET nombre = ?
                        WHERE usuario_id = ?
                    ''', (nombre, usuario_id))
                else:
                    # Crear nuevo profesional
                    cursor.execute('''
                        INSERT INTO profesionales (negocio_id, nombre, especialidad, pin, usuario_id, activo)
                        VALUES (?, ?, ?, ?, ?, ?)
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
        nueva_plantilla = request.form.get('plantilla')
        descripcion = request.form.get('descripcion')
        
        # Actualizar plantilla base
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE plantillas_mensajes 
                SET plantilla = ?, descripcion = ?
                WHERE nombre = ? AND es_base = TRUE
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
    conn = sqlite3.connect('negocio.db')
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
                VALUES (NULL, ?, ?, ?, ?, TRUE)
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
    
    conn = sqlite3.connect('negocio.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.id, c.cliente_nombre, c.hora, s.nombre as servicio, p.nombre as profesional, c.estado
        FROM citas c
        JOIN servicios s ON c.servicio_id = s.id
        JOIN profesionales p ON c.profesional_id = p.id
        WHERE c.negocio_id = ? AND c.fecha = ? AND c.estado != 'cancelado'
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

@app.route('/negocio/configuracion', methods=['GET', 'POST'])
@role_required(['propietario', 'superadmin'])
def negocio_configuracion():
    """Configuración de horarios"""
    negocio_id = session.get('negocio_id', 1)
    
    if request.method == 'POST':
        configuraciones = {}
        
        dias_semana = [
            {'id': 0, 'nombre': 'Lunes'}, {'id': 1, 'nombre': 'Martes'}, 
            {'id': 2, 'nombre': 'Miércoles'}, {'id': 3, 'nombre': 'Jueves'},
            {'id': 4, 'nombre': 'Viernes'}, {'id': 5, 'nombre': 'Sábado'},
            {'id': 6, 'nombre': 'Domingo'}
        ]
        
        for dia in dias_semana:
            dia_id = dia['id']
            activo = request.form.get(f'dia_{dia_id}_activo') == 'on'
            hora_inicio = request.form.get(f'dia_{dia_id}_inicio', '09:00')
            hora_fin = request.form.get(f'dia_{dia_id}_fin', '19:00')
            almuerzo_inicio = request.form.get(f'dia_{dia_id}_almuerzo_inicio', '')
            almuerzo_fin = request.form.get(f'dia_{dia_id}_almuerzo_fin', '')
            
            if not activo:
                almuerzo_inicio = None
                almuerzo_fin = None
            
            configuraciones[dia_id] = {
                'activo': activo,
                'hora_inicio': hora_inicio,
                'hora_fin': hora_fin,
                'almuerzo_inicio': almuerzo_inicio if almuerzo_inicio else None,
                'almuerzo_fin': almuerzo_fin if almuerzo_fin else None
            }
        
        if db.actualizar_configuracion_horarios(negocio_id, configuraciones):
            flash('✅ Configuración de horarios actualizada exitosamente', 'success')
        else:
            flash('❌ Error al actualizar la configuración', 'error')
        
        return redirect(url_for('negocio_configuracion'))
    
    config_actual = db.obtener_configuracion_horarios(negocio_id)
    
    dias_semana = [
        {'id': 0, 'nombre': 'Lunes', 'config': config_actual.get(0, {})},
        {'id': 1, 'nombre': 'Martes', 'config': config_actual.get(1, {})},
        {'id': 2, 'nombre': 'Miércoles', 'config': config_actual.get(2, {})},
        {'id': 3, 'nombre': 'Jueves', 'config': config_actual.get(3, {})},
        {'id': 4, 'nombre': 'Viernes', 'config': config_actual.get(4, {})},
        {'id': 5, 'nombre': 'Sábado', 'config': config_actual.get(5, {})},
        {'id': 6, 'nombre': 'Domingo', 'config': config_actual.get(6, {})}
    ]
    
    return render_template('negocio/configuracion.html', 
                         dias_semana=dias_semana,
                         negocio_id=negocio_id)

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

# =============================================================================
# RUTAS PARA GESTIÓN DE SERVICIOS (NEGOCIO)
# =============================================================================

@app.route('/negocio/servicios/nuevo', methods=['GET', 'POST'])
@role_required(['propietario', 'superadmin'])
def negocio_nuevo_servicio():
    """Crear nuevo servicio para el negocio"""
    if session['usuario_rol'] == 'propietario':
        negocio_id = session['negocio_id']
    else:
        negocio_id = request.args.get('negocio_id', session.get('negocio_id', 1))
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        duracion = int(request.form['duracion'])
        precio = float(request.form['precio'])
        descripcion = request.form.get('descripcion', '')
        
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO servicios (negocio_id, nombre, duracion, precio, descripcion)
                VALUES (?, ?, ?, ?, ?)
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
@role_required(['propietario', 'superadmin'])
def negocio_editar_servicio(servicio_id):
    """Editar servicio existente"""
    if session['usuario_rol'] == 'propietario':
        negocio_id = session['negocio_id']
    else:
        negocio_id = request.args.get('negocio_id', session.get('negocio_id', 1))
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    # Obtener servicio actual
    cursor.execute('SELECT * FROM servicios WHERE id = ? AND negocio_id = ?', 
                  (servicio_id, negocio_id))
    servicio = cursor.fetchone()
    
    if not servicio:
        flash('❌ Servicio no encontrado', 'error')
        conn.close()
        return redirect(url_for('negocio_servicios'))
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        duracion = int(request.form['duracion'])
        precio = float(request.form['precio'])
        descripcion = request.form.get('descripcion', '')
        activo = 'activo' in request.form
        
        try:
            cursor.execute('''
                UPDATE servicios 
                SET nombre = ?, duracion = ?, precio = ?, descripcion = ?, activo = ?
                WHERE id = ? AND negocio_id = ?
            ''', (nombre, duracion, precio, descripcion, activo, servicio_id, negocio_id))
            
            conn.commit()
            flash('✅ Servicio actualizado exitosamente', 'success')
            return redirect(url_for('negocio_servicios'))
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error actualizando servicio: {e}")
            flash('❌ Error al actualizar el servicio', 'error')
        finally:
            conn.close()
    else:
        conn.close()
        return render_template('negocio/editar_servicio.html', 
                             servicio=dict(servicio), 
                             negocio_id=negocio_id)

@app.route('/negocio/servicios/<int:servicio_id>/eliminar', methods=['POST'])
@role_required(['propietario', 'superadmin'])
def negocio_eliminar_servicio(servicio_id):
    """Eliminar servicio"""
    if session['usuario_rol'] == 'propietario':
        negocio_id = session['negocio_id']
    else:
        negocio_id = request.args.get('negocio_id', session.get('negocio_id', 1))
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    try:
        # Verificar que el servicio pertenece al negocio
        cursor.execute('SELECT id FROM servicios WHERE id = ? AND negocio_id = ?', 
                      (servicio_id, negocio_id))
        
        if not cursor.fetchone():
            flash('❌ Servicio no encontrado', 'error')
            return redirect(url_for('negocio_servicios'))
        
        # Eliminar relaciones con profesionales primero
        cursor.execute('DELETE FROM profesional_servicios WHERE servicio_id = ?', (servicio_id,))
        
        # Eliminar servicio
        cursor.execute('DELETE FROM servicios WHERE id = ?', (servicio_id,))
        
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
@role_required(['propietario', 'superadmin'])
def negocio_plantillas():
    """Plantillas personalizadas del negocio"""
    negocio_id = session.get('negocio_id', 1)
    
    plantillas = db.obtener_plantillas_unicas_negocio(negocio_id)
    
    for plantilla in plantillas:
        plantilla['es_personalizada'] = (plantilla.get('negocio_id') == negocio_id)
        plantilla['es_base'] = plantilla.get('es_base', False)
    
    return render_template('negocio/plantillas.html', 
                         plantillas=plantillas,
                         negocio_id=negocio_id)

@app.route('/negocio/plantillas/<nombre_plantilla>/editar', methods=['GET', 'POST'])
@role_required(['propietario', 'superadmin'])
def negocio_editar_plantilla(nombre_plantilla):
    """Editar plantilla personalizada del negocio"""
    negocio_id = session.get('negocio_id', 1)
    
    plantilla_actual = db.obtener_plantilla(negocio_id, nombre_plantilla)
    
    if not plantilla_actual:
        flash('Plantilla no encontrada', 'error')
        return redirect(url_for('negocio_plantillas'))
    
    if request.method == 'POST':
        nueva_plantilla = request.form.get('plantilla')
        descripcion = request.form.get('descripcion')
        
        if db.actualizar_plantilla_negocio(negocio_id, nombre_plantilla, nueva_plantilla, descripcion):
            flash('✅ Plantilla personalizada actualizada exitosamente', 'success')
            return redirect(url_for('negocio_plantillas'))
        else:
            flash('❌ Error al actualizar la plantilla', 'error')
    
    return render_template('negocio/editar_plantilla.html', 
                         plantilla=plantilla_actual,
                         es_personalizada=plantilla_actual.get('negocio_id') == negocio_id)

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
                conn = sqlite3.connect('negocio.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM profesionales WHERE usuario_id = ? AND negocio_id = ?', 
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

        # Obtener citas del profesional - DEBUG
        print(f"🔍 DEBUG - Llamando a db.obtener_citas_para_profesional...")
        citas = db.obtener_citas_para_profesional(negocio_id, profesional_id, fecha)
        print(f"🔍 DEBUG - Citas obtenidas: {len(citas)}")
        for i, cita in enumerate(citas):
            print(f"  Cita {i+1}: {cita}")
        
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
        
        # Obtener estadísticas del profesional - CORREGIDO
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Estadísticas básicas - USAR fecha Y hora en lugar de fecha_hora
        cursor.execute('''
            SELECT COUNT(*) as total_citas,
                   SUM(CASE WHEN estado = 'completada' THEN 1 ELSE 0 END) as completadas,
                   SUM(CASE WHEN estado = 'confirmada' THEN 1 ELSE 0 END) as confirmadas,
                   SUM(CASE WHEN estado = 'cancelada' THEN 1 ELSE 0 END) as canceladas,
                   COALESCE(SUM(s.precio), 0) as ingresos_totales
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.profesional_id = ? AND c.negocio_id = ?
        ''', (profesional_id, negocio_id))
        
        stats = cursor.fetchone()
        
        # Citas de esta semana - CORREGIDO
        cursor.execute('''
            SELECT COUNT(*) 
            FROM citas 
            WHERE profesional_id = ? AND negocio_id = ? 
            AND date(fecha || ' ' || hora) >= date('now', 'start of day', 'weekday 0', '-7 days')
        ''', (profesional_id, negocio_id))
        
        citas_semana = cursor.fetchone()[0]
        
        # Servicios más populares
        cursor.execute('''
            SELECT s.nombre, COUNT(*) as cantidad
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.profesional_id = ? AND c.negocio_id = ?
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
        
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Obtener todas las citas del profesional
        cursor.execute('''
            SELECT c.*, s.nombre as servicio_nombre, s.precio
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.profesional_id = ? AND c.negocio_id = ?
            ORDER BY c.fecha DESC, c.hora DESC
        ''', (profesional_id, negocio_id))
        
        citas = []
        for row in cursor.fetchall():
            citas.append(dict(
                id=row[0],
                negocio_id=row[1],
                profesional_id=row[2],
                cliente_telefono=row[3],
                cliente_nombre=row[4],
                fecha=row[5],
                hora=row[6],
                servicio_id=row[7],
                estado=row[8],
                servicio_nombre=row[12],
                precio=row[13]
            ))
        
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
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, nombre, duracion, precio 
            FROM servicios 
            WHERE negocio_id = ? AND activo = 1
            ORDER BY nombre
        ''', (negocio_id,))
        
        servicios = [dict(id=row[0], nombre=row[1], precio=row[3]) for row in cursor.fetchall()]
        
        conn.close()
        
        # Fecha de hoy para el mínimo del datepicker
        from datetime import datetime
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        return render_template('profesional/agendar_cita.html',  # ✅ Usa tu template existente
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
        # Debug: ver todos los datos del formulario
        print("🔍 DEBUG - Datos del formulario recibidos:")
        for key, value in request.form.items():
            print(f"  {key}: {value}")
        
        cliente_nombre = request.form.get('cliente_nombre')
        cliente_telefono = request.form.get('cliente_telefono')
        servicio_id = request.form.get('servicio_id')
        fecha = request.form.get('fecha')
        hora = request.form.get('hora')
        
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        
        print(f"🔍 DEBUG - Session data: profesional_id={profesional_id}, negocio_id={negocio_id}")
        
        if not all([cliente_nombre, cliente_telefono, servicio_id, fecha, hora, profesional_id]):
            print("❌ DEBUG - Faltan campos requeridos")
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('profesional_agendar'))
        
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Verificar disponibilidad
        cursor.execute('''
            SELECT id FROM citas 
            WHERE profesional_id = ? AND fecha = ? AND hora = ? AND estado != 'cancelada'
        ''', (profesional_id, fecha, hora))
        
        cita_existente = cursor.fetchone()
        if cita_existente:
            print(f"❌ DEBUG - Ya existe cita en {fecha} {hora}")
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmada', CURRENT_TIMESTAMP)
        ''', (
            negocio_id, 
            profesional_id, 
            cliente_telefono, 
            cliente_nombre, 
            fecha, 
            hora, 
            servicio_id
        ))
        
        cita_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ DEBUG - Cita creada exitosamente. ID: {cita_id}")
        flash('✅ Cita agendada exitosamente', 'success')
        return redirect(url_for('profesional_dashboard'))
        
    except Exception as e:
        print(f"❌ DEBUG - Error creando cita: {e}")
        import traceback
        traceback.print_exc()
        flash('❌ Error al agendar la cita', 'error')
        return redirect(url_for('profesional_agendar'))

@app.route('/profesional/completar-cita/<int:cita_id>', methods=['POST'])
@role_required(['profesional', 'propietario', 'superadmin'])
def completar_cita(cita_id):
    """Marcar cita como completada desde el panel del profesional"""
    try:
        profesional_id = session.get('profesional_id')
        negocio_id = session.get('negocio_id')
        
        if not profesional_id:
            flash('No se pudo identificar al profesional', 'error')
            return redirect(url_for('profesional_dashboard'))
        
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Verificar que la cita pertenece al profesional
        cursor.execute('''
            SELECT id FROM citas 
            WHERE id = ? AND profesional_id = ? AND negocio_id = ?
        ''', (cita_id, profesional_id, negocio_id))
        
        if not cursor.fetchone():
            flash('❌ Cita no encontrada', 'error')
            conn.close()
            return redirect(url_for('profesional_dashboard'))
        
        # Actualizar estado a completada
        cursor.execute('''
            UPDATE citas 
            SET estado = 'completada' 
            WHERE id = ?
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
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    query = '''
        SELECT c.id, c.cliente_nombre, c.cliente_telefono, c.fecha, c.hora, 
               s.nombre as servicio, c.estado, p.nombre as profesional_nombre
        FROM citas c
        JOIN servicios s ON c.servicio_id = s.id
        JOIN profesionales p ON c.profesional_id = p.id
        WHERE c.negocio_id = ? AND c.fecha = ?
    '''
    
    params = [negocio_id, fecha]
    
    if profesional_id and profesional_id != '':
        query += ' AND c.profesional_id = ?'
        params.append(profesional_id)
    
    query += ' ORDER BY c.hora'
    
    if limit:
        query += ' LIMIT ?'
        params.append(int(limit))
    
    cursor.execute(query, params)
    citas = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        'id': c[0],
        'cliente_nombre': c[1] or 'No especificado',
        'cliente_telefono': c[2],
        'fecha': c[3],
        'hora': c[4],
        'servicio': c[5],
        'estado': c[6],
        'profesional_nombre': c[7]
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
    
    conn = sqlite3.connect('negocio.db')
    cursor = conn.cursor()
    
    if usuario_rol == 'profesional':
        cursor.execute('SELECT profesional_id FROM citas WHERE id = ?', (cita_id,))
        cita = cursor.fetchone()
        if not cita or cita[0] != profesional_id:
            conn.close()
            return jsonify({'error': 'No autorizado'}), 403
    
    cursor.execute('UPDATE citas SET estado = "completado" WHERE id = ?', (cita_id,))
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
        
        conn = sqlite3.connect('negocio.db')
        cursor = conn.cursor()
        
        # Obtener duración del servicio
        cursor.execute('SELECT duracion FROM servicios WHERE id = ?', (servicio_id,))
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
                WHERE profesional_id = ? AND fecha = ? AND hora = ? AND estado != 'cancelada'
            ''', (profesional_id, fecha, hora_str))
            
            if not cursor.fetchone():
                horarios_disponibles.append(hora_str)
            
            hora_actual += 1
        
        conn.close()
        
        print(f"✅ Horarios disponibles para {fecha}: {horarios_disponibles}")
        
        return jsonify({
            'horarios': horarios_disponibles,
            'duracion': duracion
        })
        
    except Exception as e:
        print(f"❌ Error en api_horarios_disponibles: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Error interno del servidor'}), 500
    


# =============================================================================
# RUTAS DE DEBUG Y TEST
# =============================================================================



@app.route('/')
def index():
    """Página principal - Redirigir según autenticación"""
    if 'usuario_id' in session:
        return redirect(url_for(get_redirect_url_by_role(session.get('usuario_rol'))))
    else:
        return redirect(url_for('login'))

@app.route('/test')
def test_endpoint():
    return "✅ El servidor Flask está funcionando correctamente!"

@app.route('/debug-session')
def debug_session():
    """Debug de la sesión actual"""
    return jsonify(dict(session))

# =============================================================================
# INICIALIZACIÓN
# =============================================================================

if __name__ == '__main__':
    # Inicializar base de datos
    db.init_db()
    
    # Iniciar scheduler en hilo separado
    try:
        scheduler_thread = threading.Thread(target=iniciar_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        print("✅ Scheduler de recordatorios iniciado en segundo plano")
    except Exception as e:
        print(f"⚠️ No se pudo iniciar el scheduler: {e}")
    
    # Iniciar aplicación
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)