// Downsamples the microphone to the target rate and emits PCM16 frames.
//
// The mic runs at whatever the audio hardware uses, usually 44100 or 48000 Hz.
// The session format is fixed after the first append, so the rate has to be
// decided up front and every frame has to match it.
class PcmWorklet extends AudioWorkletProcessor {
  constructor(options) {
    super()
    this.targetRate = options.processorOptions.targetRate
    this.ratio = sampleRate / this.targetRate
    this.offset = 0
    this.out = []
  }

  process(inputs) {
    const channel = inputs[0]?.[0]
    if (!channel) return true

    // Linear interpolation is enough for speech at these rates.
    while (this.offset < channel.length) {
      const i = Math.floor(this.offset)
      const frac = this.offset - i
      const a = channel[i]
      const b = i + 1 < channel.length ? channel[i + 1] : a
      const sample = a + (b - a) * frac
      this.out.push(Math.max(-1, Math.min(1, sample)))
      this.offset += this.ratio
    }
    this.offset -= channel.length

    // Emit in 100 ms frames.
    const frame = this.targetRate / 10
    while (this.out.length >= frame) {
      const slice = this.out.splice(0, frame)
      const pcm = new Int16Array(frame)
      for (let i = 0; i < frame; i++) {
        pcm[i] = slice[i] < 0 ? slice[i] * 0x8000 : slice[i] * 0x7fff
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer])
    }

    return true
  }
}

registerProcessor('pcm-worklet', PcmWorklet)
