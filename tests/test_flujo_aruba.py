"""Prueba de integración del flujo de chat para un negocio de Colombia y uno de Aruba
usando una BD simulada (nada toca producción)."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys
os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, _SERVICIO)

from flask import Flask
import localizacion as L
import database as db
import web_chat_handler as H

# --- BD simulada
NEGOCIOS = {
    1: {'id': 1, 'nombre': 'Barbería CO', 'tipo_negocio': 'barberia', 'activo': True, 'configuracion': '{}'},
    2: {'id': 2, 'nombre': 'Barbería Aruba', 'tipo_negocio': 'barberia', 'activo': True, 'configuracion': '{}'},
}
L._consultar_bd = lambda nid: {1: {'pais': None, 'zona_horaria': None}, 2: {'pais': 'AW', 'zona_horaria': 'America/Aruba'}}.get(nid)
db.obtener_negocio_por_id = lambda nid: NEGOCIOS.get(int(nid))
PLANTILLAS = {
    'saludo_inicial': '¡Hola! 👋 Para comenzar, ingresa tu número de teléfono de 10 dígitos (debe empezar con 3, ejemplo: 3101234567):',
    'solicitar_nombre_nuevo': 'Número registrado. Ingresa tu nombre completo:',
    'telefono_validado_existente': '¡Hola {nombre_cliente}! Te identifiqué.',
}
db.obtener_plantilla = lambda nid, nombre: {'plantilla': PLANTILLAS[nombre]}
H.buscar_cliente_existente = lambda tel, nid: None

app = Flask('prueba'); app.secret_key = 'x'
ok = True
def check(nombre, cond):
    global ok; ok &= bool(cond); print(('OK  ' if cond else 'FALLO'), nombre)

def chat(neg, sid, texto):
    with app.test_request_context():
        from flask import session
        session['chat_session_id'] = sid
        return H.procesar_mensaje_chat(texto, sid, neg, session)

# ---------- Colombia: comportamiento histórico intacto
H.conversaciones_activas.clear()
r = chat(1, 'ses-co', 'hola'); print('CO saludo  :', r['message'])
check('CO: saludo pide 10 dígitos / empezar con 3', '10 dígitos' in r['message'] and 'empezar con 3' in r['message'])
r = chat(1, 'ses-co', '5601234'); print('CO 7 díg   :', r['message'])
check('CO: rechaza 7 dígitos con mensaje de 10', 'inválido' in r['message'] and '10 dígitos' in r['message'])
r = chat(1, 'ses-co', '3101234567'); print('CO válido  :', r['message'])
check('CO: acepta 3101234567', 'nombre' in r['message'].lower())

# ---------- Aruba
H.conversaciones_activas.clear()
r = chat(2, 'ses-aw', 'hola'); print('AW saludo  :', r['message'])
check('AW: saludo pide 7 dígitos', '7 dígitos' in r['message'] and '5601234' in r['message'] and 'empezar con 3' not in r['message'])
r = chat(2, 'ses-aw', '3101234567'); print('AW 10 díg  :', r['message'])
check('AW: rechaza celular colombiano', 'inválido' in r['message'] and '7 dígitos' in r['message'])
r = chat(2, 'ses-aw', '5601234'); print('AW válido  :', r['message'])
check('AW: acepta 7 dígitos', 'nombre' in r['message'].lower())
check('AW: la conversación guardó el teléfono local', H.conversaciones_activas['ses-aw_2']['telefono_cliente'] == '5601234')

H.conversaciones_activas.clear()
chat(2, 'ses-aw2', 'hola')
r = chat(2, 'ses-aw2', '+297 560 1234'); print('AW +297    :', r['message'])
check('AW: acepta +297 560 1234 y guarda 5601234', H.conversaciones_activas['ses-aw2_2']['telefono_cliente'] == '5601234')

# ---------- Hora del negocio en el mismo proceso
with app.test_request_context():
    L.fijar_negocio(1); h1 = H.datetime.now(H.tz_negocio)
    L.fijar_negocio(2); h2 = H.datetime.now(H.tz_negocio)
    L.limpiar_negocio()
check('misma instancia, distinta hora: Aruba = Colombia + 1h', (h2.replace(tzinfo=None) - h1.replace(tzinfo=None)).total_seconds() // 60 in (59, 60))

# ---------- Expiración de conversaciones (reloj fijo, no depende del negocio)
H.conversaciones_activas.clear()
chat(2, 'ses-ttl', 'hola')            # crea conversación bajo contexto Aruba
L.fijar_negocio(1)                    # limpieza bajo contexto Colombia
H._limpiar_conversaciones_viejas()
check('TTL: conversación reciente NO se borra al cambiar de negocio', 'ses-ttl_2' in H.conversaciones_activas)
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
