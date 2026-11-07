# city-network-growth-video

把「一张线网随时间长大」变成一部 2–4 分钟的解说短片：城市地铁 / 轨道 / 公交 / 管网按真实开通日期逐年生长，配章节解说、城市环线空间参照、推近—行进—拉回镜头、逐站点亮、程序化配乐与混音。

真实几何从 OSM 来，开通日期从官方公告来，里程按官方口径锚定。**禁止编造线路与站名** —— 这类片的全部价值在「数据可信」，所以走程序化渲染，不用 AI 生成视频（生成模型会顺手编线路走向、换乘关系）。

## 什么时候用

- 要「某城市地铁/轨道 XX 年发展」视频，或给一个同类参考片要仿制
- 要「线网扩张动态图 + 解说」，且在意数据准确性
- 城市有明确的环线（一环/二环/三环/绕城），需要空间参照系
- 需要「带时间和地理双维度」的生长动画（管网、高速、公交、校区扩张同理）

**不要用**：只要一张静态地图、只要一段无数据的酷炫动画、用户明确要 AI 生成影像。

## 前置条件

- Python 3.10+，`Pillow`、`numpy`、`edge-tts`
- ffmpeg（`config._ff()` 会依次找 `FFMPEG` 环境变量 / PATH / 常见安装路径）
- 能访问 overpass-api.de（或 kumi.systems 镜像）
- Windows 中文字体（雅黑 / 等线 / Segoe UI）；其他平台需改 `render_core.py` 顶部 `FNT`

## 快速开始

把 `scripts/` 全部复制到项目根目录，按下面顺序跑。每一步都有「验收点」，不通过不要往下走。

```text
项目/
├ config.py            ← 换城市只改这个
├ content.py           ← 章节文案（每章一句中文 + 一句英文）
├ data/
│   ├ openings.csv     ← 开通事件表（事实骨架）
│   ├ lines.json  rings.json  scene_raw.json  scene2.json  voice.json
├ audio/               ← <chapter>.wav + bgm.wav
└ out/                 ← 成片、封面、segs/
```

### 阶段 1｜事实基线（不可跳过）

把「每年开通了哪一段、多少公里」列成表，每条都能指到来源。交付物是 `data/openings.csv`：

```csv
date,ref,from,to,hint
2010-09-27,1,升仙湖,世纪城,科学城
2017-12-06,7,崔家店,崔家店,崔家店      # 环线成环：首=末
```

同时确认三个官方**里程锚点**（首通 / 中段 / 末章），写进 `config.ANCH`。没有锚点就不要做 KPI——用几何长度当里程会差 3–6%。

> 完整实例见 `assets/reference/openings.example.csv`（成都 2010–2025，37 行）。

### 阶段 2｜几何

```bash
python fetch_network.py --network 成都地铁 --boundary 成都市 \
    --bbox 30.0,103.4,31.35,104.75 --rings 一环路,二环路,成都三环路,成都绕城高速
```

产出 `data/lines.json`（折线 + 站点 + 颜色 + 几何长度）和 `rings.json`。

> Overpass 公共实例经常 502/超时。脚本单次请求 90 s、最多试 2 轮。遇阻时去 https://overpass-turbo.eu 手动跑同一条查询，把结果存成 `data/routes_geom.json`（站名存 `data/stop_names.json`），再 `python fetch_network.py --skip-fetch --bbox ...` 只做编译。

### 阶段 3｜分段（把日期挂到几何上）

```bash
python build_openings.py
```

把 `openings.csv` 每行匹配到具体轨道，算出归一化里程区间 `[t0,t1]`。

**验收点**：每条轨道 `cover≈1.00` 且 `gaps=[]`。出现 `!!` 说明漏了开通公告，补 CSV 再跑。

### 阶段 4｜章节文案

写 `content.py`（结构照抄 `assets/reference/content.example.py`）：

```python
CHAPTERS = [
    dict(id='intro', date=None, title='2010 年以前', chips=[],
         cn='十五年前，成都人出门，先看是堵在一环、二环，还是三环。',
         en='Fifteen years ago, ...'),
    dict(id='2010-09-27', date='2010-09-27', title='2010.09.27',
         chips=[('1', '升仙湖—世纪城')], cn='……', en='……'),
    dict(id='outro', date=None, title='2025.12', chips=[], cn='……', en='……'),
]
```

写作要求：

- 中文一句话讲清「这次开通改变了什么」，**不要年报体**
- `chips` 第二项必须是 `首站—末站`：它同时驱动徽标、主角线判定、行进方向
- 数字与画面 KPI 必须一致；拿不准就用「六百七十多公里」这类模糊口径
- 英文是同义的短句，不是逐字直译

### 阶段 5｜解说

```bash
pip install edge-tts
python tts_chapters.py                          # 云扬，-6%
python tts_chapters.py zh-CN-XiaoxiaoNeural 0   # 换音色/语速
```

产出 `audio/<id>.wav` + `data/voice.json`。**时间轴由这里的实测时长驱动**，必须先跑这一步再编译场景。

### 阶段 6｜编译场景

```bash
python compile_scene.py
```

产出 `data/scene2.json`：投影后的轨道、分段、章节时间轴、里程锚定、镜头目标。

### 阶段 7｜预览 → 整片渲染

```bash
python render_core.py preview 2,7.5,20,60,130,175   # 先看 6 帧
python render_all.py 480                            # 分段渲染 + concat
```

**必须走分段**：单条 rawvideo 管道跑 5000+ 帧会卡死。`render_all.py` 支持断点续跑，改一章只重渲那几段。

### 阶段 8｜配乐与混音

```bash
python music.py     # 程序化配乐 → audio/bgm.wav + bgm.npy
python mix.py       # 解说 + BGM（ducking）→ out/mix.wav
```

**验收点**：`mix.py` 打印的 `nar_rms / bgm_rms` 差值应在 **10–12 dB**。

### 阶段 9｜封装与交付

```bash
python assemble.py                     # -c:v copy，只换音轨
python verify.py out/成片.mp4           # 全绿才交付
```

封面从成片抽一帧（挑信息量与辨识度最高的，通常是「环线成环」或「全网最满」）。

## 关键决策速查

| 问题 | 结论 |
|---|---|
| 一章开 5 条线，聚焦哪条 | 新增里程最大的那条；其余按普通进度生长 |
| 推镜幅度 | `clamp(max(bbox*1.16, 18), net/2.9, net)` |
| 行进时长 | `max(0.055*站数+0.6, 0.042*公里+0.8)`，夹在 1.6–5.0 s |
| 章末留白 | 拉远 1.2 s，起点 `max(jt1+0.35, tE-1.45)` |
| 环线层级 | 外淡内实（128/146/160/176），讲「出圈」时才高亮 |
| BGM 调性 | 明亮题材用大调 112 BPM，I–V–vi–IV；氛围题材才用小调慢速 |
| BGM 配比 | 比解说低 10–12 dB（明亮律动型取上限） |
| 交付响度 | -12 ~ -14 LUFS，TP ≤ -0.2 dBTP |

## 五个必踩的坑（提前绕开）

1. **Pillow 的 alpha 是覆盖不是混合**：半透明光晕会把线洗白。必须拆 `bas`（实色）与 `eff`（半透明）两层，最后 `Image.alpha_composite`。
2. **新段判定要用对象身份** `id(seg) in newids`，不能用日期区间比较。
3. **反向线路**：OSM 方向常与官方公告相反。按 `chips` 的「首站—末站」判 `rev`。
4. **章首不能空镜**：先画整条 corridor 虚影（α≈46）+ 未到站空心环，再叠行进光效。
5. **响度用 LUFS 判断，不要用 RMS**；**削波要逐样点算，不要用正则解析 volumedetect**。

## 目录结构

```text
.
├ SKILL.md                      ← 完整技能说明（含全部公式与故障对照）
├ README.md
├ LICENSE
├ references/                   ← data-pipeline / motion-design / audio / visual-system / qa-checklist
├ assets/reference/             ← 成都 2010–2025 完整实例（content.example.py / openings.example.csv）
└ scripts/                      ← 全部流水线脚本
```

## 换城市/换题材怎么改

1. `config.py`：品牌文案、年份、`LON0/LAT0`、视口、`ANCH`、环线名与顺序、`EXCLUDE_STATIONS`、`LINES_ORDER`、片尾 KPI
2. `content.py`：重写章节（数量可增减，时间轴会自动重排）
3. `openings.csv`：换成该城市的开通公告
4. `render_core.py` 通常不用改；只有版式大改时才动 `PX/PR`、`CN_X/CN_W`、`VX/VY/VW/VH`

## License

[MIT](./LICENSE)
