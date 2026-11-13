# services/wabot_directorio/app.py
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import json
import os
import re
import sys
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

# Importar modelos
from models import (
    Negocio, 
    Profesional, 
    Producto, 
    FotoNegocio, 
    FotoTrabajoProfesional,
    Servicio,
    ConfiguracionHorario,
    Promocion
)

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

ACENTO_DEFECTO = '#d4a857'


def acento_del_negocio(negocio):
    """Color de acento del negocio (configuracion.color_acento, hex de 6 dígitos) y color de texto legible sobre él."""
    config = getattr(negocio, 'configuracion', None)
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except ValueError:
            config = {}
    candidato = (config or {}).get('color_acento', '') if isinstance(config, dict) else ''
    acento = candidato if re.fullmatch(r'#[0-9a-fA-F]{6}', str(candidato)) else ACENTO_DEFECTO
    r, g, b = (int(acento[i:i + 2], 16) for i in (1, 3, 5))
    luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return acento, ('#17110a' if luminancia > 0.55 else '#ffffff')

_cors_origins = [
    'https://wabot-production-d544.up.railway.app',
    'https://wabot-deployment.up.railway.app',
]
_extra_origins = os.environ.get('CORS_ORIGINS', '')
if _extra_origins:
    _cors_origins += [o.strip() for o in _extra_origins.split(',') if o.strip()]
CORS(app, origins=_cors_origins)

def simbolo_moneda(moneda):
    """Retorna el símbolo visual para códigos de moneda usados en el directorio."""
    simbolos = {
        'COP': '$',
        'USD': 'US$',
        'EUR': '€',
        'AWG': 'ƒ',
    }
    return simbolos.get(str(moneda or 'COP').upper(), '$')

app.jinja_env.globals['simbolo_moneda'] = simbolo_moneda

# Configuración de base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("La variable de entorno DATABASE_URL es requerida para ejecutar el directorio")

print(f"Conectando a: {DATABASE_URL[:50]}...")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
db_session = scoped_session(sessionmaker(bind=engine))

def asegurar_columnas_servicios():
    """Mantiene compatible el directorio con columnas creadas desde el panel."""
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE servicios ADD COLUMN IF NOT EXISTS moneda VARCHAR(10) DEFAULT 'COP'"))
            conn.execute(text("ALTER TABLE servicios ADD COLUMN IF NOT EXISTS foto_url TEXT"))
            for columna in ['instagram', 'facebook', 'tiktok', 'twitter', 'youtube', 'sitio_web']:
                conn.execute(text(f"ALTER TABLE negocios ADD COLUMN IF NOT EXISTS {columna} TEXT"))
    except Exception as e:
        print(f"Advertencia: no se pudieron verificar columnas del directorio: {e}")

asegurar_columnas_servicios()

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

@app.route('/')
def index():
    return "Directorio Wabot - Servicio funcionando correctamente"

@app.route('/test-db')
def test_db():
    """Endpoint de prueba para verificar conexión"""
    try:
        result = db_session.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        return {"status": "ok", "test": row[0]}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/negocios')
def api_negocios():
    """API para obtener todos los negocios con coordenadas"""
    try:
        negocios = db_session.query(Negocio).filter(
            Negocio.activo == True,
            Negocio.latitud.isnot(None),
            Negocio.longitud.isnot(None)
        ).all()
        
        result = []
        for n in negocios:
            result.append({
                'id': n.id,
                'nombre': n.nombre,
                'latitud': float(n.latitud) if n.latitud else None,
                'longitud': float(n.longitud) if n.longitud else None,
                'direccion': n.direccion,
                'tipo_negocio': n.tipo_negocio,
                'calificacion': float(n.calificacion_promedio) if n.calificacion_promedio else 0,
                'total_opiniones': n.total_opiniones
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/directorio')
def directorio():
    """Página principal del mapa"""
    return render_template('directorio/mapa.html')

@app.route('/negocio/<int:negocio_id>')
def pagina_negocio(negocio_id):
    """Página pública del negocio"""
    negocio = db_session.query(Negocio).filter(Negocio.id == negocio_id).first()
    if not negocio:
        return "Negocio no encontrado", 404
    
    # Servicios
    servicios = db_session.query(Servicio).filter(
        Servicio.negocio_id == negocio_id,
        Servicio.activo == True
    ).all()
    
    # ========== HORARIOS CORREGIDOS ==========
    horarios_db = db_session.query(ConfiguracionHorario).filter(
        ConfiguracionHorario.negocio_id == negocio_id
    ).order_by(ConfiguracionHorario.dia_semana).all()
    
    # Mapear números de día a nombres (1=Lunes, 7=Domingo)
    dias_map = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 
                5: 'Viernes', 6: 'Sábado', 7: 'Domingo'}
    
    # Función para convertir hora 24h a 12h
    def convertir_a_12h(hora_valor):
        if not hora_valor:
            return ""
        try:
            # Si es objeto time
            if hasattr(hora_valor, 'hour'):
                hora = hora_valor.hour
                minutos = hora_valor.minute
            else:
                # Si es string
                hora_str = str(hora_valor).strip()
                if ':' in hora_str:
                    partes = hora_str.split(':')
                    hora = int(partes[0])
                    minutos = int(partes[1]) if len(partes) > 1 else 0
                else:
                    hora = int(hora_str)
                    minutos = 0
            
            # Convertir a formato 12h
            if hora == 0:
                hora_12 = 12
                periodo = 'AM'
            elif hora < 12:
                hora_12 = hora
                periodo = 'AM'
            elif hora == 12:
                hora_12 = 12
                periodo = 'PM'
            else:
                hora_12 = hora - 12
                periodo = 'PM'
            
            return f"{hora_12}:{minutos:02d} {periodo}"
        except Exception as e:
            print(f"Error convirtiendo hora {hora_valor}: {e}")
            return str(hora_valor)
    
    # Crear lista de horarios formateados
    horarios_formateados = []
    for h in horarios_db:
        dia_nombre = dias_map.get(h.dia_semana, str(h.dia_semana))
        # Saltar si el día es inválido
        if dia_nombre in ['7', 7]:
            continue
            
        horarios_formateados.append({
            'dia': dia_nombre,
            'hora_inicio': convertir_a_12h(h.hora_inicio) if h.activo else '',
            'hora_fin': convertir_a_12h(h.hora_fin) if h.activo else '',
            'activo': h.activo
        })
    
    # Galería
    fotos_galeria = db_session.query(FotoNegocio).filter(
        FotoNegocio.negocio_id == negocio_id
    ).order_by(FotoNegocio.orden).all()
    
    # Portada y perfil
    portada_url = negocio.foto_portada
    perfil_url = negocio.foto_perfil
    
    if not portada_url and fotos_galeria:
        portada_url = fotos_galeria[0].url
    
    # Profesionales
    profesionales = db_session.query(Profesional).filter(
        Profesional.negocio_id == negocio_id, 
        Profesional.activo == True
    ).all()
    
    # Productos
    productos = db_session.query(Producto).filter(
        Producto.negocio_id == negocio_id, 
        Producto.disponible == True
    ).all()
    
    # Flota (negocios de alquiler de vehículos). Si la tabla aún no existe se muestra vacía.
    vehiculos = []
    if negocio.tipo_negocio == 'alquiler_vehiculos':
        try:
            from sqlalchemy import text
            filas = db_session.execute(text(
                "SELECT id, nombre, categoria, pasajeros, transmision, combustible, precio_dia, foto_url FROM vehiculos "
                "WHERE negocio_id = :n AND activo = TRUE ORDER BY precio_dia, nombre"), {'n': negocio_id}).mappings().all()
            vehiculos = [dict(f) for f in filas]
        except Exception:
            db_session.rollback()

    acento, acento_tinta = acento_del_negocio(negocio)
    return render_template('directorio/negocio.html',
                         vehiculos=vehiculos,
                         acento=acento,
                         acento_tinta=acento_tinta,
                         negocio=negocio,
                         servicios=servicios,
                         horarios=horarios_formateados,
                         fotos_galeria=fotos_galeria,
                         profesionales=profesionales,
                         productos=productos,
                         portada_url=portada_url,
                         perfil_url=perfil_url)

@app.route('/profesional/<int:profesional_id>/publico')
def perfil_profesional(profesional_id):
    """Perfil público del profesional"""
    profesional = db_session.query(Profesional).filter(Profesional.id == profesional_id).first()
    if not profesional:
        return "Profesional no encontrado", 404
    
    # Obtener información del negocio
    negocio = db_session.query(Negocio).filter(Negocio.id == profesional.negocio_id).first()
    
    # Obtener portada del negocio
    negocio_portada_url = None
    negocio_nombre = ""
    negocio_emoji = "🏢"
    
    if negocio:
        negocio_nombre = negocio.nombre
        negocio_emoji = negocio.emoji or "🏢"
        negocio_portada_url = negocio.foto_portada
        
        if not negocio_portada_url:
            primera_foto = db_session.query(FotoNegocio).filter(
                FotoNegocio.negocio_id == negocio.id
            ).order_by(FotoNegocio.orden).first()
            if primera_foto:
                negocio_portada_url = primera_foto.url
    
    fotos_trabajo = db_session.query(FotoTrabajoProfesional).filter(
        FotoTrabajoProfesional.profesional_id == profesional_id
    ).all()
    
    # ========== OBTENER PROMOCIÓN ACTIVA DEL PROFESIONAL ==========
    from datetime import datetime
    fecha_actual = datetime.now().date()
    
    promocion_activa = db_session.query(Promocion).filter(
        Promocion.profesional_id == profesional_id,
        Promocion.activo == True,
        Promocion.fecha_inicio <= fecha_actual,
        Promocion.fecha_fin >= fecha_actual
    ).first()
    
    promocion_data = None
    if promocion_activa:
        promocion_data = {
            'id': promocion_activa.id,
            'titulo': promocion_activa.titulo,
            'descripcion': promocion_activa.descripcion,
            'premio': promocion_activa.premio,
            'fecha_inicio': promocion_activa.fecha_inicio,
            'fecha_fin': promocion_activa.fecha_fin,
            'imagen_url': promocion_activa.imagen_url
        }
    
    acento, acento_tinta = acento_del_negocio(negocio)
    return render_template('directorio/profesional.html',
                         acento=acento,
                         acento_tinta=acento_tinta,
                         profesional=profesional,
                         fotos_trabajo=fotos_trabajo,
                         negocio_nombre=negocio_nombre,
                         negocio_emoji=negocio_emoji,
                         negocio_tipo=negocio.tipo_negocio if negocio else None,
                         negocio_portada_url=negocio_portada_url,
                         promocion=promocion_data)




# ─── Páginas de error con el diseño de la app ────────────────────────────────
_ERRORES = {
    404: ('Página no encontrada', 'La dirección que buscas no existe o se movió.'),
    500: ('Algo salió mal', 'Tuvimos un problema al procesar tu solicitud. Inténtalo de nuevo en unos minutos.'),
}


def _pagina_error(codigo):
    titulo, mensaje = _ERRORES[codigo]
    if request.path.startswith('/api/') or (request.accept_mimetypes.best == 'application/json'):
        return jsonify({'success': False, 'error': titulo}), codigo
    try:
        return render_template('error.html', codigo=codigo, titulo=titulo, mensaje=mensaje), codigo
    except Exception:
        return f'{codigo} - {titulo}', codigo


@app.errorhandler(404)
def error_404(_e):
    return _pagina_error(404)


@app.errorhandler(500)
def error_500(_e):
    return _pagina_error(500)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
