---
name: html5-canvas-artist
description: Dynamic graphics, interactive particle systems, Web Audio synthesized sound effects, and high-resolution image rendering and export using HTML5 Canvas.
---

# ✨ HTML5 Canvas Artist & Sound Synthesizer Skill

This skill guides the AI agent in creating smooth 60fps dynamic canvas animations, interactive visual feedback, Web Audio synthesizer effects, and high-DPI image exports.

## 🎯 Core Capabilities

1. **Synthesized Web Audio Effects (Zero MP3 Dependencies)**:
   - Use the native browser `AudioContext` to generate satisfying click sounds, bell rings, and wooden fish taps on demand without loading external audio files:
   ```javascript
   function playMuyuSound() {
     const ctx = new (window.AudioContext || window.webkitAudioContext)();
     const osc = ctx.createOscillator();
     const gain = ctx.createGain();
     osc.type = 'triangle';
     osc.frequency.setValueAtTime(440, ctx.currentTime);
     osc.frequency.exponentialRampToValueAtTime(80, ctx.currentTime + 0.15);
     gain.gain.setValueAtTime(0.8, ctx.currentTime);
     gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
     osc.connect(gain);
     gain.connect(ctx.destination);
     osc.start();
     osc.stop(ctx.currentTime + 0.15);
   }
   ```

2. **Dynamic Particle Bursts**:
   - Floating text badges (e.g. `功德 +1` or `Focus +1`) that float upward, fade out, and animate smoothly.
   - Canvas particle burst systems with gravity, alpha decay, and color gradients.

3. **High-Resolution Poster Export**:
   - Render HTML card elements to an off-screen `<canvas>` at 2x / 3x pixel ratio (`window.devicePixelRatio`) to generate razor-sharp PNG image files for download and social sharing via `canvas.toDataURL('image/png')`.
