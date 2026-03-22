# services/wabot_directorio/app.py
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Negocio, Profesional, Producto, FotoNegocio, FotoTrabajoProfesional, Servicio, ConfiguracionHorario
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuración de base de datos - USAR LA URL PÚBLICA
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
    
    # Obtener servicios
    servicios = db_session.query(Servicio).filter(
        Servicio.negocio_id == negocio_id,
        Servicio.activo == True
    ).all()
    
    # Obtener horarios - NO modificar los objetos originales
    horarios_db = db_session.query(ConfiguracionHorario).filter(
        ConfiguracionHorario.negocio_id == negocio_id
    ).order_by(ConfiguracionHorario.dia_semana).all()
    
    # Mapear números de día a nombres (0=Lunes, 6=Domingo)
    dias_map = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 
                4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
    
    # Función para convertir hora 24h a 12h (formato AM/PM)
    def convertir_a_12h(hora_str):
        if not hora_str:
            return ""
        try:
            # Manejar formatos como "19:00" o "19:00:00"
            partes = hora_str.split(':')
            hora = int(partes[0])
            minuto = partes[1].split('.')[0]  # por si viene con segundos
            minuto_int = int(minuto)
            
            periodo = 'AM' if hora < 12 else 'PM'
            hora_12 = hora % 12
            if hora_12 == 0:
                hora_12 = 12
            
            return f"{hora_12}:{minuto_int:02d} {periodo}"
        except Exception as e:
            print(f"Error convirtiendo hora {hora_str}: {e}")
            return hora_str
    
    # Crear lista de horarios formateados
    horarios_formateados = []
    for h in horarios_db:
        dia_nombre = dias_map.get(h.dia_semana, str(h.dia_semana))
        # Saltar si es un día inválido (por si hay algún 7)
        if dia_nombre in ['7', 7]:
            continue
            
        # Convertir horas a formato 12h
        hora_inicio_12h = convertir_a_12h(h.hora_inicio) if h.hora_inicio else ''
        hora_fin_12h = convertir_a_12h(h.hora_fin) if h.hora_fin else ''
        
        horarios_formateados.append({
            'dia': dia_nombre,
            'hora_inicio': hora_inicio_12h,
            'hora_fin': hora_fin_12h,
            'activo': h.activo
        })
    
    fotos = db_session.query(FotoNegocio).filter(FotoNegocio.negocio_id == negocio_id).order_by(FotoNegocio.orden).all()
    
    # Portada: primera foto si existe, si no, None
    portada_url = fotos[0].url if fotos else None
    
    profesionales = db_session.query(Profesional).filter(
        Profesional.negocio_id == negocio_id, 
        Profesional.activo == True
    ).all()
    productos = db_session.query(Producto).filter(
        Producto.negocio_id == negocio_id, 
        Producto.disponible == True
    ).all()
    
    return render_template('directorio/negocio.html',
                         negocio=negocio,
                         servicios=servicios,
                         horarios=horarios_formateados,
                         fotos=fotos,
                         profesionales=profesionales,
                         productos=productos,
                         portada_url=portada_url)

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