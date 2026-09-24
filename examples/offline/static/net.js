// The network badge. Asks the local server whether this machine can reach the
// internet, because navigator.onLine only knows if there is a network
// interface, not whether anything is on the other end of it.
export function watchNetwork(el, onStatus) {
  async function check() {
    try {
      const s = await (await fetch('/api/status', { cache: 'no-store' })).json()
      el.className = 'net ' + (s.online ? 'on' : 'off')
      el.textContent = s.online
        ? 'Internet on. Speech is processed on this computer'
        : 'No internet. Still works'
      onStatus?.(s)
    } catch {
      el.className = 'net'
      el.textContent = 'Local server not running'
    }
  }
  check()
  setInterval(check, 3000)
  addEventListener('online', check)
  addEventListener('offline', check)
}
