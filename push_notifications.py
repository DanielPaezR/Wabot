# push_notifications.py - VERSIÓN COMPLETA Y FUNCIONAL
import os
import json
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from pywebpush import webpush, WebPushException

push_bp = Blueprint('push', __name__)

# Configurar webpush
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', 'mailto:danielpaezrami@gmail.com')

# Función auxiliar para obtener conexión a BD
def get_db_connection():
    """Obtener conexión a la base de datos"""
    # IMPORTAR AQUÍ para evitar circular imports
    from database import get_db_connection as db_conn
    return db_conn()

# Función auxiliar para obtener suscripciones
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
    
    # Convertir a lista de diccionarios
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

@push_bp.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    """Registrar suscripción push de un profesional"""
    try:
        data = request.json
        subscription = data.get('subscription')
        profesional_id = data.get('profesional_id')
        
        if not subscription or not profesional_id:
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        
        # Guardar en base de datos
        dispositivo_info = request.headers.get('User-Agent', '')[:500]
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
            
        return jsonify({'success': True, 'message': 'Suscripto a notificaciones push'})
            
    except Exception as e:
        print(f"❌ Error en subscribe_push: {e}")
        return jsonify({'success': False, 'error': 'Error interno'}), 500

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
        
        # Obtener suscripciones del profesional
        suscripciones = obtener_suscripciones_profesional(profesional_id)
        
        if not suscripciones:
            return jsonify({'success': False, 'error': 'No hay suscripciones activas'}), 404
        
        # Configurar claims VAPID
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
        
        # Enviar a todas las suscripciones
        resultados = []
        for suscripcion in suscripciones:
            try:
                # Parsear JSON si está en string
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

def enviar_notificacion_cita_creada(cita_data):
    """Función para enviar notificación push cuando se crea una cita"""
    try:
        profesional_id = cita_data.get('profesional_id')
        
        if not profesional_id:
            print("⚠️ No hay profesional_id en cita_data")
            return False
        
        if not VAPID_PRIVATE_KEY:
            print("⚠️ VAPID_PRIVATE_KEY no configurada")
            return False
        
        suscripciones = obtener_suscripciones_profesional(profesional_id)
        
        if not suscripciones:
            print(f"⚠️ Profesional {profesional_id} no tiene suscripciones push")
            return False
        
        # Configurar claims VAPID
        vapid_claims = {
            "sub": VAPID_SUBJECT,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
        }
        
        # Preparar payload
        payload = {
            'title': '📅 Nueva Cita Agendada',
            'body': f"{cita_data.get('cliente_nombre', 'Cliente')} - {cita_data.get('fecha', '')} {cita_data.get('hora', '')}",
            'url': f"/profesional?cita={cita_data.get('id', '')}",
            'citaId': cita_data.get('id'),
            'icon': '/static/icons/icon-192x192.png',
            'timestamp': datetime.now().isoformat()
        }
        
        # Enviar notificaciones
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
                print(f"✅ Push enviado a profesional {profesional_id}")
            except Exception as e:
                print(f"❌ Error enviando push: {e}")
        
        print(f"✅ Notificaciones push enviadas: {enviados}/{len(suscripciones)}")
        return enviados > 0
        
    except Exception as e:
        print(f"❌ Error en enviar_notificacion_cita_creada: {e}")
        return False

# ============================================
# NUEVAS RUTAS PARA DEBUG Y PRUEBAS
# ============================================

@push_bp.route('/api/push/test-simple')
def test_push_simple():
    """Test SUPER SIMPLE de push"""
    try:
        # 1. Obtener primera suscripción
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT subscription_json FROM suscripciones_push LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({'error': 'No hay suscripciones'})
        
        # Extraer JSON
        if isinstance(result, dict):
            sub_json = result.get('subscription_json')
        else:
            sub_json = result[0] if result else None
        
        if not sub_json:
            return jsonify({'error': 'JSON vacío'})
        
        # 2. Parsear suscripción
        try:
            subscription = json.loads(sub_json)
        except:
            return jsonify({'error': 'JSON inválido', 'json': sub_json[:100]})
        
        # 3. Enviar push SIMPLE
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
        'CLAVE_EN_JS': 'BEEo7Fp8xHxL6E5K4n8r5T2v1Z3c6M9q0W4y7U1i5O9p3A2s8D4f6G7h2J3k5L8'[:50] + '...',
        'claves_coinciden': VAPID_PUBLIC_KEY == 'BEEo7Fp8xHxL6E5K4n8r5T2v1Z3c6M9q0W4y7U1i5O9p3A2s8D4f6G7h2J3k5L8'
    })