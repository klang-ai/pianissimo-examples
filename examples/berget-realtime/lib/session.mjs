export const ENDPOINT = 'wss://api.berget.ai/v1/realtime?intent=transcription'
export const MODEL = 'klang/pianissimo'

// The session payload the endpoint expects.
//
// chunk_seconds belongs under audio.input.transcription. Put it anywhere else
// and it is dropped silently, with no error, and you get one transcript after
// commit instead of a stream. Read it back from session.updated to confirm.
export function sessionUpdate({ rate, chunkSeconds, languages = ['sv'], serverVad = false }) {
  const transcription = { model: MODEL, languages }
  if (chunkSeconds != null) transcription.chunk_seconds = chunkSeconds

  const input = {
    format: { type: 'audio/pcm', rate },
    transcription,
  }
  if (serverVad) input.turn_detection = { type: 'server_vad' }

  return {
    type: 'session.update',
    session: { type: 'transcription', audio: { input } },
  }
}

export function appendAudio(bytes) {
  return { type: 'input_audio_buffer.append', audio: bytes.toString('base64') }
}

export const commit = { type: 'input_audio_buffer.commit' }
