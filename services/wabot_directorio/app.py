# services/wabot_directorio/app.py
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
import sys

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
    ConfiguracionHorario
)

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuración de base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:ClWjzRkhvcoQJdNPaMxLpJBJBZUIOHHX@caboose.proxy.rlwy.net:55226/railway"

print(f"Conectando a: {DATABASE_URL[:50]}...")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
db_session = scoped_session(sessionmaker(bind=engine))

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
    
    # Horarios
    horarios_db = db_session.query(ConfiguracionHorario).filter(
        ConfiguracionHorario.negocio_id == negocio_id
    ).order_by(ConfiguracionHorario.dia_semana).all()
    
    dias_map = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 
                4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
    
    horarios_formateados = []
    for h in horarios_db:
        dia_nombre = dias_map.get(h.dia_semana, str(h.dia_semana))
        if dia_nombre in ['7', 7]:
            continue
        horarios_formateados.append({
            'dia': dia_nombre,
            'hora_inicio': h.hora_inicio,
            'hora_fin': h.hora_fin,
            'activo': h.activo
        })
    
    # Galería del negocio
    fotos_galeria = db_session.query(FotoNegocio).filter(
        FotoNegocio.negocio_id == negocio_id
    ).order_by(FotoNegocio.orden).all()
    
    # Portada y perfil desde campos específicos
    portada_url = negocio.foto_portada
    perfil_url = negocio.foto_perfil
    
    # Fallback: si no hay portada, usar primera foto de galería
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
    
    return render_template('directorio/negocio.html',
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
    
    fotos_trabajo = db_session.query(FotoTrabajoProfesional).filter(
        FotoTrabajoProfesional.profesional_id == profesional_id
    ).all()
    
    return render_template('directorio/profesional.html',
                         profesional=profesional,
                         fotos_trabajo=fotos_trabajo)   



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)