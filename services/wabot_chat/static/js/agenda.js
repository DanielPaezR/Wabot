/* Wabot · agenda del día para barberos y dueños. */
(function () {
  'use strict';
  const A = window.AGENDA || {};
  const N = A.negocio || {};
  const PROS = A.profesionales || [];
  const SERVICIOS = A.servicios || [];
  const ES_DUENO = A.rol === 'dueno';
  const CLAVE_VISTO = 'wabot_agenda_visto_' + N.id;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ic = (n, c = '') => `<svg class="ic ${c}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const mayus = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
  const leer = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } };
  const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* privado */ } };
  const proPorId = (id) => PROS.find((p) => p.id === id);
  const avatar = (p, cls = '') => `<span class="avatar ${cls}">${p && p.foto ? `<img src="${esc(p.foto)}" alt="">` : esc((p && p.iniciales) || '?')}</span>`;

  async function api(ruta, opciones = {}) {
    try {
      const r = await fetch(ruta, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opciones });
      if (r.status === 401) { location.href = '/login'; return { ok: false }; }
      const d = await r.json().catch(() => ({}));
      d._status = r.status;
      return d;
    } catch (e) {
      return { ok: false, error: 'Sin conexión' };
    }
  }

  function aviso(texto) {
    let el = $('#aviso');
    if (!el) { el = document.createElement('div'); el.id = 'aviso'; el.className = 'aviso'; document.body.appendChild(el); }
    el.textContent = texto;
    el.classList.add('visible');
    clearTimeout(aviso._t);
    aviso._t = setTimeout(() => el.classList.remove('visible'), 2800);
  }

  // ───────────── estado ─────────────
  const E = { fecha: A.fecha_inicial || null, filtro: ES_DUENO ? 'todos' : A.yo, dia: null, dias: [], idsVistos: null };

  // ───────────── saludo ─────────────
  (function saludo() {
    const h = new Date().getHours();
    const parte = h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches';
    $('#ag-saludo').textContent = `${parte}${A.nombre ? ', ' + A.nombre : ''}`;
  })();

  // ───────────── tira de días ─────────────
  async function cargarDias() {
    const r = await api('/api/agenda/semana');
    if (!r.ok) return;
    E.dias = r.dias;
    if (!E.fecha) E.fecha = (r.dias.find((d) => d.hoy) || r.dias[0]).fecha;
    pintarDias();
  }
  function pintarDias() {
    const tira = $('#ag-dias');
    tira.innerHTML = E.dias.map((d) => `
      <button type="button" role="tab" class="ag-dia ${d.fecha === E.fecha ? 'elegido' : ''} ${d.hoy ? 'hoy' : ''} ${d.abierto ? '' : 'cerrado'}" data-fecha="${d.fecha}" aria-selected="${d.fecha === E.fecha}">
        <span>${esc(d.dia)}</span><strong>${d.num}</strong>
        <i class="ag-puntos">${d.citas ? '<b></b>'.repeat(Math.min(d.citas, 3)) : ''}</i>
      </button>`).join('');
    $$('.ag-dia', tira).forEach((b) => b.addEventListener('click', () => { E.fecha = b.dataset.fecha; pintarDias(); cargarDia(); }));
    const el = $('.ag-dia.elegido', tira);
    if (el) el.scrollIntoView({ block: 'nearest', inline: 'center' });
  }

  // ───────────── el día ─────────────
  async function cargarDia(silencioso) {
    if (!silencioso) $('#ag-linea').innerHTML = '<div class="ag-carga"><span class="girando"></span></div>';
    const fecha = E.fecha;
    const r = await api('/api/agenda/dia?fecha=' + encodeURIComponent(fecha || ''));
    if (!r.ok || fecha !== E.fecha) return;
    // ¿Llegaron citas nuevas mientras mirábamos?
    const ids = new Set(r.citas.filter((c) => c.estado !== 'bloqueo').map((c) => c.id));
    if (silencioso && E.idsVistos && E.dia && E.dia.fecha === r.fecha) {
      const nuevas = r.citas.filter((c) => c.estado === 'confirmado' && !E.idsVistos.has(c.id));
      if (nuevas.length) {
        const c = nuevas[0];
        aviso(`Nueva cita: ${c.cliente} · ${c.hora_txt}`);
        if (navigator.vibrate) navigator.vibrate([40, 60, 40]);
      }
    }
    E.idsVistos = ids;
    E.dia = r;
    $('#ag-fecha-txt').textContent = r.es_hoy ? `Hoy · ${mayus(r.fecha_txt)}` : mayus(r.fecha_txt);
    pintarResumen();
    pintarProxima();
    pintarEquipo();
    pintarFiltros();
    pintarLinea();
  }

  function pintarResumen() {
    const r = E.dia.resumen;
    $('#ag-resumen').innerHTML = `
      <div><span>Citas</span><strong>${r.citas}</strong><small>${r.completadas} hechas · ${r.pendientes} por atender</small></div>
      <div><span>Esperado</span><strong>${esc(r.esperado_txt)}</strong><small>${esc(E.dia.horario.txt)}</small></div>
      <div><span>Cobrado</span><strong>${esc(r.cobrado_txt)}</strong><small>${r.canceladas ? r.canceladas + ' cancelada' + (r.canceladas > 1 ? 's' : '') : 'Sin cancelaciones'}</small></div>`;
  }

  function pintarProxima() {
    const caja = $('#ag-proxima');
    const p = E.dia.proxima;
    const c = p && E.dia.citas.find((x) => x.id === p.id);
    if (!c || (ES_DUENO && E.filtro === 'todos' && PROS.length > 1)) { caja.classList.add('oculto'); return; }
    const en = p.en_minutos;
    const cuando = en <= 0 ? 'Ahora' : en < 60 ? `En ${en} min` : `En ${Math.floor(en / 60)} h ${en % 60 ? (en % 60) + ' min' : ''}`;
    caja.innerHTML = `
      <div class="ag-proxima-txt">
        <span class="sobretitulo">${en <= 0 ? 'Atendiendo' : 'Siguiente'} · ${esc(cuando)}</span>
        <strong>${esc(c.cliente)}</strong>
        <span>${esc(c.servicio)} · ${esc(c.hora_txt)}${ES_DUENO ? ' · ' + esc(c.profesional) : ''}</span>
      </div>
      <div class="ag-proxima-acciones">
        ${c.recordatorio ? `<a class="icono-boton ag-wa" href="${esc(c.recordatorio)}" target="_blank" rel="noopener" aria-label="Escribir por WhatsApp">${ic('whatsapp')}</a>` : ''}
        <button class="boton boton-primario boton-chico" type="button" data-completar="${c.id}">${ic('check')}Hecho</button>
      </div>`;
    caja.classList.remove('oculto');
    $('[data-completar]', caja).addEventListener('click', () => cambiarEstado(c.id, 'completado'));
  }

  function pintarEquipo() {
    if (!ES_DUENO) return;
    const sec = $('#ag-equipo-sec');
    if (!E.dia.es_hoy || PROS.length < 2) { sec.classList.add('oculto'); return; }
    sec.classList.remove('oculto');
    $('#ag-equipo').innerHTML = E.dia.equipo.map((p) => `
      <button type="button" class="ag-miembro ${p.estado.tipo}" data-filtro="${p.id}">
        ${avatar(p, 'avatar-sm')}
        <div><strong>${esc(p.primer_nombre)}</strong><span><i></i>${esc(p.estado.txt)}</span>
        ${p.siguiente ? `<small>Sigue ${esc(p.siguiente.cliente.split(' ')[0])} · ${esc(p.siguiente.hora_txt)}</small>` : `<small>${p.citas} cita${p.citas === 1 ? '' : 's'} hoy</small>`}</div>
      </button>`).join('');
    $$('[data-filtro]', $('#ag-equipo')).forEach((b) => b.addEventListener('click', () => { E.filtro = Number(b.dataset.filtro); pintarFiltros(); pintarLinea(); pintarProxima(); }));
  }

  function pintarFiltros() {
    if (!ES_DUENO || PROS.length < 2) return;
    const f = $('#ag-filtros');
    f.innerHTML = [`<button type="button" data-f="todos" class="${E.filtro === 'todos' ? 'elegido' : ''}">Todos</button>`]
      .concat(PROS.map((p) => `<button type="button" data-f="${p.id}" class="${E.filtro === p.id ? 'elegido' : ''}">${avatar(p, 'avatar-xs')}${esc(p.primer_nombre)}</button>`)).join('');
    $$('button', f).forEach((b) => b.addEventListener('click', () => {
      E.filtro = b.dataset.f === 'todos' ? 'todos' : Number(b.dataset.f);
      pintarFiltros(); pintarLinea(); pintarProxima();
    }));
  }

  function pintarLinea() {
    const caja = $('#ag-linea');
    const d = E.dia;
    const todos = E.filtro === 'todos';
    const citas = d.citas.filter((c) => todos || c.profesional_id === E.filtro);
    const huecos = todos ? [] : (d.huecos[E.filtro] || []);
    if (!d.horario.abierto && !citas.length) {
      caja.innerHTML = `<div class="ag-vacio">${ic('calendar')}<strong>Día cerrado</strong><span>El negocio no abre este día.</span></div>`;
      return;
    }
    const items = citas.map((c) => ({ t: c.inicio_min, tipo: 'cita', c }))
      .concat(huecos.map((h) => ({ t: h.desde_min, tipo: 'hueco', h })));
    if (d.es_hoy && d.ahora_min != null) items.push({ t: d.ahora_min, tipo: 'ahora' });
    items.sort((a, b) => a.t - b.t || (a.tipo === 'ahora' ? -1 : 1));
    const activas = citas.filter((c) => c.estado !== 'cancelado' && c.estado !== 'bloqueo');
    if (!activas.length && !huecos.length && !citas.length) {
      caja.innerHTML = `<div class="ag-vacio">${ic('calendar')}<strong>Sin citas por ahora</strong><span>Comparte tu enlace para que te reserven.</span>
        <button class="boton boton-suave boton-chico" type="button" data-copiar-enlace>${ic('share')}Copiar enlace</button></div>`;
      enlazarCopiar(caja);
      return;
    }
    caja.innerHTML = items.map((it) => {
      if (it.tipo === 'ahora') {
        const h = Math.floor(d.ahora_min / 60), m = d.ahora_min % 60;
        return `<div class="ag-ahora"><span>${((h % 12) || 12)}:${String(m).padStart(2, '0')} ${h < 12 ? 'a. m.' : 'p. m.'}</span><i></i></div>`;
      }
      if (it.tipo === 'hueco') {
        const h = it.h;
        return `<button type="button" class="ag-hueco" data-hueco="${h.desde}">
          <span class="ag-hora">${horaCorta(h.txt.split(' – ')[0])}<small>${esc(sufijo(h.txt.split(' – ')[0]))}</small></span>
          <span class="ag-hueco-txt">${ic('plus')}Libre ${h.minutos >= 60 ? Math.floor(h.minutos / 60) + ' h' + (h.minutos % 60 ? ' ' + (h.minutos % 60) + ' min' : '') : h.minutos + ' min'} <em>hasta ${esc(h.txt.split(' – ')[1])}</em></span>
        </button>`;
      }
      const c = it.c;
      const pasada = d.es_hoy && d.ahora_min != null && c.inicio_min + c.duracion <= d.ahora_min;
      if (c.estado === 'bloqueo') {
        return `<button type="button" class="ag-cita bloqueo" data-cita="${c.id}">
          <span class="ag-hora">${horaCorta(c.hora_txt)}<small>${esc(sufijo(c.hora_txt))}<br>${esc(c.duracion_txt)}</small></span>
          <span class="ag-tarjeta"><strong>${ic('lock')}${esc(c.motivo)}</strong><span>${esc(c.duracion_txt)}${todos ? ' · ' + esc(c.profesional) : ''}</span></span>
        </button>`;
      }
      const pro = proPorId(c.profesional_id);
      return `<button type="button" class="ag-cita ${c.estado} ${pasada && c.estado === 'confirmado' ? 'pendiente-cierre' : ''} ${pasada ? 'pasada' : ''}" data-cita="${c.id}">
        <span class="ag-hora">${horaCorta(c.hora_txt)}<small>${esc(sufijo(c.hora_txt))}<br>${esc(c.duracion_txt)}</small></span>
        <span class="ag-tarjeta">
          <span class="ag-tarjeta-fila"><strong>${esc(c.cliente)}</strong>${c.nueva && c.estado === 'confirmado' ? '<em class="ag-nueva">Nueva</em>' : ''}${estadoPill(c)}</span>
          <span>${esc(c.servicio)} · ${esc(c.precio_txt)}</span>
          ${todos && pro ? `<span class="ag-de">${avatar(pro, 'avatar-xs')}${esc(pro.primer_nombre)}</span>` : ''}
        </span>
      </button>`;
    }).join('');
    $$('[data-cita]', caja).forEach((b) => b.addEventListener('click', () => abrirCita(Number(b.dataset.cita))));
    $$('[data-hueco]', caja).forEach((b) => b.addEventListener('click', () => abrirNuevaCita({ hora: b.dataset.hueco, profesional_id: E.filtro })));
    const ahora = $('.ag-ahora', caja);
    if (ahora && !E.yaCentrado) { E.yaCentrado = true; setTimeout(() => ahora.scrollIntoView({ block: 'center', behavior: 'smooth' }), 150); }
  }

  const horaCorta = (t) => esc(String(t || '').split(' ')[0]);
  const sufijo = (t) => String(t || '').split(' ').slice(1).join(' ');

  function estadoPill(c) {
    const m = { completado: ['Hecha', 'ok'], cancelado: ['Cancelada', 'mal'], no_asistio: ['No vino', 'mal'] };
    return m[c.estado] ? `<em class="ag-pill ${m[c.estado][1]}">${m[c.estado][0]}</em>` : '';
  }

  // ───────────── hoja genérica ─────────────
  const hoja = $('#ag-hoja');
  let hojaAbierta = false;
  function abrirHoja(sobre, titulo, cuerpoHtml, pieHtml) {
    $('#ag-hoja-sobre').textContent = sobre || '';
    $('#ag-hoja-titulo').textContent = titulo;
    $('#ag-hoja-cuerpo').innerHTML = cuerpoHtml;
    const pie = $('#ag-hoja-pie');
    pie.innerHTML = pieHtml || '';
    pie.classList.toggle('oculto', !pieHtml);
    if (!hojaAbierta) {
      hoja.classList.remove('oculto');
      requestAnimationFrame(() => hoja.classList.add('abierta'));
      document.documentElement.classList.add('sin-scroll');
      history.pushState({ agHoja: 1 }, '');
      hojaAbierta = true;
    }
    $('#ag-hoja-cuerpo').scrollTop = 0;
  }
  function cerrarHoja(silencioso) {
    if (!hojaAbierta) return;
    hojaAbierta = false;
    hoja.classList.remove('abierta');
    document.documentElement.classList.remove('sin-scroll');
    setTimeout(() => hoja.classList.add('oculto'), 250);
    if (!silencioso && history.state && history.state.agHoja) history.back();
  }
  window.addEventListener('popstate', () => cerrarHoja(true));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrarHoja(); });
  $$('#ag-hoja [data-cerrar]').forEach((b) => b.addEventListener('click', () => cerrarHoja()));

  // ───────────── detalle de una cita ─────────────
  function abrirCita(id) {
    const c = E.dia && E.dia.citas.find((x) => x.id === id);
    if (!c) return;
    if (c.estado === 'bloqueo') {
      abrirHoja('Bloqueo', c.motivo, `
        <div class="ag-detalle"><div class="ag-detalle-fila">${ic('clock')}<div><strong>${esc(c.hora_txt)} – ${esc(c.fin_txt)}</strong><span>${esc(c.duracion_txt)} · ${esc(c.profesional)}</span></div></div></div>`,
        `<button class="boton boton-peligro ancho" type="button" id="b-desbloquear">Quitar bloqueo</button>`);
      $('#b-desbloquear').addEventListener('click', async () => {
        const r = await api('/api/agenda/bloqueos/' + c.id, { method: 'DELETE' });
        if (r.ok) { aviso('Bloqueo quitado'); cerrarHoja(); cargarDia(true); cargarDias(); } else aviso(r.error || 'No se pudo quitar');
      });
      return;
    }
    const pro = proPorId(c.profesional_id);
    const activa = c.estado === 'confirmado';
    abrirHoja(mayus(E.dia.fecha_txt), c.cliente, `
      <div class="ag-detalle">
        <div class="ag-detalle-fila"><span class="avatar avatar-sm">${esc(c.iniciales)}</span><div><strong>${esc(c.cliente)}</strong><span>${c.telefono ? esc(c.telefono) : 'Sin teléfono'}</span></div>${estadoPill(c)}</div>
        <div class="ag-detalle-fila">${ic('scissors')}<div><strong>${esc(c.servicio)}</strong><span>${esc(c.duracion_txt)} · ${esc(c.precio_txt)}</span></div></div>
        <div class="ag-detalle-fila">${ic('clock')}<div><strong>${esc(c.hora_txt)} – ${esc(c.fin_txt)}</strong><span>${pro ? 'con ' + esc(pro.nombre) : ''}</span></div></div>
      </div>
      ${c.whatsapp ? `<div class="ag-contacto">
        ${activa && c.recordatorio ? `<a class="boton ag-boton-wa" href="${esc(c.recordatorio)}" target="_blank" rel="noopener">${ic('whatsapp')}Enviar recordatorio</a>` : `<a class="boton ag-boton-wa" href="https://wa.me/${esc(c.whatsapp)}" target="_blank" rel="noopener">${ic('whatsapp')}WhatsApp</a>`}
        <a class="boton boton-suave" href="tel:+${esc(c.whatsapp)}">${ic('phone')}Llamar</a>
      </div>` : ''}
      ${activa ? `<div class="ag-estados">
        <button type="button" class="ag-estado ok" data-estado="completado">${ic('check')}<span>Atendido</span></button>
        <button type="button" class="ag-estado" data-estado="no_asistio">${ic('user')}<span>No vino</span></button>
        <button type="button" class="ag-estado mal" data-estado="cancelado">${ic('ban')}<span>Cancelar</span></button>
      </div>` : `<button type="button" class="boton boton-suave ancho ag-deshacer" data-estado="confirmado">${ic('undo')}Volver a dejarla pendiente</button>`}`);
    $$('[data-estado]', $('#ag-hoja-cuerpo')).forEach((b) => b.addEventListener('click', () => {
      const est = b.dataset.estado;
      if (est === 'cancelado' && b.dataset.seguro !== '1') {
        b.dataset.seguro = '1';
        $('span', b).textContent = '¿Seguro?';
        setTimeout(() => { b.dataset.seguro = ''; const s = $('span', b); if (s) s.textContent = 'Cancelar'; }, 3500);
        return;
      }
      cambiarEstado(c.id, est, true);
    }));
  }

  async function cambiarEstado(id, estado, cerrar) {
    const r = await api(`/api/agenda/citas/${id}/estado`, { method: 'POST', body: JSON.stringify({ estado }) });
    if (!r.ok) { aviso(r.error || 'No se pudo guardar'); return; }
    if (navigator.vibrate) navigator.vibrate(20);
    aviso({ completado: '¡Listo! Cita atendida', no_asistio: 'Marcada como "no vino"', cancelado: 'Cita cancelada · le avisamos al cliente', confirmado: 'Cita pendiente de nuevo' }[estado]);
    if (cerrar) cerrarHoja();
    cargarDia(true);
    if (estado === 'cancelado') cargarDias();
  }

  // ───────────── nueva cita (cliente que llama o llega) ─────────────
  function abrirNuevaCita(pre = {}) {
    const proInicial = pre.profesional_id && pre.profesional_id !== 'todos' ? pre.profesional_id : (ES_DUENO ? (PROS[0] || {}).id : A.yo);
    const st = { pro: proInicial, servicio: null, hora: pre.hora || null };
    const elegirPro = ES_DUENO && PROS.length > 1 ? `
      <label class="campo"><span>${esc(mayus(N.pro))}</span></label>
      <div class="ag-chips" id="nc-pros">${PROS.map((p) => `<button type="button" data-pro="${p.id}" class="${p.id === st.pro ? 'elegido' : ''}">${avatar(p, 'avatar-xs')}${esc(p.primer_nombre)}</button>`).join('')}</div>` : '';
    abrirHoja(mayus(E.dia ? E.dia.fecha_txt : ''), 'Nueva cita', `
      <form id="form-nc" class="formulario" style="margin-top:0" novalidate>
        <label class="campo"><span>Cliente</span><input name="nombre" required maxlength="60" placeholder="Nombre" autocomplete="off"></label>
        <label class="campo"><span>WhatsApp <em class="tenue">(opcional, para recordarle)</em></span><input name="telefono" type="tel" inputmode="numeric" maxlength="18" placeholder="${esc(N.tel_ejemplo)}" autocomplete="off"></label>
        ${elegirPro}
        <label class="campo"><span>Servicio</span></label>
        <div class="ag-chips ag-chips-servicios" id="nc-servicios"></div>
        <label class="campo"><span>Hora</span></label>
        <div id="nc-horas" class="rejilla-horas"><p class="tenue">Elige un servicio para ver las horas libres.</p></div>
        <p class="error-form oculto" id="nc-error"></p>
      </form>`, `<button class="boton boton-primario boton-grande ancho" type="submit" form="form-nc" id="nc-guardar">Agendar</button>`);
    const form = $('#form-nc');
    const pintarServicios = () => {
      const pro = proPorId(st.pro);
      const lista = SERVICIOS.filter((s) => !pro || !pro.servicios.length || pro.servicios.includes(s.id));
      if (st.servicio && !lista.some((s) => s.id === st.servicio)) st.servicio = null;
      $('#nc-servicios').innerHTML = lista.map((s) => `<button type="button" data-s="${s.id}" class="${s.id === st.servicio ? 'elegido' : ''}">${esc(s.nombre)}<small>${esc(s.duracion_txt)}</small></button>`).join('');
      $$('#nc-servicios button').forEach((b) => b.addEventListener('click', () => { st.servicio = Number(b.dataset.s); pintarServicios(); cargarHorasNc(); }));
    };
    const cargarHorasNc = async () => {
      const caja = $('#nc-horas');
      if (!st.servicio) return;
      caja.innerHTML = '<span class="hora esqueleto"></span>'.repeat(6);
      const r = await api(`/api/agenda/horarios?profesional_id=${st.pro}&servicio_id=${st.servicio}&fecha=${E.fecha}`);
      if (!r.ok) { caja.innerHTML = `<p class="tenue">${esc(r.error || 'No se pudieron cargar las horas')}</p>`; return; }
      if (!r.horarios.length) { caja.innerHTML = '<p class="tenue">No quedan horas libres este día para ese servicio.</p>'; st.hora = null; return; }
      if (st.hora && !r.horarios.some((h) => h.hora === st.hora)) st.hora = null;
      caja.innerHTML = r.horarios.map((h) => `<button type="button" class="hora ${h.hora === st.hora ? 'elegida' : ''}" data-h="${h.hora}">${esc(h.txt.replace(' ', ' '))}</button>`).join('');
      $$('.hora', caja).forEach((b) => b.addEventListener('click', () => { st.hora = b.dataset.h; $$('.hora', caja).forEach((x) => x.classList.toggle('elegida', x === b)); }));
      const el = st.hora && $(`.hora[data-h="${st.hora}"]`, caja);
      if (el) el.scrollIntoView({ block: 'nearest' });
    };
    $$('#nc-pros button').forEach((b) => b.addEventListener('click', () => {
      st.pro = Number(b.dataset.pro);
      $$('#nc-pros button').forEach((x) => x.classList.toggle('elegido', x === b));
      pintarServicios(); cargarHorasNc();
    }));
    pintarServicios();
    if (window.matchMedia('(min-width: 720px)').matches) form.nombre.focus();
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const err = $('#nc-error');
      const fallo = (t) => { err.textContent = t; err.classList.remove('oculto'); };
      if (form.nombre.value.trim().length < 2) return fallo('Escribe el nombre del cliente.');
      if (!st.servicio) return fallo('Elige el servicio.');
      if (!st.hora) return fallo('Elige la hora.');
      const b = $('#nc-guardar'); b.disabled = true;
      const r = await api('/api/agenda/citas', { method: 'POST', body: JSON.stringify({
        profesional_id: st.pro, servicio_id: st.servicio, fecha: E.fecha, hora: st.hora,
        nombre: form.nombre.value, telefono: form.telefono.value }) });
      b.disabled = false;
      if (!r.ok) return fallo(r.error || 'No se pudo agendar');
      aviso('Cita agendada');
      cerrarHoja(); cargarDia(true); cargarDias();
    });
  }

  // ───────────── bloquear un rato ─────────────
  function abrirBloqueo() {
    const ahora = new Date();
    let m = ahora.getHours() * 60 + ahora.getMinutes();
    m = Math.ceil(m / 15) * 15;
    const horaDef = E.dia && E.dia.es_hoy ? `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}` : '12:00';
    const st = { pro: ES_DUENO ? (E.filtro !== 'todos' ? E.filtro : (PROS[0] || {}).id) : A.yo, duracion: 60, motivo: 'Almuerzo' };
    abrirHoja(mayus(E.dia ? E.dia.fecha_txt : ''), 'Bloquear un rato', `
      <form id="form-bl" class="formulario" style="margin-top:0" novalidate>
        ${ES_DUENO && PROS.length > 1 ? `<label class="campo"><span>${esc(mayus(N.pro))}</span></label>
          <div class="ag-chips" id="bl-pros">${PROS.map((p) => `<button type="button" data-pro="${p.id}" class="${p.id === st.pro ? 'elegido' : ''}">${avatar(p, 'avatar-xs')}${esc(p.primer_nombre)}</button>`).join('')}</div>` : ''}
        <label class="campo"><span>Desde</span><input name="hora" type="time" step="900" value="${horaDef}" required></label>
        <label class="campo"><span>Durante</span></label>
        <div class="ag-chips" id="bl-dur">${[[30, '30 min'], [60, '1 hora'], [120, '2 horas'], [240, '4 horas']].map(([v, t]) => `<button type="button" data-v="${v}" class="${v === st.duracion ? 'elegido' : ''}">${t}</button>`).join('')}</div>
        <label class="campo"><span>Motivo</span></label>
        <div class="ag-chips" id="bl-mot">${['Almuerzo', 'Descanso', 'Diligencia', 'Personal'].map((t) => `<button type="button" data-v="${t}" class="${t === st.motivo ? 'elegido' : ''}">${t}</button>`).join('')}</div>
        <p class="tenue" style="font-size:13px">Durante el bloqueo nadie podrá reservar contigo. Si ya hay citas en ese rato, te avisamos.</p>
        <p class="error-form oculto" id="bl-error"></p>
      </form>`, `<button class="boton boton-primario boton-grande ancho" type="submit" form="form-bl">${ic('lock')}Bloquear</button>`);
    const grupo = (sel, clave, num) => $$(sel + ' button').forEach((b) => b.addEventListener('click', () => {
      st[clave] = num ? Number(b.dataset.v || b.dataset.pro) : b.dataset.v;
      $$(sel + ' button').forEach((x) => x.classList.toggle('elegido', x === b));
    }));
    grupo('#bl-pros', 'pro', true); grupo('#bl-dur', 'duracion', true); grupo('#bl-mot', 'motivo', false);
    $('#form-bl').addEventListener('submit', async (e) => {
      e.preventDefault();
      const r = await api('/api/agenda/bloqueos', { method: 'POST', body: JSON.stringify({
        profesional_id: st.pro, fecha: E.fecha, hora: e.target.hora.value, duracion: st.duracion, motivo: st.motivo }) });
      if (!r.ok) { const er = $('#bl-error'); er.textContent = r.error || 'No se pudo bloquear'; er.classList.remove('oculto'); return; }
      aviso('Horario bloqueado'); cerrarHoja(); cargarDia(true);
    });
  }

  // ───────────── botón + ─────────────
  $('#b-nuevo').addEventListener('click', () => {
    abrirHoja('', '¿Qué quieres hacer?', `
      <ul class="opciones">
        <li><button type="button" class="opcion" id="op-cita"><span class="avatar avatar-sm avatar-cualquiera">${ic('calendar')}</span><span class="opcion-texto"><strong>Agendar una cita</strong><span>Alguien llamó o llegó sin reserva</span></span></button></li>
        <li><button type="button" class="opcion" id="op-bloqueo"><span class="avatar avatar-sm avatar-cualquiera">${ic('lock')}</span><span class="opcion-texto"><strong>Bloquear un rato</strong><span>Almuerzo, descanso, diligencia…</span></span></button></li>
        <li><button type="button" class="opcion" data-copiar-enlace><span class="avatar avatar-sm avatar-cualquiera">${ic('share')}</span><span class="opcion-texto"><strong>Copiar mi enlace</strong><span>Para que te reserven solos</span></span></button></li>
      </ul>`);
    $('#op-cita').addEventListener('click', () => abrirNuevaCita({ profesional_id: E.filtro }));
    $('#op-bloqueo').addEventListener('click', abrirBloqueo);
    enlazarCopiar($('#ag-hoja-cuerpo'));
  });

  function enlazarCopiar(raiz) {
    $$('[data-copiar-enlace]', raiz).forEach((b) => b.addEventListener('click', async () => {
      try {
        if (navigator.share && matchMedia('(pointer: coarse)').matches) await navigator.share({ title: N.nombre, text: 'Reserva tu cita aquí:', url: A.enlace });
        else { await navigator.clipboard.writeText(A.enlace); aviso('Enlace copiado'); }
      } catch (e) { /* cancelado */ }
    }));
  }

  // ───────────── menú ─────────────
  $('#b-menu').addEventListener('click', () => {
    abrirHoja(N.nombre, 'Menú', $('#tpl-menu').innerHTML);
    enlazarCopiar($('#ag-hoja-cuerpo'));
  });

  // ───────────── notificaciones ─────────────
  let notifs = [];
  async function cargarNotificaciones() {
    const r = await api('/api/agenda/notificaciones');
    if (!r.ok) return;
    notifs = r.notificaciones;
    let sinLeer = r.sin_leer;
    if (r.rol !== 'profesional') {
      const visto = leer(CLAVE_VISTO) || 0;
      sinLeer = notifs.filter((n) => n.id > visto).length;
    }
    const badge = $('#ag-badge');
    badge.textContent = sinLeer > 9 ? '9+' : sinLeer;
    badge.classList.toggle('oculto', !sinLeer);
  }
  $('#b-notificaciones').addEventListener('click', async () => {
    const visto = leer(CLAVE_VISTO) || 0;
    abrirHoja('', 'Notificaciones', notifs.length ? `<ul class="ag-notifs">${notifs.map((n) => `
      <li class="${(ES_DUENO ? n.id > visto : !n.leida) ? 'nueva' : ''}">
        <i></i><div><strong>${esc(n.titulo)}</strong><p>${esc(n.mensaje)}</p><span>${esc(n.cuando)}${n.profesional ? ' · ' + esc(n.profesional) : ''}</span></div>
      </li>`).join('')}</ul>` : `<div class="ag-vacio">${ic('bell')}<strong>Todo al día</strong><span>Aquí verás cada reserva, cancelación y recordatorio.</span></div>`);
    if (notifs.length) guardar(CLAVE_VISTO, Math.max(...notifs.map((n) => n.id)));
    await api('/api/agenda/notificaciones/leidas', { method: 'POST', body: '{}' });
    $('#ag-badge').classList.add('oculto');
  });

  // ───────────── push ─────────────
  function b64(base64) {
    const relleno = '='.repeat((4 - (base64.length % 4)) % 4);
    const crudo = atob((base64 + relleno).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from([...crudo].map((ch) => ch.charCodeAt(0)));
  }
  async function suscribir(silencioso) {
    try {
      const clave = await fetch('/api/push/public-key').then((r) => r.json());
      if (!clave.publicKey) throw new Error('sin clave');
      const reg = await navigator.serviceWorker.register('/service-worker.js');
      await navigator.serviceWorker.ready;
      let sus = await reg.pushManager.getSubscription();
      if (!sus) sus = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(clave.publicKey) });
      const r = await api('/api/push/subscribe', { method: 'POST', body: JSON.stringify({ subscription: sus.toJSON() }) });
      if (r.success || r.ok) { $('#ag-push').classList.add('oculto'); if (!silencioso) aviso('¡Listo! Te avisaremos de cada reserva'); }
      else if (!silencioso) aviso('No se pudieron activar los avisos');
    } catch (e) { if (!silencioso) aviso('No se pudieron activar los avisos'); }
  }
  (function prepararPush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !window.Notification) return;
    if (Notification.permission === 'granted') { suscribir(true); return; }   // renueva la suscripción en silencio
    if (Notification.permission === 'denied') return;
    $('#ag-push').classList.remove('oculto');
    $('#b-push').addEventListener('click', async () => {
      const p = await Notification.requestPermission();
      if (p === 'granted') suscribir(false); else $('#ag-push').classList.add('oculto');
    });
  })();

  // ───────────── arranque y refresco ─────────────
  (async function iniciar() {
    await cargarDias();
    await cargarDia();
    cargarNotificaciones();
    if (A.cita) setTimeout(() => abrirCita(A.cita), 300);
  })();
  setInterval(() => { if (!document.hidden && !hojaAbierta) { cargarDia(true); cargarNotificaciones(); } }, 40000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { cargarDia(true); cargarNotificaciones(); } });
})();
