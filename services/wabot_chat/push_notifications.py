# push_notifications.py - VERSIÓN COMPLETA CON SOPORTE PARA CLIENTES
import os
import json
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, session
from pywebpush import webpush, WebPushException

push_bp = Blueprint('push', __name__)

# Configurar webpush
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', '')

def get_db_connection():
    """Obtener conexión a la base de datos"""
    from database import get_db_connection as db_conn
    return db_conn()

def _es_suscripcion_muerta(webpush_exception):
    """404/410 significa que el navegador invalidó la suscripción: ya no sirve reintentar"""
    response = getattr(webpush_exception, 'response', None)
    # OJO: bool(response) es False para respuestas 4xx/5xx de requests, por eso se compara con None
    return response is not None and response.status_code in (404, 410)

def _desactivar_suscripcion(tabla, suscripcion_id):
    """Marcar una suscripción push como inactiva para dejar de reintentarle envíos muertos"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'UPDATE {tabla} SET activa = FALSE WHERE id = %s', (suscripcion_id,))
        conn.commit()
        conn.close()
        print(f"🗑️ Suscripción {suscripcion_id} de {tabla} desactivada (expirada/inválida)")
    except Exception as e:
        print(f"⚠️ Error desactivando suscripción {suscripcion_id}: {e}")

def _clave_privada():
    return (os.getenv('VAPID_PRIVATE_KEY') or '').strip()


def _vapid_subject():
    """Identificación que exigen los servicios push (mailto: o https://). Apple rechaza el envío si está vacía."""
    s = (os.getenv('VAPID_SUBJECT') or '').strip()
    if s.startswith('mailto:') or s.startswith('https://'):
        return s
    if '@' in s:
        return 'mailto:' + s
    return (os.getenv('APP_BASE_URL') or 'https://wabot-production-d544.up.railway.app').strip()


def _enviar_a_suscripciones(tabla, suscripciones, payload, ttl=86400):
    """Envía ``payload`` a TODOS los dispositivos. Devuelve (enviados, fallidos).

    - Cada envío lleva sus propios claims VAPID: pywebpush les añade el destino ('aud') del servicio push, y
      reutilizar el mismo diccionario hacía que los dispositivos de otro servicio (Android/Apple/Firefox) fallaran.
    - Las suscripciones que el servicio da por muertas (404/410) se desactivan para no reintentarlas.
    """
    clave = _clave_privada()
    if not clave:
        print("⚠️ VAPID_PRIVATE_KEY no configurada: push omitido")
        return 0, len(suscripciones)
    cuerpo = json.dumps(payload, ensure_ascii=False)
    enviados = fallidos = 0
    for s in suscripciones:
        try:
            info = s.get('subscription_json')
            info = json.loads(info) if isinstance(info, str) else info
            webpush(subscription_info=info, data=cuerpo, vapid_private_key=clave,
                    vapid_claims={'sub': _vapid_subject()}, ttl=ttl, timeout=10)
            enviados += 1
        except WebPushException as e:
            fallidos += 1
            if _es_suscripcion_muerta(e):
                _desactivar_suscripcion(tabla, s.get('id'))
            else:
                print(f"❌ Error enviando push: {type(e).__name__}: {str(e)[:200]}")
        except Exception as e:
            fallidos += 1
            print(f"❌ Error enviando push: {type(e).__name__}: {str(e)[:200]}")
    return enviados, fallidos


def enviar_push_profesional(profesional_id, titulo, mensaje, cita_id=None, url=None, guardar=True):
    """Aviso a un profesional: queda en su lista de notificaciones (si ``guardar``) y se envía push a TODOS sus dispositivos.

    Devuelve {'enviados': n, 'fallidos': m, 'suscripciones': k}.
    """
    if guardar:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notificaciones_profesional (profesional_id, tipo, titulo, mensaje, leida, cita_id)
                VALUES (%s, 'push', %s, %s, FALSE, %s)
            ''', (profesional_id, titulo, mensaje, cita_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ No se pudo guardar la notificación del profesional {profesional_id}: {e}")
    suscripciones = obtener_suscripciones_profesional(profesional_id)
    if not suscripciones:
        return {'enviados': 0, 'fallidos': 0, 'suscripciones': 0}
    payload = {
        'title': titulo,
        'body': mensaje,
        'url': url or ('/profesional?cita=%s' % cita_id if cita_id else '/profesional'),
        'citaId': cita_id,
        'tag': ('cita-%s' % cita_id) if cita_id else None,
        'icon': '/static/icons/icon-192x192.png',
        'timestamp': datetime.now().isoformat(),
    }
    enviados, fallidos = _enviar_a_suscripciones('suscripciones_push', suscripciones, payload)
    return {'enviados': enviados, 'fallidos': fallidos, 'suscripciones': len(suscripciones)}

def enviar_push_propietarios(negocio_id, titulo, mensaje, url='/negocio'):
    """Push a todos los dispositivos de los propietarios del negocio. Devuelve cuántos dispositivos lo recibieron."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.subscription_json
            FROM suscripciones_push_usuarios s JOIN usuarios u ON u.id = s.usuario_id
            WHERE u.negocio_id = %s AND u.rol = 'propietario' AND COALESCE(u.activo, TRUE) = TRUE AND s.activa = TRUE
        ''', (negocio_id,))
        suscripciones = [dict(f) if hasattr(f, 'keys') else {'id': f[0], 'subscription_json': f[1]} for f in cursor.fetchall()]
    finally:
        conn.close()
    if not suscripciones:
        return 0
    payload = {'title': titulo, 'body': mensaje, 'url': url, 'icon': '/static/icons/icon-192x192.png',
               'tag': 'negocio-%s' % negocio_id, 'timestamp': datetime.now().isoformat()}
    enviados, _ = _enviar_a_suscripciones('suscripciones_push_usuarios', suscripciones, payload)
    return enviados


# ==================== FUNCIONES PARA PROFESIONALES ====================

def obtener_suscripciones_profesional(profesional_id):
    """Obtener todas las suscripciones de un profesional"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, subscription_json, dispositivo_info, activa
        FROM suscripciones_push 
        WHERE profesional_id = %s AND activa = TRUE
    ''', (profesional_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    suscripciones = []
    for row in results:
        if isinstance(row, dict):
            suscripciones.append(row)
        elif isinstance(row, (tuple, list)):
            suscripciones.append({
                'id': row[0] if len(row) > 0 else None,
                'subscription_json': row[1] if len(row) > 1 else None,
                'dispositivo_info': row[2] if len(row) > 2 else '',
                'activa': row[3] if len(row) > 3 else True
            })
    
    return suscripciones

# ==================== NUEVAS FUNCIONES PARA CLIENTES ====================

def obtener_suscripciones_cliente(telefono, negocio_id):
    """Obtener suscripciones push de un cliente"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, subscription_json, dispositivo_info, activa
        FROM suscripciones_push_clientes
        WHERE cliente_telefono = %s AND negocio_id = %s AND activa = TRUE
    ''', (telefono, negocio_id))
    
    results = cursor.fetchall()
    conn.close()
    
    suscripciones = []
    for row in results:
        if isinstance(row, dict):
            suscripciones.append(row)
        elif isinstance(row, (tuple, list)):
            suscripciones.append({
                'id': row[0],
                'subscription_json': row[1],
                'dispositivo_info': row[2],
                'activa': row[3]
            })
    
    return suscripciones

def guardar_suscripcion_cliente(telefono, negocio_id, subscription, dispositivo_info=''):
    """Guardar suscripción push de un cliente"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        subscription_json = json.dumps(subscription) if isinstance(subscription, dict) else subscription
        
        # ✅ Primero verificar si ya existe
        cursor.execute('''
            SELECT id FROM suscripciones_push_clientes
            WHERE cliente_telefono = %s AND negocio_id = %s
        ''', (telefono, negocio_id))
        
        existe = cursor.fetchone()
        
        if existe:
            # ✅ Actualizar existente
            cursor.execute('''
                UPDATE suscripciones_push_clientes
                SET subscription_json = %s, dispositivo_info = %s, activa = TRUE
                WHERE cliente_telefono = %s AND negocio_id = %s
            ''', (subscription_json, dispositivo_info, telefono, negocio_id))
            print(f"✅ Suscripción de cliente actualizada para {telefono}")
        else:
            # ✅ Insertar nuevo
            cursor.execute('''
                INSERT INTO suscripciones_push_clientes 
                (negocio_id, cliente_telefono, subscription_json, dispositivo_info, activa)
                VALUES (%s, %s, %s, %s, TRUE)
            ''', (negocio_id, telefono, subscription_json, dispositivo_info))
            print(f"✅ Nueva suscripción de cliente creada para {telefono}")
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error guardando suscripción de cliente: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def enviar_notificacion_cliente(telefono, negocio_id, titulo, mensaje, cita_id=None, url=None):
    """Enviar notificación push a un cliente (todos sus dispositivos suscritos)."""
    try:
        suscripciones = obtener_suscripciones_cliente(telefono, negocio_id)
        if not suscripciones:
            print(f"⚠️ Cliente ...{str(telefono)[-4:]} no tiene suscripciones push")
            return False
        payload = {
            'title': titulo,
            'body': mensaje,
            'url': url or f'/cliente/{negocio_id}',
            'citaId': cita_id,
            'tag': ('cita-%s' % cita_id) if cita_id else None,
            'icon': '/static/icons/icon-192x192.png',
            'timestamp': datetime.now().isoformat(),
        }
        enviados, _ = _enviar_a_suscripciones('suscripciones_push_clientes', suscripciones, payload)
        return enviados > 0
    except Exception as e:
        print(f"❌ Error en enviar_notificacion_cliente: {e}")
        return False

# ==================== FUNCIONES PARA NOTIFICACIONES DE CITAS ====================

def enviar_notificacion_cita_creada(cita_data):
    """Enviar notificaciones push cuando se crea una cita (profesional y cliente)"""
    try:
        profesional_id = cita_data.get('profesional_id')
        cliente_telefono = cita_data.get('cliente_telefono')
        negocio_id = cita_data.get('negocio_id')
        cliente_nombre = cita_data.get('cliente_nombre', 'Cliente')
        fecha = cita_data.get('fecha', '')
        hora = cita_data.get('hora', '')
        cita_id = cita_data.get('id')
        
        # 1. Enviar al profesional
        if profesional_id:
            enviar_notificacion_profesional_cita_creada(
                profesional_id, cliente_nombre, fecha, hora, cita_id
            )
        
        # 2. Enviar al cliente
        if cliente_telefono and negocio_id:
            titulo = "✅ ¡Cita Confirmada!"
            mensaje = f"Hola {cliente_nombre}, tu cita ha sido agendada para el {fecha} a las {hora}"
            url = f"/cliente/{negocio_id}?cita={cita_id}"
            
            enviar_notificacion_cliente(cliente_telefono, negocio_id, titulo, mensaje, cita_id, url)
            
            print(f"✅ Notificaciones enviadas: profesional={profesional_id}, cliente={cliente_telefono}")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error en enviar_notificacion_cita_creada: {e}")
        return False

def enviar_notificacion_profesional_cita_creada(profesional_id, cliente_nombre, fecha, hora, cita_id=None):
    """Push al profesional cuando se crea una cita (sin duplicar la entrada de su lista)."""
    try:
        r = enviar_push_profesional(profesional_id, 'Nueva cita agendada', f"{cliente_nombre} - {fecha} {hora}",
                                    cita_id=cita_id, guardar=False)
        return r['enviados'] > 0
    except Exception as e:
        print(f"❌ Error en enviar_notificacion_profesional_cita_creada: {e}")
        return False

def enviar_recordatorio_cita(cita_data, horas_antes=1):
    """Enviar recordatorio de cita al cliente"""
    try:
        cliente_telefono = cita_data.get('cliente_telefono')
        negocio_id = cita_data.get('negocio_id')
        cliente_nombre = cita_data.get('cliente_nombre', 'Cliente')
        fecha = cita_data.get('fecha', '')
        hora = cita_data.get('hora', '')
        profesional_nombre = cita_data.get('profesional_nombre', 'Profesional')
        servicio_nombre = cita_data.get('servicio_nombre', 'Servicio')
        cita_id = cita_data.get('id')
        
        if not cliente_telefono or not negocio_id:
            return False
        
        if horas_antes == 24:
            titulo = "⏰ Recordatorio: Tu cita es mañana"
            mensaje = f"Hola {cliente_nombre}, te recordamos que tienes una cita mañana {fecha} a las {hora} con {profesional_nombre} para {servicio_nombre}"
        elif horas_antes == 1:
            titulo = "🔔 ¡Tu cita es en 1 hora!"
            mensaje = f"Hola {cliente_nombre}, tu cita con {profesional_nombre} para {servicio_nombre} es a las {hora}. ¡Te esperamos!"
        else:
            titulo = "📅 Recordatorio de Cita"
            mensaje = f"Hola {cliente_nombre}, tienes una cita el {fecha} a las {hora} con {profesional_nombre}"
        
        url = f"/cliente/{negocio_id}?cita={cita_id}"
        
        return enviar_notificacion_cliente(cliente_telefono, negocio_id, titulo, mensaje, cita_id, url)
        
    except Exception as e:
        print(f"❌ Error en enviar_recordatorio_cita: {e}")
        return False

# ==================== RUTAS API ====================

@push_bp.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    """Registrar suscripción push. La identidad sale SIEMPRE de la sesión del servidor, nunca del cuerpo de la petición
    (si no, cualquiera podría suscribir su dispositivo a las notificaciones de otro profesional o cliente)."""
    try:
        data = request.get_json(silent=True) or {}
        subscription = data.get('subscription')
        if not isinstance(subscription, dict) or not subscription.get('endpoint'):
            return jsonify({'success': False, 'error': 'Suscripción no proporcionada'}), 400
        dispositivo_info = request.headers.get('User-Agent', '')[:500]

        if data.get('tipo') == 'cliente':
            telefono = session.get('cliente_telefono')
            negocio_id = data.get('negocio_id') or session.get('negocio_id')
            if not telefono or not negocio_id:
                return jsonify({'success': False, 'error': 'Identifícate en el chat con tu teléfono primero'}), 401
            ok = guardar_suscripcion_cliente(telefono, int(negocio_id), subscription, dispositivo_info)
            return jsonify({'success': ok}), (200 if ok else 500)

        profesional_id = session.get('profesional_id')
        if not profesional_id:
            return jsonify({'success': False, 'error': 'No autenticado'}), 401
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO suscripciones_push (profesional_id, subscription_json, dispositivo_info, activa)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (profesional_id, subscription_json) DO UPDATE SET activa = TRUE
        ''', (profesional_id, json.dumps(subscription), dispositivo_info))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Suscripto a notificaciones push'})
    except Exception as e:
        print(f"❌ Error en subscribe_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

@push_bp.route('/api/push/subscribe-cliente', methods=['POST'])
def subscribe_cliente_push():
    """Suscripción push de un cliente: el teléfono sale de la sesión (el que verificó el chat), no del cuerpo."""
    try:
        data = request.get_json(silent=True) or {}
        subscription = data.get('subscription')
        telefono = session.get('cliente_telefono')
        negocio_id = data.get('negocio_id') or session.get('negocio_id')
        if not telefono or not negocio_id:
            return jsonify({'success': False, 'error': 'Identifícate en el chat con tu teléfono primero'}), 401
        if not isinstance(subscription, dict) or not subscription.get('endpoint'):
            return jsonify({'success': False, 'error': 'Suscripción no proporcionada'}), 400
        ok = guardar_suscripcion_cliente(telefono, int(negocio_id), subscription, request.headers.get('User-Agent', '')[:500])
        if ok:
            return jsonify({'success': True, 'message': 'Notificaciones activadas'})
        return jsonify({'success': False, 'error': 'Error al guardar'}), 500
    except Exception as e:
        print(f"❌ Error en subscribe_cliente_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

# ==================== RUTAS EXISTENTES ====================

@push_bp.route('/api/push/debug-info')
def debug_info():
    """Estado de la configuración VAPID (solo superadmin; no expone las claves)."""
    if session.get('usuario_rol') != 'superadmin':
        return jsonify({'error': 'No autorizado'}), 403
    publica = (os.getenv('VAPID_PUBLIC_KEY') or '').strip()
    return jsonify({
        'VAPID_PUBLIC_KEY_length': len(publica),
        'VAPID_PRIVATE_KEY_exists': bool(_clave_privada()),
        'VAPID_SUBJECT_usado': _vapid_subject(),
    })