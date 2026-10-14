// AudioWorklet: mic (any device rate) -> 16 kHz mono Int16 PCM in 20 ms chunks (640 bytes).
// Boxcar-decimating resampler, no allocations in process(); good enough for speech.
// Verified in the stack probes (device 44.1/48 kHz -> 16 kHz). Plain JS on purpose: an
// AudioWorklet module is loaded by URL, so it is served as-is from /public.
class PcmCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.target = options.processorOptions?.targetRate ?? 16000;
    this.ratio = sampleRate / this.target; // `sampleRate` = AudioContext rate (global in worklet scope)
    this.chunkSamples = Math.round(this.target * 0.02); // 20 ms
    this.out = new Int16Array(this.chunkSamples);
    this.outIdx = 0;
    this.acc = 0;
    this.n = 0;
    this.phase = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.acc += ch[i];
      this.n++;
      this.phase += 1;
      if (this.phase >= this.ratio) {
        const s = Math.max(-1, Math.min(1, this.acc / this.n));
        this.out[this.outIdx++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        this.phase -= this.ratio;
        this.acc = 0;
        this.n = 0;
        if (this.outIdx === this.chunkSamples) {
          this.port.postMessage(this.out.buffer, [this.out.buffer]); // transfer, then reallocate
          this.out = new Int16Array(this.chunkSamples);
          this.outIdx = 0;
        }
      }
    }
    return true; // keep alive
  }
}
registerProcessor('pcm-capture', PcmCapture);
