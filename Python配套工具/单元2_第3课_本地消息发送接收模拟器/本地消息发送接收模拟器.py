# -*- coding: utf-8 -*-
"""
本地消息发送接收模拟器(发布订阅实验器)
========================================
配套教材:清华大学出版社《信息科技》五年级下册
          第2单元 第3课《智能种植项目设计——信息的发送与接收》(教材 P62—70)

工具定位:
    在电脑上完全本地模拟一个"智能种植大棚"里的消息发送与接收系统:
      * 左侧 3 个发送端:温度传感器 / 湿度传感器 / 光照传感器,定时把读数
        "发布"到自己选择的主题(Topic)上;
      * 中间 1 个消息服务器:显示订阅表和消息队列,负责把每条消息按主题
        "路由"给所有订阅了该主题的接收端;
      * 右侧 3 个接收端:显示屏 / 水泵 / 补光灯,各自"订阅"一个主题,
        只有主题完全一致才能收到消息并执行动作。
    学生可以亲眼观察三个核心现象:
      1. 主题匹配才能收到——把主题写错一个字母(如 farm/tmep),消息就会
         在服务器处变红,提示"无人订阅";
      2. 一个主题可以有多个订阅者——让三个接收端都订阅同一主题,
         一条消息会被复制送达每一个订阅者(广播);
      3. ACK 确认与超时重发——打开丢包开关后,开启 ACK 时丢失的消息会在
         超时后自动重发;关闭 ACK 时,丢了就永远丢了,发送方毫不知情。

技术说明(写给老师):
    * 仅使用 Python 标准库(tkinter / ttk / json / csv / random / os / datetime),
      无需安装任何第三方库,可在 Windows 上离线运行,不使用真实网络。
    * 模拟引擎用 root.after() 定时驱动,没有使用线程;
      关闭窗口时会正确取消 after 任务,不会有残留进程。
    * 模拟规则:
        - 1 个模拟周期 = 模拟世界的 1 分钟,时钟从 08:00 开始;
        - 消息走完一段路程(发送端→服务器,或 服务器→接收端)需要 3 个周期;
        - 每段路程都可能按"丢包率"丢失消息(在半路变红消失);
        - ACK 开启时:服务器收到消息会向发送端回 ACK,接收端收到消息会向
          服务器回 ACK(画面上是绿色小点往回走);某段路程丢失时,
          发出方等不到 ACK,超时 4 个周期后自动重发,同一段最多重发 2 次;
        - 主题必须逐字符完全一致才算匹配(所以 farm/temp ≠ farm/tmep)。
    * 所有数据仅在本机处理,不联网、不上传;
      导出文件写入本脚本所在目录,文件名自动加时间戳,不覆盖已有文件。
"""

import csv
import json
import os
import random
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------
# 全局常量
# ---------------------------------------------------------------
LEG_TICKS = 3        # 一段路程(发送端→服务器 或 服务器→接收端)需要的周期数
RESEND_TIMEOUT = 4   # ACK 超时重发的等待周期数
MAX_RETRY = 2        # 同一段路程最多重发次数(避免坏网络里无限重发)

# 三个发送端(虚拟传感器):名称、读数单位、读数范围与每周期波动幅度、
# 默认发布主题、消息小圆点的颜色
SENDERS = [
    {"name": "温度传感器", "unit": "℃", "min": 18, "max": 32, "step": 0.6,
     "init": 24.0, "topic": "farm/temp", "color": "#e5484d"},
    {"name": "湿度传感器", "unit": "%", "min": 30, "max": 80, "step": 1.5,
     "init": 55.0, "topic": "farm/humi", "color": "#2b7de9"},
    {"name": "光照传感器", "unit": "lx", "min": 200, "max": 1000, "step": 30,
     "init": 600.0, "topic": "farm/light", "color": "#f59e0b"},
]

# 三个接收端(显示与执行器):名称与默认订阅主题
RECEIVERS = [
    {"name": "显示屏", "topic": "farm/temp"},
    {"name": "水泵", "topic": "farm/humi"},
    {"name": "补光灯", "topic": "farm/light"},
]

# 可选主题列表:每个正确主题都配了一个"长得很像"的易错干扰项,
# 用于课堂上的"主题写错了"排错练习(farm/tmep 是 farm/temp 的手误拼法)
TOPIC_CHOICES = ["farm/temp", "farm/tmep",
                 "farm/humi", "farm/humy",
                 "farm/light", "farm/lihgt"]
NO_SUB = "(不订阅)"
SUB_CHOICES = [NO_SUB] + TOPIC_CHOICES

# 脚本所在目录:导出文件、示例方案文件都放在这里
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 帮助窗口显示的使用说明(与 使用说明.txt 内容一致的精简版)
HELP_TEXT = """【本地消息发送接收模拟器 · 快速帮助】

一、界面分区
  ① 场景区(左上):左边 3 个发送端(温度/湿度/光照传感器),中间消息
     服务器(显示订阅表和消息队列),右边 3 个接收端(显示屏/水泵/补光灯)。
     彩色圆点 = 正在传输的消息(颜色区分发送端);绿色小点 = ACK 确认;
     红色 = 丢失;服务器里变红并写"无人订阅" = 主题没人订。
  ② 配置区(右上):为每个发送端选发布主题、为每个接收端选订阅主题
     (注意有拼写很像的干扰项!),勾选消息格式(含单位/含时间),
     调发送间隔和丢包率,开关 ACK 确认。
  ③ 运行控制区(右中):开始 / 暂停 / 单步 / 重置 / 手动发一条。
  ④ 状态与日志区(下方):每条消息的完整生命周期:
     发布 → 入队 → 路由 → 送达 / 无人订阅 / 丢失 / 重发。
  ⑤ 结果区(右下):发布数/送达数/无人接收数/丢失数/重发数统计,
     以及 导出日志CSV / 导出方案TXT / 导入方案JSON / 帮助。

二、三个核心实验
  1. 主题匹配:让发送端主题和接收端订阅主题完全一致,消息才能送达;
     一个主题被多个接收端订阅时,每个订阅者都会收到一份(广播)。
  2. 写错主题排错:把某个发送端主题改成 farm/tmep(打错字),观察消息
     在服务器处变红提示"无人订阅",再改回来修好它。
  3. ACK 重发:把丢包率调到 30%~50%,先关 ACK 看消息"无声无息地丢",
     再开 ACK 看丢失的消息超时后自动重发(日志里有"重发"记录)。

三、统计口径小说明
  * 送达数:接收端每成功收到一份就 +1(广播给 3 个订阅者 = 送达 3 次);
  * 丢失数:消息在网络中每丢一次就 +1(重发成功的消息仍会计入送达);
  * 重发数:因 ACK 超时而补发的次数。

更多内容请阅读同文件夹中的《使用说明.txt》。"""


class PubSubApp:
    """本地消息发送接收模拟器主程序(单窗口 Tkinter 应用)"""

    # ===========================================================
    # 初始化
    # ===========================================================
    def __init__(self, root):
        self.root = root
        root.title("本地消息发送接收模拟器 · 清华版《信息科技》五下 第2单元第3课")
        root.geometry("1150x800")
        root.minsize(1020, 720)

        # ---- 模拟引擎状态 ----
        self.running = False         # 是否正在连续运行
        self.after_id = None         # root.after 的任务编号,关闭窗口时要取消
        self.tick_interval_ms = 500  # 每个模拟周期的真实间隔(毫秒)

        self.tick = 0                # 已经过的模拟周期数(1周期=模拟1分钟)
        self.msg_seq = 0             # 消息自增编号
        self.messages = []           # 画面上所有在途/刚结束的消息小圆点
        self.pending = []            # ACK 超时后等待重发的任务列表
        self.server_queue = []       # 服务器最近入队的消息(界面显示用)

        # 每个传感器的当前读数(随机游走,让数据看起来"活"的)
        self.readings = [s["init"] for s in SENDERS]
        self.tx_flash = [0, 0, 0]    # 发送端刚发布时闪烁几个周期
        self.rx_active = [0, 0, 0]   # 接收端刚收到消息时高亮几个周期
        self.rx_last = ["—", "—", "—"]  # 接收端最近收到的消息内容

        # ---- 统计数据(结果区显示、导出用)----
        self.stats = {"pub": 0, "deliver": 0, "nosub": 0,
                      "lost": 0, "resend": 0}
        self.log_rows = []           # 日志记录列表,导出 CSV 用

        # ---- 可调参数(与界面控件绑定的 Tk 变量)----
        # 发送端发布主题(下拉框)
        self.pub_vars = [tk.StringVar(value=s["topic"]) for s in SENDERS]
        # 接收端订阅主题(下拉框,可选"(不订阅)")
        self.sub_vars = [tk.StringVar(value=r["topic"]) for r in RECEIVERS]
        self.var_unit = tk.BooleanVar(value=True)    # 消息格式:含单位
        self.var_time = tk.BooleanVar(value=False)   # 消息格式:含时间
        self.var_interval = tk.IntVar(value=6)       # 发送间隔(周期/条)
        self.var_loss = tk.IntVar(value=0)           # 丢包率(%)
        self.var_ack = tk.BooleanVar(value=True)     # ACK 确认开关
        self.var_manual_sender = tk.StringVar(value=SENDERS[0]["name"])

        self.help_win = None         # 帮助窗口(避免重复打开)

        self._build_ui()
        # 窗口关闭时先停止模拟、取消 after 任务,再销毁窗口
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.add_log("系统", "欢迎使用!点「开始」运行模拟,点「帮助」查看三个核心实验。")
        self._render()

    # ===========================================================
    # 界面搭建
    # ===========================================================
    def _build_ui(self):
        # 中文界面字体:Windows 上用微软雅黑,其他系统自动回退到默认字体
        base_font = ("Microsoft YaHei UI", 10)
        self.root.option_add("*Font", base_font)

        # ---- 顶部标题 ----
        header = tk.Frame(self.root, bg="#1a7a4f")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text="📨 本地消息发送接收模拟器(发布订阅实验器)",
                 font=("Microsoft YaHei UI", 15, "bold"),
                 bg="#1a7a4f", fg="white").pack(side="left", padx=14, pady=6)
        tk.Label(header,
                 text="第2单元 第3课 智能种植项目设计——信息的发送与接收 · 完全离线 · 数据仅存本机",
                 bg="#1a7a4f", fg="#d7f0e2").pack(side="left", padx=6)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_rowconfigure(2, weight=2)

        # ================= ① 场景区(Canvas) =================
        scene_frame = tk.LabelFrame(
            self.root, text="① 场景区:发送端 → 消息服务器 → 接收端(主题匹配才能送达)",
            padx=4, pady=4)
        scene_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        scene_frame.grid_rowconfigure(0, weight=1)
        scene_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(scene_frame, width=690, height=500,
                                bg="#f2faf5", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # ================= 右侧面板:配置区 + 运行控制区 + 结果区 =================
        right = tk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)

        # ---- ② 配置区 ----
        cfg = tk.LabelFrame(right, text="② 配置区(改完立即生效)", padx=8, pady=2)
        cfg.pack(fill="x")

        tk.Label(cfg, text="发布主题(发送端往哪个主题发):",
                 fg="#1a7a4f", anchor="w").pack(fill="x")
        for i, s in enumerate(SENDERS):
            row = tk.Frame(cfg)
            row.pack(fill="x")
            tk.Label(row, text=s["name"], width=10, anchor="w",
                     fg=s["color"]).pack(side="left")
            cb = ttk.Combobox(row, textvariable=self.pub_vars[i],
                              values=TOPIC_CHOICES, state="readonly", width=13)
            cb.pack(side="left", padx=2)
            cb.bind("<<ComboboxSelected>>",
                    lambda _e, i=i: self._on_topic_change("发布", i))

        tk.Label(cfg, text="订阅主题(接收端只收这个主题):",
                 fg="#1a7a4f", anchor="w").pack(fill="x", pady=(4, 0))
        for j, r in enumerate(RECEIVERS):
            row = tk.Frame(cfg)
            row.pack(fill="x")
            tk.Label(row, text=r["name"], width=10, anchor="w").pack(side="left")
            cb = ttk.Combobox(row, textvariable=self.sub_vars[j],
                              values=SUB_CHOICES, state="readonly", width=13)
            cb.pack(side="left", padx=2)
            cb.bind("<<ComboboxSelected>>",
                    lambda _e, j=j: self._on_topic_change("订阅", j))

        fmt_row = tk.Frame(cfg)
        fmt_row.pack(fill="x", pady=(4, 0))
        tk.Label(fmt_row, text="消息格式:", anchor="w").pack(side="left")
        tk.Checkbutton(fmt_row, text="含单位", variable=self.var_unit,
                       command=lambda: self._on_check_change("含单位", self.var_unit)
                       ).pack(side="left")
        tk.Checkbutton(fmt_row, text="含时间", variable=self.var_time,
                       command=lambda: self._on_check_change("含时间", self.var_time)
                       ).pack(side="left", padx=6)

        def add_scale(text, var, frm, to, step, unit):
            """添加一行带说明的滑块;数值变化时写一条调参日志"""
            row = tk.Frame(cfg)
            row.pack(fill="x")
            tk.Label(row, text=text, width=13, anchor="w").pack(side="left")
            scale = tk.Scale(row, variable=var, from_=frm, to=to,
                             resolution=step, orient="horizontal",
                             length=150, showvalue=True,
                             command=lambda v, t=text, u=unit:
                                 self._on_param_change(t, v, u))
            scale.pack(side="left", fill="x", expand=True)
            tk.Label(row, text=unit, width=6, anchor="w").pack(side="left")

        add_scale("发送间隔", self.var_interval, 3, 15, 1, "周期/条")
        add_scale("丢包率", self.var_loss, 0, 80, 10, "%")

        tk.Checkbutton(cfg, text="ACK确认(收到回执;丢失的消息超时自动重发)",
                       variable=self.var_ack, anchor="w",
                       command=self._on_ack_change).pack(fill="x", pady=(2, 4))

        # ---- ③ 运行控制区 ----
        ctrl = tk.LabelFrame(right, text="③ 运行控制区", padx=8, pady=6)
        ctrl.pack(fill="x", pady=(6, 0))
        row1 = tk.Frame(ctrl)
        row1.pack(fill="x")
        self.btn_start = tk.Button(row1, text="▶ 开始", width=7,
                                   bg="#2eb872", fg="white",
                                   activebackground="#1e8f56",
                                   command=self.start)
        self.btn_start.pack(side="left", padx=2, pady=2)
        tk.Button(row1, text="⏸ 暂停", width=7,
                  command=self.pause).pack(side="left", padx=2)
        tk.Button(row1, text="⏭ 单步", width=7,
                  command=self.step_once).pack(side="left", padx=2)
        tk.Button(row1, text="🔄 重置", width=7,
                  command=self.reset).pack(side="left", padx=2)
        row2 = tk.Frame(ctrl)
        row2.pack(fill="x")
        ttk.Combobox(row2, textvariable=self.var_manual_sender,
                     values=[s["name"] for s in SENDERS],
                     state="readonly", width=10).pack(side="left", padx=2, pady=2)
        tk.Button(row2, text="✉ 手动发一条", bg="#2b7de9", fg="white",
                  activebackground="#1a5cb8",
                  command=self.manual_send).pack(side="left", padx=2, pady=2,
                                                 fill="x", expand=True)

        # ---- ⑤ 结果区 ----
        result = tk.LabelFrame(right, text="⑤ 结果区:统计与导出", padx=8, pady=6)
        result.pack(fill="both", expand=True, pady=(6, 0))
        self.lbl_stats = tk.Label(result, justify="left", anchor="w",
                                  text="", fg="#20344b")
        self.lbl_stats.pack(fill="x")
        btns = tk.Frame(result)
        btns.pack(fill="x", pady=4)
        tk.Button(btns, text="📥 导出日志CSV",
                  command=self.export_csv).grid(row=0, column=0, padx=2, pady=2,
                                                sticky="ew")
        tk.Button(btns, text="📄 导出方案TXT",
                  command=self.export_scheme_txt).grid(row=0, column=1, padx=2,
                                                       pady=2, sticky="ew")
        tk.Button(btns, text="📂 导入方案JSON",
                  command=self.import_scheme).grid(row=1, column=0, padx=2,
                                                   pady=2, sticky="ew")
        tk.Button(btns, text="❓ 帮助",
                  command=self.show_help).grid(row=1, column=1, padx=2, pady=2,
                                               sticky="ew")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)
        tk.Label(result, fg="#5b7186", justify="left", anchor="w",
                 text="导出文件保存在本程序所在文件夹,\n文件名自动加时间戳,不会覆盖旧文件。"
                 ).pack(fill="x")

        # ================= ④ 状态与日志区 =================
        log_frame = tk.LabelFrame(
            self.root, text="④ 状态与日志区(消息生命周期:发布→入队→路由→送达/无人订阅/丢失/重发)",
            padx=6, pady=4)
        log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew",
                       padx=8, pady=(0, 8))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        # 状态栏:一行实时数据
        self.lbl_status = tk.Label(log_frame, anchor="w", fg="#1a7a4f",
                                   font=("Microsoft YaHei UI", 11, "bold"))
        self.lbl_status.grid(row=0, column=0, columnspan=2, sticky="ew")

        # 滚动日志
        self.log_text = tk.Text(log_frame, height=9, state="disabled",
                                bg="#20344b", fg="#d9e4f0",
                                font=("Microsoft YaHei UI", 9))
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical",
                               command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        # 不同阶段的日志用不同颜色,方便学生追踪一条消息的一生
        self.log_text.tag_configure("发布", foreground="#9fc7ff")
        self.log_text.tag_configure("入队", foreground="#d9e4f0")
        self.log_text.tag_configure("路由", foreground="#ffd23f")
        self.log_text.tag_configure("送达", foreground="#7fe3ad")
        self.log_text.tag_configure("确认", foreground="#7fd8e3")
        self.log_text.tag_configure("无人订阅", foreground="#ff8f94")
        self.log_text.tag_configure("丢失", foreground="#ff8f94")
        self.log_text.tag_configure("重发", foreground="#ffb35c")
        self.log_text.tag_configure("调参", foreground="#c9b8f5")

    # ===========================================================
    # 模拟时钟工具
    # ===========================================================
    def clock_str(self, tick=None):
        """把周期号换算成模拟时间"HH:MM"(1周期=1分钟,从08:00开始)"""
        if tick is None:
            tick = self.tick
        minutes = tick % (24 * 60)
        hour = (8 + minutes // 60) % 24
        return "%02d:%02d" % (hour, minutes % 60)

    # ===========================================================
    # 日志
    # ===========================================================
    def add_log(self, phase, detail, msg_id=""):
        """追加一条日志:同时写入内存列表(供导出)和界面 Text(供查看)"""
        row = {"tick": self.tick, "time": self.clock_str(),
               "phase": phase, "msg": msg_id, "detail": detail}
        self.log_rows.append(row)
        if len(self.log_rows) > 2000:      # 防止长时间运行占用过多内存
            self.log_rows.pop(0)
        line = "[%s 第%d周期] [%s] %s\n" % (row["time"], self.tick, phase, detail)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, phase)
        # 界面上最多保留 500 行,超出就删掉最早的
        if int(self.log_text.index("end-1c").split(".")[0]) > 500:
            self.log_text.delete("1.0", "2.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ===========================================================
    # 参数变化回调(写日志,方便学生对照"改了什么→发生了什么")
    # ===========================================================
    def _on_topic_change(self, kind, idx):
        if kind == "发布":
            name, topic = SENDERS[idx]["name"], self.pub_vars[idx].get()
        else:
            name, topic = RECEIVERS[idx]["name"], self.sub_vars[idx].get()
        self.add_log("调参", "%s 的%s主题改为「%s」" % (name, kind, topic))
        # 善意提醒:发布主题当前没有任何订阅者时,提示学生仔细核对拼写
        if kind == "发布" and not self._subscribers_of(topic):
            self.add_log("调参", "提醒:主题「%s」目前没有任何接收端订阅,"
                         "消息将无人接收(检查一下拼写?)" % topic)
        self._render()

    def _on_check_change(self, name, var):
        self.add_log("调参", "消息格式「%s」%s" % (name, "勾选" if var.get() else "取消"))

    def _on_param_change(self, name, value, unit):
        # Scale 初始化时也会触发一次回调,此时界面尚未建完,跳过
        if not hasattr(self, "log_text"):
            return
        # 避免拖动过程刷屏:只在数值真正变化时记录
        key = (name, str(value))
        if getattr(self, "_last_param_log", None) == key:
            return
        self._last_param_log = key
        self.add_log("调参", "%s 改为 %s %s" % (name, value, unit))

    def _on_ack_change(self):
        on = self.var_ack.get()
        self.add_log("调参", "ACK确认 %s" % (
            "开启:收到消息会回执,丢失的消息超时后自动重发" if on
            else "关闭:丢失的消息不会重发,发送方也不知道丢了"))

    # ===========================================================
    # 运行控制:开始 / 暂停 / 单步 / 重置 / 手动发一条
    # ===========================================================
    def start(self):
        """开始(或继续)连续运行"""
        if self.running:
            return
        self.running = True
        self.btn_start.configure(state="disabled")
        self.add_log("系统", "模拟开始运行(1周期=模拟1分钟,消息走一段路程需%d个周期)"
                     % LEG_TICKS)
        self._schedule_next()

    def pause(self):
        """暂停连续运行(不清除任何状态)"""
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(state="normal")
        self._cancel_after()
        self.add_log("系统", "模拟已暂停,可用「单步」逐周期观察消息移动")

    def step_once(self):
        """单步:先暂停,再推进一个周期,方便逐步观察消息路由"""
        if self.running:
            self.pause()
        self._tick_once()

    def reset(self):
        """重置:清空消息、队列与统计,读数复位(主题等配置保持不变,日志保留)"""
        self.pause()
        self.tick = 0
        self.msg_seq = 0
        self.messages = []
        self.pending = []
        self.server_queue = []
        self.readings = [s["init"] for s in SENDERS]
        self.tx_flash = [0, 0, 0]
        self.rx_active = [0, 0, 0]
        self.rx_last = ["—", "—", "—"]
        self.stats = {"pub": 0, "deliver": 0, "nosub": 0,
                      "lost": 0, "resend": 0}
        self.add_log("系统", "已重置:消息、队列、统计清零(主题与参数配置保持不变)")
        self._render()

    def manual_send(self):
        """手动发一条:从下拉框选中的发送端立即发布一条消息"""
        name = self.var_manual_sender.get()
        for i, s in enumerate(SENDERS):
            if s["name"] == name:
                self.publish(i, manual=True)
                break
        if not self.running:
            self.add_log("系统", "提示:当前是暂停状态,点「单步」或「开始」让消息走起来")
        self._render()

    # ===========================================================
    # 模拟引擎(root.after 驱动,不用线程)
    # ===========================================================
    def _schedule_next(self):
        """安排下一个周期(先记下任务编号,窗口关闭时要取消)"""
        self.after_id = self.root.after(self.tick_interval_ms, self._loop)

    def _cancel_after(self):
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _loop(self):
        """after 回调:推进一个周期,然后继续排队下一次"""
        self.after_id = None
        if not self.running:
            return
        self._tick_once()
        self._schedule_next()

    def _tick_once(self):
        """推进一个模拟周期:读数波动、定时发布、处理重发、推进消息"""
        self.tick += 1

        # ---- 传感器读数随机游走(让每条消息的内容都不一样)----
        for i, s in enumerate(SENDERS):
            self.readings[i] = max(s["min"], min(
                s["max"], self.readings[i] + random.uniform(-s["step"], s["step"])))

        # ---- 定时自动发布:三个发送端错开 2 个周期,避免同时扎堆 ----
        interval = self.var_interval.get()
        for i in range(len(SENDERS)):
            if (self.tick + i * 2) % interval == 0:
                self.publish(i)

        # ---- 到期的 ACK 超时重发任务 ----
        self._process_resends()

        # ---- 所有在途消息前进一步 ----
        self._advance_messages()

        # ---- 动画计数衰减 ----
        self.tx_flash = [max(0, v - 1) for v in self.tx_flash]
        self.rx_active = [max(0, v - 1) for v in self.rx_active]

        self._render()

    # ===========================================================
    # 消息系统:发布 → 入队 → 路由 → 送达 / 无人订阅 / 丢失 / 重发
    # ===========================================================
    def _make_payload(self, i):
        """根据"消息格式"勾选项,把传感器读数拼成消息内容"""
        text = str(round(self.readings[i]))
        if self.var_unit.get():
            text += SENDERS[i]["unit"]
        if self.var_time.get():
            text = "[%s] %s" % (self.clock_str(), text)
        return text

    def _subscribers_of(self, topic):
        """返回订阅了指定主题的接收端编号列表(主题必须逐字符完全一致)"""
        return [j for j in range(len(RECEIVERS))
                if self.sub_vars[j].get() == topic and topic != NO_SUB]

    def publish(self, i, manual=False):
        """发送端 i 发布一条消息(消息生命周期的第一步)"""
        self.msg_seq += 1
        topic = self.pub_vars[i].get()
        payload = self._make_payload(i)
        self.stats["pub"] += 1
        self.tx_flash[i] = 2
        self._spawn_data("pub", i, None, topic, payload, self.msg_seq, retry=0)
        self.add_log("发布", "%s%s 发布消息 #%d → 主题「%s」 内容「%s」"
                     % (SENDERS[i]["name"], "(手动)" if manual else "",
                        self.msg_seq, topic, payload),
                     msg_id=self.msg_seq)

    def _spawn_data(self, leg, sender, receiver, topic, payload, msg_id, retry):
        """
        创建一个数据消息小圆点。
        leg: 'pub'=发送端→服务器 这一段;'deliver'=服务器→接收端 这一段。
        是否会在半路丢失,在出发时就按丢包率抽签决定(丢在路程中点)。
        """
        will_lose = random.random() < self.var_loss.get() / 100.0
        self.messages.append({
            "id": msg_id, "kind": "data", "leg": leg,
            "sender": sender, "receiver": receiver,
            "topic": topic, "payload": payload, "retry": retry,
            "progress": 0.0, "will_lose": will_lose,
            "state": "moving",     # moving / lost / nosub / done
            "done_age": 0,         # 结束后再显示几个周期(动画淡出)
        })

    def _spawn_ack(self, leg, sender, receiver, msg_id):
        """创建一个 ACK 确认小点(沿原路反向走回去,只作演示,不会丢失)"""
        self.messages.append({
            "id": msg_id, "kind": "ack", "leg": leg,
            "sender": sender, "receiver": receiver,
            "topic": "", "payload": "", "retry": 0,
            "progress": 0.0, "will_lose": False,
            "state": "moving", "done_age": 0,
        })

    def _advance_messages(self):
        """每周期让所有在途消息前进一步(可能半路丢失),到站后触发入队/路由/送达"""
        for m in self.messages:
            if m["state"] != "moving":
                m["done_age"] += 1     # 已结束的消息保留几帧用于显示颜色
                continue
            m["progress"] += 1.0 / LEG_TICKS
            # 丢包:抽中"会丢"的消息走到半路就变红消失
            if m["kind"] == "data" and m["will_lose"] and m["progress"] >= 0.5:
                self._on_lost(m)
                continue
            if m["progress"] >= 1.0:
                if m["kind"] == "ack":
                    m["state"] = "done"    # ACK 到达,只作视觉演示
                elif m["leg"] == "pub":
                    self._arrive_server(m)
                else:
                    self._arrive_receiver(m)

        # 清理:结束超过 3 个周期的消息从列表移除
        self.messages = [m for m in self.messages
                         if not (m["state"] != "moving" and m["done_age"] > 3)]

    def _arrive_server(self, m):
        """消息到达服务器:入队 → 回 ACK → 按订阅表路由"""
        m["state"] = "done"
        # 入队(服务器界面显示最近 4 条)
        self.server_queue.append("#%d %s" % (m["id"], m["topic"]))
        if len(self.server_queue) > 4:
            self.server_queue.pop(0)
        self.add_log("入队", "服务器收到消息 #%d(主题「%s」),进入消息队列"
                     % (m["id"], m["topic"]), msg_id=m["id"])
        # ACK:服务器向发送端回执"我收到了"
        if self.var_ack.get():
            self._spawn_ack("pub", m["sender"], None, m["id"])
            self.add_log("确认", "服务器 → %s:已回 ACK 确认收到 #%d"
                         % (SENDERS[m["sender"]]["name"], m["id"]), msg_id=m["id"])
        # 路由:查订阅表,把消息复制给每一个订阅者
        subs = self._subscribers_of(m["topic"])
        if not subs:
            m["state"] = "nosub"
            m["done_age"] = 0
            self.stats["nosub"] += 1
            self.add_log("无人订阅", "路由失败:主题「%s」没有任何接收端订阅,"
                         "消息 #%d 被丢弃!(检查主题拼写是否一致)"
                         % (m["topic"], m["id"]), msg_id=m["id"])
        else:
            names = "、".join(RECEIVERS[j]["name"] for j in subs)
            self.add_log("路由", "消息 #%d 按主题「%s」路由给 %d 个订阅者:%s"
                         % (m["id"], m["topic"], len(subs), names), msg_id=m["id"])
            for j in subs:
                self._spawn_data("deliver", m["sender"], j,
                                 m["topic"], m["payload"], m["id"], retry=0)

    def _arrive_receiver(self, m):
        """消息送达接收端:更新显示、执行动作、回 ACK"""
        m["state"] = "done"
        j = m["receiver"]
        self.stats["deliver"] += 1
        self.rx_last[j] = m["payload"]
        self.rx_active[j] = 3
        self.add_log("送达", "消息 #%d 送达 %s,内容「%s」"
                     % (m["id"], RECEIVERS[j]["name"], m["payload"]), msg_id=m["id"])
        if self.var_ack.get():
            self._spawn_ack("deliver", m["sender"], j, m["id"])

    def _on_lost(self, m):
        """消息在网络中丢失:ACK 开启时安排超时重发,关闭时就永远丢了"""
        m["state"] = "lost"
        self.stats["lost"] += 1
        where = ("%s→服务器" % SENDERS[m["sender"]]["name"] if m["leg"] == "pub"
                 else "服务器→%s" % RECEIVERS[m["receiver"]]["name"])
        if self.var_ack.get():
            if m["retry"] < MAX_RETRY:
                # 发出方等不到 ACK,超时后重发同一段路程
                self.pending.append({
                    "due": self.tick + RESEND_TIMEOUT, "leg": m["leg"],
                    "sender": m["sender"], "receiver": m["receiver"],
                    "topic": m["topic"], "payload": m["payload"],
                    "id": m["id"], "retry": m["retry"] + 1,
                })
                self.add_log("丢失", "消息 #%d 在「%s」途中丢失!发出方等不到 ACK,"
                             "%d 个周期后将自动重发" % (m["id"], where, RESEND_TIMEOUT),
                             msg_id=m["id"])
            else:
                self.add_log("丢失", "消息 #%d 再次丢失,已达最大重发次数(%d次),放弃"
                             % (m["id"], MAX_RETRY), msg_id=m["id"])
        else:
            self.add_log("丢失", "消息 #%d 在「%s」途中丢失!ACK已关闭:"
                         "发送方不知道丢了,不会重发" % (m["id"], where), msg_id=m["id"])

    def _process_resends(self):
        """执行所有到期的 ACK 超时重发任务"""
        due = [r for r in self.pending if r["due"] <= self.tick]
        self.pending = [r for r in self.pending if r["due"] > self.tick]
        for r in due:
            self.stats["resend"] += 1
            self._spawn_data(r["leg"], r["sender"], r["receiver"],
                             r["topic"], r["payload"], r["id"], r["retry"])
            self.add_log("重发", "ACK 超时:消息 #%d 第 %d 次重发(最多重发 %d 次)"
                         % (r["id"], r["retry"], MAX_RETRY), msg_id=r["id"])

    # ===========================================================
    # 场景绘制(Canvas 每周期全部重画)
    # ===========================================================
    # 场景各节点坐标(与 Canvas 尺寸 690x500 匹配)
    NODE_YS = [150, 265, 380]           # 三行节点的纵坐标
    SENDER_CX, SENDER_R_EDGE = 78, 136  # 发送端方框中心 / 右边缘
    SERVER_L, SERVER_R = 258, 432       # 服务器方框左右边缘
    RECEIVER_CX, RECEIVER_L_EDGE = 612, 556  # 接收端方框中心 / 左边缘

    def _dot_pos(self, m):
        """根据消息所在路段与进度,算出小圆点当前坐标(ACK 沿原路反向)"""
        p = min(1.0, m["progress"])
        if m["kind"] == "ack":
            p = 1.0 - p                # ACK 从终点走回起点
        if m["leg"] == "pub":
            y = self.NODE_YS[m["sender"]]
            x0, x1 = self.SENDER_R_EDGE, self.SERVER_L
        else:
            y = self.NODE_YS[m["receiver"]]
            x0, x1 = self.SERVER_R, self.RECEIVER_L_EDGE
        return x0 + (x1 - x0) * p, y

    def _render(self):
        """刷新场景画面、状态栏和统计数据"""
        c = self.canvas
        c.delete("all")
        small = ("Microsoft YaHei UI", 8)
        norm = ("Microsoft YaHei UI", 9)
        bold = ("Microsoft YaHei UI", 10, "bold")

        # ---- 图例 ----
        c.create_oval(14, 14, 26, 26, fill="#e5484d", outline="")
        c.create_text(31, 20, text="传输中的消息(颜色区分发送端)", anchor="w",
                      fill="#5b7186", font=small)
        c.create_oval(226, 16, 234, 24, fill="#2eb872", outline="")
        c.create_text(239, 20, text="ACK确认(往回走)", anchor="w",
                      fill="#5b7186", font=small)
        c.create_text(360, 20, text="✕红色=丢失/无人订阅", anchor="w",
                      fill="#e5484d", font=small)
        c.create_text(495, 20, text="「重发」=超时补发的消息", anchor="w",
                      fill="#b8860b", font=small)

        # ---- 发送端 / 接收端 与服务器之间的虚线通道 ----
        for y in self.NODE_YS:
            c.create_line(self.SENDER_R_EDGE, y, self.SERVER_L, y,
                          fill="#bcd9c8", width=2, dash=(5, 3), arrow="last")
            c.create_line(self.SERVER_R, y, self.RECEIVER_L_EDGE, y,
                          fill="#bcd9c8", width=2, dash=(5, 3), arrow="last")

        # ---- 左侧 3 个发送端节点 ----
        for i, s in enumerate(SENDERS):
            y = self.NODE_YS[i]
            flash = self.tx_flash[i] > 0
            c.create_rectangle(20, y - 31, self.SENDER_R_EDGE, y + 31,
                               fill="#fff8ec" if flash else "white",
                               outline=s["color"], width=3 if flash else 2)
            c.create_text(self.SENDER_CX, y - 15, text=s["name"],
                          fill=s["color"], font=bold)
            c.create_text(self.SENDER_CX, y + 4,
                          text="读数:%d%s" % (round(self.readings[i]), s["unit"]),
                          fill="#20344b", font=norm)
            c.create_text(self.SENDER_CX, y + 21, text="发布中" if flash else "待命",
                          fill="#b8860b" if flash else "#8aa39a", font=small)
            # 方框下方标出当前发布主题;若该主题无人订阅,用红色提醒
            topic = self.pub_vars[i].get()
            ok = bool(self._subscribers_of(topic))
            c.create_text(self.SENDER_CX, y + 43,
                          text="发布→" + topic,
                          fill="#1a7a4f" if ok else "#e5484d", font=small)

        # ---- 中间消息服务器 ----
        c.create_rectangle(self.SERVER_L, 105, self.SERVER_R, 432,
                           fill="white", outline="#1a7a4f", width=2)
        cx = (self.SERVER_L + self.SERVER_R) // 2
        c.create_text(cx, 122, text="📡 消息服务器", fill="#1a7a4f", font=bold)
        # 订阅表:主题 ← 订阅者(路由的依据)
        c.create_text(self.SERVER_L + 8, 146, text="订阅表(主题 ← 订阅者):",
                      anchor="w", fill="#5b7186", font=small)
        line_y = 164
        shown = []
        for topic in TOPIC_CHOICES:
            subs = self._subscribers_of(topic)
            if subs:
                shown.append((topic, subs))
        if not shown:
            c.create_text(self.SERVER_L + 12, line_y, anchor="w",
                          text="(空:当前没有任何订阅)", fill="#e5484d", font=small)
            line_y += 18
        for topic, subs in shown:
            names = "、".join(RECEIVERS[j]["name"] for j in subs)
            c.create_text(self.SERVER_L + 12, line_y, anchor="w",
                          text="%s ← %s" % (topic, names),
                          fill="#20344b", font=small)
            line_y += 18
        # 消息队列:最近入队的消息
        qy = max(line_y + 10, 246)
        c.create_text(self.SERVER_L + 8, qy, anchor="w",
                      text="消息队列(最近入队):", fill="#5b7186", font=small)
        qy += 18
        if not self.server_queue:
            c.create_text(self.SERVER_L + 12, qy, anchor="w",
                          text="(暂无消息)", fill="#8aa39a", font=small)
        for item in reversed(self.server_queue):
            c.create_text(self.SERVER_L + 12, qy, anchor="w",
                          text=item, fill="#20344b", font=small)
            qy += 18
        # 等待重发提示
        if self.pending:
            c.create_text(cx, 415, text="⏱ %d 条消息等待超时重发…" % len(self.pending),
                          fill="#b8860b", font=small)

        # ---- 右侧 3 个接收端节点 ----
        rx_desc = ["显示:", "动作:", "动作:"]
        for j, r in enumerate(RECEIVERS):
            y = self.NODE_YS[j]
            active = self.rx_active[j] > 0
            c.create_rectangle(self.RECEIVER_L_EDGE, y - 31, 668, y + 31,
                               fill="#eafaf0" if active else "white",
                               outline="#2eb872" if active else "#5b7186",
                               width=3 if active else 2)
            c.create_text(self.RECEIVER_CX, y - 15, text=r["name"],
                          fill="#20344b", font=bold)
            # 收到消息时的"执行动作":显示屏显示内容,水泵浇水,补光灯亮起
            if j == 0:
                action = self.rx_last[0]
            elif j == 1:
                action = "💦浇水中" if active else "待机"
            else:
                action = "💡亮起" if active else "熄灭"
            c.create_text(self.RECEIVER_CX, y + 4, text=rx_desc[j] + action,
                          fill="#1a7a4f" if active else "#5b7186", font=norm)
            c.create_text(self.RECEIVER_CX, y + 21,
                          text="收到:" + (self.rx_last[j][:14] or "—"),
                          fill="#8aa39a", font=small)
            # 方框下方标出订阅主题
            sub = self.sub_vars[j].get()
            c.create_text(self.RECEIVER_CX, y + 43,
                          text="订阅←" + sub,
                          fill="#1a7a4f" if sub != NO_SUB else "#e5484d",
                          font=small)

        # ---- 消息小圆点(含 ACK、丢失、无人订阅的着色)----
        for m in self.messages:
            if m["state"] == "nosub":
                # 无人订阅:红点停在服务器内部,提示主题没人订
                x, y = cx, self.NODE_YS[m["sender"]]
                c.create_oval(x - 8, y - 8, x + 8, y + 8,
                              fill="#e5484d", outline="white", width=2)
                c.create_text(x, y - 16, text="✕ 无人订阅!", fill="#e5484d",
                              font=("Microsoft YaHei UI", 9, "bold"))
                continue
            x, y = self._dot_pos(m)
            if m["kind"] == "ack":
                # ACK:绿色小点往回走
                c.create_oval(x - 4, y - 4, x + 4, y + 4,
                              fill="#2eb872", outline="white")
                c.create_text(x, y + 12, text="ACK", fill="#2eb872", font=small)
                continue
            color = SENDERS[m["sender"]]["color"]
            if m["state"] == "lost":
                c.create_text(x, y, text="✕", fill="#e5484d",
                              font=("Microsoft YaHei UI", 14, "bold"))
                c.create_text(x, y - 15, text="丢失", fill="#e5484d", font=small)
                continue
            if m["state"] == "done":
                # 刚送达/刚入队的消息淡出成浅色圆环
                c.create_oval(x - 6, y - 6, x + 6, y + 6,
                              outline="#2eb872", width=2)
                continue
            c.create_oval(x - 7, y - 7, x + 7, y + 7,
                          fill=color, outline="white", width=2)
            tag = "#%d %s" % (m["id"], m["topic"])
            if m["retry"] > 0:
                tag += "(重发)"
            c.create_text(x, y - 15, text=tag,
                          fill="#b8860b" if m["retry"] > 0 else color, font=small)

        # ---- 状态栏与统计 ----
        moving = sum(1 for m in self.messages
                     if m["state"] == "moving" and m["kind"] == "data")
        self.lbl_status.configure(
            text="🕒 模拟时间 %s(第%d周期)  |  在途消息:%d 条  |  等待重发:%d 条  |  "
                 "丢包率:%d%%  |  ACK确认:%s  |  发送间隔:每%d周期一条"
                 % (self.clock_str(), self.tick, moving, len(self.pending),
                    self.var_loss.get(), "开" if self.var_ack.get() else "关",
                    self.var_interval.get()))
        self.lbl_stats.configure(
            text="发布数:%d    送达数:%d    无人接收数:%d\n丢失数:%d    重发数:%d"
                 % (self.stats["pub"], self.stats["deliver"], self.stats["nosub"],
                    self.stats["lost"], self.stats["resend"]))

    # ===========================================================
    # 导出:日志 CSV / 方案 TXT(写到脚本目录,文件名带时间戳不覆盖)
    # ===========================================================
    @staticmethod
    def _unique_path(prefix, ext):
        """生成不与已有文件重名的导出路径:前缀_时间戳(_序号).扩展名"""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCRIPT_DIR, "%s_%s%s" % (prefix, stamp, ext))
        n = 1
        while os.path.exists(path):
            path = os.path.join(SCRIPT_DIR, "%s_%s_%d%s" % (prefix, stamp, n, ext))
            n += 1
        return path

    def export_csv(self):
        """把全部日志导出为 CSV(utf-8-sig 编码,Excel 双击可直接打开)"""
        path = self._unique_path("消息模拟器日志", ".csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["周期", "模拟时间", "阶段", "消息编号", "详情"])
            for r in self.log_rows:
                writer.writerow([r["tick"], r["time"], r["phase"],
                                 r["msg"], r["detail"]])
        self.add_log("系统", "日志已导出:%s(共%d条)"
                     % (os.path.basename(path), len(self.log_rows)))
        return path

    def export_scheme_txt(self):
        """导出当前"消息方案"TXT:发布/订阅配置、参数、统计和思考题"""
        lines = [
            "=" * 46,
            "  本地消息发送接收模拟器 · 我的消息方案",
            "=" * 46,
            "课程:清华版《信息科技》五年级下册 第2单元 第3课",
            "      智能种植项目设计——信息的发送与接收",
            "生成时间:%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "模拟进度:%s(共 %d 个周期,每周期=模拟1分钟)"
            % (self.clock_str(), self.tick),
            "",
            "一、发布配置(发送端 → 主题)",
        ]
        for i, s in enumerate(SENDERS):
            topic = self.pub_vars[i].get()
            subs = self._subscribers_of(topic)
            note = ("订阅者:" + "、".join(RECEIVERS[j]["name"] for j in subs)
                    if subs else "⚠ 该主题目前无人订阅!")
            lines.append("  %s → 「%s」(%s)" % (s["name"], topic, note))
        lines += ["", "二、订阅配置(接收端 ← 主题)"]
        for j, r in enumerate(RECEIVERS):
            lines.append("  %s ← 「%s」" % (r["name"], self.sub_vars[j].get()))
        fmt_parts = []
        if self.var_unit.get():
            fmt_parts.append("含单位")
        if self.var_time.get():
            fmt_parts.append("含时间")
        lines += [
            "",
            "三、消息参数",
            "  消息格式:%s" % ("、".join(fmt_parts) if fmt_parts else "只有数值"),
            "  发送间隔:每 %d 个周期一条" % self.var_interval.get(),
            "  丢包率:%d%%" % self.var_loss.get(),
            "  ACK确认:%s" % ("开启(丢失的消息超时自动重发)"
                              if self.var_ack.get() else "关闭(丢了就丢了)"),
            "",
            "四、实验统计",
            "  发布数:%d" % self.stats["pub"],
            "  送达数:%d(广播给多个订阅者时,每份都计一次)" % self.stats["deliver"],
            "  无人接收数:%d" % self.stats["nosub"],
            "  丢失数:%d" % self.stats["lost"],
            "  重发数:%d" % self.stats["resend"],
            "",
            "五、我的思考(请同学们补充完成)",
            "  1. 为什么主题 farm/temp 和 farm/tmep 不能互通?______________________",
            "  2. 一个主题被多个接收端订阅时,消息会怎样传递?______________________",
            "  3. ACK 确认开启和关闭,丢包时结果有什么不同?______________________",
            "  4. 我的智能种植项目里,还想增加的发送端/接收端:______________________",
            "",
            "(本方案由本机离线生成,未上传任何数据)",
        ]
        path = self._unique_path("我的消息方案", ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.add_log("系统", "方案已导出:%s" % os.path.basename(path))
        return path

    # ===========================================================
    # 导入方案 JSON
    # ===========================================================
    def import_scheme(self, path=None, choice=None):
        """
        导入消息方案 JSON。
        path:文件路径,不传则弹出文件选择框;
        choice:方案序号(0起),不传且文件里有多组方案时弹出选择窗口。
        """
        if path is None:
            path = filedialog.askopenfilename(
                title="选择消息方案文件",
                initialdir=SCRIPT_DIR,
                filetypes=[("JSON 方案文件", "*.json"), ("所有文件", "*.*")])
            if not path:
                return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            schemes = data.get("方案列表")
            if not isinstance(schemes, list) or not schemes:
                raise ValueError("文件中没有找到「方案列表」")
        except Exception as exc:
            messagebox.showerror("导入失败",
                                 "无法读取方案文件:\n%s\n\n请确认选择的是本工具的示例方案 JSON。" % exc,
                                 parent=self.root)
            return False

        if choice is not None:
            self._apply_scheme(schemes[choice])
            return True
        if len(schemes) == 1:
            self._apply_scheme(schemes[0])
            return True
        # 多组方案:弹出选择窗口,让学生挑一组
        self._show_scheme_chooser(schemes)
        return True

    def _show_scheme_chooser(self, schemes):
        """弹出一个小窗口列出所有方案,双击或点「载入」应用所选方案"""
        win = tk.Toplevel(self.root)
        win.title("选择要导入的消息方案")
        win.geometry("480x320")
        win.transient(self.root)
        tk.Label(win, text="文件中包含多组示例方案,请选择一组:",
                 anchor="w").pack(fill="x", padx=10, pady=(10, 4))
        lb = tk.Listbox(win, height=6)
        for cfg in schemes:
            lb.insert("end", " %s —— %s" % (cfg.get("名称", "未命名"),
                                            cfg.get("说明", "")[:30]))
        lb.pack(fill="both", expand=True, padx=10)
        lb.selection_set(0)

        desc = tk.Label(win, text="", anchor="w", justify="left",
                        fg="#5b7186", wraplength=450)
        desc.pack(fill="x", padx=10, pady=4)

        def show_desc(_event=None):
            sel = lb.curselection()
            if sel:
                desc.configure(text=schemes[sel[0]].get("说明", ""))

        def do_load(_event=None):
            sel = lb.curselection()
            if sel:
                self._apply_scheme(schemes[sel[0]])
                win.destroy()

        lb.bind("<<ListboxSelect>>", show_desc)
        lb.bind("<Double-Button-1>", do_load)
        show_desc()
        row = tk.Frame(win)
        row.pack(pady=6)
        tk.Button(row, text="✔ 载入所选方案", bg="#2eb872", fg="white",
                  command=do_load).pack(side="left", padx=4)
        tk.Button(row, text="取消", command=win.destroy).pack(side="left", padx=4)

    def _apply_scheme(self, cfg):
        """把一组方案写入各配置变量,并清空在途消息(统计与日志保留,便于对比)"""
        name = cfg.get("名称", "未命名")
        pub = cfg.get("发布主题", {})
        for i, s in enumerate(SENDERS):
            if s["name"] in pub:
                self.pub_vars[i].set(str(pub[s["name"]]))
        sub = cfg.get("订阅主题", {})
        for j, r in enumerate(RECEIVERS):
            if r["name"] in sub:
                self.sub_vars[j].set(str(sub[r["name"]]))
        fmt = cfg.get("消息格式", {})
        if "含单位" in fmt:
            self.var_unit.set(bool(fmt["含单位"]))
        if "含时间" in fmt:
            self.var_time.set(bool(fmt["含时间"]))
        if "发送间隔" in cfg:
            self.var_interval.set(int(cfg["发送间隔"]))
        if "丢包率" in cfg:
            self.var_loss.set(int(cfg["丢包率"]))
        if "ACK确认" in cfg:
            self.var_ack.set(bool(cfg["ACK确认"]))
        # 清空在途消息和重发任务,避免新旧方案的消息混在一起
        self.messages = []
        self.pending = []
        self.server_queue = []
        self.add_log("调参", "已导入方案「%s」:发布[%s] 订阅[%s] 间隔%d 丢包%d%% ACK%s"
                     % (name,
                        " ".join("%s→%s" % (SENDERS[i]["name"][:2], self.pub_vars[i].get())
                                 for i in range(len(SENDERS))),
                        " ".join("%s←%s" % (RECEIVERS[j]["name"][:2], self.sub_vars[j].get())
                                 for j in range(len(RECEIVERS))),
                        self.var_interval.get(), self.var_loss.get(),
                        "开" if self.var_ack.get() else "关"))
        self._render()

    # ===========================================================
    # 帮助窗口
    # ===========================================================
    def show_help(self):
        """弹出帮助窗口(重复点击只保留一个)"""
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        win = tk.Toplevel(self.root)
        self.help_win = win
        win.title("帮助 · 本地消息发送接收模拟器")
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
    # 关闭
    # ===========================================================
    def on_close(self):
        """窗口关闭:停止模拟、取消 after 任务、销毁窗口"""
        self.running = False
        self._cancel_after()
        self.root.destroy()


def main():
    root = tk.Tk()
    PubSubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
