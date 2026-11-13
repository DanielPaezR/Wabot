"""Ejecuta todas las pruebas y muestra un resumen.

    python tests/run_all.py                      # pruebas sin base de datos
    python tests/run_all.py --pg                 # además las de PostgreSQL, con una base temporal (necesita PostgreSQL instalado)
    python tests/run_all.py --pg-url URL         # además las de PostgreSQL contra una base LOCAL vacía que prepara el ejecutor
    python tests/run_all.py renta monitoreo      # solo las pruebas cuyo nombre contenga esas palabras
    python tests/run_all.py -v alquiler          # -v: muestra la salida completa de las que fallan

Cada prueba es un script independiente que imprime "RESULTADO: TODO OK" o líneas "FALLO ...".
Las pruebas con base de datos (test_pg_*.py) borran filas: solo corren contra bases locales.
"""
import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from _comun import SALIDA_SALTADA  # noqa: E402


def ejecutar(archivo, entorno):
    inicio = time.time()
    r = subprocess.run([sys.executable, os.path.join(AQUI, archivo)], env=entorno, cwd=tempfile.gettempdir(),
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
    salida = (r.stdout or '') + (r.stderr or '')
    if r.returncode == SALIDA_SALTADA:
        return 'saltada', time.time() - inicio, salida
    fallos = [l for l in salida.splitlines() if l.startswith('FALLO')]
    exito = 'RESULTADO: TODO OK' in salida and not fallos and r.returncode == 0
    return ('ok' if exito else 'FALLA'), time.time() - inicio, salida


def principal(argv):
    usar_pg = False
    detalle = False
    url_externa = None
    filtros = []
    i = 0
    while i < len(argv):
        if argv[i] == '--pg':
            usar_pg = True
        elif argv[i] in ('-v', '--detalle'):
            detalle = True
        elif argv[i] == '--pg-url':
            i += 1
            url_externa = argv[i]
        else:
            filtros.append(argv[i])
        i += 1

    archivos = sorted(f for f in os.listdir(AQUI) if f.startswith('test_') and f.endswith('.py'))
    if filtros:
        archivos = [f for f in archivos if any(p in f for p in filtros)]

    entorno = dict(os.environ, PYTHONIOENCODING='utf-8')
    entorno.pop('DATABASE_URL', None)

    import contextlib
    contexto = contextlib.nullcontext(None)
    if url_externa:
        import pg_temporal
        from _comun import HOSTS_LOCALES
        from urllib.parse import urlparse
        if urlparse(url_externa).hostname not in HOSTS_LOCALES:
            print('--pg-url debe ser una base LOCAL: las pruebas borran datos.')
            return 2
        pg_temporal.preparar(url_externa)
        contexto = contextlib.nullcontext(url_externa)
    elif usar_pg:
        import pg_temporal
        print('Levantando PostgreSQL temporal...')
        contexto = pg_temporal.base_temporal()

    resultados = []
    with contexto as url:
        if url:
            entorno['TEST_DATABASE_URL'] = url
        for archivo in archivos:
            estado, seg, salida = ejecutar(archivo, entorno)
            resultados.append((archivo, estado, seg, salida))
            marca = {'ok': 'OK    ', 'FALLA': 'FALLA ', 'saltada': 'SALTA '}[estado]
            print(f'{marca}{archivo:38s} {seg:6.1f}s')
            if estado == 'FALLA' and detalle:
                print(chr(10).join('        | ' + l[:230] for l in salida.splitlines()[-60:]))
            elif estado == 'FALLA':
                for linea in [l for l in salida.splitlines() if l.startswith('FALLO') or 'Traceback' in l or l.startswith(('AssertionError', 'RuntimeError'))][:8]:
                    print('        ' + linea[:200])

    ok = sum(1 for r in resultados if r[1] == 'ok')
    fallan = [r for r in resultados if r[1] == 'FALLA']
    saltadas = [r for r in resultados if r[1] == 'saltada']
    print(f'\n{ok} correctas, {len(fallan)} con fallos, {len(saltadas)} saltadas (de {len(resultados)})')
    if saltadas:
        print('Las saltadas necesitan PostgreSQL: usa --pg o --pg-url.')
    return 1 if fallan else 0


if __name__ == '__main__':
    sys.exit(principal(sys.argv[1:]))
