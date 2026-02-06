// ============================================
// push-simple.js - VERSIÓN CORREGIDA PARA PERMISOS
// ============================================

console.log('✅ push-simple.js CARGADO - ' + new Date().toLocaleTimeString());

// Función auxiliar para convertir clave
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

// Configurar el botón cuando la página cargue
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ DOM listo - push-simple.js');
    
    // Verificar estado ACTUAL de permisos
    console.log('🔔 Estado ACTUAL de permiso:', Notification.permission);
    
    const button = document.getElementById('pushButton');
    if (!button) {
        console.error('❌ No hay botón con id="pushButton"');
        return;
    }
    
    console.log('✅ Botón encontrado');
    
    // Actualizar texto según estado actual
    if (Notification.permission === 'granted') {
        button.textContent = '🔔 Notificaciones YA Activadas';
        button.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
        console.log('✅ Permiso ya concedido');
    } else if (Notification.permission === 'denied') {
        button.textContent = '🔔 Permiso Bloqueado 😞';
        button.style.background = 'linear-gradient(135deg, #7f8c8d, #95a5a6)';
        button.disabled = true;
        console.log('❌ Permiso bloqueado por usuario');
        button.title = 'Debes desbloquear en Configuración de Chrome';
        return;
    }
    
    // Agregar evento click
    button.addEventListener('click', async function() {
        console.log('🔘🔘🔘 USUARIO HIZO CLIC EN EL BOTÓN');
        
        // Deshabilitar botón inmediatamente
        const originalText = this.textContent;
        this.disabled = true;
        this.textContent = '⏳ Activando...';
        this.style.background = 'linear-gradient(135deg, #f39c12, #e67e22)';
        
        try {
            // PASO 1: Verificar soporte
            if (!('serviceWorker' in navigator)) {
                alert('❌ Tu navegador no soporta Service Workers');
                this.disabled = false;
                this.textContent = originalText;
                return;
            }
            
            if (!('PushManager' in window)) {
                alert('❌ Tu navegador no soporta Push Notifications');
                this.disabled = false;
                this.textContent = originalText;
                return;
            }
            
            // PASO 2: Registrar Service Worker
            console.log('📝 Registrando Service Worker...');
            let registration;
            try {
                registration = await navigator.serviceWorker.register('/service-worker.js');
                console.log('✅ Service Worker registrado');
            } catch (swError) {
                console.error('❌ Error Service Worker:', swError);
                alert('❌ Error: ' + swError.message);
                this.disabled = false;
                this.textContent = originalText;
                return;
            }
            
            // PASO 3: VERIFICAR PERMISO ACTUAL
            console.log('🔔 Verificando permiso actual...');
            
            let permission = Notification.permission;
            console.log('📊 Permiso actual:', permission);
            
            // Si ya está concedido, saltar a suscripción
            if (permission === 'granted') {
                console.log('✅ Permiso ya concedido, procediendo...');
            } 
            // Si está denegado, NO podemos hacer nada
            else if (permission === 'denied') {
                alert('❌ Has bloqueado las notificaciones. Para activarlas:\n\n1. Haz clic en 🔒 (candado) en la barra de URL\n2. Ve a "Configuración del sitio"\n3. Busca "Notificaciones"\n4. Cambia a "Permitir"');
                this.disabled = false;
                this.textContent = '🔔 Permiso Bloqueado 😞';
                this.style.background = 'linear-gradient(135deg, #7f8c8d, #95a5a6)';
                return;
            }
            // Si es "default" (nunca preguntó), pedir permiso
            else if (permission === 'default') {
                console.log('🔔 Pidiendo permiso...');
                try {
                    permission = await Notification.requestPermission();
                    console.log('✅ Nuevo permiso:', permission);
                    
                    if (permission !== 'granted') {
                        alert('❌ Debes permitir las notificaciones para recibir alertas de citas.');
                        this.disabled = false;
                        this.textContent = originalText;
                        return;
                    }
                } catch (permError) {
                    console.error('❌ Error pidiendo permiso:', permError);
                    this.disabled = false;
                    this.textContent = originalText;
                    return;
                }
            }
            
            // PASO 4: Crear suscripción (SOLO si permission === 'granted')
            console.log('🔐 Creando suscripción push...');
            
            const publicKey = 'BLUUZFhnk-K2WDcQTiLXOA8IMNF6zdWvu4YuNxswOuhnYmDZpPW6BRrIoSqRKeUw5EqDQZ6HaqHZUL5nywq8GnI';
            
            let subscription;
            try {
                // Primero verificar si ya estamos suscritos
                const existingSubscription = await registration.pushManager.getSubscription();
                
                if (existingSubscription) {
                    console.log('✅ Ya existe una suscripción');
                    subscription = existingSubscription;
                } else {
                    console.log('📝 Creando nueva suscripción...');
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(publicKey)
                    });
                    console.log('✅ Nueva suscripción creada');
                }
                
                console.log('📫 Endpoint:', subscription.endpoint.substring(0, 60) + '...');
                
            } catch (subError) {
                console.error('❌ Error suscribiendo:', subError);
                alert('❌ Error: ' + subError.message);
                this.disabled = false;
                this.textContent = originalText;
                return;
            }
            
            // PASO 5: Enviar al servidor
            console.log('📤 Enviando suscripción al servidor...');
            
            const profesionalId = document.body.dataset.profesionalId;
            if (!profesionalId) {
                alert('❌ Error: No se encontró ID del profesional');
                this.disabled = false;
                this.textContent = originalText;
                return;
            }
            
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
                
                console.log('📊 Estado:', response.status);
                
                if (!response.ok) {
                    throw new Error('Error del servidor: ' + response.status);
                }
                
                const result = await response.json();
                console.log('📦 Respuesta:', result);
                
                if (result.success) {
                    // ¡ÉXITO!
                    this.textContent = '🔔 Notificaciones Activadas ✅';
                    this.style.background = 'linear-gradient(135deg, #27ae60, #2ecc71)';
                    
                    alert('🎉 ¡NOTIFICACIONES PUSH ACTIVADAS!\n\nAhora recibirás notificaciones de nuevas citas.');
                    
                    console.log('🎉 ¡TODO COMPLETADO EXITOSAMENTE!');
                } else {
                    alert('❌ Error: ' + (result.error || 'No se pudo guardar'));
                    this.disabled = false;
                    this.textContent = originalText;
                }
                
            } catch (fetchError) {
                console.error('❌ Error enviando:', fetchError);
                alert('❌ Error de conexión');
                this.disabled = false;
                this.textContent = originalText;
            }
            
        } catch (error) {
            console.error('❌ Error general:', error);
            alert('❌ Error: ' + error.message);
            this.disabled = false;
            this.textContent = originalText;
        }
    });
    
    console.log('✅ Evento click configurado');
});