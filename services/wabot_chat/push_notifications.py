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
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', 'mailto:danielpaezrami@gmail.com')

def get_db_connection():
    """Obtener conexión a la base de datos"""
    from database import get_db_connection as db_conn
    return db_conn()

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
        cursor.execute('''
            INSERT INTO suscripciones_push_clientes 
            (negocio_id, cliente_telefono, subscription_json, dispositivo_info, activa)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (cliente_telefono, subscription_json) 
            DO UPDATE SET activa = TRUE
        ''', (negocio_id, telefono, json.dumps(subscription), dispositivo_info))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error guardando suscripción de cliente: {e}")
        return False
    finally:
        conn.close()

def enviar_notificacion_cliente(telefono, negocio_id, titulo, mensaje, cita_id=None, url=None):
    """Enviar notificación push a un cliente"""
    try:
        if not VAPID_PRIVATE_KEY:
            print("⚠️ VAPID_PRIVATE_KEY no configurada")
            return False
        
        suscripciones = obtener_suscripciones_cliente(telefono, negocio_id)
        
        if not suscripciones:
            print(f"⚠️ Cliente {telefono} no tiene suscripciones push")
            return False
        
        vapid_claims = {
            "sub": VAPID_SUBJECT,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
        }
        
        payload = {
            'title': titulo,
            'body': mensaje,
            'url': url or f'/cliente/{negocio_id}',
            'citaId': cita_id,
            'icon': '/static/icons/icon-192x192.png',
            'timestamp': datetime.now().isoformat()
        }
        
        enviados = 0
        for suscripcion in suscripciones:
            try:
                subscription_data = suscripcion.get('subscription_json')
                if isinstance(subscription_data, str):
                    subscription = json.loads(subscription_data)
                else:
                    subscription = subscription_data
                
                webpush(
                    subscription_info=subscription,
                    data=json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims
                )
                enviados += 1
            except Exception as e:
                print(f"❌ Error enviando push a cliente: {e}")
        
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
    """Enviar notificación push a profesional cuando se crea una cita"""
    try:
        if not VAPID_PRIVATE_KEY:
            return False
        
        suscripciones = obtener_suscripciones_profesional(profesional_id)
        
        if not suscripciones:
            return False
        
        vapid_claims = {
            "sub": VAPID_SUBJECT,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
        }
        
        payload = {
            'title': '📅 Nueva Cita Agendada',
            'body': f"{cliente_nombre} - {fecha} {hora}",
            'url': f"/profesional?cita={cita_id}",
            'citaId': cita_id,
            'icon': '/static/icons/icon-192x192.png',
            'timestamp': datetime.now().isoformat()
        }
        
        enviados = 0
        for suscripcion in suscripciones:
            try:
                subscription_data = suscripcion.get('subscription_json')
                if isinstance(subscription_data, str):
                    subscription = json.loads(subscription_data)
                else:
                    subscription = subscription_data
                
                webpush(
                    subscription_info=subscription,
                    data=json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims
                )
                enviados += 1
            except Exception as e:
                print(f"❌ Error enviando push a profesional: {e}")
        
        return enviados > 0
        
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
    """Registrar suscripción push (detecta automáticamente si es profesional o cliente)"""
    try:
        data = request.json
        subscription = data.get('subscription')
        tipo = data.get('tipo', 'profesional')  # 'profesional' o 'cliente'
        
        if not subscription:
            return jsonify({'success': False, 'error': 'Suscripción no proporcionada'}), 400
        
        dispositivo_info = request.headers.get('User-Agent', '')[:500]
        
        if tipo == 'profesional':
            profesional_id = data.get('profesional_id') or session.get('profesional_id')
            if not profesional_id:
                return jsonify({'success': False, 'error': 'Profesional ID requerido'}), 400
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO suscripciones_push (profesional_id, subscription_json, dispositivo_info, activa)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (profesional_id, subscription_json) 
                DO UPDATE SET activa = TRUE
            ''', (profesional_id, json.dumps(subscription), dispositivo_info))
            conn.commit()
            conn.close()
            
        elif tipo == 'cliente':
            telefono = data.get('telefono')
            negocio_id = data.get('negocio_id')
            
            if not telefono or not negocio_id:
                return jsonify({'success': False, 'error': 'Teléfono y negocio requeridos'}), 400
            
            guardar_suscripcion_cliente(telefono, negocio_id, subscription, dispositivo_info)
        
        return jsonify({'success': True, 'message': 'Suscripto a notificaciones push'})
            
    except Exception as e:
        print(f"❌ Error en subscribe_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

@push_bp.route('/api/push/subscribe-cliente', methods=['POST'])
def subscribe_cliente_push():
    """Registrar suscripción push de un cliente"""
    try:
        data = request.json
        subscription = data.get('subscription')
        telefono = data.get('telefono')
        negocio_id = data.get('negocio_id')
        
        if not subscription or not telefono or not negocio_id:
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        
        dispositivo_info = request.headers.get('User-Agent', '')[:500]
        
        success = guardar_suscripcion_cliente(telefono, negocio_id, subscription, dispositivo_info)
        
        if success:
            return jsonify({'success': True, 'message': 'Notificaciones activadas'})
        else:
            return jsonify({'success': False, 'error': 'Error al guardar'}), 500
            
    except Exception as e:
        print(f"❌ Error en subscribe_cliente_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

@push_bp.route('/api/push/test-cliente', methods=['POST'])
def test_push_cliente():
    """Probar notificaciones push para cliente"""
    try:
        data = request.json
        telefono = data.get('telefono')
        negocio_id = data.get('negocio_id')
        
        if not telefono or not negocio_id:
            return jsonify({'success': False, 'error': 'Teléfono y negocio requeridos'}), 400
        
        success = enviar_notificacion_cliente(
            telefono, 
            negocio_id,
            "🔔 Prueba de Notificación",
            "¡Las notificaciones push funcionan correctamente!",
            url=f"/cliente/{negocio_id}"
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Notificación de prueba enviada'})
        else:
            return jsonify({'success': False, 'message': 'No hay suscripciones activas'})
            
    except Exception as e:
        print(f"❌ Error en test_push_cliente: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== RUTAS EXISTENTES ====================

@push_bp.route('/api/push/send', methods=['POST'])
def send_push_notification():
    """Enviar notificación push (para uso interno)"""
    try:
        data = request.json
        profesional_id = data.get('profesional_id')
        title = data.get('title', '📅 Nueva Cita')
        body = data.get('body', '')
        url = data.get('url', '/profesional')
        cita_id = data.get('cita_id')
        
        if not profesional_id:
            return jsonify({'success': False, 'error': 'Profesional ID requerido'}), 400
        
        if not VAPID_PRIVATE_KEY:
            return jsonify({'success': False, 'error': 'VAPID_PRIVATE_KEY no configurada'}), 500
        
        suscripciones = obtener_suscripciones_profesional(profesional_id)
        
        if not suscripciones:
            return jsonify({'success': False, 'error': 'No hay suscripciones activas'}), 404
        
        vapid_claims = {
            "sub": VAPID_SUBJECT,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
        }
        
        payload = {
            'title': title,
            'body': body,
            'url': url,
            'citaId': cita_id,
            'icon': '/static/icons/icon-192x192.png',
            'timestamp': datetime.now().isoformat()
        }
        
        resultados = []
        for suscripcion in suscripciones:
            try:
                subscription_data = suscripcion.get('subscription_json')
                if isinstance(subscription_data, str):
                    subscription = json.loads(subscription_data)
                else:
                    subscription = subscription_data
                
                webpush(
                    subscription_info=subscription,
                    data=json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims
                )
                resultados.append({'success': True, 'dispositivo': suscripcion.get('dispositivo_info', '')})
            except Exception as e:
                print(f"❌ Error enviando push: {e}")
                resultados.append({'success': False, 'error': str(e)})
        
        return jsonify({
            'success': True,
            'enviados': len([r for r in resultados if r['success']]),
            'fallidos': len([r for r in resultados if not r['success']]),
            'detalles': resultados
        })
        
    except Exception as e:
        print(f"❌ Error en send_push_notification: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

@push_bp.route('/api/push/test-simple')
def test_push_simple():
    """Test SUPER SIMPLE de push"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT subscription_json FROM suscripciones_push LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({'error': 'No hay suscripciones'})
        
        if isinstance(result, dict):
            sub_json = result.get('subscription_json')
        else:
            sub_json = result[0] if result else None
        
        if not sub_json:
            return jsonify({'error': 'JSON vacío'})
        
        try:
            subscription = json.loads(sub_json)
        except:
            return jsonify({'error': 'JSON inválido', 'json': sub_json[:100]})
        
        import time
        
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                'title': '✅ TEST SIMPLE',
                'body': 'Funciona!',
                'icon': '/static/icons/icon-192x192.png'
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={
                'sub': VAPID_SUBJECT,
                'exp': int(time.time()) + 3600
            }
        )
        
        return jsonify({'success': True, 'message': '¡PUSH ENVIADO!'})
        
    except WebPushException as e:
        error_info = {
            'error': str(e),
            'type': type(e).__name__,
        }
        
        if hasattr(e, 'response'):
            error_info['status_code'] = e.response.status_code if hasattr(e, 'response') else None
            error_info['response_text'] = e.response.text[:200] if hasattr(e, 'response') and e.response.text else None
        
        return jsonify(error_info)
        
    except Exception as e:
        return jsonify({'error': str(e), 'type': type(e).__name__})

@push_bp.route('/api/push/debug-info')
def debug_info():
    """Información de debug de las claves"""
    return jsonify({
        'VAPID_PUBLIC_KEY': VAPID_PUBLIC_KEY[:50] + '...' if VAPID_PUBLIC_KEY else None,
        'VAPID_PUBLIC_KEY_length': len(VAPID_PUBLIC_KEY) if VAPID_PUBLIC_KEY else 0,
        'VAPID_PRIVATE_KEY_exists': bool(VAPID_PRIVATE_KEY),
        'VAPID_PRIVATE_KEY_length': len(VAPID_PRIVATE_KEY) if VAPID_PRIVATE_KEY else 0,
        'VAPID_SUBJECT': VAPID_SUBJECT,
        'claves_coinciden': VAPID_PUBLIC_KEY == 'BAMDIUN0qYyQ43XsRnO-kYKCYDXyPyKNC_nxn7wrBfbhyyxSxJYYWRYB36waU_XAoKHiD3sacxstM2YufRX7CrU'
    })