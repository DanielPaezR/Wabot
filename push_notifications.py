# push_notifications.py - VERSIÓN CORREGIDA DEFINITIVA
import os
import json
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from database import get_db_connection, obtener_suscripciones_profesional
from pywebpush import webpush, WebPushException  # ← SOLO ESTE IMPORT

push_bp = Blueprint('push', __name__)

# Configurar webpush - ¡NO CAMBIES ESTO!
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', 'mailto:danielpaezrami@gmail.com')

@push_bp.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    """Registrar suscripción push de un profesional - VERSIÓN SIMPLIFICADA"""
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

@push_bp.route('/api/push/test-envio-directo')
def test_envio_directo():
    """TEST DIRECTO sin complicaciones"""
    try:
        # Obtener la última suscripción
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT subscription_json FROM suscripciones_push ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({'error': 'No hay suscripciones'})
        
        # Extraer suscripción
        if isinstance(result, dict):
            sub_json = result.get('subscription_json')
        else:
            sub_json = result[0]
        
        subscription = json.loads(sub_json)
        
        # Enviar con parámetros SIMPLES
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                'title': '✅ TEST DIRECTO',
                'body': 'Probando envío simple',
                'icon': '/static/icons/icon-192x192.png'
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={
                "sub": VAPID_SUBJECT,
                "exp": int(datetime.now(timezone.utc).timestamp()) + 3600
            },
            ttl=86400
        )
        
        return jsonify({'success': True, 'message': '¡ENVIADO!'})
        
    except WebPushException as e:
        return jsonify({
            'error': str(e),
            'error_response': e.response.text if hasattr(e, 'response') else 'No response',
            'error_status': e.response.status_code if hasattr(e, 'response') else 'No status',
            'diagnostico': 'Error específico de webpush'
        })
    except Exception as e:
        return jsonify({'error': str(e)})