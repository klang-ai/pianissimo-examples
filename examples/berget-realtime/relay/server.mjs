#!/usr/bin/env node
// Relay for the browser demo.
//
// Berget authenticates the realtime endpoint with an Authorization header, and
// browsers cannot set headers on a WebSocket. Query string and subprotocol auth
// both return 401. So a browser cannot reach the endpoint directly, and this
// relay holds the key instead.
//
// It forwards frames verbatim in both directions: the browser code is the same
// code you would write against Berget, minus the credential.
//
//   BERGET_API_KEY=... node examples/berget-realtime/relay/server.mjs
//   open http://localhost:8787

import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { WebSocketServer, WebSocket } from 'ws'
import { ENDPOINT } from '../lib/session.mjs'

const key = process.env.BERGET_API_KEY
if (!key) {
  console.error('BERGET_API_KEY is not set.')
  process.exit(1)
}

const PORT = Number(process.env.PORT || 8787)
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'browser')
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }

const server = http.createServer((req, res) => {
  const rel = req.url === '/' ? 'index.html' : decodeURIComponent(req.url.slice(1))
  const file = path.join(root, rel)

  if (!file.startsWith(root)) {
    res.writeHead(403).end('forbidden')
    return
  }

  fs.readFile(file, (err, body) => {
    if (err) {
      res.writeHead(404).end('not found')
      return
    }
    res.writeHead(200, { 'content-type': types[path.extname(file)] ?? 'application/octet-stream' })
    res.end(body)
  })
})

new WebSocketServer({ server }).on('connection', (client) => {
  const upstream = new WebSocket(ENDPOINT, { headers: { Authorization: `Bearer ${key}` } })
  const queued = []

  upstream.on('open', () => {
    for (const m of queued.splice(0)) upstream.send(m)
  })

  // Forward as text. ws sends a Buffer as a binary frame, and the endpoint
  // expects JSON text frames, so it never answers.
  client.on('message', (m) => {
    const text = m.toString()
    if (upstream.readyState === WebSocket.OPEN) upstream.send(text)
    else queued.push(text)
  })

  upstream.on('message', (m) => {
    if (client.readyState === WebSocket.OPEN) client.send(m.toString())
  })

  upstream.on('close', (code, reason) => client.close(code === 1005 ? 1000 : code, reason))
  client.on('close', () => upstream.close())

  upstream.on('error', (e) => {
    console.error('upstream error:', e.message)
    if (client.readyState === WebSocket.OPEN) {
      client.send(JSON.stringify({ type: 'error', error: { message: e.message, code: 'relay_upstream_error' } }))
    }
    client.close()
  })
  client.on('error', () => upstream.close())
})

server.listen(PORT, () => console.log(`relay on http://localhost:${PORT}`))
