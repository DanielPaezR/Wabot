import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys
os.environ['DATABASE_URL'] = _url_bd_pg()
sys.path.insert(0, _SERVICIO)
import database as db
ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)
conn = db.get_db_connection(); k = conn.cursor()
k.execute("DELETE FROM numeros_whatsapp_negocio"); k.execute("DELETE FROM negocios WHERE id > 1")
k.execute("UPDATE negocios SET telefono_whatsapp='whatsapp:+573017650099' WHERE id=1")
k.execute("INSERT INTO negocios (id, nombre, telefono_whatsapp, activo) VALUES (2, 'Barber Aruba', 'whatsapp:+2975551234', TRUE), (3, 'Otro CO', '3017650099', TRUE), (4, 'Inactivo', 'whatsapp:+573009998877', FALSE)")
conn.commit(); conn.close()

check('guardar número (nuevo)', db.guardar_numero_whatsapp_negocio(1, '15551230001') == 'ok')
check('guardar número (reemplaza el del mismo negocio, sin ON CONFLICT)', db.guardar_numero_whatsapp_negocio(1, '15551230002') == 'ok')
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT numero_whatsapp FROM numeros_whatsapp_negocio WHERE negocio_id=1"); fs = k.fetchall(); c.close()
check('queda un solo número por negocio', len(fs) == 1 and fs[0]['numero_whatsapp'] == '15551230002', str(fs))
check('número ya usado por otro negocio -> duplicado', db.guardar_numero_whatsapp_negocio(2, '15551230002') == 'duplicado')
check('negocio 2 con su propio número', db.guardar_numero_whatsapp_negocio(2, '15551230003') == 'ok')

f = db.negocio_id_por_numero_whatsapp
check('exacto en tabla de números', f('+1 (555) 123-0002') == 1 and f('15551230003') == 2)
check('exacto en teléfono del negocio (whatsapp:+57...)', f('+573017650099') == 1)
check('Aruba por teléfono del negocio', f('+2975551234') == 2)
check('inactivo no se asigna', f('573009998877') is None)
check('número desconocido -> None', f('573000000000') is None)
check('vacío -> None', f('') is None and f(None) is None)
# sufijo de 10 dígitos: '3017650099' coincide con negocio 3 (exacto) -> exacto gana; negocio 1 tiene +57...
check('exacto prefiere el negocio cuyo teléfono es exactamente ese', f('3017650099') == 3)
check('sin indicativo y ambiguo (dos negocios comparten los últimos 10 dígitos) -> ninguno', f('+49 3017650099') is None, str(f('+49 3017650099')))
db.eliminar_numero_whatsapp_negocio(1)
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT count(*) AS n FROM numeros_whatsapp_negocio WHERE negocio_id=1"); n = k.fetchone()['n']; c.close()
check('eliminar número', n == 0)
c = db.get_db_connection(); k = c.cursor(); k.execute("DELETE FROM numeros_whatsapp_negocio"); k.execute("DELETE FROM negocios WHERE id > 1"); c.commit(); c.close()
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
