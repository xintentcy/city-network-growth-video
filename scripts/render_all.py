# -*- coding: utf-8 -*-
"""整片渲染：分段 → concat -c copy。可断点续跑，已完成的段直接跳过。

用法:
  python render_all.py            # 480 帧/段（约 16 秒一段，单段 1-3 分钟）
  python render_all.py 240        # 段更小，改动更省时间
  python render_all.py 480 3000   # 从第 3000 帧开始（前面的跳过，用于续跑）

产物: out/video_noaudio.mp4
"""
import subprocess
import sys
from pathlib import Path

import config as C
import render_core as R

ROOT = Path(__file__).parent
SEG = ROOT / 'out' / 'segs'
SEG.mkdir(parents=True, exist_ok=True)
N = int(round(R.TOTAL * R.FPS))
CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 480
skip_to = int(sys.argv[2]) if len(sys.argv) > 2 else 0

jobs = []
for f0 in range(0, N, CHUNK):
    f1 = min(N, f0 + CHUNK)
    jobs.append((f0, f1, SEG / ('%05d_%05d.mp4' % (f0, f1))))

print('总帧 %d · %d 段 · 每段 %d 帧 · 预计 %d 分钟'
      % (N, len(jobs), CHUNK, round(N * 0.62 / 60)), flush=True)

for f0, f1, p in jobs:
    if f0 < skip_to:
        print('skip', p.name)
        continue
    if p.exists() and p.stat().st_size > 10000:
        print('have', p.name, p.stat().st_size // 1024, 'KB')
        continue
    print('render', p.name, flush=True)
    r = subprocess.run([C.PY, str(ROOT / 'render_seg.py'), str(f0), str(f1), str(p)])
    if r.returncode != 0:
        raise SystemExit('render failed at ' + p.name)

lst = SEG / 'list.txt'
with open(lst, 'w', encoding='utf-8') as fh:
    for f0, f1, p in jobs:
        fh.write("file '%s'\n" % p.as_posix())

out = ROOT / 'out' / 'video_noaudio.mp4'
print('concat ->', out, flush=True)
subprocess.run([C.FFMPEG, '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                '-i', str(lst), '-c', 'copy', '-movflags', '+faststart', str(out)],
               check=True)
print('done', out, out.stat().st_size // 1024, 'KB')
