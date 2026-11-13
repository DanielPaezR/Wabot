import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import json, os, re, subprocess, sys
from flask import Flask, render_template

RAIZ = _SERVICIO
app = Flask('t', template_folder=os.path.join(RAIZ, 'templates'), static_folder=os.path.join(RAIZ, 'static'))
app.secret_key = 'x'
app.url_build_error_handlers.append(lambda error, endpoint, values: '#')   # rutas que no existen en esta mini-app

@app.template_filter('tojson')            # mismo comportamiento que app.py: sin escapar
def _tojson(v): return json.dumps(v)

@app.context_processor
def _ctx():
    return {'csrf_token': lambda: 'tok', 'current_user': None}

ok = True
def check(n, c):
    global ok; ok &= bool(c); print(('OK  ' if c else 'FALLO'), n)

CFG = {
  'CO': {'codigo': 'CO', 'regex': r'3\d{9}', 'prefijo': '57', 'digitos': '10', 'ejemplo': '3101234567'},
  'AW': {'codigo': 'AW', 'regex': r'[2-9]\d{6}', 'prefijo': '297', 'digitos': '7', 'ejemplo': '5601234'},
}

def js_valido(html, nombre):
    scripts = re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>', html, re.S)
    for i, js in enumerate(scripts):
        p = os.path.join(__import__('tempfile').gettempdir(), f'_chk_{nombre}_{i}.js')
        open(p, 'w', encoding='utf-8').write(js)
        r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
        os.remove(p)
        if r.returncode != 0:
            print(r.stderr[:400]); return False
    return True

with app.test_request_context('/'):
    for pais in ('CO', 'AW'):
        for tipo in ('barberia', 'renta_autos'):
            html = render_template('cliente/index.html', negocio={'id': 7, 'nombre': 'N', 'tipo_negocio': tipo, 'emoji': '💈', 'config_general': {}},
                                   tel_cfg=CFG[pais], session_id='s')
            m = re.search(r'const TEL_CFG = (\{.*?\});', html)
            check(f'cliente/index {pais}/{tipo}: TEL_CFG presente y JSON válido', m and json.loads(m.group(1))['regex'] == CFG[pais]['regex'])
            check(f'cliente/index {pais}/{tipo}: JS sin errores de sintaxis', js_valido(html, 'idx'))
    html = render_template('profesional/agendar_cita.html', tel_cfg=CFG['AW'], servicios=[], profesional_id=1, fecha_hoy='2026-11-20')
    check('agendar_cita AW: placeholder 5601234', 'Ej: 5601234' in html)
    check('agendar_cita AW: regex de Aruba y mensaje 7 dígitos', r'[2-9]\\d{6}' in html and 'debe tener 7 dígitos' in html)
    check('agendar_cita: JS sin errores de sintaxis', js_valido(html, 'agenda'))
    html = render_template('admin/nuevo_negocio.html')
    check('admin nuevo_negocio: select de país', 'name="pais"' in html and 'value="AW"' in html)
    html = render_template('admin/editar_negocio.html', negocio={'id': 2, 'nombre': 'N', 'telefono_whatsapp': 'whatsapp:+297', 'tipo_negocio': 'barberia',
                           'emoji': '💈', 'activo': True, 'direccion': '', 'latitud': None, 'longitud': None}, config={}, numero_api_whatsapp=None,
                           localizacion={'pais': 'AW', 'zona_horaria': 'America/Aruba'})
    check('admin editar_negocio: Aruba preseleccionada con su zona', re.search(r'value="AW"\s+selected', html) and 'value="America/Aruba"' in html)
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
