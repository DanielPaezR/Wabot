/* Wabot · reserva directa en el perfil público.
   Servicio → profesional → día y hora → nombre y WhatsApp. Sin chat obligatorio. */
(function () {
  'use strict';
  const W = window.WABOT || {};
  const N = W.negocio || {};
  const SERVICIOS = W.servicios || [];
  const PROS = W.profesionales || [];
  const API = '/api/reserva/' + N.id;
  const CLAVE_TOKEN = 'wabot_token_' + N.id;
  const CLAVE_CLIENTE = 'wabot_cliente';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ic = (n, c = '') => `<svg class="ic ${c}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const leer = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } };
  const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* modo privado */ } };
  const token = () => leer(CLAVE_TOKEN);
  const avatar = (p, cls = '') => `<span class="avatar ${cls}">${p && p.foto ? `<img src="${esc(p.foto)}" alt="">` : esc((p && p.iniciales) || '?')}</span>`;
  const mayus = (t) => t ? t.charAt(0).toUpperCase() + t.slice(1) : t;

  async function api(ruta, opciones = {}) {
    const cabeceras = { 'Content-Type': 'application/json' };
    const t = token();
    if (t) cabeceras['X-Cliente-Token'] = t;
    const r = await fetch(API + ruta, { credentials: 'same-origin', ...opciones, headers: cabeceras });
    let datos = {};
    try { datos = await r.json(); } catch (e) { /* sin cuerpo */ }
    datos._status = r.status;
    return datos;
  }

  function aviso(texto) {
    let el = $('#aviso');
    if (!el) { el = document.createElement('div'); el.id = 'aviso'; el.className = 'aviso'; document.body.appendChild(el); }
    el.textContent = texto;
    el.classList.add('visible');
    clearTimeout(aviso._t);
    aviso._t = setTimeout(() => el.classList.remove('visible'), 2600);
  }

  // ───────────────────────── hojas (reserva / asistente) ─────────────────────────
  let hojaAbierta = null;
  function abrirHoja(el) {
    if (hojaAbierta === el) return;
    if (hojaAbierta) cerrarHoja(true);
    hojaAbierta = el;
    el.classList.remove('oculto');
    requestAnimationFrame(() => el.classList.add('abierta'));
    document.documentElement.classList.add('sin-scroll');
    history.pushState({ hoja: el.id }, '');
  }
  function cerrarHoja(silencioso) {
    const el = hojaAbierta;
    if (!el) return;
    hojaAbierta = null;
    el.classList.remove('abierta');
    document.documentElement.classList.remove('sin-scroll');
    setTimeout(() => el.classList.add('oculto'), 260);
    if (!silencioso && history.state && history.state.hoja) history.back();
  }
  window.addEventListener('popstate', () => { if (hojaAbierta) cerrarHoja(true); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrarHoja(); });
  $$('.hoja [data-cerrar]').forEach((b) => b.addEventListener('click', () => cerrarHoja()));

  // ───────────────────────── reserva ─────────────────────────
  const hoja = $('#hoja-reserva');
  const cuerpo = $('#reserva-cuerpo');
  const pie = $('#reserva-pie');
  const E = { paso: 'servicio', servicio: null, pro: undefined, fecha: null, hora: null, dias: null, horarios: {}, enviando: false, cita: null, horaDeseada: null };

  const prosPara = (s) => PROS.filter((p) => !p.servicios.length || p.servicios.includes(s.id));
  const proPorId = (id) => PROS.find((p) => p.id === id);
  const pasos = () => {
    const l = ['servicio'];
    if (!E.servicio || prosPara(E.servicio).length > 1) l.push('profesional');
    l.push('horario', 'datos');
    return l;
  };
  const TITULOS = { servicio: 'Elige tu servicio', profesional: `¿Con quién?`, horario: 'Elige día y hora', datos: 'Confirma tu reserva', listo: '¡Listo!' };

  function abrirReserva(pre = {}) {
    E.servicio = null; E.pro = undefined; E.fecha = null; E.hora = null; E.cita = null; E.horaDeseada = null;
    if (pre.servicio_id) E.servicio = SERVICIOS.find((s) => s.id === Number(pre.servicio_id)) || null;
    if (pre.profesional_id) E.pro = Number(pre.profesional_id);
    if (pre.fecha) E.fecha = pre.fecha;
    if (pre.hora) E.horaDeseada = pre.hora;
    if (E.servicio && E.pro !== undefined && E.pro !== null) {
      const p = proPorId(E.pro);
      if (!p || !(p.servicios.length === 0 || p.servicios.includes(E.servicio.id))) E.pro = undefined;
    }
    if (E.servicio && prosPara(E.servicio).length === 1) E.pro = prosPara(E.servicio)[0].id;
    let paso = 'servicio';
    if (E.servicio) paso = E.pro === undefined ? 'profesional' : 'horario';
    abrirHoja(hoja);
    ir(paso);
  }

  function ir(paso) {
    E.paso = paso;
    const l = pasos();
    const i = l.indexOf(paso);
    $('#reserva-titulo').textContent = paso === 'profesional' ? `¿Con qué ${N.pro}?` : TITULOS[paso];
    $('#reserva-paso').textContent = paso === 'listo' ? 'Reserva confirmada' : `Paso ${i + 1} de ${l.length}`;
    $('#reserva-progreso').style.width = paso === 'listo' ? '100%' : `${((i + 1) / l.length) * 100}%`;
    $('#reserva-atras').style.visibility = i > 0 && paso !== 'listo' ? 'visible' : 'hidden';
    hoja.dataset.paso = paso;
    pintarChips();
    pie.classList.add('oculto');
    pie.innerHTML = '';
    cuerpo.scrollTop = 0;
    ({ servicio: pasoServicio, profesional: pasoProfesional, horario: pasoHorario, datos: pasoDatos, listo: pasoListo })[paso]();
  }

  if (hoja) $('#reserva-atras').addEventListener('click', () => {
    const l = pasos();
    const i = l.indexOf(E.paso);
    if (i > 0) ir(l[i - 1]);
  });

  function pintarChips() {
    const chips = [];
    if (E.paso !== 'servicio' && E.paso !== 'listo' && E.servicio) chips.push(`<button type="button" data-ir="servicio">${ic('scissors')}${esc(E.servicio.nombre)}</button>`);
    if (['horario', 'datos'].includes(E.paso) && E.pro !== undefined) {
      const p = E.pro ? proPorId(E.pro) : null;
      chips.push(`<button type="button" data-ir="profesional">${ic('user')}${p ? esc(p.primer_nombre) : 'Primer disponible'}</button>`);
    }
    if (E.paso === 'datos' && E.fecha && E.hora) chips.push(`<button type="button" data-ir="horario">${ic('clock')}${esc(E.horaTxt)}</button>`);
    const c = $('#reserva-chips');
    c.innerHTML = chips.join('');
    c.classList.toggle('oculto', !chips.length);
    $$('[data-ir]', c).forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.ir === 'profesional' && pasos().indexOf('profesional') < 0) return;
      ir(b.dataset.ir);
    }));
  }

  function pasoServicio() {
    if (!SERVICIOS.length) { cuerpo.innerHTML = '<p class="vacio">Este negocio aún no publica servicios.</p>'; return; }
    cuerpo.innerHTML = `<ul class="opciones">${SERVICIOS.map((s) => `
      <li><button type="button" class="opcion ${E.servicio && E.servicio.id === s.id ? 'elegida' : ''}" data-id="${s.id}">
        <span class="opcion-texto"><strong>${esc(s.nombre)}</strong><span>${ic('clock')}${esc(s.duracion_txt)}${s.descripcion ? ' · ' + esc(s.descripcion) : ''}</span></span>
        <span class="opcion-precio">${esc(s.precio_txt)}</span>
      </button></li>`).join('')}</ul>`;
    $$('.opcion', cuerpo).forEach((b) => b.addEventListener('click', () => {
      const s = SERVICIOS.find((x) => x.id === Number(b.dataset.id));
      if (!E.servicio || E.servicio.id !== s.id) { E.horarios = {}; E.hora = null; }
      E.servicio = s;
      const pros = prosPara(s);
      if (pros.length === 1) E.pro = pros[0].id;
      else if (E.pro && !pros.some((p) => p.id === E.pro)) E.pro = undefined;
      ir(pasos().includes('profesional') && E.pro === undefined ? 'profesional' : 'horario');
    }));
  }

  function pasoProfesional() {
    const pros = prosPara(E.servicio);
    cuerpo.innerHTML = `<ul class="opciones">
      <li><button type="button" class="opcion opcion-pro ${E.pro === null ? 'elegida' : ''}" data-id="">
        <span class="avatar avatar-cualquiera">${ic('sparkle')}</span>
        <span class="opcion-texto"><strong>Primer disponible</strong><span>Más horarios · te asignamos a quien esté libre</span></span>
        <span class="insignia">Más rápido</span>
      </button></li>
      ${pros.map((p) => `<li><button type="button" class="opcion opcion-pro ${E.pro === p.id ? 'elegida' : ''}" data-id="${p.id}">
        ${avatar(p)}
        <span class="opcion-texto"><strong>${esc(p.nombre)}</strong><span>${p.calificacion ? ic('star', 'llena') + p.calificacion.toFixed(1) + ' · ' : ''}${esc(p.especialidad || mayus(N.pro))}</span></span>
        ${ic('chevron', 'tenue')}
      </button></li>`).join('')}</ul>`;
    $$('.opcion', cuerpo).forEach((b) => b.addEventListener('click', () => {
      const nuevo = b.dataset.id ? Number(b.dataset.id) : null;
      if (nuevo !== E.pro) { E.horarios = {}; E.hora = null; }
      E.pro = nuevo;
      ir('horario');
    }));
  }

  async function cargarDias() {
    if (E.dias) return E.dias;
    const r = await api('/dias');
    E.dias = r.dias || [];
    return E.dias;
  }

  async function pasoHorario() {
    cuerpo.innerHTML = `<div class="tira-dias" id="tira-dias">${'<span class="dia esqueleto"></span>'.repeat(7)}</div><div id="horas"></div>`;
    const dias = await cargarDias();
    if (E.paso !== 'horario') return;
    E.fechaAuto = false;
    if (!E.fecha || !dias.some((d) => d.fecha === E.fecha && d.abierto)) {
      const primero = dias.find((d) => d.abierto);
      E.fecha = primero ? primero.fecha : null;
      E.fechaAuto = true;   // elegida por nosotros: si está llena, saltamos al siguiente día con espacio
    }
    const tira = $('#tira-dias');
    let mesActual = '';
    tira.innerHTML = dias.map((d) => {
      const mes = d.mes !== mesActual ? (mesActual = d.mes, `<span class="tira-mes">${esc(d.mes)}</span>`) : '';
      return `${mes}<button type="button" class="dia ${d.fecha === E.fecha ? 'elegido' : ''}" data-fecha="${d.fecha}" ${d.abierto ? '' : 'disabled'}>
        <span>${esc(d.dia)}</span><strong>${d.num}</strong></button>`;
    }).join('');
    $$('.dia', tira).forEach((b) => b.addEventListener('click', () => {
      $$('.dia', tira).forEach((x) => x.classList.toggle('elegido', x === b));
      E.fecha = b.dataset.fecha; E.hora = null; E.fechaAuto = false;
      cargarHoras();
    }));
    const elegido = $('.dia.elegido', tira);
    if (elegido) elegido.scrollIntoView({ block: 'nearest', inline: 'center' });
    if (!E.fecha) { $('#horas').innerHTML = '<p class="vacio">No hay días disponibles por ahora. Escríbenos por WhatsApp.</p>'; return; }
    cargarHoras();
  }

  async function cargarHoras() {
    const caja = $('#horas');
    const clave = `${E.servicio.id}|${E.pro || ''}|${E.fecha}`;
    caja.innerHTML = `<div class="horas-grupo"><div class="rejilla-horas">${'<span class="hora esqueleto"></span>'.repeat(8)}</div></div>`;
    let r = E.horarios[clave];
    if (!r) {
      r = await api(`/horarios?servicio_id=${E.servicio.id}&fecha=${E.fecha}${E.pro ? '&profesional_id=' + E.pro : ''}`);
      if (r.ok) E.horarios[clave] = r;
    }
    if (clave !== `${E.servicio.id}|${E.pro || ''}|${E.fecha}` || E.paso !== 'horario') return;
    if (!r.ok) { caja.innerHTML = `<p class="vacio">${esc(r.error || 'No pudimos cargar los horarios.')}</p>`; return; }
    if (!r.horarios.length && E.fechaAuto && r.siguiente) {
      E.fechaAuto = false;
      E.fecha = r.siguiente.fecha;
      $$('#tira-dias .dia').forEach((x) => x.classList.toggle('elegido', x.dataset.fecha === E.fecha));
      const el = $('#tira-dias .dia.elegido');
      if (el) el.scrollIntoView({ block: 'nearest', inline: 'center' });
      return cargarHoras();
    }
    E.fechaAuto = false;
    if (!r.horarios.length) {
      caja.innerHTML = `<div class="sin-horas">${ic('calendar')}<p>No quedan horarios para este día.</p>
        ${r.siguiente ? `<button type="button" class="boton boton-suave" id="ir-siguiente">Próximo: ${esc(r.siguiente.txt)}</button>` : ''}</div>`;
      const s = $('#ir-siguiente');
      if (s) s.addEventListener('click', () => { E.fecha = r.siguiente.fecha; E.horaDeseada = r.siguiente.hora; pasoHorario(); });
      return;
    }
    const grupos = [['Mañana', (m) => m < 720], ['Tarde', (m) => m >= 720 && m < 1080], ['Noche', (m) => m >= 1080]];
    const min = (h) => { const [a, b] = h.split(':').map(Number); return a * 60 + b; };
    caja.innerHTML = `<p class="fecha-elegida">${esc(mayus(r.fecha_txt))}</p>` + grupos.map(([nombre, f]) => {
      const lista = r.horarios.filter((h) => f(min(h.hora)));
      if (!lista.length) return '';
      return `<div class="horas-grupo"><h3>${nombre}</h3><div class="rejilla-horas">${lista.map((h) =>
        `<button type="button" class="hora ${h.hora === E.hora ? 'elegida' : ''}" data-hora="${h.hora}" data-txt="${esc(h.txt)}">${esc(h.txt.replace(' ', ' '))}</button>`).join('')}</div></div>`;
    }).join('');
    $$('.hora', caja).forEach((b) => b.addEventListener('click', () => elegirHora(b.dataset.hora, b.dataset.txt)));
    if (E.horaDeseada) {
      const b = $(`.hora[data-hora="${E.horaDeseada}"]`, caja);
      E.horaDeseada = null;
      if (b) { b.classList.add('elegida'); b.scrollIntoView({ block: 'center' }); }
    }
  }

  function elegirHora(hora, txt) {
    E.hora = hora;
    const d = (E.dias || []).find((x) => x.fecha === E.fecha);
    E.horaTxt = `${d ? (['Hoy', 'Mañana'].includes(d.dia) ? d.dia : d.dia + ' ' + d.num) : E.fecha} · ${txt}`;
    ir('datos');
  }

  function pasoDatos() {
    const c = leer(CLAVE_CLIENTE) || {};
    const p = E.pro ? proPorId(E.pro) : null;
    cuerpo.innerHTML = `
      <div class="resumen">
        <div class="resumen-fila">${p ? avatar(p, 'avatar-sm') : `<span class="avatar avatar-sm avatar-cualquiera">${ic('sparkle')}</span>`}
          <div><strong>${esc(E.servicio.nombre)}</strong><span>${p ? 'con ' + esc(p.nombre) : 'con el primer ' + esc(N.pro) + ' disponible'}</span></div>
          <span class="resumen-precio">${esc(E.servicio.precio_txt)}</span></div>
        <div class="resumen-fila resumen-cuando">${ic('calendar')}<div><strong>${esc(E.horaTxt)}</strong><span>${esc(E.servicio.duracion_txt)}${N.direccion ? ' · ' + esc(N.direccion) : ''}</span></div></div>
      </div>
      <form id="form-datos" class="formulario" novalidate>
        <label class="campo"><span>Tu nombre</span>
          <input name="nombre" autocomplete="name" required maxlength="60" placeholder="¿Cómo te llamas?" value="${esc(c.nombre || '')}"></label>
        <label class="campo"><span>WhatsApp</span>
          <input name="telefono" type="tel" inputmode="numeric" autocomplete="tel-national" required maxlength="18" placeholder="${esc(N.tel_ejemplo)}" value="${esc(c.telefono || '')}">
          <small>Para recordarte la cita. No enviamos publicidad.</small></label>
        <p class="error-form oculto" id="error-form"></p>
      </form>`;
    pie.classList.remove('oculto');
    pie.innerHTML = `<button class="boton boton-primario boton-grande ancho" type="submit" form="form-datos" id="confirmar">Confirmar reserva</button>`;
    const form = $('#form-datos');
    const primero = !c.nombre ? form.nombre : (!c.telefono ? form.telefono : null);
    if (primero && window.matchMedia('(min-width: 720px)').matches) primero.focus();
    form.addEventListener('submit', (e) => { e.preventDefault(); confirmar(form); });
  }

  async function confirmar(form) {
    if (E.enviando) return;
    const nombre = form.nombre.value.trim();
    const telefono = form.telefono.value.trim();
    const err = $('#error-form');
    const mostrar = (t, campo) => { err.textContent = t; err.classList.remove('oculto'); if (campo && form[campo]) form[campo].focus(); };
    if (nombre.length < 2) return mostrar('Escribe tu nombre.', 'nombre');
    if (telefono.replace(/\D/g, '').length < 7) return mostrar(`Escribe tu WhatsApp (ej. ${N.tel_ejemplo}).`, 'telefono');
    E.enviando = true;
    const boton = $('#confirmar');
    boton.disabled = true; boton.innerHTML = '<span class="girando"></span>Reservando…';
    const r = await api('', { method: 'POST', body: JSON.stringify({ servicio_id: E.servicio.id, profesional_id: E.pro || null, fecha: E.fecha, hora: E.hora, nombre, telefono }) })
      .catch(() => ({ ok: false, error: 'Sin conexión. Inténtalo de nuevo.' }));
    E.enviando = false;
    if (!r.ok) {
      boton.disabled = false; boton.textContent = 'Confirmar reserva';
      if (r.ocupado) {
        E.horarios = {}; E.hora = null;
        aviso(r.error);
        return ir('horario');
      }
      return mostrar(r.error || 'No pudimos reservar. Inténtalo de nuevo.', r.campo);
    }
    guardar(CLAVE_CLIENTE, { nombre: r.cliente.nombre, telefono: r.cliente.telefono });
    guardar(CLAVE_TOKEN, r.token);
    E.cita = r.cita;
    E.horarios = {};
    ir('listo');
    if (navigator.vibrate) navigator.vibrate(30);
    mostrarProxima();
  }

  function ics(c) {
    const f = (d) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const [y, m, d] = c.fecha.split('-').map(Number);
    const [h, mi] = c.hora.split(':').map(Number);
    const ini = new Date(y, m - 1, d, h, mi);
    const fin = new Date(ini.getTime() + (c.duracion || 30) * 60000);
    const txt = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Wabot//ES', 'BEGIN:VEVENT', `UID:wabot-${c.id}@wabot`,
      `DTSTAMP:${f(new Date())}`, `DTSTART:${f(ini)}`, `DTEND:${f(fin)}`, `SUMMARY:${c.servicio} · ${N.nombre}`,
      `DESCRIPTION:Con ${c.profesional}`, `LOCATION:${N.direccion || N.nombre}`,
      'BEGIN:VALARM', 'TRIGGER:-PT1H', 'ACTION:DISPLAY', 'DESCRIPTION:Tu cita es en 1 hora', 'END:VALARM', 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([txt], { type: 'text/calendar' }));
    a.download = `cita-${c.id}.ics`;
    a.click();
  }

  function pasoListo() {
    const c = E.cita;
    const p = { foto: c.profesional_foto, iniciales: c.profesional_iniciales };
    cuerpo.innerHTML = `
      <div class="exito">
        <div class="exito-check"><svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="24"/><path d="m15 27 7 7 15-16"/></svg></div>
        <h3>¡Te esperamos, ${esc(c.profesional ? (leer(CLAVE_CLIENTE) || {}).nombre || '' : '').split(' ')[0]}!</h3>
        <p>Tu cita quedó reservada.</p>
      </div>
      <div class="boleto">
        <div class="boleto-fila">${avatar(p, 'avatar-sm')}<div><strong>${esc(c.servicio)}</strong><span>con ${esc(c.profesional)}</span></div><span class="resumen-precio">${esc(c.precio_txt)}</span></div>
        <div class="boleto-corte"></div>
        <div class="boleto-datos">
          <div><span>Día</span><strong>${esc(mayus(c.fecha_txt))}</strong></div>
          <div><span>Hora</span><strong>${esc(c.hora_txt)}</strong></div>
        </div>
        ${N.direccion ? `<p class="boleto-dir">${ic('pin')}${esc(N.direccion)}</p>` : ''}
      </div>
      <div class="acciones-exito">
        <a class="boton boton-suave" href="${esc(c.google)}" target="_blank" rel="noopener">${ic('calendar')}Google Calendar</a>
        <button class="boton boton-suave" type="button" id="b-ics">${ic('download')}Apple / Outlook</button>
        <button class="boton boton-suave oculto" type="button" id="b-push">${ic('bell')}Recordarme</button>
      </div>`;
    pie.classList.remove('oculto');
    pie.innerHTML = `<a class="boton boton-secundario ancho" href="/${esc(N.slug)}/mis-citas">Ver mis citas</a><button class="boton boton-primario ancho" type="button" data-cerrar-listo>Listo</button>`;
    $('[data-cerrar-listo]', pie).addEventListener('click', () => cerrarHoja());
    $('#b-ics').addEventListener('click', () => ics(c));
    prepararPush($('#b-push'));
  }

  // ───────────────────────── notificaciones push (recordatorios) ─────────────────────────
  function b64(base64) {
    const relleno = '='.repeat((4 - (base64.length % 4)) % 4);
    const crudo = atob((base64 + relleno).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from([...crudo].map((ch) => ch.charCodeAt(0)));
  }
  async function prepararPush(boton) {
    if (!boton || !('serviceWorker' in navigator) || !('PushManager' in window) || !window.Notification) return;
    if (Notification.permission === 'denied') return;
    boton.classList.remove('oculto');
    if (Notification.permission === 'granted') boton.innerHTML = ic('check') + 'Recordatorios activos';
    boton.addEventListener('click', async () => {
      try {
        boton.disabled = true;
        const permiso = await Notification.requestPermission();
        if (permiso !== 'granted') { boton.classList.add('oculto'); return; }
        const clave = await fetch('/api/push/public-key').then((r) => r.json());
        const publica = clave.publicKey || clave.public_key || clave.key;
        if (!publica) throw new Error('sin clave');
        const reg = await navigator.serviceWorker.register('/service-worker.js');
        await navigator.serviceWorker.ready;
        let sus = await reg.pushManager.getSubscription();
        if (!sus) sus = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(publica) });
        const r = await api('/push', { method: 'POST', body: JSON.stringify({ subscription: sus.toJSON() }) });
        boton.innerHTML = r.ok ? ic('check') + 'Recordatorios activos' : 'No se pudo activar';
      } catch (e) {
        boton.innerHTML = 'No se pudo activar';
      }
    });
  }

  // ───────────────────────── tu próxima cita (en el perfil) ─────────────────────────
  async function mostrarProxima() {
    const caja = $('#cita-proxima');
    const enlace = $('#enlace-mis-citas');
    if (!token()) return;
    if (enlace) enlace.classList.remove('oculto');
    if (!caja) return;
    const r = await api('/mis-citas');
    if (!r.ok || !r.proximas || !r.proximas.length) { caja.classList.add('oculto'); return; }
    const c = r.proximas[0];
    caja.innerHTML = `${avatar({ foto: c.foto, iniciales: c.iniciales })}
      <div><span class="sobretitulo">Tu próxima cita</span><strong>${esc(mayus(c.fecha_txt))} · ${esc(c.hora_txt)}</strong><span>${esc(c.servicio)} con ${esc(c.profesional)}</span></div>
      <a class="icono-boton" href="/${esc(N.slug)}/mis-citas" aria-label="Ver mis citas">${ic('chevron')}</a>`;
    caja.classList.remove('oculto');
  }

  // ───────────────────────── mis citas (página) ─────────────────────────
  async function paginaMisCitas() {
    const caja = $('#mis-citas');
    if (!caja) return;
    const r = token() ? await api('/mis-citas') : { ok: false };
    if (!r.ok) {
      caja.innerHTML = `<div class="sin-horas">${ic('calendar')}<p>Aquí verás tus citas cuando reserves desde este teléfono.</p>
        <a class="boton boton-primario" href="/${esc(N.slug)}?reservar=1">Reservar cita</a></div>`;
      return;
    }
    const tarjeta = (c) => `<article class="cita ${c.estado}" data-id="${c.id}">
      ${avatar({ foto: c.foto, iniciales: c.iniciales })}
      <div class="cita-texto"><strong>${esc(mayus(c.fecha_txt))}</strong><span>${esc(c.hora_txt)} · ${esc(c.servicio)}</span><span class="tenue">con ${esc(c.profesional)} · ${esc(c.precio_txt)}</span></div>
      ${c.puede_cancelar ? `<button type="button" class="boton boton-peligro boton-chico" data-cancelar="${c.id}">Cancelar</button>`
        : (c.estado === 'completada' ? `<a class="boton boton-suave boton-chico" href="/calificar/${c.id}">${ic('star')}Calificar</a>`
        : `<span class="etiqueta ${c.estado}">${esc(mayus(c.estado))}</span>`)}
    </article>`;
    caja.innerHTML = `
      <h2 class="titulo-lista">Próximas</h2>
      ${r.proximas.length ? r.proximas.map(tarjeta).join('') : `<div class="sin-horas"><p>No tienes citas próximas.</p><a class="boton boton-primario" href="/${esc(N.slug)}?reservar=1">Reservar ahora</a></div>`}
      ${r.anteriores.length ? `<h2 class="titulo-lista">Historial</h2>${r.anteriores.map(tarjeta).join('')}` : ''}`;
    $$('[data-cancelar]', caja).forEach((b) => b.addEventListener('click', async () => {
      if (b.dataset.confirmar !== '1') { b.dataset.confirmar = '1'; b.textContent = '¿Seguro?'; setTimeout(() => { b.dataset.confirmar = ''; b.textContent = 'Cancelar'; }, 3500); return; }
      b.disabled = true;
      const x = await api(`/citas/${b.dataset.cancelar}/cancelar`, { method: 'POST', body: '{}' });
      if (x.ok) { aviso('Cita cancelada'); paginaMisCitas(); } else { aviso(x.error || 'No se pudo cancelar'); b.disabled = false; }
    }));
  }

  // ───────────────────────── asistente ─────────────────────────
  const hojaChat = $('#hoja-asistente');
  const historial = [];
  function burbuja(texto, quien, extra) {
    const el = document.createElement('div');
    el.className = 'burbuja ' + quien;
    el.textContent = texto;
    if (extra) el.appendChild(extra);
    $('#chat-mensajes').appendChild(el);
    el.scrollIntoView({ block: 'end', behavior: 'smooth' });
    return el;
  }
  async function preguntar(texto) {
    texto = texto.trim();
    if (!texto) return;
    $('#chat-sugerencias').classList.add('oculto');
    burbuja(texto, 'yo');
    historial.push({ role: 'user', content: texto });
    const escribiendo = burbuja('', 'bot escribiendo');
    escribiendo.innerHTML = '<i></i><i></i><i></i>';
    const r = await api('/preguntar', { method: 'POST', body: JSON.stringify({ mensajes: historial.slice(-10) }) })
      .catch(() => ({ respuesta: 'Sin conexión. Inténtalo de nuevo.' }));
    escribiendo.remove();
    const respuesta = r.respuesta || 'No te entendí bien, ¿puedes reformular?';
    historial.push({ role: 'assistant', content: respuesta });
    let extra = null;
    if (r.reserva) {
      extra = document.createElement('button');
      extra.type = 'button';
      extra.className = 'boton boton-primario boton-chico';
      const s = r.reserva.servicio_id && SERVICIOS.find((x) => x.id === Number(r.reserva.servicio_id));
      extra.innerHTML = ic('calendar') + (s ? 'Reservar ' + esc(s.nombre) : 'Reservar ahora');
      extra.addEventListener('click', () => { cerrarHoja(true); history.replaceState(null, ''); abrirReserva(r.reserva); });
    } else if (r.whatsapp && N.whatsapp) {
      extra = document.createElement('a');
      extra.className = 'boton boton-suave boton-chico';
      extra.href = `https://wa.me/${N.whatsapp}?text=${encodeURIComponent(texto)}`;
      extra.target = '_blank';
      extra.innerHTML = ic('whatsapp') + 'Escribir por WhatsApp';
    }
    burbuja(respuesta, 'bot', extra);
  }
  if (hojaChat) {
    $('#chat-form').addEventListener('submit', (e) => { e.preventDefault(); const i = $('#chat-texto'); preguntar(i.value); i.value = ''; });
    $$('#chat-sugerencias button').forEach((b) => b.addEventListener('click', () => preguntar(b.textContent)));
  }

  // ───────────────────────── enlaces de la página ─────────────────────────
  $$('[data-reservar]').forEach((b) => b.addEventListener('click', () => {
    abrirReserva({ servicio_id: b.dataset.servicio, profesional_id: b.dataset.profesional || (W.preseleccion && W.preseleccion.profesional) });
  }));
  $$('[data-asistente]').forEach((b) => b.addEventListener('click', () => {
    abrirHoja(hojaChat);
    if (window.matchMedia('(min-width: 720px)').matches) setTimeout(() => $('#chat-texto').focus(), 250);
  }));
  $$('[data-compartir]').forEach((b) => b.addEventListener('click', async () => {
    const url = location.origin + location.pathname;
    try {
      if (navigator.share) await navigator.share({ title: document.title, url });
      else { await navigator.clipboard.writeText(url); aviso('Enlace copiado'); }
    } catch (e) { /* cancelado */ }
  }));

  const visor = $('#visor');
  if (visor) {
    $$('[data-foto]').forEach((b) => b.addEventListener('click', () => {
      $('img', visor).src = b.dataset.foto;
      $('p', visor).textContent = b.dataset.texto || '';
      visor.classList.remove('oculto');
    }));
    visor.addEventListener('click', () => visor.classList.add('oculto'));
  }

  // Barra inferior: aparece al pasar el botón principal
  const barra = $('.barra-reserva');
  const principal = $('.acciones-principales [data-reservar], .pro-acciones [data-reservar]');
  if (barra && principal && 'IntersectionObserver' in window) {
    new IntersectionObserver(([e]) => barra.classList.toggle('visible', !e.isIntersecting && e.boundingClientRect.top < 0)).observe(principal);
  } else if (barra) barra.classList.add('visible');

  mostrarProxima();
  paginaMisCitas();
  const q = new URLSearchParams(location.search);
  const pre = W.preseleccion || {};
  if (q.has('reservar') || pre.servicio) abrirReserva({ servicio_id: pre.servicio, profesional_id: pre.profesional });
})();
