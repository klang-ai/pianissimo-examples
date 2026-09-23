#!/usr/bin/env node
// Stream a WAV file to Klang Pianissimo on Berget AI and print text as it arrives.
//
//   node cli/transcribe-file.mjs audio.wav
//   node cli/transcribe-file.mjs audio.wav --chunk-seconds 2
//   node cli/transcribe-file.mjs audio.wav --server-default  (leave chunk_seconds unset)
//   node cli/transcribe-file.mjs audio.wav --fast          (send faster than realtime)

import WebSocket from 'ws'
import { readWav } from '../lib/wav.mjs'
import { ENDPOINT, sessionUpdate, appendAudio, commit } from '../lib/session.mjs'

const args = process.argv.slice(2)
const file = args.find((a) => !a.startsWith('-'))
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`)
  return i === -1 ? fallback : args[i + 1]
}

if (!file) {
  console.error('usage: node cli/transcribe-file.mjs <file.wav> [--chunk-seconds N] [--server-default] [--fast]')
  process.exit(1)
}

const key = process.env.BERGET_API_KEY
if (!key) {
  console.error('BERGET_API_KEY is not set. Copy .env.example and export it, or prefix the command.')
  process.exit(1)
}

const chunkSeconds = args.includes('--server-default') ? null : Number(flag('chunk-seconds', 1))
const pace = args.includes('--fast') ? 20 : 100 // ms between 100 ms audio frames

const { pcm, rate, seconds } = readWav(file)
console.error(`${file}: ${seconds.toFixed(1)} s, PCM16 mono @ ${rate} Hz`)
console.error(chunkSeconds == null
  ? 'chunk_seconds unset: the server default is 28 s, so anything shorter returns one transcript at the end'
  : `chunk_seconds=${chunkSeconds}: expect partial text while the audio streams`)

const started = Date.now()
const at = () => ((Date.now() - started) / 1000).toFixed(2).padStart(6)

const ws = new WebSocket(ENDPOINT, { headers: { Authorization: `Bearer ${key}` } })

let final = ''
let firstDelta = null

ws.on('open', () => {
  ws.send(JSON.stringify(sessionUpdate({ rate, chunkSeconds })))
})

ws.on('message', (raw) => {
  const ev = JSON.parse(raw.toString())

  switch (ev.type) {
    case 'session.updated': {
      // Confirm what the server actually accepted before sending audio.
      const applied = ev.session?.audio?.input?.transcription
      console.error(`${at()}s session ready, model=${applied?.model} chunk_seconds=${applied?.chunk_seconds ?? 'unset'}`)
      stream()
      break
    }

    case 'conversation.item.input_audio_transcription.delta':
      if (firstDelta === null) firstDelta = Date.now()
      process.stdout.write(ev.delta)
      break

    case 'conversation.item.input_audio_transcription.completed':
      final = ev.transcript ?? ''
      console.error(`\n${at()}s complete, billed ${ev.usage?.seconds ?? '?'} s of audio`)
      setTimeout(() => ws.close(), 250)
      break

    case 'conversation.item.input_audio_transcription.failed':
    case 'error':
      console.error(`\n${at()}s error:`, JSON.stringify(ev.error ?? ev))
      process.exitCode = 1
      ws.close()
      break
  }
})

function stream() {
  const frame = Math.round(rate / 10) * 2 // 100 ms of PCM16
  let i = 0
  const timer = setInterval(() => {
    if (i >= pcm.length) {
      clearInterval(timer)
      ws.send(JSON.stringify(commit))
      return
    }
    ws.send(JSON.stringify(appendAudio(pcm.subarray(i, i + frame))))
    i += frame
  }, pace)
}

ws.on('error', (e) => {
  console.error('websocket error:', e.message)
  process.exitCode = 1
})

ws.on('close', (code) => {
  // 1012 and 1013 mean the node is draining for a deploy. Reconnect and start
  // a new session; sessions are not resumable.
  if (code === 1012 || code === 1013) console.error('server draining, retry the request')
  if (firstDelta) console.error(`first text after ${((firstDelta - started) / 1000).toFixed(2)} s`)
  if (final) console.error(`\n--- final transcript (${final.length} chars) ---\n${final}`)
})
