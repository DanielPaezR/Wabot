// static/js/push-notifications.js
class PushNotifications {
    constructor() {
        this.publicKey = 'BLUUZFhnk-K2WDcQTiLXOA8IMNF6zdWvu4YuNxswOuhnYmDZpPW6BRrIoSqRKeUw5EqDQZ6HaqHZUL5nywq8GnI'; // De Railway env
        this.profesionalId = null;
    }
    
    async inicializar(profesionalId) {
        this.profesionalId = profesionalId;
        
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.warn('⚠️ Notificaciones push no soportadas');
            return false;
        }
        
        try {
            // Registrar service worker
            const registration = await navigator.serviceWorker.register('/sw.js');
            console.log('✅ Service Worker registrado');
            
            // Solicitar permiso
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                console.warn('Permiso denegado para notificaciones');
                return false;
            }
            
            // Suscribirse
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(this.publicKey)
            });
            
            // Enviar suscripción al servidor
            await this.enviarSuscripcion(subscription);
            
            console.log('✅ Suscrito a notificaciones push');
            return true;
            
        } catch (error) {
            console.error('❌ Error inicializando push:', error);
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
            }
            return data;
        } catch (error) {
            console.error('❌ Error enviando suscripción:', error);
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

// Usar en el panel profesional
document.addEventListener('DOMContentLoaded', function() {
    // Obtener profesional_id del DOM o de la sesión
    const profesionalId = document.body.dataset.profesionalId || 
                         window.location.pathname.match(/profesional\/(\d+)/)?.[1];
    
    if (profesionalId) {
        const pushManager = new PushNotifications();
        pushManager.inicializar(profesionalId);
    }
});