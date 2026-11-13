-- ============================================================================
-- Wabot: esquema base de la base de datos (solo estructura, sin datos)
-- Volcado de produccion el 2026-11-13 con: pg_dump --schema-only --no-owner --no-privileges
--
-- Para una base NUEVA (desarrollo, pruebas, recuperacion ante desastres):
--     psql "$DATABASE_URL" -f services/wabot_chat/schema.sql
-- y despues, si quieres datos de ejemplo:  python -c "import database; database.init_db()"
--
-- Notas:
--   * citas.fecha y citas.hora son TEXT ('YYYY-MM-DD' y 'HH:MM'), no DATE/TIME.
--   * La tabla conversaciones_chat (estado del chat) la crea sola la aplicacion al primer uso.
--   * Si cambias el esquema en produccion, vuelve a generar este archivo.
-- ============================================================================

--
-- PostgreSQL database dump
--

-- Dumped from database version 17.11 (Debian 17.11-1.pgdg13+2)
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bloqueos_recurrentes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bloqueos_recurrentes (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    profesional_id integer NOT NULL,
    dias_semana text NOT NULL,
    hora_inicio time without time zone NOT NULL,
    hora_fin time without time zone NOT NULL,
    motivo text,
    fecha_inicio date,
    fecha_fin date,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);

--
-- Name: bloqueos_recurrentes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bloqueos_recurrentes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: bloqueos_recurrentes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bloqueos_recurrentes_id_seq OWNED BY public.bloqueos_recurrentes.id;

--
-- Name: citas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citas (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    profesional_id integer NOT NULL,
    cliente_telefono text NOT NULL,
    cliente_nombre text,
    fecha text NOT NULL,
    hora text NOT NULL,
    servicio_id integer NOT NULL,
    estado text DEFAULT 'confirmado'::text,
    recordatorio_24h_enviado boolean DEFAULT false,
    recordatorio_1h_enviado boolean DEFAULT false,
    notificado_profesional boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now(),
    duracion_minutos integer
);

--
-- Name: citas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.citas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: citas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.citas_id_seq OWNED BY public.citas.id;

--
-- Name: clientes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clientes (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    telefono text NOT NULL,
    nombre text NOT NULL,
    email text,
    created_at text,
    updated_at text
);

--
-- Name: clientes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.clientes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: clientes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.clientes_id_seq OWNED BY public.clientes.id;

--
-- Name: configuracion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.configuracion (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    hora_inicio text DEFAULT '09:00'::text,
    hora_fin text DEFAULT '19:00'::text,
    almuerzo_inicio text DEFAULT '13:00'::text,
    almuerzo_fin text DEFAULT '14:00'::text,
    duracion_cita_base integer DEFAULT 60
);

--
-- Name: configuracion_horarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.configuracion_horarios (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    dia_semana integer NOT NULL,
    activo boolean DEFAULT true,
    hora_inicio time without time zone NOT NULL,
    hora_fin time without time zone NOT NULL,
    almuerzo_inicio time without time zone,
    almuerzo_fin time without time zone
);

--
-- Name: configuracion_horarios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.configuracion_horarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: configuracion_horarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.configuracion_horarios_id_seq OWNED BY public.configuracion_horarios.id;

--
-- Name: configuracion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.configuracion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: configuracion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.configuracion_id_seq OWNED BY public.configuracion.id;

--
-- Name: conversaciones_whatsapp; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversaciones_whatsapp (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    cliente_telefono character varying(20) NOT NULL,
    mensaje_usuario text,
    respuesta_bot text,
    session_id character varying(100),
    leido boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
);

--
-- Name: conversaciones_whatsapp_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversaciones_whatsapp_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: conversaciones_whatsapp_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversaciones_whatsapp_id_seq OWNED BY public.conversaciones_whatsapp.id;

--
-- Name: fotos_negocio; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fotos_negocio (
    id integer NOT NULL,
    negocio_id integer,
    url character varying(500) NOT NULL,
    orden integer DEFAULT 0,
    descripcion character varying(200),
    fecha_subida timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: fotos_negocio_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fotos_negocio_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: fotos_negocio_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fotos_negocio_id_seq OWNED BY public.fotos_negocio.id;

--
-- Name: fotos_trabajo_profesional; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fotos_trabajo_profesional (
    id integer NOT NULL,
    profesional_id integer,
    url character varying(500) NOT NULL,
    descripcion character varying(200),
    fecha_subida timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: fotos_trabajo_profesional_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fotos_trabajo_profesional_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: fotos_trabajo_profesional_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fotos_trabajo_profesional_id_seq OWNED BY public.fotos_trabajo_profesional.id;

--
-- Name: imagenes_profesionales; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.imagenes_profesionales (
    id integer NOT NULL,
    profesional_id integer NOT NULL,
    negocio_id integer NOT NULL,
    tipo character varying(50) DEFAULT 'perfil'::character varying,
    nombre_archivo character varying(255) NOT NULL,
    ruta_archivo character varying(500) NOT NULL,
    url_publica character varying(500),
    mime_type character varying(100),
    "tamaño_bytes" integer,
    es_principal boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: imagenes_profesionales_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.imagenes_profesionales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: imagenes_profesionales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.imagenes_profesionales_id_seq OWNED BY public.imagenes_profesionales.id;

--
-- Name: likes_concurso; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.likes_concurso (
    id integer NOT NULL,
    participacion_id integer NOT NULL,
    ip_address character varying(50) NOT NULL,
    fecha_voto timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: likes_concurso_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.likes_concurso_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: likes_concurso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.likes_concurso_id_seq OWNED BY public.likes_concurso.id;

--
-- Name: logs_notificaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logs_notificaciones (
    id integer NOT NULL,
    accion text NOT NULL,
    datos json NOT NULL,
    resultado text,
    error text,
    fecha text DEFAULT 'NOW()'::text
);

--
-- Name: logs_notificaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.logs_notificaciones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: logs_notificaciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.logs_notificaciones_id_seq OWNED BY public.logs_notificaciones.id;

--
-- Name: negocios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.negocios (
    id integer NOT NULL,
    nombre text NOT NULL,
    telefono_whatsapp text NOT NULL,
    tipo_negocio text DEFAULT 'general'::text,
    emoji text DEFAULT '👋'::text,
    configuracion text DEFAULT '{}'::text,
    activo boolean DEFAULT true,
    fecha_creacion timestamp without time zone DEFAULT now(),
    direccion text,
    latitud double precision,
    longitud double precision,
    descripcion text,
    horario_texto character varying(500),
    calificacion_promedio numeric(2,1) DEFAULT 0,
    total_opiniones integer DEFAULT 0,
    foto_portada character varying(500),
    foto_perfil character varying(500),
    prompt_ia text DEFAULT ''::text,
    instagram text,
    facebook text,
    tiktok text,
    twitter text,
    youtube text,
    sitio_web text,
    pais text,
    zona_horaria text
);

--
-- Name: negocios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.negocios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: negocios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.negocios_id_seq OWNED BY public.negocios.id;

--
-- Name: notificaciones_profesional; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notificaciones_profesional (
    id integer NOT NULL,
    profesional_id integer NOT NULL,
    titulo text NOT NULL,
    mensaje text NOT NULL,
    tipo text DEFAULT 'info'::text,
    leida boolean DEFAULT false,
    metadata json,
    fecha_creacion date DEFAULT '2025-12-12'::date,
    fecha_leida date,
    cita_id integer
);

--
-- Name: notificaciones_profesional_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notificaciones_profesional_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: notificaciones_profesional_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notificaciones_profesional_id_seq OWNED BY public.notificaciones_profesional.id;

--
-- Name: numeros_whatsapp_negocio; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.numeros_whatsapp_negocio (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    numero_whatsapp character varying(20) NOT NULL,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);

--
-- Name: numeros_whatsapp_negocio_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.numeros_whatsapp_negocio_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: numeros_whatsapp_negocio_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.numeros_whatsapp_negocio_id_seq OWNED BY public.numeros_whatsapp_negocio.id;

--
-- Name: opiniones_negocio; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.opiniones_negocio (
    id integer NOT NULL,
    negocio_id integer,
    cliente_id integer,
    calificacion integer NOT NULL,
    comentario text,
    fecha timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT opiniones_negocio_calificacion_check CHECK (((calificacion >= 1) AND (calificacion <= 5)))
);

--
-- Name: opiniones_negocio_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.opiniones_negocio_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: opiniones_negocio_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.opiniones_negocio_id_seq OWNED BY public.opiniones_negocio.id;

--
-- Name: opiniones_profesional; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.opiniones_profesional (
    id integer NOT NULL,
    profesional_id integer,
    cliente_id integer,
    calificacion integer NOT NULL,
    comentario text,
    fecha timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT opiniones_profesional_calificacion_check CHECK (((calificacion >= 1) AND (calificacion <= 5)))
);

--
-- Name: opiniones_profesional_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.opiniones_profesional_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: opiniones_profesional_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.opiniones_profesional_id_seq OWNED BY public.opiniones_profesional.id;

--
-- Name: participaciones_concurso; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.participaciones_concurso (
    id integer NOT NULL,
    promocion_id integer NOT NULL,
    cliente_telefono character varying(50) NOT NULL,
    cliente_nombre character varying(255) NOT NULL,
    foto_url text NOT NULL,
    nota text,
    likes integer DEFAULT 0,
    fecha_creacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

--
-- Name: participaciones_concurso_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.participaciones_concurso_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: participaciones_concurso_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.participaciones_concurso_id_seq OWNED BY public.participaciones_concurso.id;

--
-- Name: plantillas_mensajes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plantillas_mensajes (
    id integer NOT NULL,
    negocio_id integer,
    nombre text NOT NULL,
    plantilla text NOT NULL,
    descripcion text,
    variables_disponibles text DEFAULT '[]'::text,
    es_base boolean DEFAULT false,
    activo boolean DEFAULT true,
    fecha_creacion timestamp without time zone DEFAULT now()
);

--
-- Name: plantillas_mensajes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plantillas_mensajes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: plantillas_mensajes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plantillas_mensajes_id_seq OWNED BY public.plantillas_mensajes.id;

--
-- Name: productos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.productos (
    id integer NOT NULL,
    negocio_id integer,
    nombre character varying(100) NOT NULL,
    descripcion text,
    precio numeric(10,2),
    imagen_url character varying(500),
    disponible boolean DEFAULT true,
    moneda character varying(5) DEFAULT 'COP'::character varying
);

--
-- Name: productos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.productos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: productos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.productos_id_seq OWNED BY public.productos.id;

--
-- Name: profesional_servicios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profesional_servicios (
    id integer NOT NULL,
    profesional_id integer NOT NULL,
    servicio_id integer NOT NULL
);

--
-- Name: profesional_servicios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.profesional_servicios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: profesional_servicios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.profesional_servicios_id_seq OWNED BY public.profesional_servicios.id;

--
-- Name: profesionales; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profesionales (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    nombre text NOT NULL,
    telefono text,
    especialidad text,
    pin text,
    usuario_id integer,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    foto_url text,
    calificacion_promedio numeric(2,1) DEFAULT 0,
    total_opiniones integer DEFAULT 0
);

--
-- Name: profesionales_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.profesionales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: profesionales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.profesionales_id_seq OWNED BY public.profesionales.id;

--
-- Name: promociones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.promociones (
    id integer NOT NULL,
    profesional_id integer NOT NULL,
    titulo character varying(200) NOT NULL,
    descripcion text,
    premio character varying(200),
    imagen_url character varying(500),
    fecha_inicio date,
    fecha_fin date,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    negocio_id integer NOT NULL,
    tipo_promocion character varying(50) DEFAULT 'concurso_fotos'::character varying,
    descuento_porcentaje integer,
    descuento_monto numeric(10,2),
    servicios_aplica text,
    hora_inicio time without time zone,
    hora_fin time without time zone
);

--
-- Name: promociones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.promociones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: promociones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.promociones_id_seq OWNED BY public.promociones.id;

--
-- Name: scheduler_ejecuciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduler_ejecuciones (
    clave text NOT NULL,
    creada timestamp without time zone DEFAULT now()
);

--
-- Name: servicios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.servicios (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    nombre text NOT NULL,
    duracion integer NOT NULL,
    precio numeric(10,2) NOT NULL,
    descripcion text,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    tipo_precio text DEFAULT '"fijo"'::text,
    precio_maximo real,
    foto_url character varying(500),
    moneda character varying(5) DEFAULT 'COP'::character varying
);

--
-- Name: servicios_adicionales_cliente; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.servicios_adicionales_cliente (
    id integer NOT NULL,
    servicio_personalizado_id integer,
    servicio_id integer,
    incluido_por_defecto boolean DEFAULT true,
    activo boolean DEFAULT true,
    fecha_creacion text
);

--
-- Name: servicios_adicionales_cliente_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.servicios_adicionales_cliente_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: servicios_adicionales_cliente_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.servicios_adicionales_cliente_id_seq OWNED BY public.servicios_adicionales_cliente.id;

--
-- Name: servicios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.servicios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: servicios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.servicios_id_seq OWNED BY public.servicios.id;

--
-- Name: servicios_personalizados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.servicios_personalizados (
    id integer NOT NULL,
    cliente_id integer,
    negocio_id integer,
    profesional_id integer,
    servicio_base_id integer,
    nombre_personalizado text,
    duracion_personalizada integer,
    precio_personalizado real,
    descripcion text,
    activo boolean DEFAULT true,
    fecha_creacion text,
    fecha_actualizacion text
);

--
-- Name: servicios_personalizados_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.servicios_personalizados_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: servicios_personalizados_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.servicios_personalizados_id_seq OWNED BY public.servicios_personalizados.id;

--
-- Name: suscripciones_push; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suscripciones_push (
    id integer NOT NULL,
    profesional_id integer NOT NULL,
    subscription_json text NOT NULL,
    dispositivo_info text,
    activa boolean DEFAULT true
);

--
-- Name: suscripciones_push_clientes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suscripciones_push_clientes (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    cliente_telefono character varying(20) NOT NULL,
    subscription_json text NOT NULL,
    dispositivo_info text,
    fecha_creacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    activa boolean DEFAULT true
);

--
-- Name: suscripciones_push_clientes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.suscripciones_push_clientes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: suscripciones_push_clientes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.suscripciones_push_clientes_id_seq OWNED BY public.suscripciones_push_clientes.id;

--
-- Name: suscripciones_push_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.suscripciones_push_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: suscripciones_push_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.suscripciones_push_id_seq OWNED BY public.suscripciones_push.id;

--
-- Name: usuarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usuarios (
    id integer NOT NULL,
    negocio_id integer NOT NULL,
    nombre text NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    rol text DEFAULT 'propietario'::text,
    activo boolean DEFAULT true,
    fecha_creacion timestamp without time zone DEFAULT now(),
    ultimo_login timestamp without time zone
);

--
-- Name: usuarios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.usuarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: usuarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.usuarios_id_seq OWNED BY public.usuarios.id;

--
-- Name: whatsapp_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_sessions (
    id integer NOT NULL,
    session_id character varying(100) NOT NULL,
    negocio_id integer NOT NULL,
    cliente_telefono character varying(20) NOT NULL,
    chat_step character varying(50) DEFAULT 'inicio'::character varying,
    datos_agendamiento jsonb DEFAULT '{}'::jsonb,
    ultima_actividad timestamp without time zone DEFAULT now(),
    created_at timestamp without time zone DEFAULT now()
);

--
-- Name: whatsapp_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.whatsapp_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: whatsapp_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.whatsapp_sessions_id_seq OWNED BY public.whatsapp_sessions.id;

--
-- Name: bloqueos_recurrentes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bloqueos_recurrentes ALTER COLUMN id SET DEFAULT nextval('public.bloqueos_recurrentes_id_seq'::regclass);

--
-- Name: citas id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citas ALTER COLUMN id SET DEFAULT nextval('public.citas_id_seq'::regclass);

--
-- Name: clientes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clientes ALTER COLUMN id SET DEFAULT nextval('public.clientes_id_seq'::regclass);

--
-- Name: configuracion id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion ALTER COLUMN id SET DEFAULT nextval('public.configuracion_id_seq'::regclass);

--
-- Name: configuracion_horarios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion_horarios ALTER COLUMN id SET DEFAULT nextval('public.configuracion_horarios_id_seq'::regclass);

--
-- Name: conversaciones_whatsapp id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversaciones_whatsapp ALTER COLUMN id SET DEFAULT nextval('public.conversaciones_whatsapp_id_seq'::regclass);

--
-- Name: fotos_negocio id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fotos_negocio ALTER COLUMN id SET DEFAULT nextval('public.fotos_negocio_id_seq'::regclass);

--
-- Name: fotos_trabajo_profesional id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fotos_trabajo_profesional ALTER COLUMN id SET DEFAULT nextval('public.fotos_trabajo_profesional_id_seq'::regclass);

--
-- Name: imagenes_profesionales id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imagenes_profesionales ALTER COLUMN id SET DEFAULT nextval('public.imagenes_profesionales_id_seq'::regclass);

--
-- Name: likes_concurso id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.likes_concurso ALTER COLUMN id SET DEFAULT nextval('public.likes_concurso_id_seq'::regclass);

--
-- Name: logs_notificaciones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs_notificaciones ALTER COLUMN id SET DEFAULT nextval('public.logs_notificaciones_id_seq'::regclass);

--
-- Name: negocios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negocios ALTER COLUMN id SET DEFAULT nextval('public.negocios_id_seq'::regclass);

--
-- Name: notificaciones_profesional id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones_profesional ALTER COLUMN id SET DEFAULT nextval('public.notificaciones_profesional_id_seq'::regclass);

--
-- Name: numeros_whatsapp_negocio id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.numeros_whatsapp_negocio ALTER COLUMN id SET DEFAULT nextval('public.numeros_whatsapp_negocio_id_seq'::regclass);

--
-- Name: opiniones_negocio id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_negocio ALTER COLUMN id SET DEFAULT nextval('public.opiniones_negocio_id_seq'::regclass);

--
-- Name: opiniones_profesional id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_profesional ALTER COLUMN id SET DEFAULT nextval('public.opiniones_profesional_id_seq'::regclass);

--
-- Name: participaciones_concurso id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.participaciones_concurso ALTER COLUMN id SET DEFAULT nextval('public.participaciones_concurso_id_seq'::regclass);

--
-- Name: plantillas_mensajes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plantillas_mensajes ALTER COLUMN id SET DEFAULT nextval('public.plantillas_mensajes_id_seq'::regclass);

--
-- Name: productos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.productos ALTER COLUMN id SET DEFAULT nextval('public.productos_id_seq'::regclass);

--
-- Name: profesional_servicios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesional_servicios ALTER COLUMN id SET DEFAULT nextval('public.profesional_servicios_id_seq'::regclass);

--
-- Name: profesionales id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesionales ALTER COLUMN id SET DEFAULT nextval('public.profesionales_id_seq'::regclass);

--
-- Name: promociones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promociones ALTER COLUMN id SET DEFAULT nextval('public.promociones_id_seq'::regclass);

--
-- Name: servicios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios ALTER COLUMN id SET DEFAULT nextval('public.servicios_id_seq'::regclass);

--
-- Name: servicios_adicionales_cliente id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios_adicionales_cliente ALTER COLUMN id SET DEFAULT nextval('public.servicios_adicionales_cliente_id_seq'::regclass);

--
-- Name: servicios_personalizados id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios_personalizados ALTER COLUMN id SET DEFAULT nextval('public.servicios_personalizados_id_seq'::regclass);

--
-- Name: suscripciones_push id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suscripciones_push ALTER COLUMN id SET DEFAULT nextval('public.suscripciones_push_id_seq'::regclass);

--
-- Name: suscripciones_push_clientes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suscripciones_push_clientes ALTER COLUMN id SET DEFAULT nextval('public.suscripciones_push_clientes_id_seq'::regclass);

--
-- Name: usuarios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios ALTER COLUMN id SET DEFAULT nextval('public.usuarios_id_seq'::regclass);

--
-- Name: whatsapp_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_sessions ALTER COLUMN id SET DEFAULT nextval('public.whatsapp_sessions_id_seq'::regclass);

--
-- Name: bloqueos_recurrentes bloqueos_recurrentes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bloqueos_recurrentes
    ADD CONSTRAINT bloqueos_recurrentes_pkey PRIMARY KEY (id);

--
-- Name: citas citas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citas
    ADD CONSTRAINT citas_pkey PRIMARY KEY (id);

--
-- Name: clientes clientes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clientes
    ADD CONSTRAINT clientes_pkey PRIMARY KEY (id);

--
-- Name: configuracion_horarios configuracion_horarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion_horarios
    ADD CONSTRAINT configuracion_horarios_pkey PRIMARY KEY (id);

--
-- Name: configuracion configuracion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion
    ADD CONSTRAINT configuracion_pkey PRIMARY KEY (id);

--
-- Name: conversaciones_whatsapp conversaciones_whatsapp_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversaciones_whatsapp
    ADD CONSTRAINT conversaciones_whatsapp_pkey PRIMARY KEY (id);

--
-- Name: fotos_negocio fotos_negocio_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fotos_negocio
    ADD CONSTRAINT fotos_negocio_pkey PRIMARY KEY (id);

--
-- Name: fotos_trabajo_profesional fotos_trabajo_profesional_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fotos_trabajo_profesional
    ADD CONSTRAINT fotos_trabajo_profesional_pkey PRIMARY KEY (id);

--
-- Name: imagenes_profesionales imagenes_profesionales_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imagenes_profesionales
    ADD CONSTRAINT imagenes_profesionales_pkey PRIMARY KEY (id);

--
-- Name: likes_concurso likes_concurso_participacion_id_ip_address_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.likes_concurso
    ADD CONSTRAINT likes_concurso_participacion_id_ip_address_key UNIQUE (participacion_id, ip_address);

--
-- Name: likes_concurso likes_concurso_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.likes_concurso
    ADD CONSTRAINT likes_concurso_pkey PRIMARY KEY (id);

--
-- Name: logs_notificaciones logs_notificaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logs_notificaciones
    ADD CONSTRAINT logs_notificaciones_pkey PRIMARY KEY (id);

--
-- Name: negocios negocios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negocios
    ADD CONSTRAINT negocios_pkey PRIMARY KEY (id);

--
-- Name: negocios negocios_telefono_whatsapp_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negocios
    ADD CONSTRAINT negocios_telefono_whatsapp_key UNIQUE (telefono_whatsapp);

--
-- Name: notificaciones_profesional notificaciones_profesional_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones_profesional
    ADD CONSTRAINT notificaciones_profesional_pkey PRIMARY KEY (id);

--
-- Name: numeros_whatsapp_negocio numeros_whatsapp_negocio_numero_whatsapp_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.numeros_whatsapp_negocio
    ADD CONSTRAINT numeros_whatsapp_negocio_numero_whatsapp_key UNIQUE (numero_whatsapp);

--
-- Name: numeros_whatsapp_negocio numeros_whatsapp_negocio_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.numeros_whatsapp_negocio
    ADD CONSTRAINT numeros_whatsapp_negocio_pkey PRIMARY KEY (id);

--
-- Name: opiniones_negocio opiniones_negocio_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_negocio
    ADD CONSTRAINT opiniones_negocio_pkey PRIMARY KEY (id);

--
-- Name: opiniones_profesional opiniones_profesional_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_profesional
    ADD CONSTRAINT opiniones_profesional_pkey PRIMARY KEY (id);

--
-- Name: participaciones_concurso participaciones_concurso_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.participaciones_concurso
    ADD CONSTRAINT participaciones_concurso_pkey PRIMARY KEY (id);

--
-- Name: plantillas_mensajes plantillas_mensajes_negocio_id_nombre_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plantillas_mensajes
    ADD CONSTRAINT plantillas_mensajes_negocio_id_nombre_key UNIQUE (negocio_id, nombre);

--
-- Name: plantillas_mensajes plantillas_mensajes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plantillas_mensajes
    ADD CONSTRAINT plantillas_mensajes_pkey PRIMARY KEY (id);

--
-- Name: productos productos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.productos
    ADD CONSTRAINT productos_pkey PRIMARY KEY (id);

--
-- Name: profesional_servicios profesional_servicios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesional_servicios
    ADD CONSTRAINT profesional_servicios_pkey PRIMARY KEY (id);

--
-- Name: profesional_servicios profesional_servicios_profesional_id_servicio_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesional_servicios
    ADD CONSTRAINT profesional_servicios_profesional_id_servicio_id_key UNIQUE (profesional_id, servicio_id);

--
-- Name: profesionales profesionales_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesionales
    ADD CONSTRAINT profesionales_pkey PRIMARY KEY (id);

--
-- Name: promociones promociones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promociones
    ADD CONSTRAINT promociones_pkey PRIMARY KEY (id);

--
-- Name: scheduler_ejecuciones scheduler_ejecuciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduler_ejecuciones
    ADD CONSTRAINT scheduler_ejecuciones_pkey PRIMARY KEY (clave);

--
-- Name: servicios_adicionales_cliente servicios_adicionales_cliente_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios_adicionales_cliente
    ADD CONSTRAINT servicios_adicionales_cliente_pkey PRIMARY KEY (id);

--
-- Name: servicios_personalizados servicios_personalizados_cliente_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios_personalizados
    ADD CONSTRAINT servicios_personalizados_cliente_id_key UNIQUE (cliente_id);

--
-- Name: servicios_personalizados servicios_personalizados_negocio_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios_personalizados
    ADD CONSTRAINT servicios_personalizados_negocio_id_key UNIQUE (negocio_id);

--
-- Name: servicios_personalizados servicios_personalizados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios_personalizados
    ADD CONSTRAINT servicios_personalizados_pkey PRIMARY KEY (id);

--
-- Name: servicios servicios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios
    ADD CONSTRAINT servicios_pkey PRIMARY KEY (id);

--
-- Name: suscripciones_push_clientes suscripciones_push_clientes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suscripciones_push_clientes
    ADD CONSTRAINT suscripciones_push_clientes_pkey PRIMARY KEY (id);

--
-- Name: suscripciones_push suscripciones_push_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suscripciones_push
    ADD CONSTRAINT suscripciones_push_pkey PRIMARY KEY (id);

--
-- Name: suscripciones_push suscripciones_push_profesional_id_subscription_json_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suscripciones_push
    ADD CONSTRAINT suscripciones_push_profesional_id_subscription_json_key UNIQUE (profesional_id, subscription_json);

--
-- Name: configuracion_horarios unique_negocio_dia; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion_horarios
    ADD CONSTRAINT unique_negocio_dia UNIQUE (negocio_id, dia_semana);

--
-- Name: usuarios usuarios_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_email_key UNIQUE (email);

--
-- Name: usuarios usuarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_pkey PRIMARY KEY (id);

--
-- Name: whatsapp_sessions whatsapp_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_sessions
    ADD CONSTRAINT whatsapp_sessions_pkey PRIMARY KEY (id);

--
-- Name: whatsapp_sessions whatsapp_sessions_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_sessions
    ADD CONSTRAINT whatsapp_sessions_session_id_key UNIQUE (session_id);

--
-- Name: idx_conversaciones_negocio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversaciones_negocio ON public.conversaciones_whatsapp USING btree (negocio_id);

--
-- Name: idx_conversaciones_telefono; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversaciones_telefono ON public.conversaciones_whatsapp USING btree (cliente_telefono);

--
-- Name: idx_fotos_negocio_orden; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fotos_negocio_orden ON public.fotos_negocio USING btree (negocio_id, orden);

--
-- Name: idx_likes_participacion; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_likes_participacion ON public.likes_concurso USING btree (participacion_id);

--
-- Name: idx_negocios_coordenadas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_negocios_coordenadas ON public.negocios USING btree (latitud, longitud) WHERE (latitud IS NOT NULL);

--
-- Name: idx_numeros_whatsapp_negocio_negocio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_numeros_whatsapp_negocio_negocio ON public.numeros_whatsapp_negocio USING btree (negocio_id);

--
-- Name: idx_numeros_whatsapp_negocio_numero; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_numeros_whatsapp_negocio_numero ON public.numeros_whatsapp_negocio USING btree (numero_whatsapp);

--
-- Name: idx_opiniones_negocio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_opiniones_negocio ON public.opiniones_negocio USING btree (negocio_id);

--
-- Name: idx_opiniones_profesional; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_opiniones_profesional ON public.opiniones_profesional USING btree (profesional_id);

--
-- Name: idx_participaciones_promocion; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_participaciones_promocion ON public.participaciones_concurso USING btree (promocion_id);

--
-- Name: idx_productos_negocio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_productos_negocio ON public.productos USING btree (negocio_id, disponible);

--
-- Name: idx_promociones_activo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_promociones_activo ON public.promociones USING btree (activo);

--
-- Name: idx_promociones_fechas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_promociones_fechas ON public.promociones USING btree (fecha_inicio, fecha_fin);

--
-- Name: idx_promociones_profesional; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_promociones_profesional ON public.promociones USING btree (profesional_id);

--
-- Name: idx_suscripciones_cliente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_suscripciones_cliente ON public.suscripciones_push_clientes USING btree (cliente_telefono, negocio_id);

--
-- Name: idx_whatsapp_sessions_actividad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_whatsapp_sessions_actividad ON public.whatsapp_sessions USING btree (ultima_actividad);

--
-- Name: idx_whatsapp_sessions_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_whatsapp_sessions_session ON public.whatsapp_sessions USING btree (session_id);

--
-- Name: bloqueos_recurrentes bloqueos_recurrentes_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bloqueos_recurrentes
    ADD CONSTRAINT bloqueos_recurrentes_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: bloqueos_recurrentes bloqueos_recurrentes_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bloqueos_recurrentes
    ADD CONSTRAINT bloqueos_recurrentes_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesionales(id) ON DELETE CASCADE;

--
-- Name: citas citas_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citas
    ADD CONSTRAINT citas_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- Name: citas citas_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citas
    ADD CONSTRAINT citas_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesionales(id);

--
-- Name: citas citas_servicio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citas
    ADD CONSTRAINT citas_servicio_id_fkey FOREIGN KEY (servicio_id) REFERENCES public.servicios(id);

--
-- Name: configuracion_horarios configuracion_horarios_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion_horarios
    ADD CONSTRAINT configuracion_horarios_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- Name: configuracion configuracion_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.configuracion
    ADD CONSTRAINT configuracion_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- Name: conversaciones_whatsapp conversaciones_whatsapp_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversaciones_whatsapp
    ADD CONSTRAINT conversaciones_whatsapp_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: promociones fk_promociones_negocio; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promociones
    ADD CONSTRAINT fk_promociones_negocio FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: fotos_negocio fotos_negocio_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fotos_negocio
    ADD CONSTRAINT fotos_negocio_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: fotos_trabajo_profesional fotos_trabajo_profesional_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fotos_trabajo_profesional
    ADD CONSTRAINT fotos_trabajo_profesional_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesionales(id) ON DELETE CASCADE;

--
-- Name: likes_concurso likes_concurso_participacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.likes_concurso
    ADD CONSTRAINT likes_concurso_participacion_id_fkey FOREIGN KEY (participacion_id) REFERENCES public.participaciones_concurso(id) ON DELETE CASCADE;

--
-- Name: numeros_whatsapp_negocio numeros_whatsapp_negocio_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.numeros_whatsapp_negocio
    ADD CONSTRAINT numeros_whatsapp_negocio_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: opiniones_negocio opiniones_negocio_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_negocio
    ADD CONSTRAINT opiniones_negocio_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clientes(id) ON DELETE SET NULL;

--
-- Name: opiniones_negocio opiniones_negocio_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_negocio
    ADD CONSTRAINT opiniones_negocio_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: opiniones_profesional opiniones_profesional_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_profesional
    ADD CONSTRAINT opiniones_profesional_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clientes(id) ON DELETE SET NULL;

--
-- Name: opiniones_profesional opiniones_profesional_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opiniones_profesional
    ADD CONSTRAINT opiniones_profesional_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesionales(id) ON DELETE CASCADE;

--
-- Name: plantillas_mensajes plantillas_mensajes_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plantillas_mensajes
    ADD CONSTRAINT plantillas_mensajes_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- Name: productos productos_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.productos
    ADD CONSTRAINT productos_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: profesional_servicios profesional_servicios_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesional_servicios
    ADD CONSTRAINT profesional_servicios_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesionales(id) ON DELETE CASCADE;

--
-- Name: profesional_servicios profesional_servicios_servicio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesional_servicios
    ADD CONSTRAINT profesional_servicios_servicio_id_fkey FOREIGN KEY (servicio_id) REFERENCES public.servicios(id) ON DELETE CASCADE;

--
-- Name: profesionales profesionales_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesionales
    ADD CONSTRAINT profesionales_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- Name: profesionales profesionales_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profesionales
    ADD CONSTRAINT profesionales_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);

--
-- Name: promociones promociones_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promociones
    ADD CONSTRAINT promociones_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id) ON DELETE CASCADE;

--
-- Name: promociones promociones_profesional_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promociones
    ADD CONSTRAINT promociones_profesional_id_fkey FOREIGN KEY (profesional_id) REFERENCES public.profesionales(id) ON DELETE CASCADE;

--
-- Name: servicios servicios_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servicios
    ADD CONSTRAINT servicios_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- Name: usuarios usuarios_negocio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_negocio_id_fkey FOREIGN KEY (negocio_id) REFERENCES public.negocios(id);

--
-- PostgreSQL database dump complete
--

