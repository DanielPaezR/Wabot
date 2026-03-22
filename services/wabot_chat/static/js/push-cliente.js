// push-cliente.js - Notificaciones push para clientes
class PushClienteNotifications {
    constructor() {
        this.publicKey = 'BAMDIUN0qYyQ43XsRnO-kYKCYDXyPyKNC_nxn7wrBfbhyyxSxJYYWRYB36waU_XAoKHiD3sacxstM2YufRX7CrU';
        this.swUrl = '/service-worker.js';
        this.telefono = null;
        this.negocioId = null;
        this.subscription = null;
    }
    
    async inicializar(telefono, negocioId) {
        this.telefono = telefono;
        this.negocioId = negocioId;
        
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.log('❌ Push no soportado');
            return false;
        }
        
        try {
            // Registrar Service Worker
            const registration = await navigator.serviceWorker.register(this.swUrl);
            console.log('✅ Service Worker registrado');
            
            // Verificar si ya tiene permiso
            if (Notification.permission === 'granted') {
                await this.subscribir(registration);
                return true;
            } else if (Notification.permission !== 'denied') {
                const permission = await Notification.requestPermission();
                if (permission === 'granted') {
                    await this.subscribir(registration);
                    return true;
                }
            }
            return false;
        } catch (error) {
            console.error('❌ Error inicializando push:', error);
            return false;
        }
    }
    
    async subscribir(registration) {
        try {
            // Verificar si ya está suscrito
            const existingSubscription = await registration.pushManager.getSubscription();
            if (existingSubscription) {
                console.log('📱 Ya está suscrito');
                this.subscription = existingSubscription;
                await this.enviarSuscripcionAlServidor();
                return true;
            }
            
            // Crear nueva suscripción
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(this.publicKey)
            });
            
            this.subscription = subscription;
            await this.enviarSuscripcionAlServidor();
            console.log('✅ Suscripción push creada');
            return true;
        } catch (error) {
            console.error('❌ Error en suscripción:', error);
            return false;
        }
    }
    
    async enviarSuscripcionAlServidor() {
        if (!this.subscription) return;
        
        try {
            const response = await fetch('/push/api/push/subscribe-cliente', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subscription: this.subscription,
                    telefono: this.telefono,
                    negocio_id: this.negocioId
                })
            });
            
            const data = await response.json();
            if (data.success) {
                console.log('✅ Suscripción guardada en el servidor');
            }
        } catch (error) {
            console.error('❌ Error guardando suscripción:', error);
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
    
    async testNotificacion() {
        try {
            const response = await fetch('/push/api/push/test-cliente', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    telefono: this.telefono,
                    negocio_id: this.negocioId
                })
            });
            
            const data = await response.json();
            if (data.success) {
                console.log('✅ Notificación de prueba enviada');
            } else {
                console.log('⚠️ No se pudo enviar notificación de prueba');
            }
        } catch (error) {
            console.error('❌ Error en test:', error);
        }
    }
}

// Exportar para uso global
window.PushClienteNotifications = PushClienteNotifications;