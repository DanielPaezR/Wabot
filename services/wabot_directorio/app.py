# services/wabot_directorio/app.py
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
import sys

# Ya no necesitamos agregar shared al path porque models.py está local
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Negocio, Profesional, Producto, FotoNegocio, FotoTrabajoProfesional
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuración de base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
db_session = scoped_session(sessionmaker(bind=engine))

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

@app.route('/')
def index():
    return "Directorio Wabot - Servicio funcionando correctamente"

@app.route('/directorio')
def directorio():
    """Página principal del mapa"""
    return render_template('directorio/mapa.html')

@app.route('/api/negocios')
def api_negocios():
    """API para obtener todos los negocios con coordenadas"""
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
            'latitud': n.latitud,
            'longitud': n.longitud,
            'direccion': n.direccion,
            'tipo_negocio': n.tipo_negocio,
            'calificacion': float(n.calificacion_promedio) if n.calificacion_promedio else 0,
            'total_opiniones': n.total_opiniones
        })
    return jsonify(result)

@app.route('/negocio/<int:negocio_id>')
def pagina_negocio(negocio_id):
    """Página pública del negocio"""
    negocio = db_session.query(Negocio).filter(Negocio.id == negocio_id).first()
    if not negocio:
        return "Negocio no encontrado", 404
    
    fotos = db_session.query(FotoNegocio).filter(FotoNegocio.negocio_id == negocio_id).order_by(FotoNegocio.orden).all()
    profesionales = db_session.query(Profesional).filter(Profesional.negocio_id == negocio_id, Profesional.activo == True).all()
    productos = db_session.query(Producto).filter(Producto.negocio_id == negocio_id, Producto.disponible == True).all()
    
    return render_template('directorio/negocio.html',
                         negocio=negocio,
                         fotos=fotos,
                         profesionales=profesionales,
                         productos=productos)

@app.route('/profesional/<int:profesional_id>/publico')
def perfil_profesional(profesional_id):
    """Perfil público del profesional"""
    profesional = db_session.query(Profesional).filter(Profesional.id == profesional_id).first()
    if not profesional:
        return "Profesional no encontrado", 404
    
    fotos_trabajo = db_session.query(FotoTrabajoProfesional).filter(FotoTrabajoProfesional.profesional_id == profesional_id).all()
    
    return render_template('directorio/profesional.html',
                         profesional=profesional,
                         fotos_trabajo=fotos_trabajo)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)