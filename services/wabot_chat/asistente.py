"""Asistente de preguntas del perfil público.

Ya no es el camino para reservar (eso lo hace el formulario en cuatro toques): responde dudas
(precios, horario, ubicación, quién hace qué, si hay espacio el sábado...) y, cuando la conversación
termina en "quiero ese turno", devuelve una propuesta de reserva que el navegador usa para abrir el
formulario ya lleno. Con OPENAI_API_KEY usa el modelo; sin ella responde con reglas simples.
"""
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

import localizacion
import publico

MODELO = os.getenv('OPENAI_CHAT_MODEL', 'gpt-4o-mini')

_cliente = None


def _cliente_openai():
    global _cliente
    if _cliente is None and os.getenv('OPENAI_API_KEY'):
        try:
            import openai
            _cliente = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'), timeout=25)
        except Exception as e:
            print(f'⚠️ [asistente] OpenAI no disponible: {e}')
            _cliente = False
    return _cliente or None


def _plano(texto):
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode('ascii')
    return texto.lower()


def _prompt_personalizado(negocio_id):
    try:
        conn = publico._conn()
        cur = conn.cursor()
        cur.execute('SELECT prompt_ia FROM negocios WHERE id = %s', (negocio_id,))
        fila = cur.fetchone()
        conn.close()
        valor = (fila['prompt_ia'] if isinstance(fila, dict) else fila[0]) if fila else ''
        return (valor or '').strip()[:3000]
    except Exception:
        return ''


def _contexto(negocio):
    servicios = publico.servicios_de(negocio['id'])
    pros = publico.profesionales_de(negocio['id'])
    semana, estado = publico.horario_semana(negocio['id'])
    return servicios, pros, semana, estado


# =============================================================================
# Respuestas sin IA
# =============================================================================

def _respuesta_reglas(negocio, pregunta):
    servicios, pros, semana, estado = _contexto(negocio)
    q = _plano(pregunta)
    vocab = negocio['vocab']
    sugerencias = ['¿Cuánto cuesta?', '¿Qué horario tienen?', '¿Dónde quedan?']

    servicio = next((s for s in servicios if _plano(s['nombre']) in q), None)
    if servicio:
        texto = f"{servicio['nombre']}: {servicio['precio_txt']} · {servicio['duracion_txt']}."
        if servicio['descripcion']:
            texto += f" {servicio['descripcion']}"
        return {'respuesta': texto, 'reserva': {'servicio_id': servicio['id']}, 'sugerencias': sugerencias}

    if re.search(r'precio|cuest|cuanto|vale|tarifa|servicio|lista|carta|menu', q):
        lineas = [f"• {s['nombre']} — {s['precio_txt']} ({s['duracion_txt']})" for s in servicios[:12]]
        return {'respuesta': 'Estos son nuestros servicios:\n' + '\n'.join(lineas), 'sugerencias': sugerencias}

    if re.search(r'horario|hora|abre|abren|cierra|cierran|atienden|domingo|sabado|festivo|dia', q):
        lineas = [f"• {d['dia']}: {d['texto']}" for d in semana]
        return {'respuesta': f"{estado['texto']}.\n" + '\n'.join(lineas), 'sugerencias': sugerencias}

    if re.search(r'donde|direccion|ubica|llegar|queda|mapa|parqueadero', q):
        if negocio['direccion']:
            return {'respuesta': f"Estamos en {negocio['direccion']}. Toca «Cómo llegar» en el perfil para abrir el mapa.",
                    'sugerencias': sugerencias}
        return {'respuesta': 'Escríbenos por WhatsApp y te enviamos la ubicación.', 'sugerencias': sugerencias}

    pro = next((p for p in pros if _plano(p['primer_nombre']) in q.split()), None)
    if pro:
        texto = f"{pro['nombre']} es parte de nuestro equipo"
        texto += f" ({pro['especialidad']})." if pro['especialidad'] else '.'
        return {'respuesta': texto + ' ¿Quieres reservar con él/ella?', 'reserva': {'profesional_id': pro['id']},
                'sugerencias': sugerencias}

    if re.search(r'barber|quien|equipo|profesional|estilista|personal', q):
        nombres = ', '.join(p['nombre'] for p in pros) or 'nuestro equipo'
        return {'respuesta': f"{vocab['equipo']}: {nombres}. Puedes elegir a uno al reservar o dejar que te asignemos el primero libre.",
                'sugerencias': sugerencias}

    if re.search(r'pago|pagar|tarjeta|nequi|daviplata|efectivo|transferencia', q):
        return {'respuesta': 'El pago se hace en el local al terminar tu servicio. Si tienes dudas sobre medios de pago, escríbenos por WhatsApp.',
                'sugerencias': sugerencias}

    if re.search(r'cancel|cambiar|mover|reprogram', q):
        return {'respuesta': 'Puedes cancelar desde «Mis citas» en este mismo perfil, y luego reservar otro horario en segundos.',
                'sugerencias': sugerencias}

    if re.search(r'reserv|cita|turno|agend|espacio|disponib|cupo|hoy|manana', q):
        return {'respuesta': 'Reservar toma menos de un minuto: elige servicio, ' + vocab['pro'] + ', día y hora. Te abro el formulario.',
                'reserva': {}, 'sugerencias': sugerencias}

    if re.search(r'^(hola|buenas|buenos|hey|que mas|saludos)', q):
        return {'respuesta': f"¡Hola! Soy el asistente de {negocio['nombre']}. Pregúntame por precios, horario, ubicación o disponibilidad.",
                'sugerencias': sugerencias}

    return {'respuesta': 'No estoy seguro de eso. Puedes escribirnos por WhatsApp y te respondemos personalmente.',
            'whatsapp': True, 'sugerencias': sugerencias}


# =============================================================================
# Respuestas con IA
# =============================================================================

_HERRAMIENTAS = [
    {'type': 'function', 'function': {
        'name': 'consultar_horarios',
        'description': 'Horarios libres reales para un servicio en una fecha. Úsala antes de afirmar que hay o no hay espacio.',
        'parameters': {'type': 'object', 'properties': {
            'fecha': {'type': 'string', 'description': 'YYYY-MM-DD'},
            'servicio_id': {'type': 'integer'},
            'profesional_id': {'type': 'integer', 'description': 'Opcional'},
        }, 'required': ['fecha', 'servicio_id']}}},
    {'type': 'function', 'function': {
        'name': 'proponer_reserva',
        'description': ('Cuando el cliente quiere reservar, propón la reserva: el sistema le mostrará un botón que abre el '
                        'formulario ya lleno. Nunca digas que la cita quedó agendada: el cliente la confirma en el formulario.'),
        'parameters': {'type': 'object', 'properties': {
            'servicio_id': {'type': 'integer'},
            'profesional_id': {'type': 'integer'},
            'fecha': {'type': 'string', 'description': 'YYYY-MM-DD'},
            'hora': {'type': 'string', 'description': 'HH:MM (24 h), tomada de consultar_horarios'},
        }}}},
]


def _sistema(negocio, servicios, pros, semana, estado):
    ahora = localizacion.ahora_en(negocio['id'])
    hoy = ahora.date()
    proximos = ', '.join(f"{publico.DIAS_LARGOS[(hoy + timedelta(days=i)).weekday()]} {(hoy + timedelta(days=i)).isoformat()}"
                         for i in range(7))
    lineas_serv = '\n'.join(f"- id {s['id']}: {s['nombre']} · {s['precio_txt']} · {s['duracion_txt']}"
                            + (f" · {s['descripcion']}" if s['descripcion'] else '') for s in servicios)
    lineas_pros = '\n'.join(f"- id {p['id']}: {p['nombre']}" + (f" ({p['especialidad']})" if p['especialidad'] else '')
                            + ('' if not p['servicios'] else f" · solo servicios {p['servicios']}") for p in pros)
    lineas_horario = '\n'.join(f"- {d['dia']}: {d['texto']}" for d in semana)
    extra = _prompt_personalizado(negocio['id'])
    return f"""Eres el asistente del perfil web de {negocio['nombre']} ({negocio['tipo_legible'] or 'negocio'}).
Respondes dudas de clientes en español, con calidez y MUY breve (1 a 3 frases, sin markdown, sin listas largas).
Hoy es {publico.DIAS_LARGOS[hoy.weekday()]} {hoy.isoformat()}, son las {ahora:%H:%M}. Próximos días: {proximos}.
Estado ahora: {estado['texto']}.
Dirección: {negocio['direccion'] or 'no registrada'}.

Servicios:
{lineas_serv or '- (sin servicios)'}

{negocio['vocab']['pros'].capitalize()}:
{lineas_pros or '- (sin equipo registrado)'}

Horario:
{lineas_horario}

Reglas:
- Usa SOLO estos datos; si no sabes algo, dilo y sugiere escribir por WhatsApp.
- Para disponibilidad llama a consultar_horarios; ofrece como máximo 3 horas concretas en formato 12 h.
- Si el cliente quiere reservar, llama a proponer_reserva con lo que se sepa y dile que toque el botón para confirmar.
- Nunca inventes precios, horarios ni nombres; nunca digas que la cita ya quedó agendada.
{('Indicaciones del negocio:' + chr(10) + extra) if extra else ''}"""


def _ejecutar(negocio, servicios, pros, nombre, argumentos, propuesta):
    if nombre == 'consultar_horarios':
        servicio = next((s for s in servicios if s['id'] == argumentos.get('servicio_id')), None)
        fecha = str(argumentos.get('fecha') or '')[:10]
        try:
            datetime.strptime(fecha, '%Y-%m-%d')
        except ValueError:
            return {'error': 'fecha inválida'}
        if not servicio:
            return {'error': 'servicio no existe'}
        libres = publico.horarios_para(negocio['id'], servicio, pros, fecha, argumentos.get('profesional_id'))
        nombres = {p['id']: p['nombre'] for p in pros}
        return {'fecha': fecha, 'horarios': [{'hora': h, 'con': [nombres[i] for i in ids]} for h, ids in list(libres.items())[:24]]}
    if nombre == 'proponer_reserva':
        for clave in ('servicio_id', 'profesional_id', 'fecha', 'hora'):
            if argumentos.get(clave):
                propuesta[clave] = argumentos[clave]
        return {'ok': True}
    return {'error': 'herramienta desconocida'}


def _respuesta_ia(cliente, negocio, mensajes):
    servicios, pros, semana, estado = _contexto(negocio)
    conversacion = [{'role': 'system', 'content': _sistema(negocio, servicios, pros, semana, estado)}]
    for m in mensajes:
        rol = 'assistant' if m.get('role') == 'assistant' else 'user'
        conversacion.append({'role': rol, 'content': str(m.get('content') or '')[:600]})
    propuesta = None
    for _ in range(4):
        respuesta = cliente.chat.completions.create(model=MODELO, messages=conversacion, tools=_HERRAMIENTAS,
                                                   temperature=0.3, max_tokens=300)
        mensaje = respuesta.choices[0].message
        if not mensaje.tool_calls:
            texto = (mensaje.content or '').strip()
            resultado = {'respuesta': texto or 'Cuéntame un poco más, ¿qué te gustaría saber?'}
            if propuesta is not None:
                resultado['reserva'] = propuesta
            return resultado
        conversacion.append({'role': 'assistant', 'content': mensaje.content or '', 'tool_calls': [
            {'id': t.id, 'type': 'function', 'function': {'name': t.function.name, 'arguments': t.function.arguments}}
            for t in mensaje.tool_calls]})
        for llamada in mensaje.tool_calls:
            try:
                argumentos = json.loads(llamada.function.arguments or '{}')
            except ValueError:
                argumentos = {}
            if llamada.function.name == 'proponer_reserva' and propuesta is None:
                propuesta = {}
            salida = _ejecutar(negocio, servicios, pros, llamada.function.name, argumentos,
                               propuesta if propuesta is not None else {})
            conversacion.append({'role': 'tool', 'tool_call_id': llamada.id, 'content': json.dumps(salida, ensure_ascii=False)})
    return {'respuesta': 'Listo. Toca el botón para revisar y confirmar tu reserva.', 'reserva': propuesta or {}}


def responder(negocio, mensajes):
    pregunta = ''
    for m in reversed(mensajes):
        if m.get('role') != 'assistant':
            pregunta = str(m.get('content') or '').strip()[:600]
            break
    if not pregunta:
        return {'respuesta': f"¡Hola! Soy el asistente de {negocio['nombre']}. ¿En qué te ayudo?"}
    cliente = _cliente_openai()
    if cliente:
        try:
            return _respuesta_ia(cliente, negocio, mensajes)
        except Exception as e:
            print(f'⚠️ [asistente] Falló la IA, respondo con reglas: {type(e).__name__}: {e}')
    return _respuesta_reglas(negocio, pregunta)
