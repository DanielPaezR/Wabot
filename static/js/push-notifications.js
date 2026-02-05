// static/js/push-notifications.js - VERSIÓN CORREGIDA
class PushNotifications {
    constructor() {
        this.publicKey = 'BLUUZFhnk-K2WDcQTiLXOA8IMNF6zdWvu4YuNxswOuhnYmDZpPW6BRrIoSqRKeUw5EqDQZ6HaqHZUL5nywq8GnI'; // De Railway env
        this.profesionalId = null;
        this.isInitialized = false;
    }
    
    async inicializar(profesionalId) {
        if (this.isInitialized) {
            console.log('⚠️ Push ya está inicializado');
            return true;
        }
        
        this.profesionalId = profesionalId;
        this.isInitialized = true;
        
        console.log('🚀 Inicializando push notifications para profesional:', profesionalId);
        
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.warn('⚠️ Notificaciones push no soportadas');
            return false;
        }
        
        try {
            // Registrar service worker - IMPORTANTE: usar la ruta correcta
            const registration = await navigator.serviceWorker.register('/service-worker.js');
            console.log('✅ Service Worker registrado en:', registration.scope);
            
            // Solicitar permiso
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                console.warn('❌ Permiso denegado para notificaciones');
                return false;
            }
            
            console.log('✅ Permiso concedido para notificaciones');
            
            // Suscribirse
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(this.publicKey)
            });
            
            console.log('✅ Suscrito a push notifications');
            console.log('🔗 Endpoint:', subscription.endpoint.substring(0, 60) + '...');
            
            // Enviar suscripción al servidor
            await this.enviarSuscripcion(subscription);
            
            console.log('🎉 Push notifications inicializadas correctamente');
            return true;
            
        } catch (error) {
            console.error('❌ Error inicializando push:', error);
            this.isInitialized = false;
            return false;
        }
    }
    
    async enviarSuscripcion(subscription) {
        try {
            const response = await fetch('/push/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription,
                    profesional_id: this.profesionalId
                })
            });
            
            const data = await response.json();
            if (data.success) {
                console.log('✅ Suscripción guardada en servidor');
            } else {
                console.error('❌ Error guardando suscripción:', data.error);
            }
            return data;
        } catch (error) {
            console.error('❌ Error enviando suscripción:', error);
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

// Inicialización automática cuando el DOM está listo
document.addEventListener('DOMContentLoaded', function() {
    console.log('📱 DOM cargado, verificando push notifications...');
    
    // Buscar el ID del profesional en múltiples lugares
    let profesionalId = null;
    
    // 1. Del atributo data del body (MEJOR PRÁCTICA)
    if (document.body.dataset.profesionalId) {
        profesionalId = document.body.dataset.profesionalId;
    }
    // 2. De la sesión (si está disponible en JavaScript)
    else if (window.profesionalData && window.profesionalData.id) {
        profesionalId = window.profesionalData.id;
    }
    // 3. De un elemento oculto en el DOM
    else {
        const hiddenInput = document.getElementById('profesional_id');
        if (hiddenInput && hiddenInput.value) {
            profesionalId = hiddenInput.value;
        }
    }
    
    // Si encontramos un ID válido, inicializar
    if (profesionalId && profesionalId > 0) {
        console.log('👨‍💼 Profesional ID encontrado:', profesionalId);
        
        const pushManager = new PushNotifications();
        pushManager.inicializar(profesionalId)
            .then(success => {
                // Actualizar botón si existe
                const button = document.getElementById('pushButton');
                if (button && success) {
                    button.textContent = '🔔 Notificaciones Activadas';
                    button.disabled = true;
                    button.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
                }
            })
            .catch(error => {
                console.error('Error en inicialización push:', error);
            });
    } else {
        console.warn('⚠️ No se pudo determinar el ID del profesional');
        console.log('ℹ️ Agrega data-profesional-id al body tag: <body data-profesional-id="{{ profesional.id }}">');
    }
});

// Hacer disponible globalmente para uso manual
window.PushNotifications = PushNotifications;