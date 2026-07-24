# -*- coding: utf-8 -*-
"""
植物生长数据采集与分析工具
==========================
配套教材:清华大学出版社《信息科技》五年级下册
          第2单元 第4课《植物生长日志——数据采集》(教材 P71—78)

工具定位:
    在电脑上模拟"给植物做生长日志"的完整过程:
    定时采集温度/湿度/光照/株高 → 表格查看 → 发现缺失和异常数据 →
    逐条清洗(剔除/标记/保留) → 画折线图看生长趋势 → 统计并导出分析报告。
    学生既可以导入老师提供的示例 CSV 练习"找坑",
    也可以自己开启模拟采集,调节采样间隔和传感器故障概率,
    体会"采样越密数据越细、传感器有故障数据就会缺失或离谱"的道理。

技术说明(写给老师):
    * 仅使用 Python 标准库(tkinter / ttk / csv / random / statistics /
      math / os / re / datetime),无需安装任何第三方库,可在 Windows 上离线运行。
    * 折线图用 tkinter Canvas 手绘,不依赖 matplotlib;
      缺失数据处折线断开,异常数据画红叉,被"标记存疑"的数据画橙色三角。
    * 模拟采集用 root.after() 定时驱动,没有使用线程;
      关闭窗口时会正确取消 after 任务,不会有残留进程。
    * 数据判定规则(简单、可解释,方便课堂讨论):
        - 温度合理范围 0~45℃;湿度 0~100%;光照 0~100000 lux;株高 0~200cm;
        - 株高比之前记录矮 1cm 以上 → 可疑(植物不会变矮);
          一次猛长超过 6cm → 可疑(不符合生长规律);
        - 空白单元格 → 缺失数据。
    * 统计特意"不自动剔除"可疑数据:学生不清洗,平均值就会被 88℃ 这类
      离谱数据带歪;剔除后统计立刻变化——让学生亲眼看到清洗的价值。
    * 导入 CSV 只读取内容到内存(处理的是副本),绝不修改原文件;
      导出文件写入本脚本所在目录,文件名自动加时间戳,不覆盖已有文件。
"""

import csv
import math
import os
import random
import re
import datetime
import statistics
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------
# 全局常量
# ---------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 四个指标的定义:内部键名 / 中文名 / 单位 / 合理下限 / 合理上限 / 折线颜色
METRICS = [
    ("temp",   "温度", "℃",   0.0, 45.0,     "#e05d44"),
    ("humi",   "湿度", "%",    0.0, 100.0,    "#2b7de9"),
    ("light",  "光照", "lux",  0.0, 100000.0, "#f59e0b"),
    ("height", "株高", "cm",   0.0, 200.0,    "#2eb872"),
]
KEYS = [m[0] for m in METRICS]
NAME2KEY = {m[1]: m[0] for m in METRICS}
KEY2META = {m[0]: m for m in METRICS}

HEIGHT_DROP_LIMIT = 1.0   # 株高比之前矮超过 1cm → 可疑
HEIGHT_JUMP_LIMIT = 6.0   # 株高一次猛增超过 6cm → 可疑

HELP_TEXT = """【植物生长数据采集与分析工具 · 快速帮助】

一、界面分区
  ① 数据区(左上):表格显示每一条采集记录。
     红色行 = 含可疑(异常)数据;黄色行 = 含缺失数据;
     灰色行 = 已剔除;橙色行 = 已标记存疑;绿色行 = 已确认保留。
  ② 采集模拟区(右上):选采样间隔(1/2/6/12小时)、拖故障概率滑块、
     定模拟天数,然后用 开始采集 / 暂停 / 单步 / 重置 控制模拟。
  ③ 图表区(左下):Canvas 折线图。可切换主指标、叠加第二指标
     (双轴对比),拖"起点/终点"滑块只看某一段时间。
     缺失处折线断开,异常数据画红叉,标记存疑画橙色三角。
  ④ 数据清洗区(右中):点「找可疑数据」列出全部候选,
     逐条选择 剔除 / 标记存疑 / 保留,每次处理都有理由说明。
  ⑤ 结果区(右下):各指标平均/最高/最低、总生长量、日均生长速度;
     导出清洗后CSV / 导出分析报告TXT / 导入CSV / 帮助。

二、推荐玩法
  1. 点「导入CSV」打开《示例数据_植物生长记录.csv》,
     先在表格里找一找:哪些行是黄色(缺失)?哪些行是红色(异常)?
  2. 看结果区:88℃ 这样的离谱数据会把平均温度带歪!
  3. 点「找可疑数据」,逐条判断:传感器坏了就剔除,
     拿不准就标记存疑,确认是真实情况就保留。
  4. 在图表区切换指标、叠加对比(比如 温度+湿度),
     观察它们一天内此起彼伏的规律,再看株高的生长趋势。
  5. 点「开始采集」继续模拟往后采集,试试把故障概率调大,
     看看数据会变成什么样。
  6. 最后导出清洗后 CSV 和分析报告 TXT,写下你的发现。

三、数据判定规则(和课堂讨论用)
  温度 0~45℃、湿度 0~100%、光照 0~100000lux、株高 0~200cm 之外 → 可疑;
  株高比之前矮 1cm 以上,或一次猛长超过 6cm → 可疑;
  空白 → 缺失。统计不会自动剔除可疑数据,要靠你亲手清洗!

四、文件安全
  导入的 CSV 只被"读取",原文件绝不会被修改;
  导出文件保存在本程序所在文件夹,文件名自动加时间戳,不覆盖旧文件。

更多内容请阅读同文件夹中的《使用说明.txt》。"""


class GrowthApp:
    """植物生长数据采集与分析工具主程序(单窗口 Tkinter 应用)"""

    # ===========================================================
    # 初始化
    # ===========================================================
    def __init__(self, root):
        self.root = root
        root.title("植物生长数据采集与分析工具 · 清华版《信息科技》五下 第2单元第4课")
        root.geometry("1220x820")
        root.minsize(1080, 720)

        # ---- 数据:每条记录是一个字典 ----
        # {"day":int, "hour":float, "values":{key:float或None},
        #  "status":{key:"ok"/"missing"/"abnormal"/"removed"},
        #  "handle":None/"剔除"/"标记"/"保留", "reasons":[理由文字]}
        self.records = []
        self.suspects = []       # 找可疑数据的候选:[记录下标, ...]
        self.clean_log = []      # 清洗操作记录(导出报告用)

        # ---- 模拟采集引擎状态 ----
        self.running = False
        self.after_id = None
        self.tick_interval_ms = 280   # 每条模拟数据的真实间隔(毫秒)
        self.sim_day = 1              # 模拟时钟:下一条数据的天数
        self.sim_hour = 0.0           # 模拟时钟:下一条数据的小时
        self.sim_height = 5.0         # 模拟植物当前株高(cm)
        self.sim_remaining = 0        # 本轮还要采集的条数
        self.sim_total = 0            # 累计模拟生成的条数

        # ---- 可调参数(与界面控件绑定)----
        self.var_interval = tk.StringVar(value="6")   # 采样间隔(小时)
        self.var_fault = tk.IntVar(value=10)          # 传感器故障概率(%)
        self.var_days = tk.IntVar(value=3)            # 模拟天数
        self.var_metric1 = tk.StringVar(value="株高")  # 图表主指标
        self.var_metric2 = tk.StringVar(value="(无)")  # 图表叠加指标
        self.var_range_a = tk.IntVar(value=0)         # 时间范围起点(%)
        self.var_range_b = tk.IntVar(value=100)       # 时间范围终点(%)

        self.help_win = None
        self._ui_ready = False
        self._build_ui()
        self._ui_ready = True

        # 窗口关闭时先停止模拟、取消 after 任务,再销毁窗口
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.set_msg("欢迎使用!点「导入CSV」打开示例数据,或点「开始采集」模拟采集。点「帮助」查看玩法。")
        self.refresh_all()

    # ===========================================================
    # 界面搭建
    # ===========================================================
    def _build_ui(self):
        base_font = ("Microsoft YaHei UI", 10)   # Windows 用微软雅黑,其他系统自动回退
        self.root.option_add("*Font", base_font)

        # ---- 顶部标题 ----
        header = tk.Frame(self.root, bg="#1f7a4d")
        header.pack(fill="x")
        tk.Label(header, text="🌱 植物生长数据采集与分析工具",
                 font=("Microsoft YaHei UI", 16, "bold"),
                 bg="#1f7a4d", fg="white").pack(side="left", padx=14, pady=6)
        tk.Label(header,
                 text="第2单元 第4课 植物生长日志——数据采集 · 完全离线 · 数据仅存本机",
                 bg="#1f7a4d", fg="#d7f2e3").pack(side="left", padx=6)

        # ---- 底部消息栏 ----
        self.lbl_msg = tk.Label(self.root, anchor="w", fg="#1f7a4d",
                                bg="#eef7f1", padx=10)
        self.lbl_msg.pack(side="bottom", fill="x")

        body = tk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        right = tk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # ================= ① 数据区 =================
        data_frame = tk.LabelFrame(left, text="① 数据区:采集记录表(红=可疑 黄=缺失 灰=已剔除 橙=已标记 绿=已保留)",
                                   padx=4, pady=2)
        data_frame.pack(fill="both", expand=True)

        cols = ("no", "day", "time", "temp", "humi", "light", "height", "state")
        heads = ("序号", "日期", "时间", "温度(℃)", "湿度(%)", "光照(lux)", "株高(cm)", "状态")
        widths = (44, 62, 54, 76, 76, 86, 76, 120)
        self.tree = ttk.Treeview(data_frame, columns=cols, show="headings", height=11)
        for c, hd, w in zip(cols, heads, widths):
            self.tree.heading(c, text=hd)
            self.tree.column(c, width=w, anchor="center", stretch=(c == "state"))
        ysb = ttk.Scrollbar(data_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        # 行颜色:异常红、缺失黄、剔除灰、标记橙、保留绿
        self.tree.tag_configure("abnormal", background="#ffd9d9", foreground="#a02020")
        self.tree.tag_configure("missing", background="#fff3c4", foreground="#7a5b00")
        self.tree.tag_configure("removed", background="#e4e4e4", foreground="#909090")
        self.tree.tag_configure("marked", background="#ffe6c7", foreground="#8a5200")
        self.tree.tag_configure("kept", background="#def3e3", foreground="#1f5c38")

        # ================= ③ 图表区 =================
        chart_frame = tk.LabelFrame(left, text="③ 图表区:折线图(缺失断线 · 异常红叉 · 标记橙三角)",
                                    padx=4, pady=2)
        chart_frame.pack(fill="both", expand=True, pady=(4, 0))

        bar = tk.Frame(chart_frame)
        bar.pack(fill="x")
        tk.Label(bar, text="指标:").pack(side="left")
        self.cmb_metric1 = ttk.Combobox(bar, textvariable=self.var_metric1, width=6,
                                        state="readonly",
                                        values=[m[1] for m in METRICS])
        self.cmb_metric1.pack(side="left")
        tk.Label(bar, text=" 叠加对比:").pack(side="left")
        self.cmb_metric2 = ttk.Combobox(bar, textvariable=self.var_metric2, width=6,
                                        state="readonly",
                                        values=["(无)"] + [m[1] for m in METRICS])
        self.cmb_metric2.pack(side="left")
        self.cmb_metric1.bind("<<ComboboxSelected>>", self.redraw_chart)
        self.cmb_metric2.bind("<<ComboboxSelected>>", self.redraw_chart)
        tk.Label(bar, text=" 时间范围 起点").pack(side="left")
        tk.Scale(bar, variable=self.var_range_a, from_=0, to=95, orient="horizontal",
                 length=110, showvalue=False,
                 command=self._on_range_change).pack(side="left")
        tk.Label(bar, text="终点").pack(side="left")
        tk.Scale(bar, variable=self.var_range_b, from_=5, to=100, orient="horizontal",
                 length=110, showvalue=False,
                 command=self._on_range_change).pack(side="left")
        self.lbl_range = tk.Label(bar, text="全部", fg="#5b7186")
        self.lbl_range.pack(side="left", padx=4)

        self.chart = tk.Canvas(chart_frame, height=270, bg="white",
                               highlightthickness=1, highlightbackground="#c8d6cd")
        self.chart.pack(fill="both", expand=True, pady=(2, 2))
        self.chart.bind("<Configure>", self.redraw_chart)

        # ================= ② 采集模拟区 =================
        sim_frame = tk.LabelFrame(right, text="② 采集模拟区:虚拟传感器定时采样", padx=8, pady=4)
        sim_frame.pack(fill="x")

        row = tk.Frame(sim_frame)
        row.pack(fill="x", pady=1)
        tk.Label(row, text="采样间隔:每").pack(side="left")
        cmb = ttk.Combobox(row, textvariable=self.var_interval, width=4,
                           state="readonly", values=["1", "2", "6", "12"])
        cmb.pack(side="left")
        cmb.bind("<<ComboboxSelected>>",
                 lambda e: self.set_msg("采样间隔改为每 %s 小时一次:间隔越小,数据越细,记录也越多。"
                                        % self.var_interval.get()))
        tk.Label(row, text="小时采 1 次").pack(side="left")
        tk.Label(row, text="   模拟天数:").pack(side="left")
        tk.Spinbox(row, textvariable=self.var_days, from_=1, to=30,
                   width=4, state="readonly").pack(side="left")
        tk.Label(row, text="天").pack(side="left")

        row2 = tk.Frame(sim_frame)
        row2.pack(fill="x", pady=1)
        tk.Label(row2, text="传感器故障概率").pack(side="left")
        tk.Scale(row2, variable=self.var_fault, from_=0, to=30, resolution=5,
                 orient="horizontal", length=150, showvalue=True,
                 command=self._on_fault_change).pack(side="left", fill="x", expand=True)
        tk.Label(row2, text="%(故障=缺失或离谱值)").pack(side="left")

        row3 = tk.Frame(sim_frame)
        row3.pack(fill="x", pady=(3, 1))
        self.btn_start = tk.Button(row3, text="▶ 开始采集", width=9,
                                   bg="#2eb872", fg="white",
                                   activebackground="#1e8f56", command=self.start_sim)
        self.btn_start.pack(side="left", padx=2)
        self.btn_pause = tk.Button(row3, text="⏸ 暂停", width=7, command=self.pause_sim)
        self.btn_pause.pack(side="left", padx=2)
        tk.Button(row3, text="⏭ 单步", width=7,
                  command=self.step_sim).pack(side="left", padx=2)
        tk.Button(row3, text="🔄 重置", width=7,
                  command=self.reset_all).pack(side="left", padx=2)

        self.lbl_sim = tk.Label(sim_frame, anchor="w", fg="#1a5cb8", justify="left")
        self.lbl_sim.pack(fill="x", pady=(2, 0))

        # ================= ④ 数据清洗区 =================
        clean_frame = tk.LabelFrame(right, text="④ 数据清洗区:找出可疑数据,逐条处理", padx=8, pady=4)
        clean_frame.pack(fill="both", expand=True, pady=(4, 0))

        tk.Button(clean_frame, text="🔍 找可疑数据(缺失 + 异常)",
                  bg="#f59e0b", fg="white", activebackground="#c47d05",
                  command=self.find_suspects).pack(fill="x", pady=(0, 3))

        lb_row = tk.Frame(clean_frame)
        lb_row.pack(fill="both", expand=True)
        self.lst_suspects = tk.Listbox(lb_row, height=5, activestyle="dotbox",
                                       font=("Microsoft YaHei UI", 9))
        self.lst_suspects.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lb_row, orient="vertical", command=self.lst_suspects.yview)
        sb.pack(side="right", fill="y")
        self.lst_suspects.configure(yscrollcommand=sb.set)
        self.lst_suspects.bind("<<ListboxSelect>>", self._on_suspect_select)

        btns = tk.Frame(clean_frame)
        btns.pack(fill="x", pady=2)
        tk.Button(btns, text="❌ 剔除", bg="#e5484d", fg="white",
                  activebackground="#b32e33",
                  command=lambda: self.handle_suspect("剔除")
                  ).pack(side="left", fill="x", expand=True, padx=1)
        tk.Button(btns, text="⚠ 标记存疑", bg="#f59e0b", fg="white",
                  activebackground="#c47d05",
                  command=lambda: self.handle_suspect("标记")
                  ).pack(side="left", fill="x", expand=True, padx=1)
        tk.Button(btns, text="✔ 保留", bg="#2eb872", fg="white",
                  activebackground="#1e8f56",
                  command=lambda: self.handle_suspect("保留")
                  ).pack(side="left", fill="x", expand=True, padx=1)

        self.lbl_feedback = tk.Label(clean_frame, anchor="nw", justify="left",
                                     wraplength=380, fg="#20344b", bg="#f4f8f5",
                                     relief="groove", bd=1, padx=6, pady=4, height=4)
        self.lbl_feedback.pack(fill="x", pady=(2, 0))
        self._set_feedback("先点「找可疑数据」,再逐条选择怎么处理。\n"
                           "剔除=数据坏了不要;标记=拿不准先留着;保留=确认是真的。")

        # ================= ⑤ 结果区 =================
        result_frame = tk.LabelFrame(right, text="⑤ 结果区:统计与导出", padx=8, pady=4)
        result_frame.pack(fill="x", pady=(4, 0))
        self.lbl_stats = tk.Label(result_frame, justify="left", anchor="w",
                                  fg="#20344b", font=("Microsoft YaHei UI", 9))
        self.lbl_stats.pack(fill="x")

        grid = tk.Frame(result_frame)
        grid.pack(fill="x", pady=3)
        tk.Button(grid, text="📥 导出清洗后CSV",
                  command=self.export_csv).grid(row=0, column=0, padx=2, pady=1, sticky="ew")
        tk.Button(grid, text="📄 导出分析报告TXT",
                  command=self.export_report).grid(row=0, column=1, padx=2, pady=1, sticky="ew")
        tk.Button(grid, text="📂 导入CSV(只读副本)",
                  command=self.import_csv).grid(row=1, column=0, padx=2, pady=1, sticky="ew")
        tk.Button(grid, text="❓ 帮助",
                  command=self.show_help).grid(row=1, column=1, padx=2, pady=1, sticky="ew")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        tk.Label(result_frame, fg="#5b7186", anchor="w", justify="left",
                 text="导入只读取内容,原文件不会被修改;导出文件保存在本程序\n所在文件夹,文件名自动加时间戳,不覆盖旧文件。"
                 ).pack(fill="x")

    # ===========================================================
    # 小工具:消息栏 / 清洗反馈
    # ===========================================================
    def set_msg(self, text):
        self.lbl_msg.configure(text="💬 " + text)

    def _set_feedback(self, text):
        self.lbl_feedback.configure(text=text)

    def _on_fault_change(self, _value=None):
        if not self._ui_ready:
            return
        self.set_msg("传感器故障概率调为 %d%%:概率越大,缺失和离谱数据越多,越考验你的清洗本领!"
                     % self.var_fault.get())

    def _on_range_change(self, _value=None):
        if not self._ui_ready:
            return
        # 保证起点在终点之前(留 5% 最小窗口)
        if self.var_range_a.get() > self.var_range_b.get() - 5:
            self.var_range_a.set(max(0, self.var_range_b.get() - 5))
        self.redraw_chart()

    @staticmethod
    def time_of(rec):
        """记录的绝对时间(小时数),用于横轴定位"""
        return (rec["day"] - 1) * 24.0 + rec["hour"]

    @staticmethod
    def time_str(rec):
        return "第%d天 %02d:%02d" % (rec["day"], int(rec["hour"]),
                                     round(rec["hour"] % 1 * 60))

    @staticmethod
    def fmt_val(key, v):
        """把数值格式化成表格/图表用的文字;None 显示为 (缺失)"""
        if v is None:
            return "(缺失)"
        if key == "light":
            return "%d" % round(v)
        return "%.1f" % v

    # ===========================================================
    # 数据判定:重算每条记录每个指标的状态(核心规则,见文件头注释)
    # ===========================================================
    def recompute_status(self):
        last_good_h = None    # 之前最近一次"可信"的株高,用于骤降/猛增判断
        for rec in self.records:
            rec["reasons"] = []
            status = {}
            if rec["handle"] == "剔除":
                for k in KEYS:
                    status[k] = "removed"
                rec["status"] = status
                continue
            kept = (rec["handle"] == "保留")
            for key, name, unit, lo, hi, _color in METRICS:
                v = rec["values"][key]
                if v is None:
                    status[key] = "missing"
                    rec["reasons"].append("%s缺失:这一时刻没有采到%s数据" % (name, name))
                    continue
                bad = None
                if v < lo or v > hi:
                    bad = ("%s=%s%s 超出合理范围(%s~%s%s),很可能是传感器故障"
                           % (name, self.fmt_val(key, v), unit,
                              self.fmt_val(key, lo), self.fmt_val(key, hi), unit))
                elif key == "height" and last_good_h is not None:
                    if v < last_good_h - HEIGHT_DROP_LIMIT:
                        bad = ("株高从 %.1fcm 骤降到 %.1fcm:植物不会突然变矮,数据可疑"
                               % (last_good_h, v))
                    elif v > last_good_h + HEIGHT_JUMP_LIMIT:
                        bad = ("株高从 %.1fcm 猛增到 %.1fcm:一次长这么多不符合生长规律"
                               % (last_good_h, v))
                if bad and not kept:
                    status[key] = "abnormal"
                    rec["reasons"].append(bad)
                else:
                    status[key] = "ok"
                    # 学生"保留"的异常株高不更新基准,避免连锁误报
                    if key == "height" and bad is None:
                        last_good_h = v
            rec["status"] = status

    def row_flag(self, rec):
        """整行的显示标签(优先级:剔除>标记>保留>异常>缺失>正常)"""
        if rec["handle"] == "剔除":
            return "removed", "已剔除"
        if rec["handle"] == "标记":
            return "marked", "已标记存疑"
        if rec["handle"] == "保留":
            return "kept", "已确认保留"
        st = rec["status"].values()
        if "abnormal" in st:
            bad = [KEY2META[k][1] for k in KEYS if rec["status"][k] == "abnormal"]
            return "abnormal", "可疑:" + "、".join(bad)
        if "missing" in st:
            miss = [KEY2META[k][1] for k in KEYS if rec["status"][k] == "missing"]
            return "missing", "缺失:" + "、".join(miss)
        return "", "正常"

    # ===========================================================
    # 界面刷新:表格 / 图表 / 统计 / 模拟状态
    # ===========================================================
    def refresh_all(self):
        self.recompute_status()
        self.refresh_table()
        self.redraw_chart()
        self.update_stats()
        self.update_sim_label()

    def refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, rec in enumerate(self.records):
            tag, state_text = self.row_flag(rec)
            vals = (i + 1, "第%d天" % rec["day"],
                    "%02d:%02d" % (int(rec["hour"]), round(rec["hour"] % 1 * 60)),
                    self.fmt_val("temp", rec["values"]["temp"]),
                    self.fmt_val("humi", rec["values"]["humi"]),
                    self.fmt_val("light", rec["values"]["light"]),
                    self.fmt_val("height", rec["values"]["height"]),
                    state_text)
            self.tree.insert("", "end", iid=str(i), values=vals,
                             tags=(tag,) if tag else ())
        # 自动滚到最新一条,方便观察模拟采集的新数据
        kids = self.tree.get_children()
        if kids:
            self.tree.see(kids[-1])

    def update_sim_label(self):
        self.lbl_sim.configure(
            text="模拟时钟:下一条 = 第%d天 %02d:00   |   本轮剩余:%d 条\n"
                 "累计模拟生成:%d 条   |   当前株高:%.1fcm   |   记录总数:%d 条"
                 % (self.sim_day, int(self.sim_hour), self.sim_remaining,
                    self.sim_total, self.sim_height, len(self.records)))

    # ===========================================================
    # ② 模拟采集:开始 / 暂停 / 单步 / 重置(root.after 驱动,不用线程)
    # ===========================================================
    def start_sim(self):
        if self.running:
            return
        if self.sim_remaining <= 0:
            # 开始新一轮:按"模拟天数 × 每天次数"计算本轮要采集的条数
            interval = int(self.var_interval.get())
            self.sim_remaining = self.var_days.get() * 24 // interval
        self.running = True
        self.btn_start.configure(state="disabled")
        self.set_msg("模拟采集开始:每 %s 小时采 1 次,本轮共 %d 条。观察表格里新数据不断流入!"
                     % (self.var_interval.get(), self.sim_remaining))
        self._schedule_next()

    def pause_sim(self):
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(state="normal")
        self._cancel_after()
        self.set_msg("模拟已暂停:可以点「单步」一条一条采,或先去清洗数据。")

    def step_sim(self):
        """单步:先暂停,再采集一条,方便逐条观察"""
        if self.running:
            self.pause_sim()
        if self.sim_remaining <= 0:
            interval = int(self.var_interval.get())
            self.sim_remaining = self.var_days.get() * 24 // interval
        self._collect_once()
        self.set_msg("单步采集了 1 条数据(第%d条),看看它正常吗?" % len(self.records))

    def reset_all(self):
        """重置:清空全部数据和清洗记录,模拟时钟归零(参数设置保持不变)"""
        self.pause_sim()
        self.records = []
        self.suspects = []
        self.clean_log = []
        self.lst_suspects.delete(0, "end")
        self.sim_day, self.sim_hour = 1, 0.0
        self.sim_height = 5.0
        self.sim_remaining = 0
        self.sim_total = 0
        self._set_feedback("已重置。先点「找可疑数据」,再逐条选择怎么处理。")
        self.set_msg("已重置:数据、图表、清洗记录全部清空(参数设置保持不变)。")
        self.refresh_all()

    def _schedule_next(self):
        self.after_id = self.root.after(self.tick_interval_ms, self._sim_loop)

    def _cancel_after(self):
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _sim_loop(self):
        self.after_id = None
        if not self.running:
            return
        self._collect_once()
        if self.sim_remaining <= 0:
            # 本轮采集完成:自动停下来,提示学生分析数据
            self.running = False
            self.btn_start.configure(state="normal")
            self.set_msg("本轮模拟采集完成!去「找可疑数据」清洗一下,再看看图表和统计吧。")
            return
        self._schedule_next()

    # -----------------------------------------------------------
    # 生成一条带日变化规律的模拟数据(含传感器故障)
    # -----------------------------------------------------------
    def _collect_once(self):
        day, hour = self.sim_day, self.sim_hour
        # 白天系数:6点~18点按正弦从0升到1再降回0,夜里为0
        if 6.0 <= hour <= 18.0:
            daylight = math.sin(math.pi * (hour - 6.0) / 12.0)
        else:
            daylight = 0.0
        # 温度:夜里约17℃,中午最高约26℃;湿度与温度大致相反;光照白天强夜里为0
        temp = 17.5 + 9.0 * daylight + random.gauss(0, 0.6)
        humi = min(98.0, max(35.0, 78.0 - 20.0 * daylight + random.gauss(0, 2.0)))
        light = max(0.0, 26000.0 * daylight + (random.gauss(0, 800) if daylight > 0 else 0.0))
        # 株高:按约 1.05cm/天 稳步生长
        interval = int(self.var_interval.get())
        self.sim_height += 1.05 * interval / 24.0 + random.uniform(0, 0.06)
        values = {"temp": round(temp, 1), "humi": round(humi, 1),
                  "light": round(light), "height": round(self.sim_height, 1)}

        # 传感器故障:按概率随机挑一个指标,让它缺失或变成离谱值
        if random.random() < self.var_fault.get() / 100.0:
            key = random.choice(KEYS)
            if random.random() < 0.5:
                values[key] = None
            else:
                weird = {"temp": random.choice([88.0, -12.0]),
                         "humi": random.choice([150.0, -5.0]),
                         "light": -999.0,
                         "height": round(max(0.3, values["height"] * 0.2), 1)}
                values[key] = weird[key]

        self.records.append({"day": day, "hour": hour, "values": values,
                             "status": {}, "handle": None, "reasons": []})
        self.sim_total += 1
        self.sim_remaining = max(0, self.sim_remaining - 1)

        # 模拟时钟前进一个采样间隔
        h = hour + interval
        self.sim_day += int(h // 24)
        self.sim_hour = h % 24
        self.refresh_all()

    def _sync_sim_clock(self):
        """导入数据后,让模拟时钟接在最后一条记录之后继续"""
        if not self.records:
            self.sim_day, self.sim_hour, self.sim_height = 1, 0.0, 5.0
            return
        last = self.records[-1]
        interval = int(self.var_interval.get())
        h = last["hour"] + interval
        self.sim_day = last["day"] + int(h // 24)
        self.sim_hour = h % 24
        # 株高基准取最后一条状态正常的株高
        self.recompute_status()
        heights = [r["values"]["height"] for r in self.records
                   if r["values"]["height"] is not None
                   and r["status"].get("height") == "ok"]
        self.sim_height = heights[-1] if heights else 5.0

    # ===========================================================
    # ④ 数据清洗:找可疑 → 逐条处理(剔除/标记/保留)
    # ===========================================================
    def find_suspects(self):
        """扫描全部记录,把未处理过的缺失/异常行列出来"""
        self.recompute_status()
        self.suspects = [i for i, rec in enumerate(self.records)
                         if rec["handle"] is None
                         and ("abnormal" in rec["status"].values()
                              or "missing" in rec["status"].values())]
        self.lst_suspects.delete(0, "end")
        for i in self.suspects:
            rec = self.records[i]
            brief = rec["reasons"][0] if rec["reasons"] else "?"
            # 列表里显示简短版,选中后在反馈区看完整理由
            self.lst_suspects.insert(
                "end", "第%d条 %s | %s" % (i + 1, self.time_str(rec),
                                           brief.split(":")[0]))
        n = len(self.suspects)
        if n == 0:
            self._set_feedback("没有找到未处理的可疑数据,数据很干净!\n"
                               "(已处理过的行不会重复出现。)")
            self.set_msg("扫描完成:0 条可疑数据。")
        else:
            self.lst_suspects.selection_set(0)
            self._on_suspect_select()
            self.set_msg("扫描完成:找到 %d 条可疑数据(表格中红色/黄色行)。请逐条判断怎么处理。" % n)
        self.refresh_table()

    def _selected_suspect(self):
        sel = self.lst_suspects.curselection()
        if not sel or sel[0] >= len(self.suspects):
            return None, None
        return sel[0], self.suspects[sel[0]]

    def _on_suspect_select(self, _event=None):
        pos, idx = self._selected_suspect()
        if idx is None:
            return
        rec = self.records[idx]
        # 同步选中表格对应行,方便对照查看
        try:
            self.tree.selection_set(str(idx))
            self.tree.see(str(idx))
        except Exception:
            pass
        reasons = "\n".join("· " + r for r in rec["reasons"]) or "· (无)"
        self._set_feedback("第%d条(%s)为什么可疑?\n%s\n请选择:❌剔除(坏数据不要) ⚠标记(拿不准) ✔保留(是真的)"
                           % (idx + 1, self.time_str(rec), reasons))

    def handle_suspect(self, action):
        """对当前选中的可疑记录执行 剔除/标记/保留,并给出理由反馈"""
        pos, idx = self._selected_suspect()
        if idx is None:
            self._set_feedback("请先点「找可疑数据」,再在列表里选中一条,才能处理哦。")
            return
        rec = self.records[idx]
        reason_brief = ";".join(rec["reasons"]) or "无"
        rec["handle"] = action

        # 面向学生的即时反馈:说明这样处理意味着什么
        if action == "剔除":
            fb = ("已剔除第%d条:%s。\n这条数据被判定为坏数据,统计和图表都不再使用它——"
                  "就像实验记录本上划掉写错的一行。" % (idx + 1, reason_brief))
        elif action == "标记":
            fb = ("已标记第%d条为存疑:%s。\n它仍然参与统计,但表格里变成橙色、图上画橙色三角,"
                  "提醒大家用它时要多留个心眼。" % (idx + 1, reason_brief))
        else:
            fb = ("已保留第%d条:你确认它是真实情况(比如那天真的特别热)。\n"
                  "它恢复为正常数据,照常参与统计和画图。" % (idx + 1))
        self._set_feedback(fb)
        self.clean_log.append("[%s] 第%d条 %s → %s(%s)"
                              % (datetime.datetime.now().strftime("%H:%M:%S"),
                                 idx + 1, self.time_str(rec), action, reason_brief))

        # 从候选列表移除,并自动选中下一条
        self.suspects.pop(pos)
        self.lst_suspects.delete(pos)
        if self.suspects:
            nxt = min(pos, len(self.suspects) - 1)
            self.lst_suspects.selection_set(nxt)
        self.refresh_all()
        if self.suspects:
            self._on_suspect_select()
        else:
            self.set_msg("可疑数据全部处理完毕!看看结果区的统计有什么变化?")

    # ===========================================================
    # ③ 图表:Canvas 手绘折线图(双轴对比 / 缺失断线 / 异常红叉)
    # ===========================================================
    def redraw_chart(self, _event=None):
        if not self._ui_ready:
            return
        c = self.chart
        c.delete("all")
        w = max(c.winfo_width(), 320)
        h = max(c.winfo_height(), 180)
        ml, mr, mt, mb = 56, 56, 26, 30      # 四边留白(左右各留一条数值轴)

        if not self.records:
            c.create_text(w / 2, h / 2, text="暂无数据:请「导入CSV」或「开始采集」",
                          fill="#8ba394", font=("Microsoft YaHei UI", 12))
            return

        key1 = NAME2KEY[self.var_metric1.get()]
        name2 = self.var_metric2.get()
        key2 = NAME2KEY.get(name2)
        if key2 == key1:
            key2 = None      # 叠加同一个指标没有意义,按"无"处理

        # ---- 按时间范围滑块截取可见记录 ----
        times = [self.time_of(r) for r in self.records]
        tmin, tmax = min(times), max(times)
        span = max(tmax - tmin, 1e-6)
        t0 = tmin + span * self.var_range_a.get() / 100.0
        t1 = tmin + span * self.var_range_b.get() / 100.0
        visible = [(i, r) for i, r in enumerate(self.records)
                   if t0 - 1e-9 <= self.time_of(r) <= t1 + 1e-9]
        self.lbl_range.configure(
            text="第%.1f~%.1f天" % (t0 / 24.0 + 1, t1 / 24.0 + 1)
            if (self.var_range_a.get(), self.var_range_b.get()) != (0, 100) else "全部")
        if not visible:
            c.create_text(w / 2, h / 2, text="这个时间范围内没有数据,请调整滑块",
                          fill="#8ba394", font=("Microsoft YaHei UI", 11))
            return

        def x_of(t):
            return ml + (w - ml - mr) * (t - t0) / max(t1 - t0, 1e-6)

        # ---- 纵轴范围:只按状态正常的数值自动缩放(离谱值贴边画,不压扁曲线)----
        def axis_range(key):
            vals = [r["values"][key] for _i, r in visible
                    if r["handle"] != "剔除" and r["values"][key] is not None
                    and r["status"].get(key) == "ok"]
            if not vals:
                lo, hi = KEY2META[key][3], KEY2META[key][4]
            else:
                lo, hi = min(vals), max(vals)
                pad = max((hi - lo) * 0.12, 0.5)
                lo, hi = lo - pad, hi + pad
            return lo, hi

        # ---- 网格与横轴(按"天"打刻度)----
        c.create_rectangle(ml, mt, w - mr, h - mb, outline="#c8d6cd")
        day0, day1 = int(t0 // 24), int(t1 // 24) + 1
        step = max(1, (day1 - day0) // 10)
        for d in range(day0, day1 + 1, step):
            t = d * 24.0
            if t0 <= t <= t1:
                x = x_of(t)
                c.create_line(x, mt, x, h - mb, fill="#eef3ef")
                c.create_text(x, h - mb + 12, text="第%d天" % (d + 1),
                              fill="#7b8f83", font=("Microsoft YaHei UI", 8))

        def draw_axis(key, side):
            """画一条纵轴(side='left'/'right'),返回 value→y 的换算函数"""
            lo, hi = axis_range(key)
            _k, name, unit, _lo, _hi, color = KEY2META[key]

            def y_of(v):
                y = (h - mb) - (h - mb - mt) * (v - lo) / max(hi - lo, 1e-6)
                return min(max(y, mt + 4), h - mb - 4)   # 离谱值贴边显示

            for j in range(5):
                v = lo + (hi - lo) * j / 4.0
                y = (h - mb) - (h - mb - mt) * j / 4.0
                if side == "left":
                    c.create_line(ml, y, w - mr, y, fill="#f2f6f3")
                    c.create_text(ml - 4, y, text=self.fmt_val(key, v),
                                  anchor="e", fill=color, font=("Microsoft YaHei UI", 8))
                else:
                    c.create_text(w - mr + 4, y, text=self.fmt_val(key, v),
                                  anchor="w", fill=color, font=("Microsoft YaHei UI", 8))
            label_x = ml - 4 if side == "left" else w - mr + 4
            c.create_text(label_x, mt - 12, text="%s(%s)" % (name, unit),
                          anchor="e" if side == "left" else "w",
                          fill=color, font=("Microsoft YaHei UI", 9, "bold"))
            return y_of

        def draw_series(key, y_of, dash=None):
            """画一条折线:正常点连线,缺失/剔除断开,异常红叉,标记橙三角"""
            color = KEY2META[key][5]
            prev = None
            for _i, rec in visible:
                if rec["handle"] == "剔除":
                    prev = None
                    continue
                v = rec["values"][key]
                if v is None:                     # 缺失 → 折线断开
                    prev = None
                    continue
                x = x_of(self.time_of(rec))
                st = rec["status"].get(key, "ok")
                if st == "abnormal":
                    y = y_of(v)
                    if rec["handle"] == "标记":   # 橙色三角 = 存疑但保留
                        c.create_polygon(x, y - 6, x - 6, y + 5, x + 6, y + 5,
                                         fill="", outline="#f59e0b", width=2)
                    else:                          # 红叉 = 未处理的异常
                        c.create_line(x - 5, y - 5, x + 5, y + 5,
                                      fill="#e5484d", width=2)
                        c.create_line(x - 5, y + 5, x + 5, y - 5,
                                      fill="#e5484d", width=2)
                    prev = None                    # 异常点两侧折线断开
                    continue
                y = y_of(v)
                if prev is not None:
                    c.create_line(prev[0], prev[1], x, y, fill=color,
                                  width=2, dash=dash)
                c.create_oval(x - 2.5, y - 2.5, x + 2.5, y + 2.5,
                              fill=color, outline="")
                prev = (x, y)

        y1 = draw_axis(key1, "left")
        draw_series(key1, y1)
        if key2:
            y2 = draw_axis(key2, "right")
            draw_series(key2, y2, dash=(4, 3))

        # ---- 图例 ----
        lx = ml + 8
        c.create_line(lx, mt + 8, lx + 22, mt + 8, fill=KEY2META[key1][5], width=2)
        c.create_text(lx + 26, mt + 8, text=KEY2META[key1][1], anchor="w",
                      fill=KEY2META[key1][5], font=("Microsoft YaHei UI", 9))
        if key2:
            lx2 = lx + 70
            c.create_line(lx2, mt + 8, lx2 + 22, mt + 8, fill=KEY2META[key2][5],
                          width=2, dash=(4, 3))
            c.create_text(lx2 + 26, mt + 8, text=KEY2META[key2][1], anchor="w",
                          fill=KEY2META[key2][5], font=("Microsoft YaHei UI", 9))

    # ===========================================================
    # ⑤ 统计:平均/最高/最低、总生长量、日均生长速度
    # ===========================================================
    def _included_values(self, key):
        """参与统计的数值:未剔除、非缺失(注意:未处理的异常值也算,会把统计带歪!)"""
        return [r["values"][key] for r in self.records
                if r["handle"] != "剔除" and r["values"][key] is not None]

    def _growth_info(self):
        """总生长量与日均速度:用状态正常的株高的首末两条计算"""
        good = [(self.time_of(r), r["values"]["height"], r) for r in self.records
                if r["handle"] != "剔除" and r["values"]["height"] is not None
                and r["status"].get("height") == "ok"]
        if len(good) < 2:
            return None
        (ta, ha, ra), (tb, hb, rb) = good[0], good[-1]
        days = max((tb - ta) / 24.0, 1e-6)
        return {"total": hb - ha, "days": days, "rate": (hb - ha) / days,
                "from": (ra, ha), "to": (rb, hb)}

    def update_stats(self):
        lines = []
        for key, name, unit, _lo, _hi, _c in METRICS:
            vals = self._included_values(key)
            if vals:
                lines.append("%s:平均 %s%s | 最高 %s%s | 最低 %s%s(%d个值)"
                             % (name, self.fmt_val(key, statistics.mean(vals)), unit,
                                self.fmt_val(key, max(vals)), unit,
                                self.fmt_val(key, min(vals)), unit, len(vals)))
            else:
                lines.append("%s:暂无数据" % name)
        g = self._growth_info()
        if g:
            lines.append("总生长量:%.1fcm(%s %.1fcm → %s %.1fcm)"
                         % (g["total"], self.time_str(g["from"][0]), g["from"][1],
                            self.time_str(g["to"][0]), g["to"][1]))
            lines.append("日均生长速度:%.2f cm/天(跨度 %.1f 天)" % (g["rate"], g["days"]))
        else:
            lines.append("总生长量 / 日均生长速度:株高有效数据不足")

        self.recompute_status()
        n_ab = sum(1 for r in self.records if r["handle"] is None
                   and "abnormal" in r["status"].values())
        n_ms = sum(1 for r in self.records if r["handle"] is None
                   and "missing" in r["status"].values())
        n_rm = sum(1 for r in self.records if r["handle"] == "剔除")
        n_mk = sum(1 for r in self.records if r["handle"] == "标记")
        summary = ("记录 %d 条 | 未处理可疑 %d 条 | 未处理缺失 %d 条 | 已剔除 %d | 已标记 %d"
                   % (len(self.records), n_ab, n_ms, n_rm, n_mk))
        if n_ab:
            summary += "\n⚠ 还有可疑数据没处理,上面的统计可能被离谱值带歪了!"
        lines.append(summary)
        self.lbl_stats.configure(text="\n".join(lines))

    # ===========================================================
    # 导入 CSV(只读取内容到内存 = 处理副本,绝不修改原文件)
    # ===========================================================
    def import_csv(self, path=None):
        if self.running:
            self.pause_sim()
        if path is None:
            path = filedialog.askopenfilename(
                title="选择植物生长记录 CSV(只读取,不会修改原文件)",
                initialdir=SCRIPT_DIR,
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
            if not path:
                return False
        try:
            rows = self._read_csv_rows(path)
            new_records = self._parse_rows(rows)
            if not new_records:
                raise ValueError("没有解析到任何数据行")
        except Exception as exc:
            messagebox.showerror(
                "导入失败",
                "无法读取这个 CSV 文件:\n%s\n\n请确认表头包含 日期/时间/温度/湿度/光照/株高。" % exc,
                parent=self.root)
            return False

        self.records = new_records
        self.suspects = []
        self.clean_log = []
        self.lst_suspects.delete(0, "end")
        self._sync_sim_clock()
        self.refresh_all()
        n_issue = sum(1 for r in self.records
                      if "abnormal" in r["status"].values()
                      or "missing" in r["status"].values())
        self.set_msg("已导入 %d 条记录(只读取了副本,原文件未被修改)。表格里有 %d 行标了颜色,"
                     "点「找可疑数据」开始清洗吧!" % (len(self.records), n_issue))
        self._set_feedback("导入完成:共 %d 条记录,其中 %d 行含缺失或异常。\n"
                           "先观察表格颜色,再点「找可疑数据」。" % (len(self.records), n_issue))
        return True

    @staticmethod
    def _read_csv_rows(path):
        """读 CSV,自动尝试 utf-8-sig 和 gbk 两种常见编码"""
        for enc in ("utf-8-sig", "gbk"):
            try:
                with open(path, "r", encoding=enc, newline="") as f:
                    return list(csv.reader(f))
            except UnicodeDecodeError:
                continue
        raise ValueError("文件编码无法识别(试过 utf-8 和 gbk)")

    def _parse_rows(self, rows):
        """把 CSV 行解析成记录列表:按表头关键字找列,数值留空视为缺失"""
        rows = [r for r in rows if any(cell.strip() for cell in r)]
        if not rows:
            return []
        header = rows[0]
        col = {}
        for i, cell in enumerate(header):
            cell = cell.strip()
            for kw, key in (("日期", "day"), ("时间", "time"), ("温度", "temp"),
                            ("湿度", "humi"), ("光照", "light"), ("株高", "height")):
                if kw in cell and key not in col:
                    col[key] = i
        for key in KEYS:
            if key not in col:
                raise ValueError("表头里找不到「%s」列" % KEY2META[key][1])

        records = []
        base_date = None
        for lineno, row in enumerate(rows[1:], start=2):
            # ---- 日期:支持 "第X天" / 纯数字 / YYYY-MM-DD(自动换算为第几天)----
            day = len(records) // 4 + 1     # 兜底:没有日期列时粗略排
            if "day" in col and col["day"] < len(row):
                raw = row[col["day"]].strip()
                m = re.search(r"第\s*(\d+)\s*天", raw)
                if m:
                    day = int(m.group(1))
                elif raw.isdigit():
                    day = int(raw)
                else:
                    try:
                        d = datetime.date.fromisoformat(raw.replace("/", "-"))
                        if base_date is None:
                            base_date = d
                        day = (d - base_date).days + 1
                    except ValueError:
                        pass
            # ---- 时间:HH:MM,缺省按行内顺序排 0/6/12/18 点 ----
            hour = (len(records) % 4) * 6.0
            if "time" in col and col["time"] < len(row):
                m = re.search(r"(\d{1,2})[::](\d{1,2})", row[col["time"]])
                if m:
                    hour = int(m.group(1)) + int(m.group(2)) / 60.0
            # ---- 四个指标:空白 → None(缺失);解析失败也按缺失处理 ----
            values = {}
            for key in KEYS:
                raw = row[col[key]].strip() if col[key] < len(row) else ""
                if raw == "":
                    values[key] = None
                else:
                    try:
                        values[key] = float(raw)
                    except ValueError:
                        values[key] = None
            records.append({"day": day, "hour": hour, "values": values,
                            "status": {}, "handle": None, "reasons": []})
        return records

    # ===========================================================
    # 导出:清洗后 CSV / 分析报告 TXT(写到脚本目录,时间戳文件名不覆盖)
    # ===========================================================
    @staticmethod
    def _unique_path(prefix, ext):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCRIPT_DIR, "%s_%s%s" % (prefix, stamp, ext))
        n = 1
        while os.path.exists(path):
            path = os.path.join(SCRIPT_DIR, "%s_%s_%d%s" % (prefix, stamp, n, ext))
            n += 1
        return path

    def export_csv(self):
        """导出清洗后的 CSV:已剔除的行不写入;标记/保留情况写进备注列"""
        if not self.records:
            self.set_msg("还没有数据可导出:先「导入CSV」或「开始采集」。")
            return None
        self.recompute_status()
        path = self._unique_path("清洗后_植物生长记录", ".csv")
        n_rm = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["日期", "时间", "温度(℃)", "湿度(%)",
                             "光照(lux)", "株高(cm)", "清洗备注"])
            for rec in self.records:
                if rec["handle"] == "剔除":
                    n_rm += 1
                    continue
                note = {"标记": "标记存疑", "保留": "确认保留"}.get(rec["handle"], "")
                miss = [KEY2META[k][1] for k in KEYS
                        if rec["status"].get(k) == "missing"]
                if miss:
                    note = (note + ";" if note else "") + "缺失:" + "、".join(miss)
                writer.writerow(
                    ["第%d天" % rec["day"],
                     "%02d:%02d" % (int(rec["hour"]), round(rec["hour"] % 1 * 60))]
                    + ["" if rec["values"][k] is None else self.fmt_val(k, rec["values"][k])
                       for k in KEYS]
                    + [note])
        self.set_msg("清洗后数据已导出:%s(写入 %d 条,剔除的 %d 条未写入;原文件未被修改)。"
                     % (os.path.basename(path), len(self.records) - n_rm, n_rm))
        return path

    def export_report(self):
        """生成分析报告 TXT:数据概况、统计、清洗记录和留给学生的思考题"""
        if not self.records:
            self.set_msg("还没有数据可分析:先「导入CSV」或「开始采集」。")
            return None
        self.recompute_status()
        n_ab = sum(1 for r in self.records if r["handle"] is None
                   and "abnormal" in r["status"].values())
        n_ms = sum(1 for r in self.records if r["handle"] is None
                   and "missing" in r["status"].values())
        n_rm = sum(1 for r in self.records if r["handle"] == "剔除")
        n_mk = sum(1 for r in self.records if r["handle"] == "标记")
        n_kp = sum(1 for r in self.records if r["handle"] == "保留")
        days = sorted({r["day"] for r in self.records})

        lines = [
            "=" * 46,
            "  植物生长数据采集与分析报告",
            "=" * 46,
            "课程:清华版《信息科技》五年级下册 第2单元 第4课",
            "      植物生长日志——数据采集",
            "生成时间:%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "",
            "一、数据概况",
            "  记录总数:%d 条(第%d天 ~ 第%d天,共 %d 天)" %
            (len(self.records), days[0], days[-1], len(days)),
            "  未处理可疑:%d 条 | 未处理缺失:%d 条" % (n_ab, n_ms),
            "  已剔除:%d 条 | 已标记存疑:%d 条 | 已确认保留:%d 条" % (n_rm, n_mk, n_kp),
            "",
            "二、各指标统计(不含已剔除行;缺失值不参与计算)",
        ]
        for key, name, unit, _lo, _hi, _c in METRICS:
            vals = self._included_values(key)
            if vals:
                lines.append("  %s:平均 %s%s | 最高 %s%s | 最低 %s%s(%d 个有效值)"
                             % (name, self.fmt_val(key, statistics.mean(vals)), unit,
                                self.fmt_val(key, max(vals)), unit,
                                self.fmt_val(key, min(vals)), unit, len(vals)))
            else:
                lines.append("  %s:无有效数据" % name)
        if n_ab:
            lines.append("  ⚠ 注意:还有 %d 条可疑数据未处理,以上统计可能被带歪!" % n_ab)

        lines += ["", "三、生长趋势"]
        g = self._growth_info()
        if g:
            lines += [
                "  总生长量:%.1f cm(%s %.1fcm → %s %.1fcm)"
                % (g["total"], self.time_str(g["from"][0]), g["from"][1],
                   self.time_str(g["to"][0]), g["to"][1]),
                "  日均生长速度:%.2f cm/天(时间跨度 %.1f 天)" % (g["rate"], g["days"]),
            ]
        else:
            lines.append("  株高有效数据不足,无法计算生长趋势。")

        lines += ["", "四、数据清洗记录(共 %d 次操作)" % len(self.clean_log)]
        if self.clean_log:
            lines += ["  " + s for s in self.clean_log]
        else:
            lines.append("  (还没有做过清洗操作)")

        lines += [
            "",
            "五、我的发现(请同学们补充完成)",
            "  1. 我一共找到了____处缺失数据和____处异常数据,",
            "     其中最离谱的一个是:________________________。",
            "  2. 清洗前后,平均温度从____℃变成了____℃,说明____________。",
            "  3. 从折线图上看,温度和湿度在一天之内的变化规律是:____________。",
            "  4. 我的植物平均每天长高____cm,长得最快的是第____天前后。",
            "  5. 如果采样间隔从6小时改成1小时,数据会有什么不同?____________",
            "",
            "(本报告由本机离线生成,未上传任何数据)",
        ]
        path = self._unique_path("植物生长分析报告", ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.set_msg("分析报告已导出:%s(保存在本程序所在文件夹)。" % os.path.basename(path))
        return path

    # ===========================================================
    # 帮助窗口
    # ===========================================================
    def show_help(self):
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        win = tk.Toplevel(self.root)
        self.help_win = win
        win.title("帮助 · 植物生长数据采集与分析工具")
        win.geometry("580x540")
        text = tk.Text(win, wrap="word", padx=12, pady=10,
                       font=("Microsoft YaHei UI", 10))
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(win, orient="vertical", command=text.yview)
        sb.pack(side="right", fill="y")
        text.configure(yscrollcommand=sb.set)
        tk.Button(win, text="关闭", command=win.destroy).pack(side="bottom", pady=4)

    # ===========================================================
    # 关闭:停止模拟、取消 after 任务、销毁窗口
    # ===========================================================
    def on_close(self):
        self.running = False
        self._cancel_after()
        self.root.destroy()


def main():
    root = tk.Tk()
    GrowthApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
