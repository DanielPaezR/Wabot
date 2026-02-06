// ============================================
// push-simple.js - VERSIÓN DEFINITIVA SIMPLE
// ============================================

console.log('✅ push-simple.js CARGADO - ' + new Date().toLocaleTimeString());

// Función auxiliar para convertir clave - DEBE ESTAR AL INICIO
function urlBase64ToUint8Array(base64String) {
    console.log('🔑 Convirtiendo clave:', base64String.substring(0, 20) + '...');
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, '+')
        .replace(/_/g, '/');
    
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

// Configurar el botón cuando la página cargue
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ DOM listo - push-simple.js');
    
    // Verificar datos del body
    console.log('🔍 Body dataset:', document.body.dataset);
    console.log('👤 Profesional ID desde data:', document.body.dataset.profesionalId);
    
    const button = document.getElementById('pushButton');
    if (!button) {
        console.error('❌ No hay botón con id="pushButton"');
        console.log('💡 Buscando botones en la página...');
        const allButtons = document.querySelectorAll('button');
        console.log('🔘 Botones encontrados:', allButtons.length);
        allButtons.forEach((btn, i) => {
            console.log(`  ${i}: ${btn.textContent} - id="${btn.id}"`);
        });
        return;
    }
    
    console.log('✅ Botón encontrado:', button);
    console.log('📝 Texto del botón:', button.textContent);
    
    // Agregar estilo ROJO para DEBUG (visible)
    button.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
    button.style.color = 'white';
    button.style.border = 'none';
    button.style.padding = '12px 20px';
    button.style.borderRadius = '8px';
    button.style.fontWeight = 'bold';
    button.style.fontSize = '16px';
    button.style.cursor = 'pointer';
    button.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
    button.style.margin = '10px 0';
    console.log('🎨 Estilos debug aplicados al botón');
    
    // Agregar evento click AL BOTÓN
    button.addEventListener('click', async function() {
        console.log('🔘🔘🔘 USUARIO HIZO CLIC EN EL BOTÓN');
        console.log('📱 Navegador:', navigator.userAgent);
        
        // Verificar si estamos en HTTPS (importante para Service Workers)
        if (window.location.protocol !== 'https:') {
            console.warn('⚠️ NO ESTAMOS EN HTTPS, Service Workers requieren HTTPS');
            alert('⚠️ Para notificaciones push necesitas HTTPS');
        }
        
        // Deshabilitar botón inmediatamente
        const originalText = this.textContent;
        this.disabled = true;
        this.textContent = '⏳ Activando...';
        this.style.background = 'linear-gradient(135deg, #f39c12, #e67e22)';
        
        try {
            // PASO 1: Verificar soporte
            console.log('🔍 Verificando soporte del navegador...');
            console.log('- ServiceWorker:', 'serviceWorker' in navigator);
            console.log('- PushManager:', 'PushManager' in window);
            console.log('- Notification:', 'Notification' in window);
            
            if (!('serviceWorker' in navigator)) {
                const errorMsg = '❌ Tu navegador no soporta Service Workers';
                console.error(errorMsg);
                alert(errorMsg);
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            if (!('PushManager' in window)) {
                const errorMsg = '❌ Tu navegador no soporta Push Notifications';
                console.error(errorMsg);
                alert(errorMsg);
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            // PASO 2: Registrar Service Worker
            console.log('📝 Registrando Service Worker...');
            let registration;
            try {
                registration = await navigator.serviceWorker.register('/service-worker.js');
                console.log('✅ Service Worker registrado en scope:', registration.scope);
                console.log('👷 Service Worker state:', registration.active ? 'Activo' : 'No activo');
                
                // Esperar a que esté listo
                if (registration.installing) {
                    console.log('⏳ Service Worker instalando...');
                    await new Promise(resolve => {
                        const worker = registration.installing;
                        worker.addEventListener('statechange', function() {
                            if (this.state === 'activated') {
                                console.log('✅ Service Worker activado');
                                resolve();
                            }
                        });
                    });
                } else if (registration.waiting) {
                    console.log('⏳ Service Worker esperando...');
                    registration.waiting.postMessage({type: 'SKIP_WAITING'});
                }
                
            } catch (swError) {
                console.error('❌ Error registrando Service Worker:', swError);
                alert('❌ Error con Service Worker: ' + swError.message);
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            // PASO 3: PEDIR PERMISO
            console.log('🔔 Pidiendo permiso de notificaciones...');
            let permission;
            try {
                permission = await Notification.requestPermission();
                console.log('✅ Permiso:', permission);
            } catch (permError) {
                console.error('❌ Error pidiendo permiso:', permError);
                alert('❌ Error al pedir permiso: ' + permError.message);
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            if (permission !== 'granted') {
                alert('❌ Necesitas permitir las notificaciones para recibir alertas de citas.');
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            // PASO 4: Crear suscripción
            console.log('🔐 Creando suscripción push...');
            
            // CLAVE PÚBLICA CORRECTA DE RAILWAY
            const publicKey = 'BLUUZFhnk-K2WDcQTiLXOA8IMNF6zdWvu4YuNxswOuhnYmDZpPW6BRrIoSqRKeUw5EqDQZ6HaqHZUL5nywq8GnI';
            console.log('🔑 Usando clave pública (primeros 20):', publicKey.substring(0, 20) + '...');
            
            let subscription;
            try {
                subscription = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(publicKey)
                });
                
                console.log('✅ Suscrito exitosamente');
                console.log('📫 Endpoint:', subscription.endpoint.substring(0, 80) + '...');
                console.log('🔑 Subscription JSON:', JSON.stringify(subscription.toJSON()));
                
            } catch (subError) {
                console.error('❌ Error suscribiendo:', subError);
                alert('❌ Error al crear suscripción: ' + subError.message + '\n\n¿Estás en HTTPS?');
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            // PASO 5: Enviar al servidor
            console.log('📤 Enviando suscripción al servidor...');
            
            const profesionalId = document.body.dataset.profesionalId;
            if (!profesionalId) {
                console.error('❌ No se encontró profesional_id en data attribute');
                alert('❌ Error interno: No se encontró ID del profesional');
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                return;
            }
            
            console.log('👤 Enviando para profesional_id:', profesionalId);
            
            try {
                const response = await fetch('/api/push/subscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        subscription: subscription,
                        profesional_id: profesionalId
                    })
                });
                
                console.log('📊 Estado de respuesta:', response.status);
                
                const result = await response.json();
                console.log('📦 Respuesta del servidor:', result);
                
                if (result.success) {
                    // ¡ÉXITO!
                    this.textContent = '🔔 Notificaciones Activadas ✅';
                    this.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
                    
                    console.log('🎉 ¡TODO COMPLETADO EXITOSAMENTE!');
                    
                    // Mostrar alerta de éxito
                    alert('🎉 ¡NOTIFICACIONES PUSH ACTIVADAS!\n\nAhora recibirás notificaciones cuando:\n• Agenden una cita para ti\n• Te envíen recordatorios\n• Hayan novedades importantes\n\nPara probar: Ve a /push/test-manual');
                    
                    // Guardar en localStorage que ya está activado
                    localStorage.setItem('pushActivated', 'true');
                } else {
                    console.error('❌ Error del servidor:', result.error);
                    alert('❌ Error del servidor: ' + (result.error || 'No se pudo guardar la suscripción'));
                    this.disabled = false;
                    this.textContent = originalText;
                    this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
                }
                
            } catch (fetchError) {
                console.error('❌ Error enviando al servidor:', fetchError);
                alert('❌ Error de conexión: ' + fetchError.message);
                this.disabled = false;
                this.textContent = originalText;
                this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
            }
            
        } catch (error) {
            console.error('❌ Error general:', error);
            console.error('❌ Stack:', error.stack);
            alert('❌ Error inesperado: ' + error.message);
            this.disabled = false;
            this.textContent = originalText;
            this.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
        }
    });
    
    console.log('✅ Evento click configurado en el botón');
});

console.log('✅ push-simple.js terminado de cargar');