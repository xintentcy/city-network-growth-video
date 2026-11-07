# -*- coding: utf-8 -*-
"""解说词与章节内容（事实口径：成都轨道集团公开发布，截至 2025.12）。"""

CHAPTERS = [
    dict(id='intro', date=None, title='2010 年以前', chips=[],
         cn='十五年前，成都人出门，先看是堵在一环、二环，还是三环。',
         en='Fifteen years ago, getting around Chengdu meant one question: '
            'stuck on the 1st Ring, the 2nd, or the 3rd?'),

    dict(id='2010-09-27', date='2010-09-27', title='2010.09.27',
         chips=[('1', '升仙湖—世纪城')],
         cn='2010 年 9 月 27 日，1 号线一期通车，18.5 公里，南北穿过主城。这是西部第一条地铁。',
         en='Sept 27, 2010: Line 1 opens, 18.5 km north to south — the first metro in western China.'),

    dict(id='2012-09-16', date='2012-09-16', title='2012.09.16',
         chips=[('2', '茶店子客运站—成都行政学院')],
         cn='两年后，2 号线一期开通，东西向拉出一条线。一横一竖，主城有了个十字。',
         en='Two years later, Line 2 cuts east to west. The city now has a cross.'),

    dict(id='2013-06-08', date='2013-06-08', title='2013.06.08',
         chips=[('2', '茶店子客运站—犀浦')],
         cn='2013 年，2 号线往西伸到犀浦，郫都的大学城接进了线网。',
         en='2013: Line 2 reaches west to Xipu, pulling in the university town of Pidu.'),

    dict(id='2014-10-26', date='2014-10-26', title='2014.10.26',
         chips=[('2', '成都行政学院—龙泉驿')],
         cn='一年后往东，成都第一条高架地铁通到龙泉驿，出了三环。',
         en='A year on, the city’s first elevated line runs east to Longquanyi — beyond the 3rd Ring.'),

    dict(id='2015-07-25', date='2015-07-25', title='2015.07.25',
         chips=[('1', '世纪城—广都 / 四河')],
         cn='2015 年，1 号线继续往南，第一次伸进天府新区。',
         en='2015: Line 1 pushes south into Tianfu New Area.'),

    dict(id='2015-12-26', date='2015-12-26', title='2015.12.26',
         chips=[('4', '非遗博览园—万年场')],
         cn='年底，4 号线一期开通，东西向再多一条骨干。',
         en='By year end, Line 4 opens — another east-west backbone.'),

    dict(id='2016-07-31', date='2016-07-31', title='2016.07.31',
         chips=[('3', '军区总医院—太平园')],
         cn='2016 年，3 号线一期来了，米字骨架成形。',
         en='2016: Line 3 arrives, and the cross grows into a star.'),

    dict(id='2017-06-02', date='2017-06-02', title='2017.06.02',
         chips=[('4', '万盛—非遗博览园 / 万年场—西河')],
         cn='4 号线二期两头延伸，温江和西河都进了线网。',
         en='Line 4 extends both ways, bringing Wenjiang and Xihe onto the map.'),

    dict(id='2017-09-06', date='2017-09-06', title='2017.09.06',
         chips=[('10', '太平园—双流机场')],
         cn='9 月，10 号线通到双流机场。赶飞机，第一次可以坐地铁。',
         en='September: Line 10 reaches Shuangliu Airport. For the first time, you can take the metro to a flight.'),

    dict(id='2017-12-06', date='2017-12-06', title='2017.12.06',
         chips=[('7', '环线 · 全线通车')],
         cn='12 月，7 号线成环。地铁第一次自己围成一个圈，这个圈，正好落在二环和三环之间。',
         en='December: Line 7 closes the loop — the metro’s first ring, sitting neatly between the 2nd and 3rd Ring Roads.'),

    dict(id='2018-03-18', date='2018-03-18', title='2018.03.18',
         chips=[('1', '韦家碾 / 科学城 / 五根松')],
         cn='2018 年，1 号线三期北到韦家碾，南到科学城，一条线拉到四十一公里。',
         en='2018: Line 1 stretches to Weijianian in the north and Science City in the south — 41 km end to end.'),

    dict(id='2018-12-26', date='2018-12-26', title='2018.12.26',
         chips=[('3', '双流西站 / 成都医学院')],
         cn='年底，3 号线南北延伸，新都和双流接进来。',
         en='Year end: Line 3 extends both ways, adding Xindu and Shuangliu.'),

    dict(id='2019-12-27', date='2019-12-27', title='2019.12.27',
         chips=[('5', '华桂路—回龙'), ('10', '太平园—新平')],
         cn='2019 年，5 号线和 10 号线二期开通，线网第一次超过三百公里。',
         en='2019: Lines 5 and 10 phase 2 open. The network passes 300 km.'),

    dict(id='2020-09-27', date='2020-09-27', title='2020.09.27',
         chips=[('18', '火车南站—三岔')],
         cn='2020 年 9 月，18 号线开出主城，时速一百四十公里的市域快线，一路东南到三岔。镜头得往后退了。',
         en='Sept 2020: Line 18 leaves the city core — a 140 km/h express running southeast to Sancha. Time to pull the camera back.'),

    dict(id='2020-12-18', date='2020-12-18', title='2020.12.18',
         chips=[('6', '望丛祠—兰家沟'), ('8', '十里店—莲花'), ('9', '金融城东—黄田坝'),
                ('17', '九江北—机投桥'), ('18', '三岔—天府机场北')],
         cn='三个月后，五条线同一天开通，线网五百五十八公里。一年新增两百多公里。',
         en='Three months later, five lines open on one day: 558 km. Over 200 km added in a single year.'),

    dict(id='2023-11-28', date='2023-11-28', title='2023.11.28',
         chips=[('19', '九江北—天府站')],
         cn='2023 年，19 号线二期通车。双流机场和天府机场，第一次能坐地铁一线直达。',
         en='2023: Line 19 phase 2 links Shuangliu and Tianfu airports on one ride.'),

    dict(id='2024-09-29', date='2024-09-29', title='2024.09.29',
         chips=[('S3', '福田—资阳北站')],
         cn='2024 年 9 月，S3 资阳线开通。地铁第一次开出成都，到了隔壁的资阳。',
         en='Sept 2024: the S3 Ziyang line opens — the metro leaves Chengdu for the first time.'),

    dict(id='2024-12-19', date='2024-12-19', title='2024.12.19',
         chips=[('8', '十里店—桂龙路 / 莲花—龙港'), ('27', '石佛—蜀鑫路')],
         cn='年底，8 号线二期和 27 号线开通，线网到了六百四十多公里。',
         en='Year end: Line 8 phase 2 and Line 27 open. The network passes 640 km.'),

    dict(id='2025-09-17', date='2025-09-17', title='2025.09.17',
         chips=[('17', '机投桥—高洪'), ('10', '武侯祠—太平园')],
         cn='2025 年 9 月，17 号线二期、10 号线三期开通，线网六百七十多公里。',
         en='Sept 2025: Line 17 phase 2 and Line 10 phase 3 open. Past 670 km.'),

    dict(id='2025-12-16', date='2025-12-16', title='2025.12.16',
         chips=[('13', '瓦窑滩—龙安'), ('30', '双流机场2航站楼东—龙泉驿火车站南')],
         cn='12 月 16 日，13 号线和 30 号线开通。十七条地铁，七百一十六公里。',
         en='Dec 16: Lines 13 and 30 open. Seventeen lines, 716 km.'),

    dict(id='outro', date=None, title='2025.12', chips=[],
         cn='十五年前，一环以内就是成都。现在，地铁铺到了绕城外面，最远的一站，已经出了成都市界。',
         en='Fifteen years ago, Chengdu meant inside the 1st Ring. Today the metro runs past the Ring Expressway — '
            'and its farthest station is out of town.'),
]

# 片头前的城市环线说明（叠加在开场）
RING_NOTE = '城市环线参照：一环 · 二环 · 三环 · 绕城高速'

TAGS = {
    "intro": "",
    "2010-09-27": "升仙湖—世纪城",
    "2012-09-16": "茶店子客运站—成都行政学院",
    "2013-06-08": "茶店子客运站—犀浦",
    "2014-10-26": "成都行政学院—龙泉驿 · 首条高架",
    "2015-07-25": "世纪城—广都 / 四河",
    "2015-12-26": "非遗博览园—万年场",
    "2016-07-31": "军区总医院—太平园",
    "2017-06-02": "万盛—非遗博览园 / 万年场—西河",
    "2017-09-06": "太平园—双流机场",
    "2017-12-06": "环线全线成环",
    "2018-03-18": "韦家碾 / 科学城 / 五根松",
    "2018-12-26": "双流西站 / 成都医学院",
    "2019-12-27": "华桂路—回龙 / 太平园—新平",
    "2020-09-27": "火车南站—三岔",
    "2020-12-18": "五线齐发 · 同日开通",
    "2023-11-28": "九江北—天府站",
    "2024-09-29": "福田—资阳北站",
    "2024-12-19": "两线开通",
    "2025-09-17": "机投桥—高洪 / 武侯祠—太平园",
    "2025-12-16": "两线开通 · 首次越过绕城",
    "outro": ""
}

for _c in CHAPTERS:
    _c['tag'] = TAGS.get(_c['id'], '')
