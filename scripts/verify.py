# -*- coding: utf-8 -*-
"""交付前验收：时长/帧数、音频峰值与响度、接缝帧差、首尾淡入淡出。

用法:
  python verify.py
  python verify.py out/成都地铁十五年-解说版.mp4

任何一项 ❌ 都不要交付——先修，再验。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import config as C

ROOT = Path(__file__).parent
FINAL = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / 'out' / 'final.mp4')
SILENT = ROOT / 'out' / 'video_noaudio.mp4'
SEG = ROOT / 'out' / 'segs'
TMP = ROOT / 'out' / '_verify'
TMP.mkdir(parents=True, exist_ok=True)


def probe(p):
    r = subprocess.run([C.FFPROBE, '-v', 'error', '-show_entries',
                        'format=duration,size', '-show_entries',
                        'stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames',
                        '-of', 'json', str(p)], capture_output=True, text=True)
    return json.loads(r.stdout)


def grab(p, t):
    out = TMP / ('g_%.3f.jpg' % t)
    subprocess.run([C.FFMPEG, '-y', '-v', 'error', '-ss', '%.3f' % t, '-i', str(p),
                    '-frames:v', '1', '-q:v', '3', str(out)], check=True)
    return Image.open(out).convert('L')


def dif(a, b):
    x = np.asarray(a, np.float32)
    y = np.asarray(b, np.float32)
    return float(np.abs(x - y).mean())


def main():
    ok = True

    def chk(name, cond, detail=''):
        nonlocal ok
        ok = ok and bool(cond)
        print('%s %-26s %s' % ('✅' if cond else '❌', name, detail))

    if not FINAL.exists():
        raise SystemExit('找不到成片: %s' % FINAL)

    info = probe(FINAL)
    vs = [s for s in info['streams'] if s['codec_type'] == 'video'][0]
    aus = [s for s in info['streams'] if s['codec_type'] == 'audio']
    dur = float(info['format']['duration'])
    print('— 容器 —')
    chk('分辨率', (vs['width'], vs['height']) == (C.W, C.H),
        '%dx%d' % (vs['width'], vs['height']))
    chk('帧率', vs['r_frame_rate'] in ('30/1', '30000/1001'), vs['r_frame_rate'])
    chk('音轨存在', bool(aus), aus[0]['codec_name'] if aus else '无')
    exp = None
    if SILENT.exists():
        si = probe(SILENT)
        frames = int([s for s in si['streams'] if s['codec_type'] == 'video'][0]['nb_frames'])
        exp = frames / 30.0
        chk('帧数', abs(dur - exp) < 0.5, '成片 %.2fs / 无音轨 %.2fs（%d 帧）'
            % (dur, exp, frames))

    # ---------- 音频 ----------
    print('— 音频 —')
    r = subprocess.run([C.FFMPEG, '-v', 'error', '-i', str(FINAL), '-map', '0:a:0',
                        '-ac', '2', '-ar', '48000', '-f', 'f32le', '-'],
                       capture_output=True)
    a = np.frombuffer(r.stdout[:len(r.stdout) // 4 * 4], np.float32)
    m = a.reshape(-1, 2).mean(1)
    chk('无削波', float(np.abs(a).max()) <= 1.0,
        '峰值 %.3f · >1.0 样点 %d' % (float(np.abs(a).max()), int((np.abs(a) > 1.0).sum())))
    chk('音画等长', abs(len(m) / 48000 - dur) < 0.6,
        '音频 %.2fs / 视频 %.2fs' % (len(m) / 48000, dur))

    r = subprocess.run([C.FFMPEG, '-hide_banner', '-nostats', '-i', str(FINAL),
                        '-af', 'loudnorm=print_format=summary', '-f', 'null', '-'],
                       capture_output=True, text=True, errors='ignore')
    def g(k):
        mm = re.search(k + r':\s*([-\d.]+)', r.stderr)
        return float(mm.group(1)) if mm else float('nan')
    I, TP, LRA = g('Input Integrated'), g('Input True Peak'), g('Input LRA')
    chk('整体响度', -16 <= I <= -11, '%.1f LUFS（网络投放建议 -14 ~ -12）' % I)
    chk('真峰值', TP <= -0.2, '%.1f dBTP（≤ -0.2 才不炸）' % TP)

    # 首尾必须淡入淡出，不能有硬切
    n = int(0.25 * 48000)
    head = [np.sqrt((m[i * n:(i + 1) * n] ** 2).mean()) for i in range(8)]
    tail = [np.sqrt((m[len(m) - (i + 1) * n:len(m) - i * n] ** 2).mean()) for i in range(8)][::-1]
    chk('片头渐入', head[0] < head[-1] * 0.6 + 1e-6,
        '0-2s %.1f→%.1f dB' % (20 * np.log10(max(head[0], 1e-9)),
                               20 * np.log10(max(head[-1], 1e-9))))
    chk('片尾收束', tail[-1] < tail[0] * 0.6 + 1e-6,
        '末 2s %.1f→%.1f dB' % (20 * np.log10(max(tail[0], 1e-9)),
                                20 * np.log10(max(tail[-1], 1e-9))))

    # ---------- 接缝 ----------
    print('— 接缝 —')
    segs = sorted(SEG.glob('*_*.mp4')) if SEG.exists() else []
    if len(segs) < 2:
        print('（无分段目录，跳过接缝检查）')
    else:
        worst = []
        for a_, b_ in zip(segs, segs[1:]):
            fa = grab(a_, float(probe(a_)['format']['duration']) - 0.05)
            fb = grab(b_, 0.02)
            worst.append((dif(fa, fb), a_.name, b_.name))
        worst.sort(reverse=True)
        bad = [w for w in worst if w[0] > 3.5]
        chk('跨段无跳帧', not bad, '最大帧差 %.2f（阈值 3.5）' % worst[0][0])
        for d, x, y in worst[:3]:
            print('    %.2f  %s | %s' % (d, x, y))

    # ---------- 画面静帧 ----------
    print('— 画面 —')
    ts = [dur * k / 12 for k in range(1, 12)]
    imgs = [grab(FINAL, t) for t in ts]
    still = [(round(dif(imgs[i], imgs[i + 1]), 2), round(ts[i], 1))
             for i in range(len(imgs) - 1)]
    chk('无长时间静帧', all(d > 0.4 for d, _ in still),
        '最小帧差 %.2f（采样 12 点）' % min(d for d, _ in still))

    print('\n%s' % ('全部通过，可以交付。' if ok else '存在 ❌ 项，修完再交付。'))
    print('成片: %s  %.1f MB  %.2fs' % (FINAL, FINAL.stat().st_size / 1048576, dur))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
