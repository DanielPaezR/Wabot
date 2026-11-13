"""Utilidades comunes de las pruebas."""
import os
import sys
from urllib.parse import urlparse

SALIDA_SALTADA = 78          # código de salida de una prueba que no puede correr aquí (el ejecutor la cuenta como saltada)
HOSTS_LOCALES = ('127.0.0.1', 'localhost', '::1')


def url_bd_pg():
    """URL de la base PostgreSQL de pruebas (variable TEST_DATABASE_URL).

    Las pruebas con base de datos BORRAN filas (citas, conversaciones, etc.), así que se niegan a correr contra
    cualquier base que no sea local. Nunca apuntes TEST_DATABASE_URL a producción.
    """
    url = os.environ.get('TEST_DATABASE_URL', '').strip()
    if not url:
        print('SALTADA: define TEST_DATABASE_URL (PostgreSQL local) o usa:  python tests/run_all.py --pg')
        sys.exit(SALIDA_SALTADA)
    host = urlparse(url).hostname
    if host not in HOSTS_LOCALES:
        print(f'RECHAZADA: estas pruebas borran datos y solo corren contra una base local (host={host!r}).')
        sys.exit(2)
    return url
