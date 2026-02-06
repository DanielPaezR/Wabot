// push-notifications.js - VERSIÓN CORREGIDA
console.log('🚀 push-notifications.js INICIADO - ' + new Date().toLocaleTimeString());

class PushNotifications {
    constructor() {
        console.log('🔧 Constructor PushNotifications');
        // ¡¡¡CLAVE CORRECTA!!! Verifica que sea EXACTAMENTE esta:
        this.publicKey = 'W3rZlst2q3iEdvKoNY_XSC3vlcjViAatSfytBNvN9tryKzOUfgAK1Yp8u9aA5E130qssYJySPAc98xuYiMB4HQ';
        this.profesionalId = null;
        this.isInitialized = false;
        console.log('✅ Clave configurada (primeros 20 chars):', this.publicKey.substring(0, 20) + '...');
    }
    
    async inicializar(profesionalId) {
        console.log('🚀 Inicializando para profesional:', profesionalId);
        
        if (this.isInitialized) {
            console.log('⚠️ Ya inicializado');
            return true;
        }
        
        this.profesionalId = profesionalId;
        
        console.log('🔍 Verificando soporte del navegador...');
        console.log('- ServiceWorker en navigator:', 'serviceWorker' in navigator);
        console.log('- PushManager en window:', 'PushManager' in window);
        
        if (!('serviceWorker' in navigator)) {
            console.error('❌ ServiceWorker no soportado');
            alert('Tu navegador no soporta Service Workers');
            return false;
        }
        
        if (!('PushManager' in window)) {
            console.error('❌ Push API no soportada');
            alert('Tu navegador no soporta Push Notifications');
            return false;
        }
        
        try {
            console.log('📝 Registrando Service Worker...');
            const registration = await navigator.serviceWorker.register('/service-worker.js');
            console.log('✅ Service Worker registrado:', registration.scope);
            
            console.log('🔔 Solicitando permiso...');
            const permission = await Notification.requestPermission();
            console.log('✅ Permiso:', permission);
            
            if (permission !== 'granted') {
                console.warn('❌ Permiso denegado');
                alert('Por favor, permite las notificaciones');
                return false;
            }
            
            console.log('🔐 Suscribiendo a push...');
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(this.publicKey)
            });
            
            console.log('✅ Suscrito. Endpoint:', subscription.endpoint.substring(0, 60) + '...');
            
            // Enviar al servidor
            const result = await this.enviarSuscripcion(subscription);
            
            if (result && result.success) {
                console.log('🎉 ¡PUSH ACTIVADO!');
                this.isInitialized = true;
                return true;
            } else {
                console.error('❌ Error enviando suscripción:', result ? result.error : 'sin respuesta');
                return false;
            }
            
        } catch (error) {
            console.error('❌ Error crítico:', error);
            alert('Error: ' + error.message);
            return false;
        }
    }
    
    async enviarSuscripcion(subscription) {
        try {
            console.log('📤 Enviando suscripción al servidor...');
            
            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    subscription: subscription,
                    profesional_id: this.profesionalId
                })
            });
            
            console.log('📊 Estado:', response.status);
            const data = await response.json();
            console.log('📦 Respuesta:', data);
            
            return data;
            
        } catch (error) {
            console.error('❌ Error enviando:', error);
            return { success: false, error: error.message };
        }
    }
    
    urlBase64ToUint8Array(base64String) {
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
}

// INICIALIZACIÓN AUTOMÁTICA
console.log('🔍 Iniciando inicialización automática...');

// Esperar a que el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePush);
} else {
    initializePush();
}

function initializePush() {
    console.log('📱 initializePush() ejecutado');
    
    const profesionalId = document.body.dataset.profesionalId;
    console.log('👤 Profesional ID encontrado:', profesionalId);
    
    if (!profesionalId || profesionalId === '') {
        console.warn('⚠️ No hay profesional_id en data attribute');
        console.log('💡 Agrega: <body data-profesional-id="{{ session.profesional_id }}">');
        return;
    }
    
    const button = document.getElementById('pushButton');
    if (!button) {
        console.error('❌ No se encontró el botón con id="pushButton"');
        return;
    }
    
    console.log('✅ Botón encontrado:', button);
    
    // Configurar evento click
    button.addEventListener('click', async function() {
        console.log('🔘 Botón clickeado');
        
        if (this.disabled) {
            console.log('⚠️ Botón ya está deshabilitado');
            return;
        }
        
        this.disabled = true;
        this.textContent = '⏳ Activando...';
        
        const pushManager = new PushNotifications();
        try {
            const success = await pushManager.inicializar(profesionalId);
            
            if (success) {
                this.textContent = '🔔 Notificaciones Activadas';
                this.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
                console.log('✅ Botón actualizado a "Notificaciones Activadas"');
            } else {
                this.textContent = '🔔 Activar Notificaciones Push';
                this.disabled = false;
                console.log('❌ Falló la activación');
            }
        } catch (error) {
            console.error('❌ Error en evento click:', error);
            this.textContent = '🔔 Activar Notificaciones Push';
            this.disabled = false;
        }
    });
    
    console.log('✅ Evento click configurado en el botón');
}

// Hacer disponible globalmente
window.PushNotifications = PushNotifications;
console.log('✅ push-notifications.js cargado completamente');