const RATE = 16000
const MODEL = 'klang/pianissimo'

const startBtn = document.getElementById('start')
const stopBtn = document.getElementById('stop')
const chunkInput = document.getElementById('chunk')
const statusEl = document.getElementById('status')
const outEl = document.getElementById('out')
const logEl = document.getElementById('log')

let ws = null
let audio = null
let stream = null
let firstDeltaAt = null
let startedAt = 0

const log = (msg) => {
  const t = ((performance.now() - startedAt) / 1000).toFixed(2)
  logEl.textContent = `${t}s  ${msg}\n` + logEl.textContent
}

const setStatus = (text, kind = '') => {
  statusEl.textContent = text
  statusEl.className = kind
}

async function start() {
  startBtn.disabled = true
  outEl.textContent = ''
  logEl.textContent = ''
  firstDeltaAt = null
  startedAt = performance.now()

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (e) {
    setStatus('Microphone blocked: ' + e.message, 'err')
    startBtn.disabled = false
    return
  }

  setStatus('Connecting')
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`)

  ws.onopen = () => {
    const chunkSeconds = Number(chunkInput.value)
    const transcription = { model: MODEL, languages: ['sv'] }

    // chunk_seconds goes here, under transcription. Anywhere else and it is
    // dropped without an error, and text only arrives after the turn is
    // committed. session.updated below echoes what the server really applied.
    if (chunkSeconds > 0) transcription.chunk_seconds = chunkSeconds

    ws.send(JSON.stringify({
      type: 'session.update',
      session: {
        type: 'transcription',
        audio: { input: { format: { type: 'audio/pcm', rate: RATE }, transcription } },
      },
    }))
  }

  ws.onmessage = async (e) => {
    const ev = JSON.parse(e.data)

    if (ev.type === 'session.updated') {
      const applied = ev.session?.audio?.input?.transcription
      log(`session ready, chunk_seconds=${applied?.chunk_seconds ?? 'unset'}`)
      if (chunkInput.value === '0') {
        log(`server default ${applied?.chunk_seconds} s: no text until you have spoken that long`)
      }
      await startAudio()
      setStatus('Listening', 'live')
      stopBtn.disabled = false
    } else if (ev.type === 'conversation.item.input_audio_transcription.delta') {
      if (firstDeltaAt === null) {
        firstDeltaAt = performance.now()
        log(`first text after ${((firstDeltaAt - startedAt) / 1000).toFixed(2)} s`)
      }
      outEl.textContent += ev.delta
    } else if (ev.type === 'conversation.item.input_audio_transcription.completed') {
      log(`complete, billed ${ev.usage?.seconds ?? '?'} s`)
    } else if (ev.type === 'error') {
      log('error: ' + JSON.stringify(ev.error))
      setStatus('Error: ' + (ev.error?.message ?? 'unknown'), 'err')
    } else {
      log(ev.type)
    }
  }

  ws.onclose = () => {
    setStatus('Disconnected')
    teardown()
  }

  ws.onerror = () => setStatus('Connection failed. Is the relay running?', 'err')
}

async function startAudio() {
  audio = new AudioContext()
  await audio.audioWorklet.addModule('pcm-worklet.js')

  const source = audio.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(audio, 'pcm-worklet', {
    processorOptions: { targetRate: RATE },
  })

  node.port.onmessage = ({ data }) => {
    if (ws?.readyState !== WebSocket.OPEN) return
    const bytes = new Uint8Array(data)
    let bin = ''
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
    ws.send(JSON.stringify({ type: 'input_audio_buffer.append', audio: btoa(bin) }))
  }

  source.connect(node)
  // Keep the worklet pulling without routing the mic back to the speakers.
  node.connect(audio.destination)
  audio.suspend().then(() => audio.resume())
}

function stop() {
  stopBtn.disabled = true
  setStatus('Finishing')
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))
    setTimeout(() => ws.close(), 1500)
  } else {
    teardown()
  }
}

function teardown() {
  stream?.getTracks().forEach((t) => t.stop())
  audio?.close()
  stream = null
  audio = null
  ws = null
  startBtn.disabled = false
  stopBtn.disabled = true
}

startBtn.addEventListener('click', start)
stopBtn.addEventListener('click', stop)
