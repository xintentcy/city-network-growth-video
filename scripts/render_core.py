# -*- coding: utf-8 -*-
"""v2 渲染器：1080p 深色科技风 + 城市环线参照 + 章节化叙事。

用法:
  python render_v2.py preview 2,7.5,20,60,130,175
  python render_v2.py video
"""
import json, math, subprocess, sys, time
from bisect import bisect_left, bisect_right
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ROOT = Path(__file__).parent
W, H = 1920, 1080
SS = 2
FPS = 30
import config as C
FFMPEG = C.FFMPEG

S = json.load(open(ROOT / 'data' / 'scene2.json', encoding='utf-8'))
VX, VY, VW, VH = S['view']
CH = S['chapters']
TOTAL = S['total']

# ---------------- 字体 ----------------
FNT = {'yh':  ('C:/Windows/Fonts/msyh.ttc', 0),
       'yh_l': ('C:/Windows/Fonts/msyhl.ttc', 0),
       'yh_b': ('C:/Windows/Fonts/msyhbd.ttc', 0),
       'd':   ('C:/Windows/Fonts/Deng.ttf', 0),
       'd_l': ('C:/Windows/Fonts/Dengl.ttf', 0),
       'd_b': ('C:/Windows/Fonts/Dengb.ttf', 0),
       'en':  ('C:/Windows/Fonts/segoeui.ttf', 0),
       'en_l':('C:/Windows/Fonts/segoeuil.ttf', 0)}
_fc = {}
def font(k, s):
    if (k, s) not in _fc:
        p, i = FNT[k]
        _fc[(k, s)] = ImageFont.truetype(p, s, index=i)
    return _fc[(k, s)]

def hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def rgb2hsl(r, g, b):
    r, g, b = r / 255, g / 255, b / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2; d = mx - mn
    if d == 0: return 0.0, 0.0, l
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r: h = ((g - b) / d + (6 if g < b else 0)) / 6
    elif mx == g: h = ((b - r) / d + 2) / 6
    else: h = ((r - g) / d + 4) / 6
    return h, s, l

def hsl2rgb(h, s, l):
    if s == 0:
        v = int(round(l * 255)); return (v, v, v)
    def f(p, q, t):
        if t < 0: t += 1
        if t > 1: t -= 1
        if t < 1 / 6: return p + (q - p) * 6 * t
        if t < 1 / 2: return q
        if t < 2 / 3: return p + (q - p) * (2 / 3 - t) * 6
        return p
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return tuple(int(round(c * 255)) for c in (f(p, q, h + 1 / 3), f(p, q, h), f(p, q, h - 1 / 3)))

COLOR = {}
for tr in S['tracks']:
    r, g, b = hex2rgb(tr['color'])
    h, s, l = rgb2hsl(r, g, b)
    COLOR[tr['ref']] = hsl2rgb(h, min(0.95, max(s, 0.66)), max(l, 0.64))

# ---------------- 相机 / 线路聚焦 ----------------
CAMS = S['cams']
ASPECT = VW / VH

def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)

def clamp(x, a, b):
    return a if x < a else (b if x > b else x)

def _slice(tr, t0, t1):
    """按归一化里程取轨道子段。"""
    cum, L = tr['cum'], tr['cum'][-1]
    i0 = bisect_left(cum, t0 * L)
    i1 = min(len(cum) - 1, bisect_left(cum, t1 * L) + 1)
    return tr['pts'][i0:i1 + 1]

def _resample(pts, step=0.3):
    """重采样成等距折线，便于按里程取点（行进光点、拖尾）。"""
    out = [(pts[0][0], pts[0][1], 0.0)]
    d = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-9: continue
        n = max(1, int(seg / step))
        for k in range(1, n + 1):
            d += seg / n
            out.append((a[0] + (b[0] - a[0]) * k / n,
                        a[1] + (b[1] - a[1]) * k / n, d))
    return out

NET = [c['to'] for c in S['cams']]

# 每章聚焦一条“主角线”：推近 → 首站跑末站 → 停顿 → 拉回全网
FOC = {}
for _i, _ch in enumerate(CH):
    if not _ch['date'] or not _ch['chips']:
        continue
    best = None
    for _ref, _lab in _ch['chips']:
        _segs = [(tr, sg) for tr in S['tracks'] if tr['ref'] == _ref
                 for sg in tr['segs'] if sg['date'] == _ch['date']]
        if not _segs: continue
        _byti = {}
        for tr, sg in _segs: _byti.setdefault(tr['ti'], []).append(sg)
        _ti = max(_byti, key=lambda k: sum(s['km'] for s in _byti[k]))
        _newkm = sum(s['km'] for s in _byti[_ti])
        if best is None or _newkm > best[0]:
            best = (_newkm, _ref, _ti)
    if not best: continue
    _newkm, ref, ti = best
    tr = next(t for t in S['tracks'] if t['ti'] == ti)
    opens = [sg for sg in tr['segs'] if sg['tA'] <= _ch['tE'] + 1e-6]
    if not opens: continue
    t0 = min(sg['t0'] for sg in opens)
    t1 = max(sg['t1'] for sg in opens)
    path = _slice(tr, t0, t1)
    if len(path) < 2: continue
    st = [dict(n=s['n'], x=s['x'], y=s['y'], t=s['t'], new=False) for s in tr['stops']
          if t0 - 1e-6 <= s['t'] <= t1 + 1e-6]
    st.sort(key=lambda s: s['t'])
    for s in st:
        s['new'] = any(sg['t0'] - 1e-6 <= s['t'] <= sg['t1'] + 1e-6
                       and sg['date'] == _ch['date'] for sg in opens)
        s['d'] = (s['t'] - t0) * tr['cum'][-1]
    # 行进方向：以章节标注的“首站—末站”为准，必要时反向
    rev = False
    _lab = _ch['chips'][0][1] if _ch['chips'] else ''
    if '—' in _lab and st:
        _a, _b = _lab.split('—')[0].strip(), _lab.split('—')[-1].strip()
        if _a == st[-1]['n'] and _b == st[0]['n']:
            rev = True
    xs = [p[0] for p in path]; ys = [p[1] for p in path]
    w = max(xs) - min(xs); h = max(ys) - min(ys)
    fit = max(w * 1.16, h * 1.16 * ASPECT, 18.0)
    net = NET[_i][0]
    span = min(fit, max(22.0, net * 1.0))      # 不为了取全景而拉远
    span = max(span, net / 2.9)                # 单次推近不过猛

    rp = _resample(path)
    plen = rp[-1][2]
    grow = max([sg['dur'] for sg in opens if sg['date'] == _ch['date']] or [0.6])
    pt1 = _ch['tA'] + 0.95                                  # 推镜结束
    jt0 = _ch['tA'] + max(1.12, grow + 0.42)                # 起步（等新线画完）
    cap = max(1.3, (_ch['tE'] - 1.45) - 0.35 - jt0)
    jdur = clamp(max(0.055 * len(st) + 0.60, plen * 0.042 + 0.80), 1.6, min(5.0, cap))
    jt1 = jt0 + jdur                                        # 到末站
    pl0 = max(jt1 + 0.35, _ch['tE'] - 1.45)                 # 拉远开始
    pl1 = min(_ch['tE'] - 0.12, pl0 + 1.20)

    if rev:
        for _s in st:
            _s['d'] = plen - _s['d']
        st.sort(key=lambda x: x['d'])
    FOC[_ch['id']] = dict(
        ref=ref, ti=ti, rp=rp, rd=[q[2] for q in rp], rev=rev, tb=t0,
        d0=0.0, d1=round(rp[-1][2], 3), st=st, n=len(st), km=round(plen, 1),
        newids={id(sg) for sg in opens if sg['date'] == _ch['date']},
        span=round(span, 2), cx=round((max(xs) + min(xs)) / 2, 3),
        cy=round((max(ys) + min(ys)) / 2, 3),
        pt1=round(pt1, 3), jt0=round(jt0, 3), jt1=round(jt1, 3), jdur=round(jdur, 3),
        pl0=round(pl0, 3), pl1=round(pl1, 3), net=list(NET[_i]))

# 连续关键帧：章节之间不断镜
KFS = [(0.0, CAMS[0]['from'][0], CAMS[0]['from'][1], CAMS[0]['from'][2], 'inout')]
KFS.append((round(CH[0]['tE'] - 0.35, 3), CAMS[0]['from'][0] * 0.965,
            CAMS[0]['from'][1], CAMS[0]['from'][2], 'inout'))
_hold = [CAMS[0]['from'][0], CAMS[0]['from'][1], CAMS[0]['from'][2]]
for _i, _ch in enumerate(CH):
    f = FOC.get(_ch['id'])
    if not f: continue
    # 章首先“停住”，推镜从章首开始，节奏才干净
    KFS.append((round(_ch['tA'], 3), _hold[0], _hold[1], _hold[2], 'inout'))
    KFS.append((f['pt1'], f['span'], f['cx'], f['cy'], 'out'))
    KFS.append((f['pl0'], round(f['span'] * 1.06, 3), f['cx'], f['cy'], 'inout'))
    KFS.append((f['pl1'], f['net'][0], f['net'][1], f['net'][2], 'inout'))
    _hold = list(f['net'])
KFS.append((CH[-1]['tE'] - 0.2, NET[-1][0] * 0.955, NET[-1][1], NET[-1][2], 'inout'))
KFS.append((CH[-1]['tE'] - 0.2, NET[-1][0] * 0.955, NET[-1][1], NET[-1][2], 'inout'))
KFS.sort(key=lambda k: k[0])
KTS = [k[0] for k in KFS]

def cam_at(t):
    i = bisect_left(KTS, t) - 1
    if i < 0: i = 0
    if i >= len(KFS) - 1:
        k = KFS[-1]
        return k[1], k[2], k[3]
    a, b = KFS[i], KFS[i + 1]
    x = clamp((t - a[0]) / max(1e-6, b[0] - a[0]), 0.0, 1.0)
    e = b[4]
    x = 1 - (1 - x) ** 3 if e == 'out' else (x ** 3 if e == 'in' else x * x * (3 - 2 * x))
    return (a[1] + (b[1] - a[1]) * x,
            a[2] + (b[2] - a[2]) * x,
            a[3] + (b[3] - a[3]) * x)

def make_tf(t):
    span, cx, cy = cam_at(t)
    sc = VW / span
    ox = VX - cx * sc
    oy = VY - cy * sc
    return sc, ox, oy

# ---------------- 时间工具 ----------------
def chapter_at(t):
    cur = CH[0]
    for c in CH:
        if t >= c['tA']: cur = c
    return cur

def idx_of(t):
    i = 0
    for k, c in enumerate(CH):
        if t >= c['tA']: i = k
    return i

def ease01(x):
    return smooth(x)

def focus_state(t):
    """返回 (聚焦信息, 聚焦强度, 行进进度)。强度用于亮的线/暗其它线以及站名淡入。"""
    f = FOC.get(CH[idx_of(t)]['id'])
    if not f: return None, 0.0, 0.0
    a = 0.0
    if f['pt1'] - 0.68 < t < f['pl1'] + 0.05:
        a = ease01((t - (f['pt1'] - 0.68)) / 0.68)
        if t > f['pl0'] - 0.12:
            a *= 1 - ease01((t - (f['pl0'] - 0.12)) / 0.5)
    p = clamp((t - f['jt0']) / max(1e-6, f['jt1'] - f['jt0']), 0.0, 1.0)
    return f, a, p

def head_coord(f, p):
    """行进进度 → 路径坐标（反向线路从末端往起点走）。"""
    d = f['d1'] * p
    return f['d1'] - d if f.get('rev') else d

def pt_at(f, d):
    """按里程在重采样折线上取点。"""
    rd, rp = f['rd'], f['rp']
    if d <= 0: return rp[0][0], rp[0][1]
    if d >= rd[-1]: return rp[-1][0], rp[-1][1]
    i = bisect_left(rd, d)
    a, b = rp[i - 1], rp[i]
    q = (d - a[2]) / max(1e-9, b[2] - a[2])
    return a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q

def seg_prog(sg, ref, t, L):
    """分段绘制进度。主角线的新增段由行进光点推进，保证“线随车走”。"""
    f = FOC.get(CH[idx_of(t)]['id'])
    if f and id(sg) in f['newids']:
        _f, _fa, p = focus_state(t)
        head = head_coord(f, p)
        a_, b_ = (sg['t0'] - f['tb']) * L, (sg['t1'] - f['tb']) * L
        if f.get('rev'):
            return clamp((b_ - head) / max(1e-6, b_ - a_), 0.0, 1.0)
        return clamp((head - a_) / max(1e-6, b_ - a_), 0.0, 1.0)
    return clamp((t - sg['tA']) / sg['dur'], 0.0, 1.0)

def seg_span(sg, ref, t, L):
    """当前已绘制的归一化区间 (u0,u1)；反向线路从另一头长出来。"""
    fr = seg_prog(sg, ref, t, L)
    if fr <= 0: return None
    f = FOC.get(CH[idx_of(t)]['id'])
    if f and f.get('rev') and id(sg) in f['newids']:
        return sg['t1'] - (sg['t1'] - sg['t0']) * fr, sg['t1']
    return sg['t0'], sg['t0'] + (sg['t1'] - sg['t0']) * fr

# 年份进度：章节日期 → 时间轴位置
YR0, YR1 = float(C.YEAR_A), C.YEAR_B + C.YEAR_B_FRAC
KNOTS = []
prev = 2010.0
for c in CH:
    if not c['date']: continue
    y = int(c['date'][:4]) + (int(c['date'][5:7]) - 1) / 12
    grow = max([sg['dur'] for tr in S['tracks'] for sg in tr['segs'] if sg['date'] == c['date']] or [0.6])
    _fo = FOC.get(c['id'])
    if _fo:
        grow = max(grow, _fo['jt1'] - c['tA'])
    KNOTS.append((c['tA'], prev, y))
    KNOTS.append((c['tA'] + grow, prev, y))
    KNOTS.append((c['tE'], y, y))
    prev = y

def year_at(t):
    if t <= KNOTS[0][0]: return KNOTS[0][1]
    for (t0, a0, _), (t1, _a, b1) in zip(KNOTS, KNOTS[1:]):
        if t <= t1:
            f = (t - t0) / max(1e-6, t1 - t0)
            return a0 + (b1 - a0) * f
    return KNOTS[-1][2]

# 里程
def cum_geo(t):
    s = 0.0
    for tr in S['tracks']:
        L = tr['cum'][-1]
        for sg in tr['segs']:
            s += sg['km'] * seg_prog(sg, tr['ref'], t, L)
    return s

ANCH = S['anch']
def disp_km(g):
    if g <= ANCH[0][0]:
        return ANCH[0][1] * (g / ANCH[0][0]) if ANCH[0][0] else 0.0
    for (g0, v0), (g1, v1) in zip(ANCH, ANCH[1:]):
        if g <= g1:
            return v0 + (v1 - v0) * (g - g0) / max(1e-6, g1 - g0)
    return ANCH[-1][1]

def km_at(t):
    return disp_km(cum_geo(t))

def open_refs(t):
    return {tr['ref'] for tr in S['tracks'] if any(sg['tA'] <= t for sg in tr['segs'])}

# ---------------- 背景 ----------------
def build_bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = VX, VY - 20
    d = np.sqrt(((xx - cx) / 1250) ** 2 + ((yy - cy) / 1020) ** 2)
    d = np.clip(d, 0, 1)[..., None]
    c_in = np.array([12, 20, 35], np.float32)
    c_mid = np.array([7, 12, 21], np.float32)
    c_out = np.array([3, 5, 9], np.float32)
    f1 = np.clip(d / 0.55, 0, 1); f2 = np.clip((d - 0.55) / 0.45, 0, 1)
    img = np.where(d < 0.55, c_in + (c_mid - c_in) * f1, c_mid + (c_out - c_mid) * f2)

    grid = ((xx % 70) < 1) | ((yy % 70) < 1)
    img[grid] += np.array([6, 11, 19], np.float32) * 0.45

    left = np.clip(1 - (xx - 40) / 620, 0, 1)[..., None] ** 1.4
    img = img * (1 - left * 0.35)
    left2 = np.clip(1 - (xx - 560) / 300, 0, 1)[..., None]
    img = img * (1 - left2 * 0.22)
    bot = np.clip((yy - (H - 250)) / 250, 0, 1)[..., None] ** 1.35
    img = img * (1 - bot * 0.72)
    top = np.clip(1 - yy / 150, 0, 1)[..., None] ** 1.6
    img = img * (1 - top * 0.5)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')

BG = build_bg()

# 环线极值点（用于标签）
def ring_extreme(k):
    pts = [p for seg_ in S['rings'][k] for p in seg_]
    return {'w': min(pts, key=lambda p: p[0]), 'e': max(pts, key=lambda p: p[0]),
            'n': min(pts, key=lambda p: p[1]), 's': max(pts, key=lambda p: p[1])}

REXT = {k: ring_extreme(k) for k in S['ringOrder']}
RING_ALPHA = C.RING_ALPHA
RING_LABEL = C.RING_LABEL

def simp(pts, min_d=2.0):
    if len(pts) < 3: return pts
    out = [pts[0]]; lx, ly = pts[0]
    for x, y in pts[1:-1]:
        if abs(x - lx) + abs(y - ly) >= min_d:
            out.append((x, y)); lx, ly = x, y
    out.append(pts[-1])
    return out

# ---------------- 动态地图层 ----------------
# 每个站点“开门”的时刻（其所在分段开通时间），用于逐站点亮
ST_OPEN = {}
for _tr in S['tracks']:
    _l = []
    for _st in _tr['stops']:
        _ts = [sg['tA'] for sg in _tr['segs'] if sg['t0'] - 1e-6 <= _st['t'] <= sg['t1'] + 1e-6]
        _l.append(min(_ts) if _ts else None)
    ST_OPEN[_tr['ti']] = _l


def dynamic_layer(t):
    """两层：base（环线 + 轨道，实色）与 eff（站点/光效，半透明），最后真混合。
    Pillow 直接画 RGBA 会“覆盖”而不是“混合”，所以把光效单独一层合成。"""
    sc, ox, oy = make_tf(t)
    size = (W * SS, H * SS)
    bas = Image.new('RGBA', size, (0, 0, 0, 0)); db = ImageDraw.Draw(bas)
    eff = Image.new('RGBA', size, (0, 0, 0, 0)); de = ImageDraw.Draw(eff)
    k = SS
    T = lambda p: ((p[0] * sc + ox) * k, (p[1] * sc + oy) * k)

    f, fa, p = focus_state(t)
    fref = f['ref'] if f else None
    span = cam_at(t)[0]
    jd = f['d1'] if f else 0.0

    # 环线（压在轨道下面）
    for rk in S['ringOrder']:
        a = int(RING_ALPHA[rk] * (1 - 0.30 * fa))
        for seg_ in S['rings'][rk]:
            if len(seg_) < 2: continue
            db.line(simp([T(q) for q in seg_]), fill=(146, 168, 198, a), width=2, joint='curve')

    # 轨道；聚焦时其它线压暗，形成前后景
    for tr in S['tracks']:
        bit = 1.0 if (fref is None or tr['ref'] == fref) else 1 - 0.64 * fa
        base_col = COLOR[tr['ref']]
        col = tuple(int(c * (0.40 + 0.60 * bit)) for c in base_col) + (255,)
        wd = 10 + (2 if (tr['ref'] == fref and fa > 0.3) else 0)
        pts, cum = tr['pts'], tr['cum']
        for sg in tr['segs']:
            sp = seg_span(sg, tr['ref'], t, cum[-1])
            if not sp: continue
            a, b = sp[0] * cum[-1], sp[1] * cum[-1]
            i0 = bisect_left(cum, a); i1 = bisect_right(cum, b)
            chunk = simp([T(q) for q in pts[i0:i1]])
            if len(chunk) > 1:
                db.line(chunk, fill=col, width=wd, joint='curve')

    # 全网普通站点：随推近逐级显现
    zst = clamp((74 - span) / 24, 0.0, 1.0)
    if zst > 0.02:
        for tr in S['tracks']:
            if fa > 0.03 and tr['ref'] == fref: continue
            ot = ST_OPEN[tr['ti']]
            for st, to in zip(tr['stops'], ot):
                if to is None or to > t: continue
                x, y = T((st['x'], st['y']))
                r = 1.8 * k
                de.ellipse([x - r, y - r, x + r, y + r],
                           fill=(198, 222, 246, int(132 * zst)))

    # 换乘站
    opened_now = {tr['ref'] for tr in S['tracks'] if any(sg['tA'] <= t for sg in tr['segs'])}
    for tr in S['tracks']:
        for st in tr['stops']:
            if len(_st_refs.get(st['n'], ()) & opened_now) < 2: continue
            for sg in tr['segs']:
                sp = seg_span(sg, tr['ref'], t, tr['cum'][-1])
                if not sp: continue
                if sp[0] - 1e-6 <= st['t'] <= sp[1] + 1e-6:
                    x, y = T((st['x'], st['y']))
                    r = 3.6 * k
                    de.ellipse([x - r, y - r, x + r, y + r], fill=(238, 247, 255, 210))
                    break

    # ---------- 线路聚焦：站点依次点亮 + 行进光点 ----------
    if f and fa > 0.02:
        colf = COLOR[f['ref']]
        travel = jd * p
        head = jd - travel if f.get('rev') else travel
        # 全线虚影：先把整条走廊描出来，章首不空镜，也交代“要走的全程”
        ghost = simp([T(q[:2]) for q in f['rp']], 3.0)
        if len(ghost) > 1:
            de.line(ghost, fill=colf + (int(46 * fa),), width=5, joint='curve')
        # 已行进段：一层柔光
        if p > 0.002:
            i = bisect_left(f['rd'], head)
            walked = f['rp'][i:] if f.get('rev') else f['rp'][:i + 1]
            seg_pts = simp([T(q[:2]) for q in walked], 3.0)
            if len(seg_pts) > 1:
                de.line(seg_pts, fill=colf + (int(54 * fa),), width=16, joint='curve')

        # 涟漪先画，站点点在上面
        for st in f['st']:
            frac = st['d'] / jd if jd > 1e-6 else 0.0
            x, y = T((st['x'], st['y']))
            age = (p - frac) * f['jdur']
            if age < 0:
                # 未到站：沿线空环预告，越接近光点越亮
                near = clamp(1.0 - (st['d'] - travel) / 14.0, 0.45, 1.0)
                r = 3.0 * k
                de.ellipse([x - r, y - r, x + r, y + r],
                           outline=colf + (int(140 * fa * near),), width=int(max(1, 1.3 * k)))
                continue
            ttl = 0.52
            if age < ttl:
                q = age / ttl
                rr = (4.4 + 17 * q) * k
                de.ellipse([x - rr, y - rr, x + rr, y + rr],
                           outline=colf + (int(160 * (1 - q) * fa),), width=int(max(1, 1.7 * k)))
            if st['new']:
                q = min(1.0, age / 1.05)
                rr = (6.5 + 10 * q) * k
                de.ellipse([x - rr, y - rr, x + rr, y + rr],
                           outline=colf + (int(90 * (1 - q) * fa),), width=int(max(1, 1.2 * k)))

        # 行进光点拖尾
        hfade = 1.0
        if t < f['jt0'] + 0.25:
            hfade = clamp((t - f['jt0'] + 0.15) / 0.4, 0, 1)
        if t > f['jt1']:
            hfade = clamp(1 - (t - f['jt1']) / 0.55, 0, 1)
        if hfade > 0.01:
            hx, hy = T(pt_at(f, head))
            for j in range(11, 0, -1):
                dj = head + j * (jd * 0.0125) if f.get('rev') else head - j * (jd * 0.0125)
                if dj < 0 or dj > jd: break
                px, py = T(pt_at(f, dj))
                rr = (7.2 - 0.5 * j) * k
                al = int((96 - 7 * j) * hfade * fa)
                if rr > 0 and al > 1:
                    de.ellipse([px - rr, py - rr, px + rr, py + rr], fill=colf + (al,))
            for j in range(8, 0, -1):
                rr = 24 * j / 8 * k
                de.ellipse([hx - rr, hy - rr, hx + rr, hy + rr],
                           fill=colf + (int((30 * (1 - j / 9) ** 1.6 + 2) * hfade * fa),))

        # 站点点（白芯 + 线色环）
        for st in f['st']:
            frac = st['d'] / jd if jd > 1e-6 else 0.0
            age = (p - frac) * f['jdur']
            if age < 0: continue
            x, y = T((st['x'], st['y']))
            g = min(1.0, age / 0.26)
            pop = 1 + 0.55 * math.sin(g * math.pi) * (1 - 0.25 * g)
            r = 2.7 * pop * k
            de.ellipse([x - r, y - r, x + r, y + r],
                       fill=(255, 255, 255, int(250 * fa if fa < 1 else 250)))
            r2 = max(0.9 * k, r - 1.5 * k)
            de.ellipse([x - r2, y - r2, x + r2, y + r2], fill=colf + (int(225 * fa),))

        # 头部白芯
        if hfade > 0.01:
            hx, hy = T(pt_at(f, head))
            r = 6.6 * k
            de.ellipse([hx - r, hy - r, hx + r, hy + r], fill=(255, 255, 255, 252))

        # 到站收束
        age_end = (t - f['jt1']) if p >= 1 else 0
        if 0 < age_end < 0.9 and f['st']:
            last = f['st'][-1]
            x, y = T((last['x'], last['y']))
            q = age_end / 0.9
            rr = (7 + 28 * q) * k
            de.ellipse([x - rr, y - rr, x + rr, y + rr],
                       outline=colf + (int(200 * (1 - q) ** 1.4 * fa),), width=int(max(1, 2.4 * k)))

    # 生长头部（主角线由行进光点接管）
    for tr in S['tracks']:
        if fref == tr['ref'] and f and p < 0.999:
            continue
        base_col = COLOR[tr['ref']]
        pts, cum = tr['pts'], tr['cum']
        for sg in tr['segs']:
            fr = (t - sg['tA']) / sg['dur']
            if fr <= 0 or fr >= 1: continue
            d = (sg['t0'] + (sg['t1'] - sg['t0']) * fr) * cum[-1]
            i = min(len(pts) - 1, bisect_left(cum, d))
            x, y = T(pts[i])
            R = 26 * k
            for j in range(9, 0, -1):
                rr = R * j / 9
                de.ellipse([x - rr, y - rr, x + rr, y + rr],
                           fill=base_col + (int(40 * (1 - j / 10) ** 1.7 + 2),))
            r = 6.5 * k
            de.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 252))

    return Image.alpha_composite(bas, eff).reduce(SS)

_st_refs = {}
for tr in S['tracks']:
    for st in tr['stops']:
        _st_refs.setdefault(st['n'], set()).add(tr['ref'])
TRANSFER = {k for k, v in _st_refs.items() if len(v) >= 2}

def composite(t):
    img = BG.copy()
    small = dynamic_layer(t)
    glow = small.filter(ImageFilter.GaussianBlur(12))
    g = Image.new('RGB', (W, H), (0, 0, 0))
    g.paste(glow, (0, 0), glow)
    g = Image.fromarray(np.clip(np.asarray(g, np.float32) * 1.62, 0, 255).astype(np.uint8), 'RGB')
    img = ImageChops.add(img, g)
    return Image.alpha_composite(img.convert('RGBA'), small).convert('RGB')

# ---------------- 文本工具 ----------------
def txt(dr, xy, s, f, fill, anchor='lm', sp=0.0):
    if not s: return
    if sp == 0:
        dr.text(xy, s, font=f, fill=fill, anchor=anchor); return
    ws = [dr.textlength(c, font=f) for c in s]
    total = sum(ws) + sp * (len(s) - 1)
    x, y = xy
    if anchor[0] == 'm': x -= total / 2
    elif anchor[0] == 'r': x -= total
    a = 'l' + anchor[1]
    for c, w in zip(s, ws):
        dr.text((x, y), c, font=f, fill=fill, anchor=a)
        x += w + sp

NO = '，。、；：！？）」』】”’,.;:!?)]}%'
NUM = '零〇一二三四五六七八九十百千万亿两'
WIDOW = 4

def wrap(dr, s, f, maxw):
    """按像素宽度折行：行首不留标点、末行不留孤字、中文数字不断开。"""
    lines, cur = [], ''
    for c in s:
        if dr.textlength(cur + c, font=f) > maxw and cur:
            if c in NO and len(cur) > 1:
                # 标点不能落在行首：把上一行最后一个字一起带下去
                lines.append(cur[:-1]); cur = cur[-1] + c
            else:
                lines.append(cur); cur = c
        else:
            cur += c
    if cur: lines.append(cur)
    # 末行只剩标点时，从上一行回拉几个字
    if len(lines) > 1 and not lines[-1].strip(NO):
        k = min(3, len(lines[-2]) - 1)
        lines[-1] = lines[-2][-k:] + lines[-1]
        lines[-2] = lines[-2][:-k]
    # 末行过短（孤字/孤词）时回拉，避免“网。”“里。”这类尾巴
    while len(lines) > 1 and len(lines[-1].rstrip(NO)) < WIDOW and len(lines[-2]) > WIDOW + 1:
        lines[-1] = lines[-2][-1] + lines[-1]
        lines[-2] = lines[-2][:-1]
    # 中文数字不要拆到两行：“六百 / 七十” 这种要并到下一行
    for i in range(len(lines) - 1):
        a = ''
        for ch in reversed(lines[i]):
            if ch in NUM: a = ch + a
            else: break
        if not a:
            continue
        j = 0
        while j < len(lines[i + 1]) and lines[i + 1][j] in NUM:
            j += 1
        if j == 0:
            continue
        if dr.textlength(a + lines[i + 1], font=f) <= maxw:
            lines[i] = lines[i][:-len(a)]
            lines[i + 1] = a + lines[i + 1]
    return lines

def wrap_w(dr, s, f, maxw):
    """西文按词折行，避免把单词从中间切断。"""
    lines, cur = [], ''
    for w in s.split(' '):
        cand = w if not cur else cur + ' ' + w
        if dr.textlength(cand, font=f) <= maxw or not cur:
            cur = cand
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def T_chip(dr, x, y, ref, label, a):
    col = COLOR.get(ref, (150, 180, 210))
    fr = font('d', 17)
    wref = dr.textlength(ref, font=fr)
    pw = int(max(34, wref + 26))
    hh = 31
    dr.rounded_rectangle([x, y - hh / 2, x + pw, y + hh / 2], radius=9,
                         fill=col + (int(58 * a),), outline=col + (int(150 * a),), width=1)
    dr.text((x + pw / 2, y - 1), ref, font=fr, fill=col + (int(255 * a),), anchor='mm')
    xx = x + pw + 11
    if label:
        fl = font('yh', 17)
        for ln in wrap(dr, label, fl, 636 - xx):
            dr.text((xx, y), ln, font=fl, fill=(176, 198, 226, int(230 * a)), anchor='lm')
            y += 22
    return xx + (dr.textlength(label, font=font('yh', 17)) if label else 0)

# ---------------- HUD ----------------
PX, PR = 96, 636
def draw_hud(img, t):
    dr = ImageDraw.Draw(img, 'RGBA')
    k = idx_of(t)
    ch = CH[k]
    ap = ease01((t - 0.9) / 0.9)
    if ch['id'] == 'outro':
        ap *= max(0.0, min(1.0, 1 - (t - (ch['tE'] - 1.7)) / 1.1))
    if ap <= 0.005: return
    a = ap

    txt(dr, (PX, 74), C.BRAND, font('yh', 27), (208, 226, 248, int(240 * a)), 'lm', 1.4)
    txt(dr, (PX + 1, 104), f'{C.CITY_EN}  /  {C.YEAR_A} — {C.YEAR_B}', font('d', 11),
        (142, 172, 212, int(150 * a)), 'lm', 1.5)

    # 日期
    title = ch['title']
    if '.' in title:
        txt(dr, (PX - 3, 146), title, font('d', 84), (240, 246, 255, int(250 * a)), 'la', 0.5)
    else:
        txt(dr, (PX - 1, 164), title, font('yh_l', 60), (240, 246, 255, int(250 * a)), 'la', 1.5)

    # 线路徽标 + 标签
    ych = 262
    xx = PX
    for ref, _lab in ch['chips']:
        col = COLOR[ref]
        fr = font('d', 15)
        w = max(30, int(dr.textlength(ref, font=fr)) + 15)
        dr.rounded_rectangle([xx, ych - 15, xx + w, ych + 15], radius=7,
                             fill=col + (int(48 * a),), outline=col + (int(145 * a),), width=1)
        dr.text((xx + w / 2, ych - 1), ref, font=fr, fill=col + (int(250 * a),), anchor='mm')
        xx += w + 8
    if ch.get('tag'):
        fl = font('yh', 17)
        for ln in wrap(dr, ch['tag'], fl, PR - PX)[:2]:
            txt(dr, (PX + 1, ych + 38), ln, fl, (178, 199, 227, int(228 * a)), 'lm', 0.5)

    # 时间轴
    y0 = 330
    L, R = PX, PR
    dr.line([(L, y0), (R, y0)], fill=(120, 160, 210, int(40 * a)), width=1)
    yr = year_at(t)
    p = max(0.0, min(1.0, (yr - YR0) / (YR1 - YR0)))
    xp = L + (R - L) * p
    dr.line([(L, y0 + 1), (xp, y0 + 1)], fill=(158, 212, 255, int(240 * a)), width=2)
    for yv in range(2010, 2026):
        cx = L + (R - L) * ((yv - YR0) / (YR1 - YR0))
        big = yv % 5 == 0
        dr.line([(cx, y0 - (5 if big else 3)), (cx, y0 + (5 if big else 3))],
                fill=(140, 178, 224, int((110 if big else 55) * a)), width=1)
        if big:
            txt(dr, (cx, y0 + 24), str(yv), font('d', 12), (146, 180, 224, int(160 * a)), 'mm', 0.4)
    dr.ellipse([xp - 4, y0 - 3, xp + 4, y0 + 5], fill=(255, 255, 255, int(250 * a)))
    dr.ellipse([xp - 11, y0 - 10, xp + 11, y0 + 12], fill=(150, 205, 255, int(26 * a)))

    # 数据表
    bx0, bx1, by0, by1 = PX - 4, PR, 366, 566
    dr.rounded_rectangle([bx0, by0, bx1, by1], radius=4,
                         fill=(255, 255, 255, int(7 * a)), outline=(255, 255, 255, int(15 * a)), width=1)
    rows = [('开通线路', 'LINES', f"{ch['nLines']}", '条'),
            ('运营里程', 'LENGTH', f"{int(round(km_at(t)))}", 'km'),
            ('数据截至', 'AS OF', C.DATA_ASOF, '')]
    for i, (cn, en, val, unit) in enumerate(rows):
        yy = by0 + 40 + i * 68
        txt(dr, (bx0 + 22, yy), cn, font('yh', 13), (140, 172, 212, int(185 * a)), 'lm', 1.2)
        txt(dr, (bx0 + 22, yy + 19), en, font('d', 9), (122, 152, 192, int(95 * a)), 'lm', 1.6)
        fv = font('d', 40 if unit else 30)
        fh = font('yh', 14)
        wv = dr.textlength(val, font=fv)
        wu = dr.textlength(unit, font=fh) if unit else 0
        rx = bx1 - 20
        dr.text((rx - wu - (6 if unit else 0), yy + 2), val, font=fv,
                fill=(238, 244, 255, int(250 * a)), anchor='rs')
        if unit:
            dr.text((rx, yy + 2), unit, font=fh, fill=(150, 186, 228, int(190 * a)), anchor='rs')
        if i < 2:
            dr.line([(bx0 + 18, yy + 34), (bx1 - 18, yy + 34)],
                    fill=(255, 255, 255, int(11 * a)), width=1)

    # 口径
    for _i, _ln in enumerate(C.FOOTNOTES[:2]):
        txt(dr, (PX, 590 + _i * 18), _ln, font('yh', 11),
            (128, 158, 198, int((150 - 20 * _i) * a)), 'lm')

    # 线路清单
    ORDER = C.LINES_ORDER
    opened = open_refs(t)
    for i, ref in enumerate(ORDER):
        cx = PX + (i % 9) * 60
        cy = 656 + (i // 9) * 34
        on = ref in opened
        col = COLOR[ref]
        if on:
            dr.rounded_rectangle([cx, cy, cx + 48, cy + 26], radius=5,
                                 fill=col + (int(40 * a),), outline=col + (int(120 * a),), width=1)
            dr.text((cx + 24, cy + 13), ref, font=font('d', 15), fill=col + (int(255 * a),), anchor='mm')
        else:
            dr.rounded_rectangle([cx, cy, cx + 48, cy + 26], radius=5,
                                 outline=(255, 255, 255, int(13 * a)), width=1)
            dr.text((cx + 24, cy + 13), ref, font=font('d', 15),
                    fill=(120, 140, 166, int(70 * a)), anchor='mm')

    # 右上图例
    for _i, _ln in enumerate(C.RING_LEGEND[:2]):
        txt(dr, (1862, 50 + _i * 22), _ln, font('yh', 13 if _i == 0 else 11),
            (150, 184, 226, int((175 if _i == 0 else 120) * a)), 'rm',
            0.8 if _i == 0 else 0.0)
    txt(dr, (1862, 1052), C.CREDIT, font('yh', 11),
        (124, 154, 194, int(105 * a)), 'rm')

RING_HI = C.RING_HI

def draw_ring_labels(img, t, alpha=1.0):
    if t < 1.4: return
    dr = ImageDraw.Draw(img, 'RGBA')
    sc, ox, oy = make_tf(t)
    a0 = ease01((t - 1.4) / 1.2) * alpha
    span = cam_at(t)[0]
    LIM = {'一环': (56, 76), '二环': (72, 94), '三环': (96, 112)}
    for rk in S['ringOrder']:
        side, name = RING_LABEL[rk]
        p = REXT[rk][side]
        x, y = p[0] * sc + ox, p[1] * sc + oy
        if not (0 <= x <= W and 0 <= y <= H): continue
        side_eff = side
        if side == 'n' and y < 46: side_eff = 's'
        if side == 's' and y > H - 200: side_eff = 'n'
        if side == 'w' and x < 150: side_eff = 'e'
        if side == 'e' and x > W - 150: side_eff = 'w'
        side = side_eff
        hl = 0.0
        if 0.0 < t < 12.0:
            m = {'一环': 5.5, '二环': 6.4, '三环': 7.3}.get(rk)
            if m and m - 0.3 < t < m + 1.0:
                hl = math.sin((t - (m - 0.3)) / 1.3 * math.pi)
        if rk in RING_HI.get(CH[idx_of(t)]['id'], ()):
            c = CH[idx_of(t)]
            hl = max(hl, 0.75 * ease01((t - c['tA'] - 0.1) / 0.6) * (1 - ease01((t - (c['tE'] - 0.6)) / 0.5)))
        zf = 1.0
        if rk in LIM:
            lo, hi = LIM[rk]
            zf = 1.0 - ease01((span - lo) / (hi - lo))
        al = min(1.0, a0 * zf * (0.62 + 0.5 * hl + (0.25 if rk == '一环' else 0.0)))
        if al <= 0.03: continue
        col = (176 + int(70 * hl), 206 + int(40 * hl), 240, int(215 * min(1, al)))
        if side == 'w':
            dr.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=col)
            dr.line([(x - 16, y), (x - 4, y)], fill=col, width=1)
            pos, an = (x - 21, y), 'rm'
        elif side == 'e':
            dr.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=col)
            dr.line([(x + 4, y), (x + 16, y)], fill=col, width=1)
            pos, an = (x + 21, y), 'lm'
        elif side == 'n':
            dr.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=col)
            dr.line([(x, y - 4), (x, y - 15)], fill=col, width=1)
            pos, an = (x, y - 20), 'mb'
        else:
            dr.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=col)
            dr.line([(x, y + 4), (x, y + 15)], fill=col, width=1)
            pos, an = (x, y + 20), 'mt'
        if hl > 0.02:
            for seg_ in S['rings'][rk]:
                if len(seg_) < 2: continue
                dr.line([(p2[0] * sc + ox, p2[1] * sc + oy) for p2 in seg_],
                        fill=(198, 228, 255, int(104 * hl)), width=3, joint='curve')
        f = font('yh', 15)
        dr.text((pos[0] + 1, pos[1] + 1), name, font=f, fill=(6, 10, 18, int(170 * min(1, al))), anchor=an)
        dr.text(pos, name, font=f, fill=col, anchor=an)

# ---------------- 站名层 ----------------
def draw_focus_labels(img, t):
    """聚焦线路上，站点随行进依次亮出站名；当前站用高亮标签跟随。"""
    f, fa, p = focus_state(t)
    if not f or fa <= 0.02: return
    dr = ImageDraw.Draw(img, 'RGBA')
    sc, ox, oy = make_tf(t)
    S2 = lambda p_: (p_[0] * sc + ox, p_[1] * sc + oy)
    fl = font('yh', 13)
    occ = []
    PAD = 4

    def free(r):
        if r[0] < 596 or r[2] > 1886 or r[1] < 68 or r[3] > 896: return False
        r = (r[0] - PAD, r[1] - PAD, r[2] + PAD, r[3] + PAD)
        for o in occ:
            if r[0] < o[2] and o[0] < r[2] and r[1] < o[3] and o[1] < r[3]: return False
        return True

    # 当前站：离行进光点最近的站
    cur, curd = None, 9e9
    for st in f['st']:
        fr = st['d'] / f['d1'] if f['d1'] > 1e-6 else 0
        dd = abs(fr - p)
        if dd < curd:
            cur, curd = st, dd

    # 先给普通站名留位，再放当前站标签（当前站始终优先）
    for st in f['st']:
        if st is cur: continue
        fr = st['d'] / f['d1'] if f['d1'] > 1e-6 else 0
        age = (p - fr) * f['jdur']
        if age < 0.10: continue
        a = fa * clamp((age - 0.10) / 0.28, 0.0, 1.0)
        if a <= 0.03: continue
        x, y = S2((st['x'], st['y']))
        w = dr.textlength(st['n'], font=fl)
        for dx, dy, an in ((11, 0, 'lm'), (-11, 0, 'rm'), (0, -18, 'mb'), (0, 18, 'mt')):
            if an == 'lm':   r = (x + dx, y + dy - 8, x + dx + w, y + dy + 8)
            elif an == 'rm': r = (x + dx - w, y + dy - 8, x + dx, y + dy + 8)
            else:            r = (x + dx - w / 2, y + dy - 8, x + dx + w / 2, y + dy + 8)
            if not free(r): continue
            occ.append(r)
            tx = r[0] + 1 if an == 'lm' else (r[0] + 1 if an == 'rm' else r[0] + 1)
            dr.text((tx, y + dy + 1), st['n'], font=fl, fill=(2, 5, 10, int(150 * a)))
            dr.text((r[0] + 1, y + dy), st['n'], font=fl, fill=(203, 222, 242, int(206 * a)))
            break

    if cur is not None and p > 0.004:
        x, y = S2((cur['x'], cur['y']))
        fcb = font('yh_b', 14)
        w = dr.textlength(cur['n'], font=fcb)
        col = COLOR[f['ref']]
        cw, chh = w + 20, 26
        placed = None
        for dx, dy, an in ((16, 0, 'lm'), (-16, 0, 'rm'), (0, -22, 'mb'), (0, 22, 'mt')):
            if an == 'lm':   r = (x + dx, y + dy - chh / 2, x + dx + cw, y + dy + chh / 2)
            elif an == 'rm': r = (x + dx - cw, y + dy - chh / 2, x + dx, y + dy + chh / 2)
            else:            r = (x + dx - cw / 2, y + dy - chh / 2, x + dx + cw / 2, y + dy + chh / 2)
            if free(r):
                placed = (r, an); break
        if placed:
            r, an = placed
            occ.append(r)
            dr.rounded_rectangle(r, radius=7, fill=(5, 9, 16, int(232 * fa)),
                                 outline=col + (int(170 * fa),), width=1)
            dr.rounded_rectangle([r[0] + 1, r[1] + 1, r[0] + 4, r[3] - 1], radius=2,
                                 fill=col + (int(230 * fa),))
            dr.text((r[0] + cw / 2 + 3, (r[1] + r[3]) / 2), cur['n'], font=fcb,
                    fill=(246, 250, 255, int(250 * fa)), anchor='mm')
            # 与站点的连线
            cx_ = r[0] - 2 if an == 'lm' else (r[2] + 2 if an == 'rm' else (r[0] + r[2]) / 2)
            cy_ = r[3] + 2 if an == 'mb' else (r[1] - 2 if an == 'mt' else (r[1] + r[3]) / 2)
            dr.line([(x, y), (cx_, cy_)], fill=col + (int(120 * fa),), width=1)


# ---------------- 字幕 ----------------
CN_X, CN_W = 96, 944
EN_X, EN_W = 1064, 790
def draw_caption(img, t):
    k = idx_of(t)
    ch = CH[k]
    a = 1.0
    if t < ch['nA'] - 0.2: return
    if t < ch['nA'] + 0.35:
        a = (t - (ch['nA'] - 0.2)) / 0.55
    out_at = ch['tE'] - 0.30
    if t > out_at:
        a = max(0.0, 1 - (t - out_at) / 0.4)
    if ch['id'] == 'outro':
        out_at = ch['tE'] - 2.6
        if t > out_at:
            a = max(0.0, 1 - (t - out_at) / 0.8)
    if a <= 0.01: return
    dr = ImageDraw.Draw(img, 'RGBA')
    ai = int(250 * a)
    dy = (1 - ease01(min(1, (t - (ch['nA'] - 0.2)) / 0.55))) * 12

    dr.line([(1030, 932), (1030, 1046)], fill=(255, 255, 255, int(26 * a)), width=1)
    f = font('yh', 36)
    y = 948 + dy
    for ln in wrap(dr, ch['cn'], f, CN_W):
        dr.text((CN_X, y), ln, font=f, fill=(238, 245, 255, ai), anchor='lm')
        y += 50
    fe = font('en', 16)
    ye = 952 + dy
    for ln in wrap_w(dr, ch['en'], fe, EN_W):
        dr.text((EN_X + 1, ye + 1), ln, font=fe, fill=(2, 5, 10, int(ai * 0.55)), anchor='lm')
        dr.text((EN_X, ye), ln, font=fe, fill=(158, 192, 234, int(ai * 0.82)), anchor='lm')
        ye += 24

# ---------------- 片头 ----------------
def draw_intro(img, t):
    if t > 2.6: return
    a = 1.0
    if t < 0.45: a = t / 0.45
    elif t > 1.9: a = max(0.0, 1 - (t - 1.9) / 0.7)
    if a <= 0.01: return
    dr = ImageDraw.Draw(img, 'RGBA')
    ai = int(250 * a)
    dy = (1 - ease01(min(1, t / 1.2))) * 16
    txt(dr, (95, 934 + dy), C.INTRO['main'], font('yh_l', 66), (242, 248, 255, ai), 'lm', 3.0)
    txt(dr, (99, 992 + dy), C.INTRO['sub'], font('yh', 19),
        (152, 194, 240, int(ai * 0.9)), 'lm', 1.6)
    dr.line([(99, 1024 + dy), (99 + 236, 1024 + dy)],
            fill=(130, 190, 255, int(ai * 0.45)), width=1)

# ---------------- 片尾 ----------------
def draw_end(img, t):
    ch = CH[-1]
    t0 = ch['tE'] - 0.6
    if t < t0: return img
    a = ease01((t - t0) / 0.9)
    img = img.filter(ImageFilter.GaussianBlur(4.5 * a))
    img = Image.blend(img, Image.new('RGB', (W, H), (3, 5, 9)), 0.84 * a)
    dr = ImageDraw.Draw(img, 'RGBA')
    ai = int(252 * a)
    cx = W / 2
    txt(dr, (cx, 430), C.OUTRO['title'], font('yh_l', 54), (240, 247, 255, ai), 'mm', 3.2)
    txt(dr, (cx, 480), C.OUTRO['sub'], font('d', 13),
        (146, 182, 228, int(ai * 0.7)), 'mm', 3.4)
    dr.line([(cx - 120, 512), (cx + 120, 512)], fill=(120, 180, 245, int(ai * 0.38)), width=1)
    txt(dr, (cx, 566), C.OUTRO['kpi'], font('yh', 27),
        (182, 212, 246, int(ai * 0.95)), 'mm', 1.0)
    txt(dr, (cx, 614), C.OUTRO['far'], font('yh', 17),
        (142, 178, 220, int(ai * 0.66)), 'mm', 1.4)
    txt(dr, (cx, 672), C.OUTRO['line1'],
        font('yh', 13), (126, 158, 200, int(ai * 0.6)), 'mm', 0.4)
    txt(dr, (cx, 694), C.OUTRO['line2'],
        font('yh', 13), (126, 158, 200, int(ai * 0.5)), 'mm', 0.4)
    return img

SCRIM = Image.new('RGBA', (W, 240), (0, 0, 0, 0))
_d = ImageDraw.Draw(SCRIM)
for _i in range(240):
    _d.line([(0, _i), (W, _i)], fill=(3, 5, 9, int(238 * (_i / 239) ** 0.72)))

def add_scrim(img):
    img.alpha_composite(SCRIM, (0, H - 240))
    return img

def frame(t):
    img = composite(t).convert('RGBA')
    draw_ring_labels(img, t)
    img = add_scrim(img).convert('RGB')
    draw_focus_labels(img, t)
    draw_hud(img, t)
    draw_caption(img, t)
    if t < 2.6:
        draw_intro(img, t)
    return draw_end(img, t)

# ---------------- 入口 ----------------
if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'preview'
    outd = ROOT / 'out'; outd.mkdir(exist_ok=True)
    if mode == 'preview':
        for t in [float(x) for x in sys.argv[2].split(',')]:
            t0 = time.time(); im = frame(t)
            p = outd / f'p_{t:06.2f}.png'; im.save(p)
            print(p.name, f'{time.time()-t0:.2f}s')
    else:
        n = int(round(TOTAL * FPS))
        out = outd / 'video_noaudio.mp4'
        cmd = [FFMPEG, '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'medium',
               '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        for i in range(n):
            proc.stdin.write(frame(i / FPS).tobytes())
            if i % 120 == 0:
                el = time.time() - t0
                print(f'  {i}/{n}  {el:.0f}s  eta {el/(i+1)*(n-i-1):.0f}s', flush=True)
        proc.stdin.close(); proc.wait()
        print('video', out, f'{time.time()-t0:.0f}s', out.stat().st_size // 1024, 'KB')
