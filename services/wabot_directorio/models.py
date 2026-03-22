# services/wabot_directorio/models.py
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, JSON, DECIMAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Negocio(Base):
    __tablename__ = 'negocios'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    telefono_whatsapp = Column(String(20))
    tipo_negocio = Column(String(50))
    emoji = Column(String(10))
    configuracion = Column(JSON)
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    direccion = Column(String(300))
    latitud = Column(Float)
    longitud = Column(Float)
    descripcion = Column(Text)
    horario_texto = Column(String(500))
    calificacion_promedio = Column(DECIMAL(2, 1), default=0)
    total_opiniones = Column(Integer, default=0)
    foto_portada = Column(String(500))   # Banner superior
    foto_perfil = Column(String(500))    # Logo/perfil circular
    
    # Relaciones
    fotos = relationship("FotoNegocio", back_populates="negocio")
    profesionales = relationship("Profesional", back_populates="negocio")
    productos = relationship("Producto", back_populates="negocio")
    servicios = relationship("Servicio", back_populates="negocio")
    horarios = relationship("ConfiguracionHorario", back_populates="negocio")

class Servicio(Base):
    __tablename__ = 'servicios'
    
    id = Column(Integer, primary_key=True)
    negocio_id = Column(Integer, ForeignKey('negocios.id'))
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)
    duracion = Column(Integer)
    precio = Column(DECIMAL(10, 2))
    precio_maximo = Column(DECIMAL(10, 2))
    tipo_precio = Column(String(20))
    activo = Column(Boolean, default=True)
    foto_url = Column(String(500))   # Foto ejemplo del servicio
    
    negocio = relationship("Negocio", back_populates="servicios")
    for s in servicios:
        print(f"📸 Servicio: {s.nombre} - foto_url: {s.foto_url}")

class ConfiguracionHorario(Base):
    __tablename__ = 'configuracion_horarios'
    
    id = Column(Integer, primary_key=True)
    negocio_id = Column(Integer, ForeignKey('negocios.id'))
    dia_semana = Column(Integer)
    hora_inicio = Column(String(10))
    hora_fin = Column(String(10))
    activo = Column(Boolean, default=True)
    
    negocio = relationship("Negocio", back_populates="horarios")

class FotoNegocio(Base):
    __tablename__ = 'fotos_negocio'
    
    id = Column(Integer, primary_key=True)
    negocio_id = Column(Integer, ForeignKey('negocios.id'))
    url = Column(String(500), nullable=False)
    orden = Column(Integer, default=0)
    descripcion = Column(String(200))
    fecha_subida = Column(DateTime, default=datetime.utcnow)
    
    negocio = relationship("Negocio", back_populates="fotos")

class Profesional(Base):
    __tablename__ = 'profesionales'
    
    id = Column(Integer, primary_key=True)
    negocio_id = Column(Integer, ForeignKey('negocios.id'))
    nombre = Column(String(100), nullable=False)
    telefono = Column(String(20))
    especialidad = Column(String(100))
    pin = Column(String(10))
    usuario_id = Column(Integer)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    foto_url = Column(String(500))
    calificacion_promedio = Column(DECIMAL(2, 1), default=0)
    total_opiniones = Column(Integer, default=0)
    
    negocio = relationship("Negocio", back_populates="profesionales")
    fotos_trabajo = relationship("FotoTrabajoProfesional", back_populates="profesional")

class FotoTrabajoProfesional(Base):
    __tablename__ = 'fotos_trabajo_profesional'
    
    id = Column(Integer, primary_key=True)
    profesional_id = Column(Integer, ForeignKey('profesionales.id'))
    url = Column(String(500), nullable=False)
    descripcion = Column(String(200))
    fecha_subida = Column(DateTime, default=datetime.utcnow)
    
    profesional = relationship("Profesional", back_populates="fotos_trabajo")

class Producto(Base):
    __tablename__ = 'productos'
    
    id = Column(Integer, primary_key=True)
    negocio_id = Column(Integer, ForeignKey('negocios.id'))
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)
    precio = Column(DECIMAL(10, 2))
    imagen_url = Column(String(500))
    disponible = Column(Boolean, default=True)
    
    negocio = relationship("Negocio", back_populates="productos")

class OpinionNegocio(Base):
    __tablename__ = 'opiniones_negocio'
    
    id = Column(Integer, primary_key=True)
    negocio_id = Column(Integer, ForeignKey('negocios.id'))
    cliente_id = Column(Integer, ForeignKey('clientes.id'))
    calificacion = Column(Integer, nullable=False)
    comentario = Column(Text)
    fecha = Column(DateTime, default=datetime.utcnow)
    
    negocio = relationship("Negocio")

class OpinionProfesional(Base):
    __tablename__ = 'opiniones_profesional'
    
    id = Column(Integer, primary_key=True)
    profesional_id = Column(Integer, ForeignKey('profesionales.id'))
    cliente_id = Column(Integer, ForeignKey('clientes.id'))
    calificacion = Column(Integer, nullable=False)
    comentario = Column(Text)
    fecha = Column(DateTime, default=datetime.utcnow)
    
    profesional = relationship("Profesional")