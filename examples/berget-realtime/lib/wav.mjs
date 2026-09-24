import fs from 'node:fs'

// Minimal RIFF/WAVE reader. Returns the raw PCM bytes plus the format fields
// the realtime session needs. Only uncompressed PCM16 is supported, which is
// what the endpoint wants anyway.
export function readWav(path) {
  const buf = fs.readFileSync(path)

  if (buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error(`${path} is not a RIFF/WAVE file`)
  }

  let fmt = null
  let data = null
  let off = 12

  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4)
    const size = buf.readUInt32LE(off + 4)
    const body = buf.subarray(off + 8, off + 8 + size)

    if (id === 'fmt ') {
      fmt = {
        format: body.readUInt16LE(0),
        channels: body.readUInt16LE(2),
        rate: body.readUInt32LE(4),
        bits: body.readUInt16LE(14),
      }
    } else if (id === 'data') {
      data = body
    }

    off += 8 + size + (size % 2) // chunks are word aligned
  }

  if (!fmt || !data) throw new Error(`${path} is missing a fmt or data chunk`)
  if (fmt.format !== 1 || fmt.bits !== 16) {
    throw new Error(`${path} must be uncompressed PCM16, got format ${fmt.format} / ${fmt.bits} bit`)
  }
  if (fmt.channels !== 1) {
    throw new Error(`${path} must be mono, got ${fmt.channels} channels`)
  }

  return { pcm: data, rate: fmt.rate, seconds: data.length / 2 / fmt.rate }
}
