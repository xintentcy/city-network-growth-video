# -*- coding: utf-8 -*-
"""混音：解说为主，配乐自动避让（ducking），输出成片音轨。"""
import json, subprocess
from pathlib import Path
import numpy as np
import config as C

ROOT = Path(__file__).parent
SR = 48000
S = json.load(open(ROOT / 'data' / 'scene2.json', encoding='utf-8'))
DUR = S['total']
N = int(SR * DUR)

def read_wav(p):
    import wave
    with wave.open(str(p), 'rb') as w:
        n = w.getnframes(); ch = w.getnchannels()
        a = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768.0
    if ch > 1: a = a.reshape(-1, ch).mean(1)
    return a

def place(buf, x, idx):
    i0 = max(0, idx); off = i0 - idx
    n = min(len(x) - off, len(buf) - i0)
    if n > 0:
        buf[i0:i0 + n] += x[off:off + n]

nar = np.zeros(N, np.float32)
for c in S['chapters']:
    p = ROOT / 'audio' / f"{c['id']}.wav"
    if not p.exists(): continue
    a = read_wav(p)                           # 已按 loudnorm 统一到 -17 LUFS
    f = int(0.018 * SR)
    a[:f] *= np.linspace(0, 1, f); a[-f:] *= np.linspace(1, 0, f)
    place(nar, a, int(c['nA'] * SR))

# ---------- 避让包络 ----------
env = np.abs(nar)
k = int(0.02 * SR)
env = np.convolve(env, np.ones(k, np.float32) / k, 'same')
k2 = int(0.12 * SR)
env = np.convolve(env, np.ones(k2, np.float32) / k2, 'same')
env = env / (env.max() or 1)
duck = 1.0 - 0.45 * np.clip(env * 2.6, 0, 1)

bgm = np.load(ROOT / 'audio' / 'bgm.npy')
assert bgm.shape[1] >= N
# 0.20：新配乐（D 大调 112BPM，明亮律动）在同响度下更"抢"，比旧版再低约 1 dB
bgm = bgm[:, :N] * C.BGM_GAIN * duck

mix = bgm.copy()
mix[0] += nar; mix[1] += nar

# 母带：轻微压缩 + 限幅
mix = np.tanh(mix * 1.15) / 1.15
peak = float(np.abs(mix).max())
mix = mix / peak * 0.94
mix = np.tanh(mix * 1.02) * 0.955
mix = mix / max(float(np.abs(mix).max()), 1e-6) * 0.92

import wave
y = (np.clip(mix.T, -1, 1) * 32767).astype(np.int16)
with wave.open(str(ROOT / 'out' / 'mix.wav'), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(y.tobytes())

print('mix ok  peak %.3f  nar_rms %.4f  bgm_rms %.4f' %
      (peak, float(np.sqrt((nar ** 2).mean())), float(np.sqrt((bgm ** 2).mean()))))
