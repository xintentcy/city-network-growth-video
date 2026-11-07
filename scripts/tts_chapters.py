# -*- coding: utf-8 -*-
"""逐章生成中文解说 → 48k 单声道 wav，并记录时长供时间轴使用。

用法:
  python tts_chapters.py                            # 默认音色
  python tts_chapters.py zh-CN-YunyangNeural -6%
  python tts_chapters.py zh-CN-XiaoxiaoNeural 0     # 换音色/语速（rate 单位 %）

产物: audio/<chapter_id>.wav + data/voice.json({'voice','rate','dur':{id:秒}})

依赖: pip install edge-tts
音频链固定为 highpass → loudnorm(-17 LUFS) → 轻微去齿音。每章必须先做 loudnorm，
否则混音时会出现"某几章忽大忽小"。想重做单章：删掉该章 wav 再跑。
"""
import asyncio, json, subprocess, sys
from pathlib import Path

import edge_tts

import config as C

ROOT = Path(__file__).parent
AUD = ROOT / 'audio'
AUD.mkdir(exist_ok=True)

VOICE = sys.argv[1] if len(sys.argv) > 1 else 'zh-CN-YunyangNeural'
RATE = sys.argv[2] if len(sys.argv) > 2 else '-6%'

from content import CHAPTERS  # noqa: E402

AF = ('highpass=f=80,'
      'loudnorm=I=-17:TP=-3:LRA=9,'
      'treble=g=-2:f=6800:width_type=o:width=1.6')


async def one(ch):
    mp3 = AUD / ('%s.mp3' % ch['id'])
    wav = AUD / ('%s.wav' % ch['id'])
    fresh = mp3.exists() and wav.exists() and wav.stat().st_mtime >= mp3.stat().st_mtime
    if not fresh:
        if not mp3.exists():
            await edge_tts.Communicate(ch['cn'], VOICE, rate=RATE).save(str(mp3))
        subprocess.run([C.FFMPEG, '-v', 'error', '-y', '-i', str(mp3),
                        '-af', AF, '-ac', '1', '-ar', '48000', str(wav)], check=True)
    out = subprocess.run([C.FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'default=nw=1:nk=1', str(wav)],
                         capture_output=True, text=True)
    return float(out.stdout.strip())


async def main():
    durs = {}
    for ch in CHAPTERS:
        d = await one(ch)
        durs[ch['id']] = round(d, 3)
        print('%-12s %5.2fs  %s' % (ch['id'], d, ch['cn'][:26]), flush=True)
    json.dump({'voice': VOICE, 'rate': RATE, 'dur': durs},
              open(ROOT / 'data' / 'voice.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('章节 %d · 解说总长 %.2fs' % (len(durs), sum(durs.values())))


asyncio.run(main())
