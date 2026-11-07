# -*- coding: utf-8 -*-
"""程序化配乐 v2：D 大调，112 BPM，明亮轻快。

设计要点
- 调性/速度：D 大调（明亮）、112 BPM（行进感但不急促）
- 织体：马林巴八分琶音为主体，钟琴高频点缀，柔和铺底只做和声胶水
- 律动：轻 kick（1、2.5 拍）+ 沙锤八分 + 高能量段才进拍手，整体"弹跳"不"轰"
- 结构：I–V–vi–IV 四小节循环，旋律 16 小节一乐句（后 8 小节留白给解说）
- 全长一次写完，不做采样循环，因此没有循环断点；首 2.5s 渐入、末 6s 收束
"""
import json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parent
SR = 48000
S = json.load(open(ROOT / 'data' / 'scene2.json', encoding='utf-8'))
DUR = S['total']
N = int(SR * DUR)
T = np.arange(N) / SR
rng = np.random.default_rng(20261021)

import config as C
BPM = C.BPM
BEAT = 60.0 / BPM
BAR = 4 * BEAT


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# ---------------- 和声：I–V–vi–IV (D–A–Bm–G) ----------------
# (低音, 和弦音, 高音旋律锚点)
PROG = [tuple(x) for x in C.KEY_PROG]

# 旋律：每小节 (拍位, midi, 时值拍)
MEL = [
    [(0.0, 78, 1.0), (1.0, 81, 1.0), (2.0, 78, 1.4), (3.5, 76, 0.5)],
    [(0.0, 76, 1.0), (1.0, 73, 1.0), (2.0, 76, 1.8)],
    [(0.0, 74, 1.0), (1.0, 78, 1.0), (2.0, 81, 1.4), (3.5, 78, 0.5)],
    [(0.0, 79, 1.0), (1.0, 76, 1.0), (2.0, 74, 1.8)],
]
# 第二乐句（变奏）：上移三度，收在属音
MEL2 = [
    [(0.0, 81, 1.0), (1.0, 78, 1.0), (2.0, 81, 1.4), (3.5, 83, 0.5)],
    [(0.0, 81, 1.0), (1.0, 76, 1.0), (2.0, 73, 1.8)],
    [(0.0, 78, 1.0), (1.0, 81, 1.0), (2.0, 86, 1.4), (3.5, 83, 0.5)],
    [(0.0, 83, 1.0), (1.0, 79, 1.0), (2.0, 74, 1.8)],
]
ARP_PAT = [
    [0, 1, 2, 1, 2, 1, 0, 2],
    [0, 2, 1, 2, 0, 1, 2, 1],
    [0, 1, 2, 0, 2, 1, 2, 1],
    [0, 2, 1, 0, 1, 2, 1, 2],
]


def place(buf, x, idx, gain=1.0, pan=0.0):
    """把单声道片段写入立体声缓冲，pan ∈ [-1, 1]。"""
    n_buf = buf.shape[1]
    if idx >= n_buf or idx + len(x) <= 0:
        return
    i0 = max(0, idx)
    off = i0 - idx
    n = min(len(x) - off, n_buf - i0)
    if n <= 0:
        return
    seg = x[off:off + n]
    th = (pan + 1) * math.pi / 4
    buf[0, i0:i0 + n] += seg * gain * math.cos(th) * 1.4142
    buf[1, i0:i0 + n] += seg * gain * math.sin(th) * 1.4142


def attack(x, sec=0.003):
    a = min(len(x), int(sec * SR))
    if a > 1:
        x[:a] *= np.linspace(0, 1, a) ** 0.7
    return x


# ---------------- 音色 ----------------
def marimba(f, dur=0.80, amp=0.11):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5.4)
         + 0.26 * np.sin(2 * np.pi * f * 4.02 * tt) * np.exp(-tt * 12)
         + 0.10 * np.sin(2 * np.pi * f * 9.1 * tt) * np.exp(-tt * 20))
    return (attack(x) * amp).astype(np.float32)


def bell(f, dur=2.4, amp=0.075):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * tt) * np.exp(-tt * 1.7)
         + 0.45 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt * 3.6)
         + 0.20 * np.sin(2 * np.pi * f * 5.40 * tt) * np.exp(-tt * 6.5))
    return (attack(x, 0.004) * amp).astype(np.float32)


def sparkle(f, dur=0.55, amp=0.030):
    """高频玻璃质感点缀，给琶音加"亮"。"""
    n = int(dur * SR)
    tt = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 3.01 * tt))
    x *= np.exp(-tt * 9.0)
    return (attack(x, 0.002) * amp).astype(np.float32)


def pad_voice(f, dur, amp=0.045):
    """三个微失谐正弦叠加，慢起慢收，只做和声胶水。"""
    n = int(dur * SR)
    tt = np.arange(n) / SR
    x = np.zeros(n, np.float32)
    for det, ph in ((0.0, 0.0), (0.0032, 1.1), (-0.0029, 2.4)):
        x += np.sin(2 * np.pi * f * (1 + det) * tt + ph).astype(np.float32) / 3
    x += 0.28 * np.sin(2 * np.pi * f * 2 * tt + 0.7).astype(np.float32)
    a = int(0.55 * SR)
    r = int(0.70 * SR)
    e = np.ones(n, np.float32)
    e[:min(a, n)] = np.linspace(0, 1, min(a, n)) ** 1.4
    e[n - min(r, n):] *= np.linspace(1, 0, min(r, n)) ** 1.2
    return (x * e * amp).astype(np.float32)


def bass_note(f, dur, amp=0.17):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * tt)
         + 0.30 * np.sin(2 * np.pi * f * 2 * tt)
         + 0.10 * np.sin(2 * np.pi * f * 3 * tt))
    e = np.exp(-tt * 1.5)
    a = int(0.012 * SR)
    e[:a] *= np.linspace(0, 1, a)
    r = int(0.10 * SR)
    e[n - r:] *= np.linspace(1, 0, r) ** 1.5
    return (x * e * amp).astype(np.float32)


def kick(amp=0.30):
    n = int(0.26 * SR)
    tt = np.arange(n) / SR
    f = 108 * np.exp(-tt * 30) + 46
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9.5)
    return (attack(x, 0.0015) * amp).astype(np.float32)


def shaker(amp=0.055, dur=0.05):
    n = int(dur * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = np.diff(x, prepend=0)
    x *= np.exp(-np.arange(n) / SR * 95)
    return (x * amp).astype(np.float32)


def clap(amp=0.085):
    n = int(0.16 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    k = np.ones(6, np.float32) / 6
    x = np.convolve(x, k, 'same')
    env = np.exp(-np.arange(n) / SR * 26)
    for d in (0, int(0.011 * SR), int(0.023 * SR)):
        if d < n:
            env[d:] += np.exp(-np.arange(n - d) / SR * 40) * 0.55
    return (x * env * amp).astype(np.float32)


def swell(dur=1.3, amp=0.030):
    """章节切换的空气感推子（替代原来的 whoosh，更轻）。"""
    n = int(dur * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    k = np.ones(140, np.float32) / 140
    x = np.convolve(x, k, 'same')
    b = np.linspace(0, 1, n)
    x *= (b ** 2.0) * ((1 - b) ** 0.5) * 3.2
    return (x * amp).astype(np.float32)


# ---------------- 分轨 ----------------
pad = np.zeros((2, N), np.float32)
bass = np.zeros((2, N), np.float32)
arp = np.zeros((2, N), np.float32)
mel = np.zeros((2, N), np.float32)
per = np.zeros((2, N), np.float32)
fx = np.zeros((2, N), np.float32)

nbars = int(math.ceil(DUR / BAR))

for b in range(nbars):
    t0 = b * BAR
    idx = int(t0 * SR)
    root, tones, _ = PROG[b % 4]
    ph = (b // 8) % 2                     # 乐句：0 = 主题, 1 = 变奏

    # --- 铺底：整小节长音，两小节换一次（省 CPU，听感更连贯）---
    if b % 2 == 0:
        for k, nt in enumerate(tones):
            x = pad_voice(midi(nt), BAR * 2 + 0.9, 0.052)
            place(pad, x, idx, 1.0 if k < 2 else 0.82,
                  pan=(-0.30 if k == 0 else (0.30 if k == 2 else 0.0)))

    # --- 贝斯：根音 1 拍 + 3 拍 + 3.5 拍过门 ---
    place(bass, bass_note(midi(root), BEAT * 1.55), idx, 1.0)
    place(bass, bass_note(midi(root), BEAT * 0.92), idx + int(2 * BEAT * SR), 0.88)
    place(bass, bass_note(midi(root + 12), BEAT * 0.42, 0.13),
          idx + int(3.5 * BEAT * SR), 0.72)

    # --- 马林巴琶音：八分音符，逐音左右微摆（用中音区本体，高频交给 sparkle）---
    seq = [tones[i] for i in ARP_PAT[b % 4]]
    for j in range(8):
        nt = seq[j]
        g = (1.0 if j % 4 == 0 else 0.78) * (0.92 if ph == 0 else 1.0)
        place(arp, marimba(midi(nt), 0.72, 0.096),
              idx + int(j * BEAT / 2 * SR), g, pan=(-0.22 if j % 2 else 0.22))
        if j % 2 == 0:                     # 高频玻璃点缀，隔一个音
            place(arp, sparkle(midi(nt + 12), 0.5, 0.030),
                  idx + int(j * BEAT / 2 * SR), 0.9, pan=0.36)

    # --- 旋律：8 小节一乐句，后 8 小节留白 ---
    if (b % 16) < 8:
        for (bt, nt, dur_b) in (MEL if ph == 0 else MEL2)[b % 4]:
            place(mel, marimba(midi(nt), max(0.55, dur_b * BEAT * 1.5), 0.105),
                  idx + int(bt * BEAT * SR), 1.0, pan=-0.06)
            place(mel, marimba(midi(nt + 12), 0.7, 0.030),
                  idx + int(bt * BEAT * SR), 0.8, pan=0.10)

    # --- 打击：轻 kick + 八分沙锤 ---
    place(per, kick(0.26), idx, 1.0)
    place(per, kick(0.17), idx + int(2.5 * BEAT * SR), 0.95)
    for j in range(8):
        acc = 1.0 if j % 2 else 0.62
        place(per, shaker(0.052, 0.05), idx + int(j * BEAT / 2 * SR), acc, pan=0.30)

# ---------------- 章节事件：钟琴 + 轻推子 ----------------
for c in S['chapters']:
    if not c['date']:
        continue
    idx = int((c['tA'] + 0.02) * SR)
    _, tones, anchor = PROG[int(c['tA'] / BAR) % 4]
    place(fx, bell(midi(anchor + 12), 2.6, 0.070), idx, 1.0, pan=-0.18)
    place(fx, bell(midi(tones[-1] + 24), 2.2, 0.042), idx + int(0.10 * BEAT * SR), 0.9, pan=0.24)
    place(fx, swell(1.3, 0.026), idx - int(0.45 * SR), 1.0)

# ---------------- 能量曲线：随线网规模逐层加入 ----------------
def ctrl(points):
    xs = np.array([p[0] for p in points], np.float32)
    ys = np.array([p[1] for p in points], np.float32)
    return np.interp(T, xs, ys).astype(np.float32)


ch_t = [c['nA'] for c in S['chapters']]
n_open = [c['nLines'] for c in S['chapters']]
open_ctrl = [(0, 0)] + list(zip(ch_t, n_open)) + [(DUR, 17)]
open_g = ctrl(open_ctrl) / 17.0


def bump(x, a=0.30, b=6.0):
    return np.clip((x - a) / (b - a), 0, 1)


pad_g = 0.42 + 0.58 * bump(open_g)
arp_g = 0.66 + 0.34 * bump(open_g, 0.05, 3.0)
mel_g = 0.34 + 0.66 * bump(open_g, 0.12, 4.5)
bass_g = 0.34 + 0.66 * bump(open_g, 0.10, 3.5)
per_g = 0.30 + 0.70 * bump(open_g, 0.10, 4.0)
clap_g = bump(open_g, 0.55, 9.0) * 0.9
fx_g = 0.65 + 0.35 * open_g

# 片尾收束（末 6 秒逐层退出，避免硬切）
end0 = S['chapters'][-1]['tE'] - 5.0
tail = np.clip((T - end0) / 6.2, 0, 1)
fade_in = np.clip(T / 2.5, 0, 1) ** 1.25
hard_end = np.clip((DUR - T) / 1.2, 0, 1) ** 1.0

for name, g in (('pad', pad_g), ('arp', arp_g), ('mel', mel_g),
                ('bass', bass_g), ('per', per_g), ('fx', fx_g)):
    g *= (1 - 0.90 * tail ** 1.3)
    g *= fade_in * hard_end

# 拍手单独一条（只在高能量段）
clap_buf = np.zeros((2, N), np.float32)
for b in range(nbars):
    idx = int(b * BAR * SR)
    if idx >= N:
        break
    place(clap_buf, clap(0.080), idx + int(1 * BEAT * SR), 1.0, pan=-0.12)
    place(clap_buf, clap(0.070), idx + int(3 * BEAT * SR), 1.0, pan=0.14)

mix = (pad * pad_g + bass * bass_g + arp * arp_g
       + mel * mel_g + per * per_g + fx * fx_g).astype(np.float32)
mix += clap_buf * (clap_g * fade_in * hard_end * (1 - 0.9 * tail ** 1.3))


def delay(buf, dbeat=0.375, fb=0.26, wet=0.30):
    """琶音乒乓延迟：给亮色音符加空间，不糊。"""
    d = int(dbeat * BEAT * SR)
    w = np.zeros_like(buf)
    for k in range(1, 5):
        g = fb ** (k - 1)
        if d * k >= N:
            break
        w[0, d * k:] += buf[0, :N - d * k] * g
        w[1, d * k:] += buf[1, :N - d * k] * g
    w = w[::-1]
    return buf + w * wet


arp_o = arp * arp_g * fade_in * hard_end * (1 - 0.9 * tail ** 1.3)
mix = mix + delay(arp_o) * 0.30

# 扩散混响（多抽头，很短，保持干净）
for d, g in ((0.029, 0.17), (0.043, 0.145), (0.067, 0.115), (0.097, 0.088),
             (0.131, 0.068), (0.181, 0.052), (0.243, 0.038), (0.317, 0.026)):
    dd = int(d * SR)
    mix[0, dd:] += mix[0, :-dd] * g * 0.97
    mix[1, dd:] += mix[1, :-dd] * g

# ---------------- 母带 ----------------
peak = float(np.max(np.abs(mix)))
mix = mix / max(peak, 1e-6) * 0.70
mix = np.tanh(mix * 1.06) * 0.93
# 与旧版（-15.3 LUFS）对齐：整体再抬，真峰值仍留 ~1 dB 余量
mix = mix * 1.50

# 高频轻微提亮（一阶差分混入），让"明亮"落在音色上而不是音量上
hi = np.diff(mix, axis=1, prepend=0)
mix = mix * 0.975 + hi * 0.05
mix = np.clip(mix, -1, 1)

print('peak %.3f  rms %.4f  dur %.2fs  bars %d  bpm %g'
      % (float(np.max(np.abs(mix))), float(np.sqrt((mix ** 2).mean())), DUR, nbars, BPM))
for nm, x in (('pad', pad * pad_g), ('bass', bass * bass_g), ('arp', arp * arp_g),
              ('mel', mel * mel_g), ('per', per * per_g), ('fx', fx * fx_g)):
    print('  %-5s rms %.4f' % (nm, float(np.sqrt((x ** 2).mean()))))

import wave
y = (np.clip(mix.T, -1, 1) * 32767).astype(np.int16)
with wave.open(str(ROOT / 'audio' / 'bgm.wav'), 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(y.tobytes())
np.save(ROOT / 'audio' / 'bgm.npy', mix)
print('saved audio/bgm.wav + bgm.npy')
