"""WhatsApp Business Cloud API de Meta, conectada directamente a la app (sin n8n).

Está inactiva mientras no se definan estas variables de entorno:

  META_WHATSAPP_TOKEN   token permanente (usuario del sistema) con permiso whatsapp_business_messaging
  META_APP_SECRET       "Clave secreta de la app": se usa para verificar la firma de cada notificación
  META_VERIFY_TOKEN     texto cualquiera que se escribe también en Meta al configurar el webhook

URL del webhook en Meta (campo "messages"):  https://<tu-app>/api/whatsapp/meta/webhook

Flujo: Meta envía el mensaje -> se verifica la firma -> se responde 200 de inmediato -> en segundo plano se procesa
con la misma lógica del chat (procesar_whatsapp_entrante) y la respuesta se envía por la API de Meta.
El negocio se identifica por el número al que escribió el cliente (metadata.display_phone_number).
"""
import hashlib
import hmac
import os
import threading

import requests

GRAPH_VERSION = os.getenv('META_GRAPH_VERSION', 'v21.0')
_MAX_TEXTO = 4000          # límite de un mensaje de texto: 4096
_MAX_CUERPO_INTERACTIVO = 1000   # límite del cuerpo de botones/lista: 1024
_MAX_TITULO_BOTON = 20
_MAX_TITULO_FILA = 24
_MENSAJE_NO_SOPORTADO = "Por ahora solo puedo leer mensajes de texto. Escríbeme lo que necesitas o responde *hola* para ver el menú."


def configurado():
    return all(os.getenv(v) for v in ('META_WHATSAPP_TOKEN', 'META_APP_SECRET', 'META_VERIFY_TOKEN'))


def firma_valida(cuerpo, cabecera_firma, secreto):
    """Verifica X-Hub-Signature-256 ('sha256=<hmac del cuerpo con la clave secreta de la app>')."""
    if not secreto or not cabecera_firma or not cabecera_firma.startswith('sha256='):
        return False
    esperada = hmac.new(secreto.encode('utf-8'), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera_firma[len('sha256='):])


def extraer_mensajes(payload):
    """Notificación de Meta -> lista de mensajes entrantes normalizados.

    Cada uno: {'phone_number_id', 'to', 'from', 'message', 'message_id', 'soportado'}.
    Las notificaciones de estado (entregado/leído) no traen 'messages' y se ignoran.
    """
    mensajes = []
    for entrada in (payload or {}).get('entry', []) or []:
        for cambio in entrada.get('changes', []) or []:
            valor = cambio.get('value') or {}
            meta = valor.get('metadata') or {}
            for m in valor.get('messages', []) or []:
                tipo = m.get('type')
                texto, soportado = '', True
                if tipo == 'text':
                    texto = (m.get('text') or {}).get('body', '')
                elif tipo == 'interactive':
                    inter = m.get('interactive') or {}
                    elegido = inter.get('button_reply') or inter.get('list_reply') or {}
                    texto = elegido.get('id') or elegido.get('title') or ''
                elif tipo == 'button':
                    texto = (m.get('button') or {}).get('text', '')
                else:
                    soportado = False
                mensajes.append({
                    'phone_number_id': meta.get('phone_number_id'),
                    'to': meta.get('display_phone_number') or '',
                    'from': m.get('from') or '',
                    'message': (texto or '').strip(),
                    'message_id': m.get('id') or '',
                    'soportado': soportado,
                })
    return mensajes


def construir_envios(respuesta, destinatario):
    """Respuesta de procesar_whatsapp_entrante -> lista de cuerpos para POST /{phone_number_id}/messages."""
    texto = (respuesta.get('message') or '').strip() or '...'
    botones = respuesta.get('buttons') or []

    def base(tipo):
        return {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': destinatario, 'type': tipo}

    def solo_texto(t):
        envio = base('text')
        envio['text'] = {'body': t[:_MAX_TEXTO], 'preview_url': False}
        return envio

    if not botones:
        return [solo_texto(texto)]

    envios = []
    cuerpo = texto
    if len(texto) > _MAX_CUERPO_INTERACTIVO:
        # el texto largo va como mensaje normal y las opciones en uno interactivo corto
        envios.append(solo_texto(texto))
        cuerpo = 'Elige una opción:'

    opciones = [{'id': str(b['id'])[:200], 'title': str(b['title'])} for b in botones]
    interactivo = base('interactive')
    if len(opciones) <= 3:
        interactivo['interactive'] = {
            'type': 'button',
            'body': {'text': cuerpo},
            'action': {'buttons': [{'type': 'reply', 'reply': {'id': o['id'], 'title': o['title'][:_MAX_TITULO_BOTON]}} for o in opciones]},
        }
    else:
        interactivo['interactive'] = {
            'type': 'list',
            'body': {'text': cuerpo},
            'action': {
                'button': 'Ver opciones',
                'sections': [{'title': 'Opciones', 'rows': [{'id': o['id'], 'title': o['title'][:_MAX_TITULO_FILA]} for o in opciones[:10]]}],
            },
        }
    envios.append(interactivo)
    return envios


def enviar(phone_number_id, cuerpo, token=None):
    """POST a la API de Meta. Devuelve (ok, detalle)."""
    token = token or os.getenv('META_WHATSAPP_TOKEN', '')
    url = f'https://graph.facebook.com/{GRAPH_VERSION}/{phone_number_id}/messages'
    try:
        r = requests.post(url, json=cuerpo, headers={'Authorization': f'Bearer {token}'}, timeout=15)
        if r.status_code >= 400:
            return False, f'HTTP {r.status_code}: {r.text[:300]}'
        return True, ''
    except requests.RequestException as e:
        return False, str(e)


def manejar_notificacion(payload, procesar, reclamar=None, enviar_fn=None, contexto=None):
    """Procesa todos los mensajes de una notificación. Pensada para correr en un hilo.

    procesar(dict{'from','to','message','message_id'}) -> (respuesta, status)   (app.procesar_whatsapp_entrante)
    reclamar(clave) -> bool    True si este proceso es el primero en ver ese mensaje (Meta reintenta entregas)
    contexto()     -> administrador de contexto (el chat necesita un contexto de petición de Flask)
    """
    enviar_fn = enviar_fn or enviar
    resultados = []
    for msg in extraer_mensajes(payload):
        if not msg['phone_number_id'] or not msg['from']:
            continue
        if reclamar and msg['message_id'] and not reclamar('wamid_' + msg['message_id']):
            resultados.append((msg['message_id'], 'repetido'))
            continue
        try:
            if not msg['soportado'] or not msg['message']:
                respuesta = {'message': _MENSAJE_NO_SOPORTADO}
            else:
                entrada = {'from': msg['from'], 'to': msg['to'], 'message': msg['message'], 'message_id': msg['message_id']}
                if contexto:
                    with contexto():
                        respuesta, status = procesar(entrada)
                else:
                    respuesta, status = procesar(entrada)
                if status == 404:      # número que no pertenece a ningún negocio: no se responde
                    resultados.append((msg['message_id'], 'sin_negocio'))
                    continue
                if status != 200:
                    respuesta = {'message': 'Tuve un problema para responderte. Inténtalo de nuevo en un momento.'}
            for cuerpo in construir_envios(respuesta, msg['from']):
                ok, detalle = enviar_fn(msg['phone_number_id'], cuerpo)
                if not ok:
                    print(f"❌ [META] No se pudo enviar la respuesta: {detalle}")
                    resultados.append((msg['message_id'], 'error_envio'))
                    break
            else:
                resultados.append((msg['message_id'], 'enviado'))
        except Exception as e:
            print(f"❌ [META] Error procesando el mensaje {msg['message_id']}: {e}")
            resultados.append((msg['message_id'], 'error'))
    return resultados


def registrar(app, procesar, reclamar=None):
    """Registra las rutas de Meta en la app Flask. Sin variables de entorno responden 404 (como si no existieran)."""
    from flask import Response, abort, request

    @app.route('/api/whatsapp/meta/webhook', methods=['GET'])
    def meta_verificar():
        if not configurado():
            abort(404)
        if request.args.get('hub.mode') == 'subscribe' and hmac.compare_digest(
                request.args.get('hub.verify_token', ''), os.getenv('META_VERIFY_TOKEN', '')):
            return Response(request.args.get('hub.challenge', ''), mimetype='text/plain')
        abort(403)

    @app.route('/api/whatsapp/meta/webhook', methods=['POST'])
    def meta_recibir():
        if not configurado():
            abort(404)
        cuerpo = request.get_data()
        if not firma_valida(cuerpo, request.headers.get('X-Hub-Signature-256', ''), os.getenv('META_APP_SECRET', '')):
            abort(403)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return Response('', status=200)
        hilo = threading.Thread(
            target=manejar_notificacion,
            kwargs={'payload': payload, 'procesar': procesar, 'reclamar': reclamar,
                    'contexto': lambda: app.test_request_context('/')},
            daemon=True,
        )
        hilo.start()
        return Response('', status=200)   # Meta exige 200 rápido; la respuesta al cliente se envía aparte
