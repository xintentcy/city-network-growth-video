# 动效设计与实现规格

这套片子的动效不是"线条生长的粒子效果"，而是**一条叙事线**：每章讲一次开通，
镜头推近到这条线 → 一个光点从首站跑到末站 → 沿途站点依次点亮 → 镜头拉回全网。
所有时间参数都由章节时长和解说长度反推，不写死。

## 1. 章节时间轴

```
片头：    start=0,        nA=2.6,                     tE = nA + voice + 1.4
中间章：  start=t+GAP,    nA=start+LEAD,              tE = nA + voice + TAIL
片尾：    start=t+1.0,    nA=start+0.7,               tE = nA + voice + 3.0
总时长：  TOTAL = tE_last + END_HOLD(4.8)
```
`GAP=0.5 LEAD=0.4 TAIL=0.58`。`voice` 是 TTS 实测时长（`data/voice.json`）。
**不要**按文案字数估时长——中文 TTS 的时长差异足够让字幕和推镜错位半秒。

## 2. 镜头：连续关键帧，不是"每章一段缓动"

早期版本给每章单独算 from→to 再做缓动，结果章与章之间必然出现一次"跳"。
改成一条贯穿全片的 `KFS=[(t, span, cx, cy, ease)]`，`cam_at(t)` 用二分查段插值：

```python
def cam_at(t):
    i = bisect_left(KTS, t) - 1
    a, b = KFS[max(i,0)], KFS[min(i+1, len(KFS)-1)]
    x = clamp((t - a[0]) / max(1e-6, b[0] - a[0]), 0, 1)
    e = b[4]
    x = 1-(1-x)**3 if e=='out' else (x**3 if e=='in' else x*x*(3-2*x))
    return lerp(a[1:4], b[1:4], x)
```

每章固定四拍（时长由章节长度自适应）：

| 拍 | 时间点 | 动作 | 缓动 |
|---|---|---|---|
| 落定 | `tA` | 保持上一章的全网构图 | inout |
| 推近 | `tA → tA+0.95` | 推到主角线 | `1-(1-x)³`（起步快、收尾软） |
| 行进 | `jt0 → jt1` | 光点跑首→末 | 线性（节奏感来自等速） |
| 停顿 | `jt1 → pl0` | 停住看末站 | — |
| 拉回 | `pl0 → pl1` | 退回全网 | smoothstep |

关键帧序列：

```python
KFS.append((ch.tA, *hold, 'inout'))
KFS.append((f.pt1, f.span, f.cx, f.cy, 'out'))
KFS.append((f.pl0, f.span*1.06, f.cx, f.cy, 'inout'))
KFS.append((f.pl1, *f.net, 'inout'))
hold = list(f.net)          # 下一章从这个构图起跳
```

## 3. 推镜幅度（span）

```python
fit  = max(w*1.16, h*1.16*ASPECT, 18)     # 线路 bbox，留 16% 边距
span = min(fit, net*1.0)                  # 不为取全景而拉远
span = max(span, net/2.9)                 # 单次推近不超过全网的 2.9 倍
```
`net` 是"该章结束时全网所需 span"（`cams[i].to`）。
两个 clamp 缺一不可：不设上限，短支线会推到糊；不设下限，长线一推就是
"从上往下看一只蚂蚁"，观众失去空间感。

## 4. 主角线（每章只聚焦一条）

一章可能同时开通 5 条线（2020-12-18 五线齐发）。规则：**新增里程最大者当主角**，
其余线按普通进度生长。

```python
for len(ref) in chapter.chips:
    segs = [sg for tr in tracks if tr.ref==ref for sg in tr.segs if sg.date==ch.date]
    newkm = sum(sg.km for sg in segs)      # 同 ref 多条轨道时取里程最大那条
choose ref with max(newkm)
```

**判定新段必须用对象身份 `id(sg) in newids`，不能用日期区间比较。**
同一条轨道上属于其它日期的分段会被区间比较误判成"本章新增"，后果是章首整条线
已经画满、里程虚高 6 km。

## 5. 行进方向

以章节标注的"首站—末站"为准。OSM 的 line 方向取决于 way 串接顺序，和官方公告
经常相反：

```python
lab = ch.chips[0][1]                  # 例：'福田—资阳北站'
if lab.split('—')[0].strip() == st[-1].name and lab.split('—')[-1].strip() == st[0].name:
    rev = True
    st = sorted(st, key=lambda s: plen - s.d)   # 站序倒置
```
反向时**里程坐标也要倒**（`d → plen-d`），否则站点点亮顺序和光点位置对不上。

## 6. 行进动画的三个坐标

这是最容易写错的地方，务必分清：

- `p ∈ [0,1]`：行进进度（时间函数）
- `head = d1*p`（反向 `head = d1-d1*p`）：光点在**路径里程坐标**上的位置
- `travel = d1*p`：已经走过的里程（永远单调增，用于里程读数）

主角线的新增段由光点推进（"线随车走"）：

```python
def seg_prog(sg, ref, t, L):
    f = FOC[当前章]
    if id(sg) in f.newids:
        head = head_coord(f, focus_state(t)[2])
        a, b = (sg.t0 - f.tb) * L, (sg.t1 - f.tb) * L   # 必须减 tb（路径起点）
        return clamp((head - a) / (b - a), 0, 1) if not f.rev \
          else clamp((b - head) / (b - a), 0, 1)
    return clamp((t - sg.tA) / sg.dur, 0, 1)
```
`tb` 是这条聚焦路径覆盖的轨道起点（归一化里程）。漏掉 `tb` 会让里程读数在
反向章节里 2 秒内倒跳 29 km。

## 7. 行进时长

```python
cap  = max(1.3, (tE - 1.45) - 0.35 - jt0)          # 章尾必须留出拉远时间
jdur = clamp(max(0.055*n_st + 0.60, plen*0.042 + 0.80), 1.6, min(5.0, cap))
```
两条经验权重：**每站 55 ms**（站点多要留出点亮节奏）+ **每公里 42 ms**（长线要跑得久），
取大者，再夹在 1.6–5.0 s。2020-12-18 六号线 56 站 68 km → 3.68 s；2010 一号线
12 站 18 km → 1.6 s（下限）。

## 8. 站点视觉语法

| 状态 | 画法 | 意义 |
|---|---|---|
| 未到站 | 空心环 `r=3`，`near` 随距离 0.45→1.0 变亮 | "路已铺好，站还没点亮" |
| 刚到站 | 白芯 + 线色环，`pop = 1+0.55*sin(g·π)` 回弹 0.26 s | 到站的那一下 |
| 到站涟漪 | 外扩 `4.4→21px`，0.52 s 淡出 | 冲击感 |
| 新增站 | 额外外扩环 1.05 s | 本章首次出现 |
| 末站收束 | `7→35px` 环，0.9 s，`(1-q)^1.4` | 讲完了 |

**章首不能是空镜**：整条 corridor 先以 `α≈46` 描出虚影（width 5），
再叠行进柔光（width 16, α54）+ 拖尾（11 段递减排布）。
没有这一层，镜头推过去画面是空的，观众以为卡了。

## 9. 站名标注（屏幕空间贪心避让）

1. 先放普通站名（只放在已点亮的站），四方向候选 `lm / rm / mb / mt`，间距 11 px
2. 每个候选框外扩 `PAD=4` 做碰撞检测，还要满足安全区 `x∈[596,1886], y∈[68,896]`
3. 都放不下就**放弃这个站名**（宁可少一个，不要叠字）
4. 当前站最后放，用高亮胶囊 + 引线，优先级最高（先占位会把当前站挤掉）

密集章节（56 站）中部会有 2–3 处重叠，属于可接受损耗；要彻底解决只能做
"标签抽稀"（按缩放级别分级显示），代价是信息密度下降。

## 10. 双层 alpha 合成（Pillow 的坑）

`ImageDraw.Draw(rgba_img)` 直接画半透明白色光晕时，**alpha 是被覆盖而不是混合**，
结果是线被"洗白"到几乎看不见（实测 RGB 27,34,82，应为 89,78,248）。

正确做法是拆两层再真混合：

```python
bas = Image.new('RGBA', size, (0,0,0,0))   # 环线 + 轨道：实色，width 10-12
eff = Image.new('RGBA', size, (0,0,0,0))   # 站点/光晕/拖尾/涟漪：半透明
...
return Image.alpha_composite(bas, eff).reduce(SS)
```
`ImageDraw.Draw(ov, 'RGBA')` 也救不了，它只影响绘制模式，不影响写入方式。

## 11. 生长头部

非聚焦线路的分段按 `(t - tA)/dur` 长出来，头部画 9 层降透明度光晕 + 白芯，
半径 26 px。**聚焦线在全线走完前跳过生长头部**，否则光点后面会拖一颗多余的白球。

## 12. 性能预算

- 2× 超采样（`SS=2` → 3840×2160 画布）+ `.reduce(2)`：抗锯齿，代价 ×4 像素
- 单帧 0.55–0.65 s（i5 级 CPU），5774 帧 ≈ 60 分钟
- 泛光用 `GaussianBlur(12)` + `ImageChops.add`，不要逐图层 blur
- 环线与轨道做折线抽稀（`min_d=2.0`），否则 1320px 视口里画十几万点
