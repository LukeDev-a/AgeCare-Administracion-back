/* El servidor valida el acceso inicial; este control retira partidas ya abiertas. */
(() => {
  const unavailable = new URL('no-disponible.html', document.currentScript.src).href;
  let checking = false;
  async function check() {
    if (checking) return;
    checking = true;
    try {
      // Consulta pública: no enviar cookies ni credenciales desde el iframe.
      const response = await fetch(location.pathname, { method: 'HEAD', cache: 'no-store', credentials: 'omit' });
      if (!response.ok) stop();
    } catch { stop(); }
    finally { checking = false; }
  }
  function stop() {
    // Cambiar de documento detiene también timers, audio y listeners del juego.
    location.replace(unavailable);
  }
  setInterval(check, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void check(); });
  window.addEventListener('focus', () => void check());
})();
