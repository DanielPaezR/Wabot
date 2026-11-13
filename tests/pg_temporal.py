"""Base PostgreSQL temporal para las pruebas: crea un clúster desechable, carga schema.sql y los datos de ejemplo."""
import contextlib
import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SERVICIO = os.path.join(RAIZ, 'services', 'wabot_chat')
SCHEMA = os.path.join(SERVICIO, 'schema.sql')


def _binario(nombre):
    ruta = shutil.which(nombre)
    if ruta:
        return ruta
    patrones = [
        rf'C:\Program Files\PostgreSQL\*\bin\{nombre}.exe',
        f'/usr/lib/postgresql/*/bin/{nombre}',
        f'/usr/local/pgsql/bin/{nombre}',
        f'/opt/homebrew/opt/postgresql*/bin/{nombre}',
    ]
    for patron in patrones:
        coincidencias = sorted(glob.glob(patron))
        if coincidencias:
            return coincidencias[-1]
    return None


def _puerto_libre():
    with contextlib.closing(socket.socket()) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def preparar(url):
    """Carga schema.sql en la base ``url`` (vacía) y los datos de ejemplo de la aplicación."""
    import psycopg2
    with open(SCHEMA, encoding='utf-8') as f:
        script = f.read()
    conn = psycopg2.connect(url)
    conn.autocommit = True
    conn.cursor().execute(script)
    conn.close()

    entorno = dict(os.environ, DATABASE_URL=url.replace('postgres://', 'postgresql://'), PYTHONIOENCODING='utf-8', PYTHONPATH=SERVICIO)
    r = subprocess.run([sys.executable, '-c', 'import database; database.init_db()'], env=entorno,
                       cwd=tempfile.gettempdir(), capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        raise RuntimeError('No se pudieron crear los datos de ejemplo:\n' + r.stderr[-1500:])

    # init_db inserta filas con id fijo: las secuencias deben seguir a partir del mayor id
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='id'")
    for (tabla,) in cur.fetchall():
        cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (f'public.{tabla}',))
        secuencia = cur.fetchone()[0]
        if secuencia:
            cur.execute(f'SELECT setval(%s, GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.{tabla}), 1))', (secuencia,))
    conn.close()


@contextlib.contextmanager
def base_temporal():
    """Levanta un PostgreSQL desechable (necesita initdb/postgres instalados) y devuelve su URL."""
    initdb, postgres, pg_ctl = _binario('initdb'), _binario('postgres'), _binario('pg_ctl')
    if not (initdb and postgres and pg_ctl):
        raise RuntimeError('No encuentro PostgreSQL (initdb/postgres/pg_ctl). Instálalo o pasa una base local con --pg-url.')
    carpeta = tempfile.mkdtemp(prefix='wabot_pg_')
    datos = os.path.join(carpeta, 'datos')
    puerto = _puerto_libre()
    subprocess.run([initdb, '-D', datos, '-U', 'test', '--auth=trust', '-E', 'UTF8'], check=True, capture_output=True)
    proceso = subprocess.Popen([postgres, '-D', datos, '-p', str(puerto), '-c', 'listen_addresses=127.0.0.1', '-c', 'lc_messages=C'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import psycopg2
        for _ in range(60):
            try:
                psycopg2.connect(host='127.0.0.1', port=puerto, user='test', dbname='postgres').close()
                break
            except Exception:      # incluye UnicodeDecodeError de psycopg2 antiguos con mensajes localizados
                time.sleep(0.5)
        else:
            raise RuntimeError('PostgreSQL temporal no arrancó')
        conn = psycopg2.connect(host='127.0.0.1', port=puerto, user='test', dbname='postgres')
        conn.autocommit = True
        conn.cursor().execute('CREATE DATABASE wabot_test')
        conn.close()
        url = f'postgresql://test@127.0.0.1:{puerto}/wabot_test'
        preparar(url)
        yield url
    finally:
        subprocess.run([pg_ctl, 'stop', '-D', datos, '-m', 'fast'], capture_output=True)
        with contextlib.suppress(Exception):
            proceso.wait(timeout=20)
        shutil.rmtree(carpeta, ignore_errors=True)
