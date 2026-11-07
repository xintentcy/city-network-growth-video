# -*- coding: utf-8 -*-
"""渲染单段帧区间 → mp4。超长 rawvideo 管道跑久了会卡死，所以整片一律走分段。

用法: python render_seg.py 0 480 out/segs/00000_00480.mp4
"""
import subprocess
import sys
import time
from pathlib import Path

import config as C
import render_core as R


def main():
    f0, f1 = int(sys.argv[1]), int(sys.argv[2])
    out = Path(sys.argv[3])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.part.mp4')
    cmd = [C.FFMPEG, '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', '%dx%d' % (R.W, R.H), '-r', str(R.FPS), '-i', '-',
           '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
           '-pix_fmt', 'yuv420p', '-threads', '4', str(tmp)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    for i in range(f0, f1):
        p.stdin.write(R.frame(i / R.FPS).tobytes())
        if (i - f0) % 60 == 0:
            el = time.time() - t0
            done = i - f0 + 1
            print('  [%d-%d] %d/%d  %.0fs  eta %.0fs'
                  % (f0, f1, done, f1 - f0, el, el / done * (f1 - f0 - done)), flush=True)
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        raise SystemExit('ffmpeg failed %d' % p.returncode)
    tmp.replace(out)
    print('seg %s %df %.0fs' % (out.name, f1 - f0, time.time() - t0), flush=True)


if __name__ == '__main__':
    main()
