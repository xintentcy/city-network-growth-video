# -*- coding: utf-8 -*-
"""合成成片：视频 + 混音音轨，输出最终文件。"""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).parent
import config as C
FF, FFPROBE = C.FFMPEG, C.FFPROBE
v = ROOT / 'out' / 'video_noaudio.mp4'
a = ROOT / 'out' / 'mix.wav'
out = ROOT / 'out' / '成都地铁十五年-解说版.mp4'

subprocess.run([FF, '-y', '-v', 'error', '-i', str(v), '-i', str(a),
                '-map', '0:v:0', '-map', '1:a:0',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                '-shortest', '-movflags', '+faststart', str(out)], check=True)

r = subprocess.run([FFPROBE, '-v', 'error', '-show_entries',
                    'format=duration,size,bit_rate', '-show_entries',
                    'stream=codec_name,width,height,r_frame_rate,channels',
                    '-of', 'default=nw=1', str(out)], capture_output=True, text=True)
print(r.stdout)
print('OK', out, out.stat().st_size // 1024 // 1024, 'MB')
