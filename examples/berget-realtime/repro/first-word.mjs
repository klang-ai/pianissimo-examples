#!/usr/bin/env node
// Minimal reproduction: the first word is lost when the stream is segmented.
//
// One audio file, two sessions. The ONLY difference between them is
// chunk_seconds. Everything else, the audio, the pacing, the rate, the model,
// is identical.
//
//   BERGET_API_KEY=sk_ber_... node examples/berget-realtime/repro/first-word.mjs examples/berget-realtime/repro/counting-sv.wav
//
// Expected: run A keeps the opening word, run B drops it.

import WebSocket from 'ws'
import { readWav } from '../lib/wav.mjs'
import { ENDPOINT, MODEL } from '../lib/session.mjs'

const file = process.argv[2] ?? new URL('counting-sv.wav', import.meta.url).pathname
const key = process.env.BERGET_API_KEY
if (!key) {
  console.error('BERGET_API_KEY is not set')
  process.exit(1)
}

const { pcm, rate, seconds } = readWav(file)

function run(label, chunkSeconds) {
  return new Promise((resolve) => {
    const ws = new WebSocket(ENDPOINT, { headers: { Authorization: `Bearer ${key}` } })
    const transcription = { model: MODEL, languages: ['sv'] }
    if (chunkSeconds != null) transcription.chunk_seconds = chunkSeconds

    let text = ''
    let applied = null

    ws.on('open', () => ws.send(JSON.stringify({
      type: 'session.update',
      session: {
        type: 'transcription',
        audio: { input: { format: { type: 'audio/pcm', rate }, transcription } },
      },
    })))

    ws.on('message', (raw) => {
      const ev = JSON.parse(raw.toString())
      if (ev.type === 'session.updated') {
        applied = ev.session?.audio?.input?.transcription?.chunk_seconds
        stream(ws)
      } else if (ev.type === 'conversation.item.input_audio_transcription.delta') {
        text += ev.delta
      } else if (ev.type === 'conversation.item.input_audio_transcription.completed') {
        setTimeout(() => ws.close(), 300)
      } else if (ev.type === 'error') {
        console.error(label, 'error:', JSON.stringify(ev.error))
        ws.close()
      }
    })

    ws.on('close', () => resolve({ label, requested: chunkSeconds, applied, text: text.trim() }))
  })
}

// 100 ms frames at realtime pace, identical in both runs.
function stream(ws) {
  const frame = Math.round(rate / 10) * 2
  let i = 0
  const timer = setInterval(() => {
    if (i >= pcm.length) {
      clearInterval(timer)
      ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))
      return
    }
    ws.send(JSON.stringify({
      type: 'input_audio_buffer.append',
      audio: pcm.subarray(i, i + frame).toString('base64'),
    }))
    i += frame
  }, 100)
}

console.log(`audio: ${file}`)
console.log(`       ${seconds.toFixed(1)} s, PCM16 mono @ ${rate} Hz`)
console.log(`       the file says "Ett, Stockholm är Sveriges huvudstad. Två, ..."\n`)

// Sequential, so the two runs never compete for the same session capacity.
const a = await run('A', null)
const b = await run('B', 3)

for (const r of [a, b]) {
  const kept = /^\s*(ett|1[.,])/i.test(r.text)
  console.log(`--- run ${r.label}: chunk_seconds ${r.requested ?? 'unset'} (server applied ${r.applied})`)
  console.log(`    opening word: ${kept ? 'KEPT' : 'LOST'}`)
  console.log(`    ${r.text.slice(0, 90)}\n`)
}

const verdict = /^\s*(ett|1[.,])/i.test(a.text) && !/^\s*(ett|1[.,])/i.test(b.text)
console.log(verdict
  ? 'Reproduced: same audio, same pacing, only chunk_seconds differs.'
  : 'Not reproduced in this run.')
