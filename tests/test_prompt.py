import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys, json
os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, _SERVICIO)
import localizacion as L
import database as db
import web_chat_handler as H

L._consultar_bd = lambda nid: None
CONF = json.dumps({'telefono_contacto': '+297 560 1234', 'horario_atencion': 'Lun-Sáb 9-19', 'politica_cancelacion': 'Hasta 2h antes'})
NEG = {
 1: {'id': 1, 'nombre': 'Barbería Aruba', 'telefono_whatsapp': 'whatsapp:+2975601234', 'tipo_negocio': 'barberia', 'direccion': None, 'configuracion': CONF},
 2: {'id': 2, 'nombre': 'Spa X', 'telefono_whatsapp': 'whatsapp:+573001112222', 'tipo_negocio': 'spa_unas', 'direccion': 'Calle 1', 'configuracion': '{}'},
}
COLS = {1: {'prompt_ia': None, 'descripcion': 'Cortes clásicos y barba'}, 2: {'prompt_ia': 'Hola {nombre_negocio}, estás en {direccion}. Tel {telefono}. {horarios} | {politica_cancelacion}', 'descripcion': None}}
db.obtener_negocio_por_id = lambda nid: NEG[int(nid)]
db.obtener_profesionales = lambda nid: [{'nombre': 'Pedro'}, {'nombre': 'Luis'}]
db.obtener_servicios = lambda nid: [{'nombre': 'Corte', 'precio': 25, 'duracion': 30, 'tipo_precio': 'fijo', 'moneda': 'AWG'},
                                    {'nombre': 'Barba', 'precio': 15, 'precio_maximo': 25, 'duracion': 20, 'tipo_precio': 'rango'}]
db.obtener_horarios_por_dia = lambda nid, f: {'activo': True, 'hora_inicio': '09:00', 'hora_fin': '19:00'}
H._leer_columna_negocio.__globals__['_leer_columna_negocio'] = lambda nid, col: (COLS[nid].get(col) or None)

ok = True
def check(n, c):
    global ok; ok &= bool(c); print(('OK  ' if c else 'FALLO'), n)

p1 = H.construir_prompt_negocio(1)
print('--- negocio 1 (sin prompt, dirección NULL):\n', p1, '\n')
check('default: no muestra "None"', 'None' not in p1)
check('default: usa teléfono de contacto de la configuración', '+297 560 1234' in p1 and 'whatsapp:' not in p1)
check('default: incluye servicios con precio y duración', 'Corte ($25 AWG, 30 min)' in p1 and 'Barba ($15 - $25, 20 min)' in p1)
check('default: incluye política de cancelación y horario', 'Hasta 2h antes' in p1 and 'Lun-Sáb 9-19' in p1)
check('default: incluye descripción y tipo legible', 'Cortes clásicos y barba' in p1 and '(barbería)' in p1)
check('default: omite dirección vacía', 'Dirección:' not in p1)

p2 = H.construir_prompt_negocio(2)
print('--- negocio 2 (prompt personalizado):\n', p2, '\n')
check('personalizado: reemplaza variables', 'Hola Spa X, estás en Calle 1.' in p2 and 'Tel +573001112222' in p2)
check('personalizado: {horarios} y {politica_cancelacion} reemplazados', '{horarios}' not in p2 and 'No disponible' in p2)
check('personalizado: sin llaves sin reemplazar', not any(v in p2 for v, _ in H.VARIABLES_PROMPT))

# el botón del editor inserta variables y no valores fijos
vals = H.valores_variables_prompt(1)
check('todas las variables del editor tienen valor', all(v in vals for v, _ in H.VARIABLES_PROMPT))
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
