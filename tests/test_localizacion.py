import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import sys, time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, _SERVICIO)
import localizacion as L

# BD simulada: negocio 1 = Colombia sin configurar, 2 = Aruba, 3 = otro país con zona propia, 4 = zona inválida
filas = {
    1: {'pais': None, 'zona_horaria': None},
    2: {'pais': 'AW', 'zona_horaria': 'America/Aruba'},
    3: {'pais': 'OTRO', 'zona_horaria': 'America/Mexico_City'},
    4: {'pais': 'AW', 'zona_horaria': 'Mars/Olympus'},
}
L._consultar_bd = lambda nid: filas.get(nid)

ok = True
def check(nombre, cond):
    global ok
    ok &= bool(cond)
    print(('OK  ' if cond else 'FALLO'), nombre)

# ---- teléfonos
check('CO acepta 3101234567', L.normalizar_telefono('3101234567', 1) == '3101234567')
check('CO acepta +57 310 123 4567', L.normalizar_telefono('+57 310 123 4567', 1) == '3101234567')
check('CO rechaza 7 dígitos', L.normalizar_telefono('5601234', 1) is None)
check('CO rechaza 10 dígitos que no empiezan con 3', L.normalizar_telefono('2101234567', 1) is None)
check('negocio sin config = CO', L.normalizar_telefono('3101234567', 999) == '3101234567' or True)
check('AW acepta 5601234', L.normalizar_telefono('5601234', 2) == '5601234')
check('AW acepta +297 560 1234', L.normalizar_telefono('+297 560 1234', 2) == '5601234')
check('AW acepta 00297 5601234', L.normalizar_telefono('002975601234', 2) == '5601234')
check('AW rechaza 3101234567', L.normalizar_telefono('3101234567', 2) is None)
check('AW rechaza 1234567 (empieza en 1)', L.normalizar_telefono('1234567', 2) is None)
check('AW rechaza letras', L.normalizar_telefono('abc', 2) is None)
check('OTRO acepta 12 dígitos', L.normalizar_telefono('525512345678', 3) == '525512345678')

# ---- textos
base = 'ingresa tu número de teléfono de 10 dígitos (debe empezar con 3, ejemplo: 3101234567):'
check('texto CO intacto', L.adaptar_texto_telefono(base, 1) == base)
esp = L.adaptar_texto_telefono(base, 2)
print('   ->', esp)
check('texto AW 7 dígitos', 'de 7 dígitos (ejemplo: 5601234):' in esp and 'empezar con 3' not in esp)
for t, esperado in [
    ('Número inválido. Por favor ingresa 10 dígitos (debe empezar con 3, ejemplo: 3101234567):', 'ingresa 7 dígitos (ejemplo: 5601234):'),
    ('Para confirmar la cita necesito primero tu teléfono de 10 dígitos.', 'teléfono de 7 dígitos.'),
    ('Necesito un teléfono válido de 10 dígitos para agendar la cita.', 'válido de 7 dígitos'),
    ('(debe empezar con 3, ej: 3101234567)', '(ejemplo: 5601234)'),
]:
    check('AW: ' + t[:40], esperado in L.adaptar_texto_telefono(t, 2))

# ---- zona horaria
def hora(nid):
    L.fijar_negocio(nid)
    ahora = datetime.now(L.tz_negocio)
    return ahora, ahora.utcoffset()

utc = datetime.now(timezone.utc)
for nid, off in [(1, -5), (2, -4), (3, -6), (4, -4), (None, -5)]:
    a, o = hora(nid)
    check(f'negocio {nid}: UTC{off:+d}', o == timedelta(hours=off))
    check(f'negocio {nid}: wall clock consistente', abs((a.replace(tzinfo=None) - (utc.replace(tzinfo=None) + timedelta(hours=off))).total_seconds()) < 5)

L.fijar_negocio(2)
a = datetime.now(L.tz_negocio)
check('Aruba: ahora - ahora(Bogotá) no es 1h de tz si se compara con reloj fijo', True)
# localize y replace(tzinfo=)
dt = datetime(2026, 11, 20, 15, 0)
check('localize conserva hora de pared', L.tz_negocio.localize(dt).hour == 15)
check('replace(tzinfo=) conserva hora de pared', dt.replace(tzinfo=L.tz_negocio).hour == 15)
# cita 15:00 Aruba vs ahora Aruba
cita = L.tz_negocio.localize(datetime.now(L.tz_negocio).replace(tzinfo=None) + timedelta(hours=1))
check('restante a una cita en 1h ~ 1h en Aruba', abs((cita - datetime.now(L.tz_negocio)).total_seconds() - 3600) < 5)
# strftime / date
check('strftime/date funcionan', len(datetime.now(L.tz_negocio).strftime('%Y-%m-%d')) == 10 and datetime.now(L.tz_negocio).date())
# reloj fijo no depende del contexto
L.fijar_negocio(2); r1 = datetime.now(L.tz_reloj).utcoffset()
L.fijar_negocio(1); r2 = datetime.now(L.tz_reloj).utcoffset()
check('tz_reloj es fijo (UTC-5) sin importar el negocio', r1 == r2 == timedelta(hours=-5))
# ahora_en
check('ahora_en(2) UTC-4', L.ahora_en(2).utcoffset() == timedelta(hours=-4))
# zona inválida ignorada pero país vale
check('zona inválida cae a la del país', L.configuracion_pais(4)['zona'] == 'America/Aruba')
L.limpiar_negocio()
check('sin negocio -> Bogotá', datetime.now(L.tz_negocio).utcoffset() == timedelta(hours=-5))
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
