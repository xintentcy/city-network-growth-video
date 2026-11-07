# -*- coding: utf-8 -*-
"""从 OpenStreetMap 抓取线网几何 + 城市边界 + 环线，编译成 data/lines.json。

用法:
  # 联网抓取
  python fetch_network.py --network 成都地铁 --boundary 成都市 \
      --bbox 30.0,103.4,31.35,104.75 \
      --rings 一环路,二环路,成都三环路,成都绕城高速

  # 已有原始数据（如从 overpass-turbo 导出）→ 只做编译
  python fetch_network.py --skip-fetch --bbox 30.0,103.4,31.35,104.75

产物:
  data/routes_geom.json    route=subway 关系原始几何（out body geom）
  data/stop_names.json     节点 id → 站名（out tags）
  data/city_boundary.json  行政边界
  data/rings.json          环线折线
  data/lines.json          {ref: {ref, tracks:[{terminals,color,points,stops,km}]}}

注意:
- Overpass **必须带 User-Agent**，否则 406
- 公共实例经常 502/超时。脚本单次请求 90s、最多试 2 轮，失败就明确报错；
  实在不行去 overpass-turbo.eu 手动导出到 data/routes_geom.json，再用 --skip-fetch
"""
import argparse
import collections
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {'User-Agent': 'NetworkGrowthViz/1.0 (research; OSM ODbL)'}
ENDPOINTS = ['https://overpass-api.de/api/interpreter',
             'https://overpass.kumi.systems/api/interpreter',
             'https://overpass.private.coffee/api/interpreter']
TIMEOUT = 90


def overpass(query, out, tries=2):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for k in range(tries):
        for ep in ENDPOINTS:
            host = ep.split('/')[2]
            try:
                body = urllib.parse.urlencode({'data': query}).encode()
                req = urllib.request.Request(ep, data=body, headers=UA)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    raw = r.read()
                out.write_bytes(raw)
                print('  fetched %-26s %6d KB  (%s)'
                      % (out.name, len(raw) // 1024, host))
                return json.loads(raw)
            except Exception as e:
                last = e
                print('  fail  %-26s %s: %s'
                      % (host, type(e).__name__, str(e)[:70]))
        if k + 1 < tries:
            time.sleep(8)
    raise SystemExit(
        '\nOverpass 抓取失败（%s）。\n'
        '可选做法：\n'
        '  1) 稍后重试，公共实例常短暂 502\n'
        '  2) 打开 https://overpass-turbo.eu 粘贴查询、导出 GeoJSON/JSON 存成 %s，\n'
        '     然后加 --skip-fetch 只跑编译\n' % (last, out))


def walk_polyline(ways):
    """把一条线路的多段 way 首尾相接连成一条折线。"""
    segs = []
    for w in ways:
        g = w.get('geometry') or []
        pts = [(p['lon'], p['lat']) for p in g]
        if len(pts) >= 2:
            segs.append(pts)
    if not segs:
        return []
    key = lambda p: (round(p[0], 6), round(p[1], 6))
    ends = collections.defaultdict(list)
    for i, s in enumerate(segs):
        ends[key(s[0])].append((i, 0))
        ends[key(s[-1])].append((i, 1))
    used = [False] * len(segs)
    start = None
    for v in ends.values():
        if len(v) == 1:                  # 端点：只被一条 way 使用
            start = v[0]
            break
    i, rev = start if start else (0, 0)
    used[i] = True
    path = list(reversed(segs[i])) if rev else list(segs[i])
    while True:
        tail = key(path[-1])
        nxt = None
        for (j, r) in ends.get(tail, []):
            if not used[j]:
                nxt = (j, r)
                break
        if nxt is None:
            break
        j, r = nxt
        used[j] = True
        s = segs[j]
        path += (list(reversed(s)) if r else list(s))[1:]
    return path


def cumlen(path, lat0):
    c = [0.0]
    kx = math.cos(math.radians(lat0)) * 111320
    for a, b in zip(path, path[1:]):
        c.append(c[-1] + math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * 110540))
    return c


def compile_lines(routes, names, lat0, out_path, verbose=True):
    """把 Overpass 的 route 关系编译成 lines.json 结构（离线也能跑）。"""
    byref = collections.defaultdict(list)
    for e in routes.get('elements', []):
        t = e.get('tags', {})
        nm = t.get('name') or ''
        if '快线' in nm or '直达' in nm or '联络' in nm:
            continue
        ref = t.get('ref')
        if not ref:                      # 少数线路没有 ref，按名称兜底
            for tok in nm.replace('线', ' ').replace('地铁', ' ').split():
                if tok.isdigit() or tok.upper().startswith('S'):
                    ref = tok
                    break
        if not ref:
            continue
        byref[str(ref)].append(e)

    lines = {}
    for ref, rels in byref.items():
        # 同一 ref 常有上下行/区间车多个关系：按首末站对分组，取站数最多的
        best = {}
        for e in rels:
            nodes = [m for m in e['members'] if m['type'] == 'node']
            if len(nodes) < 2:
                continue
            ends = frozenset([names.get(str(nodes[0]['ref']), ''),
                              names.get(str(nodes[-1]['ref']), '')])
            if ends not in best or len(nodes) > best[ends][0]:
                best[ends] = (len(nodes), e)
        cand = sorted([v[1] for v in best.values()],
                      key=lambda e: -len([m for m in e['members'] if m['type'] == 'node']))
        chosen = []
        for e in cand:
            ss = set(names.get(str(m['ref']), '')
                     for m in e['members'] if m['type'] == 'node')
            if any(ss <= c['ss'] for c in chosen):     # 区间车/短交路剔除
                continue
            chosen.append({'e': e, 'ss': ss})

        tracks = []
        for ch in chosen:
            e = ch['e']
            path = walk_polyline([m for m in e['members'] if m['type'] == 'way'])
            if len(path) < 2:
                continue
            cl = cumlen(path, lat0)
            total = cl[-1]
            stops = []
            for m in e['members']:
                if m['type'] != 'node':
                    continue
                lon, lat = m.get('lon'), m.get('lat')
                if lon is None:
                    continue
                bi = min(range(len(path)),
                         key=lambda i: (path[i][0] - lon) ** 2 + (path[i][1] - lat) ** 2)
                stops.append({'name': names.get(str(m['ref'])) or ('node%s' % m['ref']),
                              'lon': lon, 'lat': lat,
                              't': cl[bi] / total if total else 0.0, 'd': cl[bi]})
            if stops and stops[0]['t'] > stops[-1]['t']:        # 统一成 t 递增
                stops.reverse()
                path.reverse()
                stops = [dict(s, t=1 - s['t'], d=total - s['d']) for s in stops]
            tracks.append({'terminals': [stops[0]['name'], stops[-1]['name']],
                           'color': (e['tags'].get('colour') or '#888888'),
                           'points': [[round(x, 6), round(y, 6)] for x, y in path],
                           'stops': stops, 'km': round(total / 1000, 2)})
        if tracks:
            lines[ref] = {'ref': ref, 'tracks': tracks}

    json.dump(lines, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False)
    if verbose:
        print('\n线路 %d 条，轨道 %d 条'
              % (len(lines), sum(len(v['tracks']) for v in lines.values())))
        for ref in sorted(lines, key=lambda x: (len(x), x)):
            for tr in lines[ref]['tracks']:
                print('  %-3s %-13s→%-13s %6.1fkm  %2d站  %s'
                      % (ref, tr['terminals'][0][:6], tr['terminals'][1][:6],
                         tr['km'], len(tr['stops']), tr['color']))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--network', default='', help='OSM route=subway 的 network 标签，如 成都地铁')
    ap.add_argument('--boundary', default='', help='行政边界名称，如 成都市')
    ap.add_argument('--bbox', required=True, help='S,W,N,E')
    ap.add_argument('--rings', default='', help='环线 name 标签，逗号分隔（由外到内）')
    ap.add_argument('--out', default='data')
    ap.add_argument('--skip-fetch', action='store_true', help='用已有 data/*.json 只做编译')
    a = ap.parse_args()
    D = Path(a.out)
    D.mkdir(parents=True, exist_ok=True)
    BB = '(%s)' % a.bbox

    names = {}
    routes_path = D / 'routes_geom.json'
    if a.skip_fetch:
        if not routes_path.exists():
            raise SystemExit('--skip-fetch 需要 %s 已存在' % routes_path)
        routes = json.load(open(routes_path, encoding='utf-8'))
        names = {str(k): v for k, v in
                 json.load(open(D / 'stop_names.json', encoding='utf-8')).items()} \
            if (D / 'stop_names.json').exists() else {}
    else:
        print('[1/4] 线路关系')
        routes = overpass('[out:json][timeout:300];rel["route"="subway"]'
                          '["network"="%s"]%s;out body geom;' % (a.network, BB),
                          routes_path)
        print('[2/4] 站名')
        st = overpass('[out:json][timeout:180];'
                      '(node["railway"="station"]["station"="subway"]%s;'
                      'node["railway"="station"]["subway"="yes"]%s;);out tags;'
                      % (BB, BB), D / 'stop_names.json')
        names = {str(e['id']): (e.get('tags', {}).get('name') or '')
                 for e in st.get('elements', [])}
        if a.boundary:
            print('[3/4] 城市边界')
            overpass('[out:json][timeout:180];rel["boundary"="administrative"]'
                     '["name"="%s"];out geom;' % a.boundary, D / 'city_boundary.json')
        if a.rings:
            print('[4/4] 环线')
            rings = {}
            for rn in [s.strip() for s in a.rings.split(',') if s.strip()]:
                raw = overpass('[out:json][timeout:180];'
                               '(rel["name"="%s"];way["name"="%s"];);out geom;' % (rn, rn),
                               D / ('ring_%s.json' % rn))
                segs = []
                for e in raw.get('elements', []):
                    if e['type'] == 'relation':
                        for m in e.get('members', []):
                            g = m.get('geometry') or []
                            if m.get('type') == 'way' and len(g) >= 2:
                                segs.append([[p['lon'], p['lat']] for p in g])
                    else:
                        g = e.get('geometry') or []
                        if len(g) >= 2:
                            segs.append([[p['lon'], p['lat']] for p in g])
                if segs:
                    rings[rn] = segs
                    print('  %-14s %d segs' % (rn, len(segs)))
            if rings:
                json.dump({'rings': rings}, open(D / 'rings.json', 'w', encoding='utf-8'),
                          ensure_ascii=False)

    lat0 = float(a.bbox.split(',')[0]) + 0.3
    compile_lines(routes, names, lat0, D / 'lines.json')


if __name__ == '__main__':
    main()
