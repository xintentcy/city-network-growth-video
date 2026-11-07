# -*- coding: utf-8 -*-
"""编译 v2 场景：章节时间轴（跟随解说）、数据驱动镜头、真实城市环线。"""
import json, math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
import config as C

W, H = C.W, C.H
VX, VY = C.VX, C.VY
VW, VH = C.VW, C.VH
ASPECT = VW / VH

LON0, LAT0 = C.LON0, C.LAT0
KX = math.cos(math.radians(LAT0)) * 111.32
KY = 110.54

def km(lon, lat):
    return ((lon - LON0) * KX, -(lat - LAT0) * KY)

raw = json.load(open(ROOT / 'data' / 'scene_raw.json', encoding='utf-8'))
rings = json.load(open(ROOT / 'data' / 'rings.json', encoding='utf-8'))['rings']
voice = json.load(open(ROOT / 'data' / 'voice.json', encoding='utf-8'))['dur']
from content import CHAPTERS

UNOPEN = set(C.EXCLUDE_STATIONS)

# ---------- 轨道 ----------
tracks = []
for ti, tr in enumerate(raw['tracks']):
    pts = [km(*p) for p in tr['points']]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    stops = [{'n': s['name'], 't': s['t'],
              'x': km(s['lon'], s['lat'])[0], 'y': km(s['lon'], s['lat'])[1]}
             for s in tr['stops'] if s['name'] not in UNOPEN]
    tracks.append({'ti': ti, 'ref': tr['ref'], 'color': tr['color'], 'km': tr['km'],
                   'pts': [[round(x, 5), round(y, 5)] for x, y in pts],
                   'cum': [round(c, 5) for c in cum], 'stops': stops, 'segs': []})

canon = {}
for tr in tracks:
    if tr['ref'] not in canon or tr['km'] > canon[tr['ref']]['km']:
        canon[tr['ref']] = tr

# ---------- 时间轴 ----------
GAP, LEAD, TAIL = C.GAP, C.LEAD, C.TAIL
chapters, t = [], 0.0
last = len(CHAPTERS) - 1
for i, ch in enumerate(CHAPTERS):
    if i == 0:
        start, nA = 0.0, 2.6
        end = nA + voice[ch['id']] + 1.4
    elif i == last:
        start = t + 1.0
        nA = start + 0.7
        end = nA + voice[ch['id']] + 3.0
    else:
        start = t + GAP
        nA = start + LEAD
        end = nA + voice[ch['id']] + TAIL
    chapters.append({'id': ch['id'], 'date': ch['date'], 'title': ch['title'],
                     'chips': ch['chips'], 'tag': ch['tag'], 'cn': ch['cn'], 'en': ch['en'],
                     'tA': round(start, 3), 'nA': round(nA, 3),
                     'nDur': round(voice[ch['id']], 3), 'tE': round(end, 3)})
    t = end
TOTAL = round(t + C.END_HOLD, 3)

# ---------- 分段去重后挂到章节 ----------
seen = {}
for sg in raw['segs']:
    key = (sg['ref'], sg['date'], sg['from'], sg['to'])
    ti = sg['ti']
    if key in seen:
        if ti == canon[sg['ref']]['ti']:
            seen[key] = sg
        continue
    seen[key] = sg

segs = list(seen.values())
for sg in segs:
    ch = next((c for c in chapters if c['date'] == sg['date']), None)
    if ch is None:
        print('!! 无章节', sg['date'], sg['ref']); continue
    tr = next(x for x in tracks if x['ti'] == sg['ti'])
    km_s = (sg['t1'] - sg['t0']) * tr['km']
    dur = min(1.15, max(0.55, 0.30 + 0.026 * km_s))
    tr['segs'].append({'t0': sg['t0'], 't1': sg['t1'], 'date': sg['date'],
                       'tA': ch['tA'], 'dur': round(dur, 3), 'km': round(km_s, 2)})

def cum_geo(tnow):
    s = 0.0
    for tr in tracks:
        for sg in tr['segs']:
            f = max(0.0, min(1.0, (tnow - sg['tA']) / sg['dur']))
            s += sg['km'] * f
    return s

def open_refs(tnow):
    return {tr['ref'] for tr in tracks if any(sg['tA'] <= tnow for sg in tr['segs'])}

# ---------- 里程口径：锚定官方节点，中间线性映射 ----------
ANCH = list(C.ANCH)
anch = []
for cid, val in ANCH:
    ch = next(c for c in chapters if c['id'] == cid)
    anch.append((cum_geo(ch['tE'] - 1e-6), val))
print('几何锚点', [(round(a, 1), b) for a, b in anch], '几何合计', round(cum_geo(TOTAL), 1))

def disp_km(g):
    if g <= anch[0][0]:
        return anch[0][1] * (g / anch[0][0]) if anch[0][0] else 0.0
    for (g0, v0), (g1, v1) in zip(anch, anch[1:]):
        if g <= g1:
            return v0 + (v1 - v0) * (g - g0) / max(1e-6, g1 - g0)
    return anch[-1][1] + (g - anch[-1][0])

def km_at(tnow):
    return disp_km(cum_geo(tnow))

for ch in chapters:
    ch['cum'] = int(round(km_at(ch['tE'] - 1e-6)))
    ch['nLines'] = len(open_refs(ch['tE'] - 1e-6))

# ---------- 环线 ----------
RINGS = {k: [[[round(v, 5) for v in km(*p)] for p in s] for s in sl] for k, sl in rings.items()}
RING_ORDER = list(C.RING_ORDER)
def ring_pts(k):
    return [p for s in RINGS[k] for p in s]
RC = {k: [sum(p[0] for p in ring_pts(k)) / len(ring_pts(k)),
          sum(p[1] for p in ring_pts(k)) / len(ring_pts(k))] for k in RING_ORDER}

def stitch_closed(sl, tol=0.02):
    key = lambda p: (round(p[0] / tol), round(p[1] / tol))
    ends = defaultdict(list)
    for i, s in enumerate(sl):
        ends[key(s[0])].append((i, 0)); ends[key(s[-1])].append((i, 1))
    used = [False] * len(sl); best = []
    for st in range(len(sl)):
        if used[st]: continue
        used[st] = True; path = list(sl[st])
        while True:
            nxt = None
            for i, r in ends.get(key(path[-1]), []):
                if not used[i]: nxt = (i, r); break
            if nxt is None: break
            used[nxt[0]] = True
            s = sl[nxt[0]]
            path += (list(reversed(s)) if nxt[1] else list(s))[1:]
        if len(path) > len(best): best = path
    return best

RCITY = stitch_closed(RINGS['绕城'])

def inside(poly, p):
    x, y = p; c = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            c = not c
    return c

cross = sorted({tr['ref'] for tr in tracks if any(not inside(RCITY, p) for p in tr['pts'][::2])},
               key=lambda x: (len(x), x))
print('越过绕城的线路', cross, len(cross))

# ---------- 镜头 ----------
def opened_pts(refs, tnow):
    out = []
    for tr in tracks:
        if tr['ref'] not in refs: continue
        pts, cum = tr['pts'], tr['cum']
        for sg in tr['segs']:
            f = max(0.0, min(1.0, (tnow - sg['tA']) / sg['dur']))
            if f <= 0: continue
            a = sg['t0']; b = sg['t0'] + (sg['t1'] - sg['t0']) * f
            i0 = bisect_left(cum, a * cum[-1]); i1 = bisect_right(cum, b * cum[-1])
            out.extend(pts[i0:i1:3])
    return out

def cam_target(refs, tnow):
    pts = opened_pts(refs, tnow)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    for p in ring_pts('绕城')[::2]:
        xs.append(p[0]); ys.append(p[1])
    x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
    span = max((x1 - x0) * 1.12, (y1 - y0) * 1.12 * ASPECT, 31.0)
    span = min(span, 106.0)
    cx = (x0 + x1) / 2 * 0.86 + RC['二环'][0] * 0.14
    cy = (y0 + y1) / 2 * 0.86 + RC['二环'][1] * 0.14
    return [round(span, 2), round(cx, 2), round(cy, 2)]

CAMS, prev = [], [31.0, RC['二环'][0], RC['二环'][1]]
for ch in chapters:
    tgt = cam_target(open_refs(ch['tE']), ch['tE']) if ch['date'] else prev
    CAMS.append({'t0': ch['tA'], 't1': round(ch['tA'] + 1.5, 3), 'from': prev, 'to': tgt})
    prev = tgt

scene = {'W': W, 'H': H, 'fps': 30, 'total': TOTAL,
         'view': [VX, VY, VW, VH], 'mapLeft': 600,
         'tracks': tracks, 'rings': RINGS, 'ringOrder': RING_ORDER,
         'ringC': RC, 'ringCity': RCITY, 'chapters': chapters, 'cams': CAMS,
         'crossLines': cross, 'nLinesTotal': len(tracks),
         'kmTotal': anch[-1][1], 'anch': [[round(a, 2), b] for a, b in anch]}
json.dump(scene, open(ROOT / 'data' / 'scene2.json', 'w', encoding='utf-8'), ensure_ascii=False)

pts = opened_pts(open_refs(TOTAL), TOTAL)
xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
sp,cx,cy = CAMS[-1]['to']
print('全量 bbox x %.1f..%.1f  y %.1f..%.1f' % (min(xs),max(xs),min(ys),max(ys)))
print('末镜 span %.1f 视图 x %.1f..%.1f  y %.1f..%.1f' % (sp, cx-sp/2, cx+sp/2, cy-sp/2/ASPECT, cy+sp/2/ASPECT))
print(f'总时长 {TOTAL:.1f}s  章节 {len(chapters)}  段 {len(segs)}')
for ch, c in zip(chapters, CAMS):
    print(f"  {ch['id']:>12} {ch['tA']:6.2f}→{ch['tE']:6.2f} {ch['nLines']:>2}条 "
          f"{ch['cum']:>5d}km  cam {c['to']}")
