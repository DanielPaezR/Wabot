// ============================================
// push-simple.js - VERSIÓN PWA DEFINITIVA
// ============================================

console.log('🚀 PUSH PARA PWA INICIADO');

// Función para convertir clave
function urlBase64ToUint8Array(base64String) {
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

// SOLUCIÓN: Esperar a que TODO esté listo
window.addEventListener('load', function() {
    console.log('✅ Página completamente cargada');
    
    setTimeout(function() {
        inicializarPush();
    }, 1000);
});

function inicializarPush() {
    console.log('🔧 Inicializando sistema de push...');
    
    const button = document.getElementById('pushButton');
    if (!button) {
        console.error('❌ Botón no encontrado');
        return;
    }
    
    console.log('✅ Botón encontrado');
    
    // Mostrar información útil
    console.log('📱 ¿Es PWA?', window.matchMedia('(display-mode: standalone)').matches);
    console.log('🔔 Permiso actual:', Notification.permission);
    
    // Actualizar texto inicial del botón
    if (Notification.permission === 'granted') {
        button.textContent = '🔔 Notificaciones YA Activadas';
        button.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
        button.disabled = true;
        console.log('✅ Permiso ya concedido');
    } else if (Notification.permission === 'denied') {
        button.textContent = '🔔 Permitir en Configuración';
        button.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
        console.log('❌ Permiso bloqueado');
        
        // Cambiar comportamiento: abrir configuración
        button.onclick = function() {
            alert('Para activar notificaciones:\n\n1. Toca el 🔒 en la barra URL\n2. Ve a "Configuración del sitio"\n3. Busca "Notificaciones"\n4. Cambia a "Permitir"\n5. Recarga la página');
        };
        return;
    }
    
    // Configurar evento click NORMAL
    button.addEventListener('click', async function() {
        console.log('🔘 Botón presionado');
        
        this.disabled = true;
        this.textContent = '⏳ Activando...';
        
        try {
            // 1. Registrar Service Worker (IMPORTANTE para PWA)
            console.log('📝 Registrando Service Worker...');
            const registration = await navigator.serviceWorker.register('/service-worker.js');
            console.log('✅ Service Worker registrado:', registration.scope);
            
            // 2. Pedir permiso SOLO si es necesario
            let permission = Notification.permission;
            if (permission === 'default') {
                console.log('🔔 Pidiendo permiso...');
                permission = await Notification.requestPermission();
                console.log('✅ Permiso:', permission);
            }
            
            if (permission !== 'granted') {
                alert('Por favor, permite las notificaciones para recibir alertas de citas.');
                this.disabled = false;
                this.textContent = '🔔 Activar Notificaciones';
                return;
            }
            
            // 3. Suscribirse a Push
            console.log('🔐 Suscribiendo a push...');
            const publicKey = 'W3rZlst2q3iEdvKoNY_XSC3vlcjViAatSfytBNvN9tryKzOUfgAK1Yp8u9aA5E130qssYJySPAc98xuYiMB4HQ';
            
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(publicKey)
            });
            
            console.log('✅ Suscrito. Endpoint:', subscription.endpoint.substring(0, 50) + '...');
            
            // 4. Enviar al servidor
            const profesionalId = document.body.dataset.profesionalId;
            console.log('👤 Profesional ID:', profesionalId);
            
            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subscription: subscription,
                    profesional_id: profesionalId
                })
            });
            
            const result = await response.json();
            console.log('📦 Respuesta:', result);
            
            if (result.success) {
                // ¡ÉXITO!
                this.textContent = '🔔 Notificaciones Activadas ✅';
                this.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
                
                alert('🎉 ¡LISTO! Ahora recibirás notificaciones cuando:\n• Agenden citas para ti\n• Hayan recordatorios\n• Novedades importantes');
                
                // Opcional: Mostrar notificación de prueba
                if (registration.showNotification) {
                    registration.showNotification('¡Configuración Exitosa!', {
                        body: 'Las notificaciones push están activadas',
                        icon: '/static/icons/icon-192x192.png'
                    });
                }
                
            } else {
                throw new Error(result.error || 'Error del servidor');
            }
            
        } catch (error) {
            console.error('❌ Error:', error);
            alert('Error: ' + error.message);
            this.disabled = false;
            this.textContent = '🔔 Activar Notificaciones';
        }
    });
    
    console.log('✅ Sistema push listo');
}