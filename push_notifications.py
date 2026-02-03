# push_notifications.py - SISTEMA DE NOTIFICACIONES PUSH
import os
import json
from flask import Blueprint, request, jsonify
from database import guardar_suscripcion_push, obtener_suscripciones_profesional
import webpush

push_bp = Blueprint('push', __name__)

# Configurar webpush
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_CLAIMS = {
    "sub": os.getenv('VAPID_SUBJECT', 'mailto:admin@tuapp.com')
}

webpush.setVapidDetails(
    VAPID_CLAIMS["sub"],
    VAPID_PUBLIC_KEY,
    VAPID_PRIVATE_KEY
)

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
        dispositivo_info = request.headers.get('User-Agent', '')
        
        if guardar_suscripcion_push(profesional_id, subscription, dispositivo_info):
            return jsonify({'success': True, 'message': 'Suscripto a notificaciones push'})
        else:
            return jsonify({'success': False, 'error': 'Error guardando suscripción'}), 500
            
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
        
        # Obtener suscripciones del profesional
        suscripciones = obtener_suscripciones_profesional(profesional_id)
        
        if not suscripciones:
            return jsonify({'success': False, 'error': 'No hay suscripciones activas'}), 404
        
        payload = {
            'title': title,
            'body': body,
            'url': url,
            'citaId': cita_id,
            'icon': '/static/icons/icon-192x192.png'
        }
        
        # Enviar a todas las suscripciones
        resultados = []
        for suscripcion in suscripciones:
            try:
                webpush.send_notification(
                    suscripcion['subscription'],
                    json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS
                )
                resultados.append({'success': True, 'dispositivo': suscripcion.get('dispositivo', '')})
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
        # Importar aquí para evitar dependencia circular
        from database import obtener_suscripciones_profesional
        
        profesional_id = cita_data.get('profesional_id')
        
        if not profesional_id:
            print("⚠️ No hay profesional_id en cita_data")
            return False
        
        suscripciones = obtener_suscripciones_profesional(profesional_id)
        
        if not suscripciones:
            print(f"⚠️ Profesional {profesional_id} no tiene suscripciones push")
            return False
        
        # Preparar payload
        payload = {
            'title': '📅 Nueva Cita Agendada',
            'body': f"{cita_data.get('cliente_nombre', 'Cliente')} - {cita_data.get('fecha', '')} {cita_data.get('hora', '')}",
            'url': f"/profesional?cita={cita_data.get('id', '')}",
            'citaId': cita_data.get('id'),
            'icon': '/static/icons/icon-192x192.png',
            'timestamp': cita_data.get('created_at', '')
        }
        
        # Enviar notificaciones
        enviados = 0
        for suscripcion in suscripciones:
            try:
                webpush.send_notification(
                    suscripcion['subscription'],
                    json.dumps(payload),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS
                )
                enviados += 1
            except Exception as e:
                print(f"❌ Error enviando push a dispositivo {suscripcion.get('dispositivo', '')}: {e}")
        
        print(f"✅ Notificaciones push enviadas: {enviados}/{len(suscripciones)}")
        return enviados > 0
        
    except Exception as e:
        print(f"❌ Error en enviar_notificacion_cita_creada: {e}")
        return False