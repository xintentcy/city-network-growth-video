# -*- coding: utf-8 -*-
"""把"官方开通事件表"编译成分段（seg）：每条线路按开通日期切成区间。

用法:
  python build_openings.py            # 读 data/lines.json + data/openings.csv
  python build_openings.py --check    # 只做覆盖度体检

data/openings.csv 每行 = 一次开通公告:
  date,ref,from,to,hint
  2010-09-27,1,升仙湖,世纪城,科学城
  2017-12-06,7,崔家店,崔家店,崔家店        ← 环线成环用 首=末 表示整条

hint 用来在同一条 ref 的多条轨道（主线/支线/区间）里挑对那一条，填该轨道上任一站。
"""
import csv, json, sys
from pathlib import Path
import config as C

ROOT = Path(__file__).parent
D = ROOT / 'data'


def idx(tr, name):
    ns = [s['name'] for s in tr['stops']]
    if name in ns:
        return ns.index(name)
    alt = name[:-1] if name.endswith('站') else name + '站'
    return ns.index(alt) if alt in ns else None


def main():
    lines = json.load(open(D / 'lines.json', encoding='utf-8'))
    rows = list(csv.DictReader(open(D / 'openings.csv', encoding='utf-8-sig')))

    tracks = []
    for ref, info in lines.items():
        for tr in info['tracks']:
            tracks.append({'ref': ref, **tr})
    for tr in tracks:
        tr['stops'] = [s for s in tr['stops'] if s['name'] not in set(C.EXCLUDE_STATIONS)]

    # 先剔掉"共线/贯通段"整条关系（否则同一条线的开通里程会算进别的线）
    if C.DROP_TRACKS:
        bad = {tuple(x) for x in C.DROP_TRACKS}
        n0 = len(tracks)
        tracks = [tr for tr in tracks
                  if (tr['ref'], tr['terminals'][0]) not in bad
                  and (tr['ref'], tr['terminals'][1]) not in bad]
        if len(tracks) != n0:
            print('按 DROP_TRACKS 剔除 %d 条关系' % (n0 - len(tracks)))

    # 同 ref 下，被别的轨道站集包含的（区间车/短交路）剔掉
    keep = []
    for i, tr in enumerate(tracks):
        ss = {s['name'] for s in tr['stops']}
        covered = any(j != i and ss <= {s['name'] for s in o['stops']}
                      and len(o['stops']) > len(tr['stops'])
                      for j, o in enumerate(tracks) if o['ref'] == tr['ref'])
        if not covered:
            keep.append(tr)
    tracks = keep

    segs, errs = [], []
    for r in rows:
        date, ref = r['date'].strip(), r['ref'].strip()
        a, b, hint = r['from'].strip(), r['to'].strip(), (r.get('hint') or '').strip()
        # 同一条线常有「主线」和「含延伸段/共线段的整线」两条关系：
        # 在同时命中两端站的候选里取站数最多的那条（超集），否则同一段会被拆到两条轨道上
        cand = []
        for i, tr in enumerate(tracks):
            if tr['ref'] != ref:
                continue
            if hint and idx(tr, hint) is None:
                continue
            if idx(tr, a) is None or idx(tr, b) is None:
                continue
            cand.append((len(tr['stops']), i))
        if not cand:
            errs.append((date, ref, a, b, hint))
            continue
        ti = max(cand)[1]
        tr = tracks[ti]
        ia, ib = idx(tr, a), idx(tr, b)
        ta, tb = tr['stops'][ia]['t'], tr['stops'][ib]['t']
        if a == b:                      # 整条线（环线）
            ta, tb = 0.0, 1.0
        if tb < ta:
            ta, tb = tb, ta
        segs.append({'ti': ti, 'ref': ref, 'date': date,
                     't0': round(ta, 5), 't1': round(tb, 5), 'from': a, 'to': b})

    # 同 ref 的"路线变体"去重：没有任何分段、且站集与已覆盖轨道高度重合的轨道直接丢掉，
    # 否则同一段线路会被画两遍（OSM 常同时提供"主线"和"含支线/机场段的整线"两条关系）
    byref = {}
    for i, tr in enumerate(tracks):
        byref.setdefault(tr['ref'], []).append(i)
    covered = {s['ti'] for s in segs}
    drop = set()
    for ref, idxs in byref.items():
        for i in idxs:
            if i in covered:
                continue
            si = {s['name'] for s in tracks[i]['stops']}
            for j in idxs:
                if j not in covered:
                    continue
                sj = {s['name'] for s in tracks[j]['stops']}
                if len(si & sj) / max(1, len(si)) > 0.8:
                    drop.add(i)
                    break
    if drop:
        remap, kept = {}, []
        for i, tr in enumerate(tracks):
            if i in drop:
                continue
            remap[i] = len(kept)
            kept.append(tr)
        print('丢弃重复路线 %d 条' % len(drop))
        tracks = kept
        segs = [dict(s, ti=remap[s['ti']]) for s in segs if s['ti'] in remap]

    # 去重（同一 (ref,date,from,to) 只留一条）
    seen, uniq = set(), []
    for s in segs:
        k = (s['ref'], s['date'], s['from'], s['to'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    segs = uniq

    print('轨道 %d 条 · 分段 %d 条 · 未匹配 %d' % (len(tracks), len(segs), len(errs)))
    for e in errs:
        print('  !! 未匹配', e)

    # 覆盖度体检：只对每条 ref 的"主轨"报错，支线/变体只做信息提示
    prim = {}
    for ti, tr in enumerate(tracks):
        tot = sum(s['t1'] - s['t0'] for s in segs if s['ti'] == ti)
        prim.setdefault(tr['ref'], []).append((ti, tot))
    bad = 0
    for ref, lst in prim.items():
        lst.sort(key=lambda x: -x[1])
        main = lst[0][0]
        for ti, tr in enumerate(tracks):
            if tr['ref'] != ref:
                continue
            cov = sorted([(s['t0'], s['t1']) for s in segs if s['ti'] == ti])
            total = sum(b - a for a, b in cov)
            gaps = [(round(b1, 3), round(a2, 3)) for (a1, b1), (a2, b2)
                    in zip(cov, cov[1:]) if a2 - b1 > 0.02]
            if ti == main and (total < 0.92 or gaps):
                bad += 1
                print('  !! %-3s %-12s→%-12s cover=%.2f gaps=%s'
                      % (tr['ref'], tr['terminals'][0][:6],
                         tr['terminals'][1][:6], total, gaps))
            elif ti != main:
                print('     变体 %-3s %-12s→%-12s cover=%.2f（不单独报错）'
                      % (tr['ref'], tr['terminals'][0][:6],
                         tr['terminals'][1][:6], total))
    print('主轨覆盖度异常: %d' % bad)

    out = {'tracks': tracks, 'segs': segs}
    json.dump(out, open(D / 'scene_raw.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print('saved data/scene_raw.json')


if __name__ == '__main__':
    main()
