# -*- coding: utf-8 -*-
"""
智能家居控制与规则模拟器
========================
配套教材:清华大学出版社《信息科技》五年级下册
          第3单元 第2课《智能家居背后的技术原理——小程序控制开关灯》(教材 P91—101)

工具定位:
    在电脑上模拟"用手机小程序远程控制家里的灯"的完整过程。
    左边是一部虚拟手机,上面运行着虚构小程序「我家小屋」(不是任何真实平台);
    中间是消息链路:小程序 → 网络 → 物联网平台 → 控制器;
    右边是家里的两个房间(客厅、卧室)和真实的灯。
    学生点小程序上的按钮发出开关灯指令,亲眼看到指令小圆点沿链路逐跳移动、
    控制器执行后灯亮/灭,再看到"状态回传"小圆点返回小程序、图标才更新。
    还可以制造网络延迟、丢包、断网,切换访客账号体验权限拒绝,
    关闭防抖体验连点造成灯闪烁,并勾选"天黑自动开灯"等自动化规则。

核心可观察现象(对应教材知识点):
    1. 指令要经过"发送→送达→执行→回传→图标更新"完整生命周期;
    2. 状态回传丢失时,小程序图标与灯的真实状态会不一致(界面会给出⚠提醒);
    3. 访客账号没有开灯权限,指令走到物联网平台就被拒绝并回传"被拒"通知;
    4. 关闭防抖后快速连点按钮,多条切换指令都会被执行,灯会来回闪烁;
    5. 把环境光照调低,勾选的"天黑自动开灯"规则会由平台自动发出指令。

技术说明(写给老师):
    * 仅使用 Python 标准库(tkinter / ttk / json / csv / random / os / datetime),
      无需安装任何第三方库,可在 Windows 上离线运行。
    * 模拟引擎用 root.after() 定时驱动,没有使用线程;
      关闭窗口时会正确取消 after 任务,不会有残留进程。
    * 消息链路模型:
        - 链路共 4 个节点:小程序(0) → 网络(1) → 物联网平台(2) → 控制器(3);
        - 每个模拟周期,消息前进一跳;"网络延迟"让每一跳多等几个周期;
        - 只有经过"网络段"(小程序↔网络↔平台之间的两条边)的消息
          才会受丢包和断网影响;平台↔控制器视为可靠的本地连接,
          所以存放在平台上的自动化规则在手机断网时仍能工作;
        - 断网时消息在网络段排队,排队超过 25 个周期判定过期作废;
        - 权限校验发生在物联网平台节点:访客账号的"开灯"指令会被拒绝,
          并生成一条"被拒"通知回传给小程序(访客可以关灯);
        - 控制器执行指令后,生成"状态回传"消息按原路返回,
          小程序收到回传后才更新按钮图标——回传丢了,图标就不会更新;
        - 防抖开启时,同一盏灯在 3 个周期内的重复点击会被小程序忽略。
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
NODE_NAMES = ["小程序", "网络", "物联网平台", "控制器"]   # 链路四节点
NET_EDGES = ((0, 1), (1, 2))     # "网络段":只有这两条边会丢包/断网
QUEUE_EXPIRE_TICKS = 25          # 断网排队超过 25 个周期判定指令过期
DEBOUNCE_TICKS = 3               # 防抖窗口:同一盏灯 3 个周期内只接受一次点击
RULE_COOLDOWN_TICKS = 15         # 光照类规则触发后的冷却周期,防止反复触发
SAVER_ON_TICKS = 60              # 节能规则:灯连续亮 60 个周期就自动关
DARK_THRESHOLD = 30              # 环境光照低于 30% 视为"天黑"
BRIGHT_THRESHOLD = 70            # 环境光照高于 70% 视为"天亮"

LAMPS = ("living", "bed")                         # 两盏灯的内部编号
LAMP_NAMES = {"living": "客厅灯", "bed": "卧室灯"}  # 界面显示名

# 脚本所在目录:导出文件、示例场景文件都放在这里
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 帮助窗口显示的使用说明(与 使用说明.txt 内容一致的精简版)
HELP_TEXT = """【智能家居控制与规则模拟器 · 快速帮助】

一、界面分区
  ① 场景区(左上):
     左边手机上是虚构小程序「我家小屋」,有客厅灯、卧室灯两个按钮,
       按钮上的图标显示"小程序认为"的灯状态;
     中间下方是消息链路:小程序→网络→物联网平台→控制器,
       橙色圆点=开关灯指令,绿色圆点=状态回传,
       灰色=断网排队中,红色=丢失/过期/被拒;
     右边是家里的客厅和卧室,灯亮时有黄色光效——
       它才是灯的"真实状态"。
  ② 参数区(右上):网络延迟、丢包率、环境光照 3 个滑块,
     断网、防抖 2 个开关,家人/访客账号切换。
  ③ 规则区(右中):3 条可勾选的自动化规则(存放在物联网平台上)。
  ④ 运行控制区:开始 / 暂停 / 单步 / 重置;
     开关灯要直接点手机上的小程序按钮。
  ⑤ 状态与日志区(下方)+ 结果区(右下):
     每条指令的生命周期日志、统计数据和
     导出日志CSV / 导出小结TXT / 导入示例场景 / 帮助。

二、基本玩法
  1. 点「开始」让模拟时间流动;
  2. 点手机上的「客厅灯」按钮,看橙色指令圆点逐跳走到控制器,
     灯亮了,再看绿色回传圆点走回小程序,按钮图标才变亮;
  3. 把丢包率调大:回传丢失时,灯是亮的、图标却没变——
     中间面板会出现 ⚠ 不一致提醒;
  4. 切到「访客」账号再点开灯:指令走到平台就被拒绝;
  5. 关掉「防抖」快速连点按钮:多条切换指令让灯来回闪烁;
  6. 勾选「天黑自动开客厅灯」,把环境光照拖到 30% 以下,
     平台会自动发出开灯指令(手机断网时它照样工作)。

三、一条指令的生命周期
  发送 → 送达(到控制器)→ 执行(灯变化)→ 回传 → 图标更新
  半路上可能:排队(断网)、丢失(丢包)、过期(排队太久)、
  被拒(访客无开灯权限)。中间面板会实时显示最近一条指令走到哪一步。

更多内容请阅读同文件夹中的《使用说明.txt》。"""


class SmartHomeApp:
    """智能家居控制与规则模拟器主程序(单窗口 Tkinter 应用)"""

    # ===========================================================
    # 初始化
    # ===========================================================
    def __init__(self, root):
        self.root = root
        root.title("智能家居控制与规则模拟器 · 清华版《信息科技》五下 第3单元第2课")
        root.geometry("1150x820")
        root.minsize(1020, 720)

        # ---- 模拟引擎状态 ----
        self.running = False        # 是否正在连续运行
        self.after_id = None        # root.after 的任务编号,关闭窗口时要取消
        self.tick_interval_ms = 400  # 每个模拟周期的真实间隔(毫秒)
        self.tick = 0               # 已经过的模拟周期数

        # ---- 家居设备状态 ----
        # actual:灯的真实状态(True=亮);app:小程序图标显示的状态
        self.actual = {"living": False, "bed": False}
        self.app_state = {"living": False, "bed": False}
        self.pending = {"living": None, "bed": None}   # 已发出但未确认的目标状态
        self.last_click = {"living": -99, "bed": -99}  # 上次点击周期号(防抖用)
        self.on_since = {"living": None, "bed": None}  # 灯连续亮起的起始周期(节能规则用)
        self.reject_flash = {"living": -99, "bed": -99}  # "被拒"提示的显示时刻

        # ---- 消息与规则 ----
        self.messages = []          # 正在传输的消息列表(字典)
        self.msg_id = 0             # 指令自增编号
        self.last_traced = None     # 最近一条指令(中间面板显示其生命周期)
        self.rule_cooldown = {"dark": 0, "dawn": 0}    # 光照规则冷却计数

        # ---- 统计数据(结果区显示、导出小结用)----
        self.stats = {"cmd": 0, "success": 0, "rejected": 0,
                      "lost": 0, "rule": 0}
        self.log_rows = []          # 日志记录列表,导出 CSV 用

        # ---- 可调参数(与界面滑块/开关绑定的 Tk 变量)----
        self.var_latency = tk.IntVar(value=0)      # 网络延迟(每跳额外等待周期数)
        self.var_loss = tk.IntVar(value=0)         # 丢包率(%)
        self.var_ambient = tk.IntVar(value=70)     # 环境光照(%)
        self.var_offline = tk.BooleanVar(value=False)   # 断网开关
        self.var_debounce = tk.BooleanVar(value=True)   # 防抖开关
        self.var_account = tk.StringVar(value="家人")    # 当前登录账号
        self.var_rule_dark = tk.BooleanVar(value=False)   # 规则1:天黑自动开客厅灯
        self.var_rule_dawn = tk.BooleanVar(value=False)   # 规则2:天亮自动关所有灯
        self.var_rule_saver = tk.BooleanVar(value=False)  # 规则3:长亮节能自动关

        self.help_win = None        # 帮助窗口(避免重复打开)

        self._build_ui()
        # 窗口关闭时先停止模拟、取消 after 任务,再销毁窗口
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.add_log("系统", "欢迎使用!点「开始」运行模拟,再点手机上的小程序按钮开关灯。")
        self._render()

    # ===========================================================
    # 界面搭建
    # ===========================================================
    def _build_ui(self):
        # 中文界面字体:Windows 上用微软雅黑,其他系统自动回退到默认字体
        base_font = ("Microsoft YaHei UI", 10)
        self.root.option_add("*Font", base_font)

        # ---- 顶部标题 ----
        header = tk.Frame(self.root, bg="#7a3db8")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text="🏠 智能家居控制与规则模拟器",
                 font=("Microsoft YaHei UI", 16, "bold"),
                 bg="#7a3db8", fg="white").pack(side="left", padx=14, pady=6)
        tk.Label(header,
                 text="第3单元 第2课 智能家居背后的技术原理——小程序控制开关灯 · 完全离线 · 虚构小程序,不涉及真实平台",
                 bg="#7a3db8", fg="#ecdcff").pack(side="left", padx=6)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_rowconfigure(2, weight=2)

        # ================= ① 场景区(Canvas) =================
        scene_frame = tk.LabelFrame(
            self.root,
            text="① 场景区:小程序「我家小屋」 + 消息链路 + 房间与灯(开关灯请直接点手机上的按钮)",
            padx=4, pady=4)
        scene_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        scene_frame.grid_rowconfigure(0, weight=1)
        scene_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(scene_frame, width=700, height=490,
                                bg="#f2edfa", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        # 小程序按钮的点击绑定:tag 绑定只需做一次,重画后依然有效
        self.canvas.tag_bind("btn_living", "<Button-1>",
                             lambda e: self.on_lamp_button("living"))
        self.canvas.tag_bind("btn_bed", "<Button-1>",
                             lambda e: self.on_lamp_button("bed"))

        # ================= 右侧面板 =================
        right = tk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)

        # ---- ② 参数区 ----
        param_frame = tk.LabelFrame(right, text="② 参数区(调节立即生效)",
                                    padx=8, pady=2)
        param_frame.pack(fill="x")

        def add_scale(text, var, frm, to, step, unit):
            """添加一行带说明的滑块;数值变化时写一条调参日志"""
            row = tk.Frame(param_frame)
            row.pack(fill="x")
            tk.Label(row, text=text, width=13, anchor="w").pack(side="left")
            scale = tk.Scale(row, variable=var, from_=frm, to=to,
                             resolution=step, orient="horizontal",
                             length=150, showvalue=True,
                             command=lambda v, t=text, u=unit:
                             self._on_param_change(t, v, u))
            scale.pack(side="left", fill="x", expand=True)
            tk.Label(row, text=unit, width=3, anchor="w").pack(side="left")
            return scale

        add_scale("网络延迟", self.var_latency, 0, 3, 1, "档")
        add_scale("丢包率", self.var_loss, 0, 80, 10, "%")
        add_scale("环境光照", self.var_ambient, 0, 100, 5, "%")

        check_row = tk.Frame(param_frame)
        check_row.pack(fill="x", pady=(2, 0))
        tk.Checkbutton(check_row, text="🔌 断网", variable=self.var_offline,
                       command=self._on_offline_change).pack(side="left")
        tk.Checkbutton(check_row, text="🛡 防抖(防连点)", variable=self.var_debounce,
                       command=self._on_debounce_change).pack(side="left", padx=10)

        acc_row = tk.Frame(param_frame)
        acc_row.pack(fill="x", pady=(0, 4))
        tk.Label(acc_row, text="登录账号:").pack(side="left")
        tk.Radiobutton(acc_row, text="👨‍👩‍👧 家人", value="家人",
                       variable=self.var_account,
                       command=self._on_account_change).pack(side="left")
        tk.Radiobutton(acc_row, text="🧑 访客(无开灯权限)", value="访客",
                       variable=self.var_account,
                       command=self._on_account_change).pack(side="left", padx=6)

        # ---- ③ 规则区 ----
        rule_frame = tk.LabelFrame(right, text="③ 规则区:自动化规则(存放在物联网平台上)",
                                   padx=8, pady=2)
        rule_frame.pack(fill="x", pady=(6, 0))
        tk.Checkbutton(rule_frame,
                       text="🌙 天黑自动开客厅灯(光照 < %d%%)" % DARK_THRESHOLD,
                       variable=self.var_rule_dark, anchor="w",
                       command=lambda: self._on_rule_change("天黑自动开客厅灯",
                                                            self.var_rule_dark)
                       ).pack(fill="x")
        tk.Checkbutton(rule_frame,
                       text="🌞 天亮自动关所有灯(光照 > %d%%)" % BRIGHT_THRESHOLD,
                       variable=self.var_rule_dawn, anchor="w",
                       command=lambda: self._on_rule_change("天亮自动关所有灯",
                                                            self.var_rule_dawn)
                       ).pack(fill="x")
        tk.Checkbutton(rule_frame,
                       text="💡 长亮节能:连续亮 %d 周期自动关" % SAVER_ON_TICKS,
                       variable=self.var_rule_saver, anchor="w",
                       command=lambda: self._on_rule_change("长亮节能",
                                                            self.var_rule_saver)
                       ).pack(fill="x")

        # ---- ④ 运行控制区 ----
        ctrl_frame = tk.LabelFrame(right, text="④ 运行控制区", padx=8, pady=6)
        ctrl_frame.pack(fill="x", pady=(6, 0))
        row1 = tk.Frame(ctrl_frame)
        row1.pack(fill="x")
        self.btn_start = tk.Button(row1, text="▶ 开始", width=7,
                                   bg="#2eb872", fg="white",
                                   activebackground="#1e8f56",
                                   command=self.start)
        self.btn_start.pack(side="left", padx=2, pady=2)
        self.btn_pause = tk.Button(row1, text="⏸ 暂停", width=7,
                                   command=self.pause)
        self.btn_pause.pack(side="left", padx=2)
        tk.Button(row1, text="⏭ 单步", width=7,
                  command=self.step_once).pack(side="left", padx=2)
        tk.Button(row1, text="🔄 重置", width=7,
                  command=self.reset).pack(side="left", padx=2)
        tk.Label(ctrl_frame, fg="#5b7186", anchor="w",
                 text="开/关灯 = 直接点左边手机上的小程序按钮").pack(fill="x")

        # ---- ⑥ 结果区 ----
        result_frame = tk.LabelFrame(right, text="⑥ 结果区:统计与导出", padx=8, pady=6)
        result_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.lbl_stats = tk.Label(result_frame, justify="left", anchor="w",
                                  text="", fg="#20344b")
        self.lbl_stats.pack(fill="x")
        btns = tk.Frame(result_frame)
        btns.pack(fill="x", pady=4)
        tk.Button(btns, text="📥 导出日志CSV",
                  command=self.export_csv).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="📄 导出小结TXT",
                  command=self.export_report).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="📂 导入示例场景",
                  command=self.import_scene).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="❓ 帮助",
                  command=self.show_help).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)
        tk.Label(result_frame, fg="#5b7186", justify="left", anchor="w",
                 text="导出文件保存在本程序所在文件夹,\n文件名自动加时间戳,不会覆盖旧文件。"
                 ).pack(fill="x")

        # ================= ⑤ 状态与日志区 =================
        log_frame = tk.LabelFrame(self.root, text="⑤ 状态与日志区(每条指令的生命周期都会记录在这里)",
                                  padx=6, pady=4)
        log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew",
                       padx=8, pady=(0, 8))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        # 状态栏:一行实时数据
        self.lbl_status = tk.Label(log_frame, anchor="w", fg="#7a3db8",
                                   font=("Microsoft YaHei UI", 11, "bold"))
        self.lbl_status.grid(row=0, column=0, columnspan=2, sticky="ew")

        # 滚动日志
        self.log_text = tk.Text(log_frame, height=9, state="disabled",
                                bg="#241b33", fg="#e6def5",
                                font=("Microsoft YaHei UI", 9))
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical",
                               command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        # 不同类型日志用不同颜色,方便学生找到关键事件
        self.log_text.tag_configure("指令", foreground="#9fc7ff")
        self.log_text.tag_configure("设备", foreground="#7fe3ad")
        self.log_text.tag_configure("网络", foreground="#ffb35c")
        self.log_text.tag_configure("安全", foreground="#ff8f94")
        self.log_text.tag_configure("规则", foreground="#d8a6ff")
        self.log_text.tag_configure("调参", foreground="#9adbe0")

    # ===========================================================
    # 日志
    # ===========================================================
    def add_log(self, kind, content):
        """追加一条日志:同时写入内存列表(供导出)和界面 Text(供查看)"""
        row = {"tick": self.tick, "type": kind, "content": content,
               "living": "亮" if self.actual["living"] else "灭",
               "bed": "亮" if self.actual["bed"] else "灭",
               "app": "客厅%s/卧室%s" % ("开" if self.app_state["living"] else "关",
                                        "开" if self.app_state["bed"] else "关")}
        self.log_rows.append(row)
        if len(self.log_rows) > 1200:      # 防止长时间运行占用过多内存
            self.log_rows.pop(0)
        line = "[周期%03d] [%s] %s\n" % (self.tick, kind, content)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, kind)
        # 界面上最多保留 500 行,超出就删掉最早的
        if int(self.log_text.index("end-1c").split(".")[0]) > 500:
            self.log_text.delete("1.0", "2.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ===========================================================
    # 参数变化回调(写日志,方便学生对照"改了什么→发生了什么")
    # ===========================================================
    def _on_param_change(self, name, value, unit):
        # Scale 初始化时也会触发一次回调,此时界面尚未建完,跳过
        if not hasattr(self, "log_text"):
            return
        # 避免拖动过程刷屏:只在数值真正变化时记录
        key = (name, str(value))
        if getattr(self, "_last_param_log", None) == key:
            return
        self._last_param_log = key
        self.add_log("调参", "%s 改为 %s%s" % (name, value, unit))
        self._render()

    def _on_offline_change(self):
        if self.var_offline.get():
            self.add_log("网络", "网络断开!此后发送的指令会在网络段排队等待")
        else:
            self.add_log("网络", "网络恢复!排队指令继续发送,排队超过%d周期的会被判过期"
                         % QUEUE_EXPIRE_TICKS)
        self._render()

    def _on_debounce_change(self):
        on = self.var_debounce.get()
        self.add_log("调参", "防抖 %s" % ("开启:%d周期内的连点会被忽略" % DEBOUNCE_TICKS if on
                                         else "关闭(小心!快速连点会让灯闪烁)"))

    def _on_account_change(self):
        acc = self.var_account.get()
        if acc == "访客":
            self.add_log("安全", "已切换为「访客」账号:没有开灯权限,开灯指令会被平台拒绝(可以关灯)")
        else:
            self.add_log("安全", "已切换为「家人」账号:拥有全部控制权限")
        self._render()

    def _on_rule_change(self, name, var):
        self.add_log("规则", "自动化规则「%s」%s" % (name, "已开启" if var.get() else "已关闭"))

    # ===========================================================
    # 运行控制:开始 / 暂停 / 单步 / 重置
    # ===========================================================
    def start(self):
        """开始(或继续)连续运行"""
        if self.running:
            return
        self.running = True
        self.btn_start.configure(state="disabled")
        self.add_log("系统", "模拟开始运行(每 %.1f 秒推进一个周期)"
                     % (self.tick_interval_ms / 1000.0))
        self._schedule_next()

    def pause(self):
        """暂停连续运行(不清除任何状态)"""
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(state="normal")
        self._cancel_after()
        self.add_log("系统", "模拟已暂停,可用「单步」逐周期观察指令移动")

    def step_once(self):
        """单步:先暂停,再推进一个周期,方便逐跳观察消息移动"""
        if self.running:
            self.pause()
        self._tick_once()

    def reset(self):
        """重置:灯全灭、消息清空、统计清零(参数滑块与规则勾选保持不变,日志保留)"""
        self.pause()
        self.tick = 0
        self.actual = {"living": False, "bed": False}
        self.app_state = {"living": False, "bed": False}
        self.pending = {"living": None, "bed": None}
        self.last_click = {"living": -99, "bed": -99}
        self.on_since = {"living": None, "bed": None}
        self.reject_flash = {"living": -99, "bed": -99}
        self.messages = []
        self.last_traced = None
        self.rule_cooldown = {"dark": 0, "dawn": 0}
        self.var_offline.set(False)
        self.stats = {"cmd": 0, "success": 0, "rejected": 0,
                      "lost": 0, "rule": 0}
        self.add_log("系统", "已重置:所有灯熄灭、消息清空、统计清零(参数与规则勾选保持不变)")
        self._render()

    # ===========================================================
    # 小程序按钮点击(场景区手机上的按钮就是操作入口)
    # ===========================================================
    def on_lamp_button(self, lamp):
        """点击小程序上的灯按钮:经过防抖检查后,发出一条开/关灯指令"""
        name = LAMP_NAMES[lamp]
        # ---- 防抖:同一盏灯短时间内的重复点击被小程序直接忽略 ----
        if self.var_debounce.get() and self.tick - self.last_click[lamp] < DEBOUNCE_TICKS:
            self.add_log("安全", "防抖生效:忽略了对「%s」的连点(距上次点击不足%d周期)"
                         % (name, DEBOUNCE_TICKS))
            return
        self.last_click[lamp] = self.tick
        # 目标动作:按"小程序当前认为的状态"取反;若已有未确认指令,则按它继续取反,
        # 这样关闭防抖后快速连点会发出 开/关/开… 交替指令,灯就会闪烁
        base_on = self.pending[lamp] if self.pending[lamp] is not None \
            else self.app_state[lamp]
        action = "关" if base_on else "开"
        self.pending[lamp] = (action == "开")
        msg = self._send_command(lamp, action, source="user")
        self.add_log("指令", "指令#%d 发送:小程序请求「%s%s」(账号:%s)"
                     % (msg["id"], action, name, msg["account"]))
        if not self.running:
            self.add_log("系统", "提示:当前是暂停状态,点「单步」或「开始」让指令走起来")
        self._render()

    # ===========================================================
    # 消息系统:小程序(0)→网络(1)→物联网平台(2)→控制器(3);回传反向
    # ===========================================================
    def _send_command(self, lamp, action, source):
        """创建一条下行控制指令。source: 'user'=小程序按钮, 'rule'=平台规则"""
        self.stats["cmd"] += 1
        self.msg_id += 1
        msg = {
            "id": self.msg_id, "lamp": lamp, "action": action,
            "dir": "down", "kind": "rule" if source == "rule" else "cmd",
            "label": "%s%s" % (action, LAMP_NAMES[lamp]),
            # 规则指令由平台直接发出(hop=2),不经过手机和网络段
            "hop": 2 if source == "rule" else 0,
            "wait": 0,        # 延迟造成的额外等待周期
            "queued": False,  # 是否因断网排队
            "done": False,    # 是否已结束(执行/被拒/丢失/过期)
            "done_age": 0,    # 结束后再显示几个周期(动画淡出)
            "result": "",     # 结束原因,用于着色
            "sent_tick": self.tick,
            "account": "平台规则" if source == "rule" else self.var_account.get(),
            "checked": source == "rule",   # 权限是否已校验(规则视为平台自己发出)
            "origin": None,
            "trace": ["规则触发(平台发出)"] if source == "rule" else ["发送"],
        }
        self.messages.append(msg)
        self.last_traced = msg
        return msg

    def _send_return(self, origin, kind, label):
        """创建一条上行回传消息(状态回传或被拒通知),从当前节点走回小程序"""
        self.msg_id += 1
        msg = {
            "id": self.msg_id, "lamp": origin["lamp"], "action": origin["action"],
            "dir": "up", "kind": kind, "label": label,
            "hop": 3 if kind == "status" else 2,   # 状态回传从控制器出发,被拒通知从平台出发
            "wait": 0, "queued": False, "done": False, "done_age": 0,
            "result": "", "sent_tick": self.tick,
            "account": origin["account"], "checked": True,
            "origin": origin, "trace": None,
        }
        self.messages.append(msg)
        return msg

    @staticmethod
    def _finish_msg(msg, result):
        """标记消息结束:result 取值 ok/lost/expired/rejected"""
        msg["done"] = True
        msg["result"] = result

    @staticmethod
    def _edge_risky(msg):
        """判断消息下一跳要走的边是否属于'网络段'(会丢包/断网)"""
        if msg["dir"] == "down":
            edge = (msg["hop"], msg["hop"] + 1)
        else:
            edge = (msg["hop"] - 1, msg["hop"])
        return edge in NET_EDGES

    def _advance_messages(self):
        """每周期让所有在途消息前进一跳(受延迟/丢包/断网影响)"""
        offline = self.var_offline.get()
        # 用快照遍历:途中生成的回传消息下个周期才开始移动
        for m in list(self.messages):
            if m["done"]:
                m["done_age"] += 1     # 已结束的消息保留几帧用于显示颜色
                continue

            # 延迟:每一跳走完后要等 wait 个周期
            if m["wait"] > 0:
                m["wait"] -= 1
                continue

            # 断网排队中:等网络恢复;恢复时检查是否过期
            if m["queued"]:
                if offline:
                    continue
                m["queued"] = False
                if self.tick - m["sent_tick"] > QUEUE_EXPIRE_TICKS:
                    # 排队太久:过期指令作废——防止网络恢复后一堆旧指令乱执行
                    self.stats["lost"] += 1
                    self._finish_msg(m, "expired")
                    self.pending[m["lamp"]] = None
                    self._trace(m, "排队太久,过期作废")
                    self.add_log("安全", "指令#%d「%s」排队超过%d周期已过期,作废不执行"
                                 % (m["id"], m["label"], QUEUE_EXPIRE_TICKS))
                    continue

            # ---- 检查下一跳要走的边:断网排队 / 丢包 ----
            if self._edge_risky(m):
                if offline:
                    if not m["queued"]:
                        m["queued"] = True
                        self._trace(m, "排队中(断网)")
                        self.add_log("网络", "断网中:指令#%d「%s」在网络段排队等待"
                                     % (m["id"], m["label"]))
                    continue
                if random.random() < self.var_loss.get() / 100.0:
                    self.stats["lost"] += 1
                    self._finish_msg(m, "lost")
                    # 小程序等不到确认(超时):取消"发送中"提示,但图标不会更新
                    self.pending[m["lamp"]] = None
                    if m["dir"] == "up" and m["kind"] == "status":
                        # 核心现象:状态回传丢失 → 小程序图标不更新,与灯不一致
                        self._trace(m, "回传丢失")
                        self.add_log("网络", "⚠ 状态回传「%s」在网络中丢失!小程序图标不会更新,"
                                             "可能和灯的真实状态不一致" % m["label"])
                    else:
                        self._trace(m, "丢失")
                        self.add_log("网络", "指令#%d「%s」在网络中丢失!接收方永远收不到它"
                                     % (m["id"], m["label"]))
                    continue

            # ---- 正常前进一跳 ----
            m["hop"] += 1 if m["dir"] == "down" else -1
            m["wait"] = self.var_latency.get()

            # 下行指令到达物联网平台(节点2):做权限校验
            if m["dir"] == "down" and m["hop"] == 2 and not m["checked"]:
                m["checked"] = True
                if m["account"] == "访客" and m["action"] == "开":
                    # 访客没有开灯权限:平台拒绝执行,并回传"被拒"通知
                    self.stats["rejected"] += 1
                    self._finish_msg(m, "rejected")
                    self._trace(m, "被平台拒绝(访客无开灯权限)")
                    self.add_log("安全", "指令#%d「%s」被物联网平台拒绝:访客账号没有开灯权限"
                                 % (m["id"], m["label"]))
                    self._send_return(m, "reject", "被拒:无权限")
                    continue

            # 下行指令到达控制器(节点3):执行
            if m["dir"] == "down" and m["hop"] >= 3:
                self._exec_command(m)
            # 上行回传到达小程序(节点0):更新图标或显示被拒
            elif m["dir"] == "up" and m["hop"] <= 0:
                self._deliver_return(m)

        # 清理:结束超过 3 个周期的消息从列表移除
        self.messages = [m for m in self.messages
                         if not (m["done"] and m["done_age"] > 3)]

    @staticmethod
    def _trace(msg, stage):
        """给指令的生命周期轨迹追加一个阶段(回传消息记到原指令上)"""
        target = msg["origin"] if msg["origin"] is not None else msg
        if target.get("trace") is not None:
            target["trace"].append(stage)

    def _exec_command(self, m):
        """下行指令到达控制器:执行开/关灯,并生成状态回传消息"""
        lamp = m["lamp"]
        turn_on = (m["action"] == "开")
        self._finish_msg(m, "ok")
        self._trace(m, "送达")
        self._trace(m, "执行")
        self.stats["success"] += 1
        changed = (self.actual[lamp] != turn_on)
        self.actual[lamp] = turn_on
        # 记录灯连续亮起的起始周期(节能规则用)
        if turn_on:
            if self.on_since[lamp] is None:
                self.on_since[lamp] = self.tick
        else:
            self.on_since[lamp] = None
        if changed:
            self.add_log("设备", "控制器执行指令#%d:%s → %s%s"
                         % (m["id"], m["label"], LAMP_NAMES[lamp],
                            "亮了💡" if turn_on else "熄灭"))
        else:
            self.add_log("设备", "控制器执行指令#%d:%s(灯本来就是%s的)"
                         % (m["id"], m["label"], "亮" if turn_on else "灭"))
        # 生成状态回传:告诉小程序"灯现在真的开/关了"
        self._send_return(m, "status", "%s已%s" % (LAMP_NAMES[lamp], m["action"]))
        self._trace(m, "回传中")

    def _deliver_return(self, m):
        """上行回传到达小程序:状态回传→更新图标;被拒通知→提示无权限"""
        lamp = m["lamp"]
        self._finish_msg(m, "ok")
        if m["kind"] == "status":
            self.app_state[lamp] = (m["action"] == "开")
            self.pending[lamp] = None
            self._trace(m, "图标更新")
            self.add_log("指令", "小程序收到状态回传「%s」,按钮图标已更新✔" % m["label"])
        else:   # reject:被拒通知
            self.pending[lamp] = None
            self.reject_flash[lamp] = self.tick
            self._trace(m, "小程序收到被拒通知")
            self.add_log("安全", "小程序收到「被拒」通知:%s的开灯请求没有权限,图标保持不变"
                         % LAMP_NAMES[lamp])

    # ===========================================================
    # 自动化规则引擎(运行在"物联网平台"上,每周期检查一次)
    # ===========================================================
    def _lamp_busy(self, lamp):
        """该灯是否已有未完成的下行指令在路上(避免规则重复发指令)"""
        return any((not m["done"]) and m["dir"] == "down" and m["lamp"] == lamp
                   for m in self.messages)

    def _run_rules(self):
        ambient = self.var_ambient.get()
        for key in self.rule_cooldown:
            if self.rule_cooldown[key] > 0:
                self.rule_cooldown[key] -= 1

        # 规则1:天黑自动开客厅灯
        if (self.var_rule_dark.get() and ambient < DARK_THRESHOLD
                and not self.actual["living"]
                and self.rule_cooldown["dark"] == 0
                and not self._lamp_busy("living")):
            self.stats["rule"] += 1
            self.rule_cooldown["dark"] = RULE_COOLDOWN_TICKS
            msg = self._send_command("living", "开", source="rule")
            self.add_log("规则", "规则触发:天黑了(光照%d%% < %d%%),平台自动发出指令#%d「开客厅灯」"
                         % (ambient, DARK_THRESHOLD, msg["id"]))

        # 规则2:天亮自动关所有灯
        if (self.var_rule_dawn.get() and ambient > BRIGHT_THRESHOLD
                and self.rule_cooldown["dawn"] == 0):
            fired = False
            for lamp in LAMPS:
                if self.actual[lamp] and not self._lamp_busy(lamp):
                    self.stats["rule"] += 1
                    fired = True
                    msg = self._send_command(lamp, "关", source="rule")
                    self.add_log("规则", "规则触发:天亮了(光照%d%% > %d%%),平台自动发出指令#%d「关%s」"
                                 % (ambient, BRIGHT_THRESHOLD, msg["id"], LAMP_NAMES[lamp]))
            if fired:
                self.rule_cooldown["dawn"] = RULE_COOLDOWN_TICKS

        # 规则3:长亮节能——灯连续亮太久自动关
        if self.var_rule_saver.get():
            for lamp in LAMPS:
                since = self.on_since[lamp]
                if (since is not None and self.tick - since >= SAVER_ON_TICKS
                        and not self._lamp_busy(lamp)):
                    self.stats["rule"] += 1
                    self.on_since[lamp] = self.tick   # 重新计时,避免连发
                    msg = self._send_command(lamp, "关", source="rule")
                    self.add_log("规则", "规则触发:%s已连续亮%d周期,平台自动发出指令#%d「关灯」节能"
                                 % (LAMP_NAMES[lamp], SAVER_ON_TICKS, msg["id"]))

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
        """推进一个模拟周期:规则检查 → 消息移动 → 重绘"""
        self.tick += 1
        self._run_rules()
        self._advance_messages()
        self._render()

    # ===========================================================
    # 场景绘制(Canvas 每周期全部重画;tag 绑定在 _build_ui 里只做一次)
    # ===========================================================
    def _render(self):
        c = self.canvas
        c.delete("all")
        ambient = self.var_ambient.get()
        offline = self.var_offline.get()
        f9 = ("Microsoft YaHei UI", 9)
        f8 = ("Microsoft YaHei UI", 8)
        fb = ("Microsoft YaHei UI", 10, "bold")

        # ------------------ 左:手机与小程序 ------------------
        c.create_rectangle(16, 34, 180, 344, fill="#20344b",
                           outline="#0e1c2c", width=3)
        c.create_rectangle(24, 56, 172, 322, fill="#f7fbff", outline="")
        c.create_line(80, 45, 116, 45, fill="#5b7186", width=3)  # 听筒
        c.create_rectangle(24, 56, 172, 82, fill="#7a3db8", outline="")
        c.create_text(98, 69, text="我家小屋(虚构小程序)", fill="white", font=f9)
        c.create_text(98, 95, text="账号:%s" % self.var_account.get(),
                      fill="#7a3db8" if self.var_account.get() == "家人" else "#e5484d",
                      font=f9)

        # 两个灯按钮(点击入口,tag 绑定见 _build_ui)
        btn_boxes = {"living": (34, 110, 162, 178), "bed": (34, 192, 162, 260)}
        for lamp, (x1, y1, x2, y2) in btn_boxes.items():
            tag = "btn_%s" % lamp
            on = self.app_state[lamp]
            busy = self._lamp_busy(lamp)
            fill = "#fff3c4" if on else "#e8eef5"
            c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="#7a3db8",
                               width=2, tags=tag)
            # 小灯图标:黄色=小程序认为已开
            cx, cy = x1 + 22, (y1 + y2) // 2
            icon_fill = "#ffd23f" if on else "#b9c4cf"
            c.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, fill=icon_fill,
                          outline="#8a7a20" if on else "#7d8a96", width=2, tags=tag)
            if on:
                for dx, dy in ((-18, 0), (18, 0), (0, -18), (0, 18)):
                    c.create_line(cx + dx * 0.8, cy + dy * 0.8, cx + dx, cy + dy,
                                  fill="#f0a820", width=2, tags=tag)
            c.create_text((x1 + x2) // 2 + 12, cy - 12, text=LAMP_NAMES[lamp],
                          font=fb, fill="#20344b", tags=tag)
            c.create_text((x1 + x2) // 2 + 12, cy + 10,
                          text="图标:%s" % ("开" if on else "关"),
                          font=f8, fill="#5b7186", tags=tag)
            # 状态小字:发送中 / 被拒
            note, color = "", "#5b7186"
            if self.tick - self.reject_flash[lamp] <= 6:
                note, color = "✋ 被拒:无权限", "#e5484d"
            elif busy or self.pending[lamp] is not None:
                note, color = "指令发送中…", "#f59e0b"
            if note:
                c.create_text((x1 + x2) // 2, y2 - 8, text=note,
                              font=f8, fill=color, tags=tag)
        c.create_text(98, 288, text="👆 点按钮开/关灯", fill="#7a3db8", font=f9)
        c.create_text(98, 308, text="图标=小程序认为的状态,\n要等状态回传才更新",
                      fill="#5b7186", font=f8, justify="center")

        # ------------------ 右:房子与两个房间 ------------------
        hx1, hx2 = 468, 690
        c.create_polygon(hx1 - 12, 58, (hx1 + hx2) // 2, 14, hx2 + 12, 58,
                         fill="#b06a3b", outline="#7c4522")
        c.create_rectangle(hx1, 58, hx2, 344, fill="#f7efe2", outline="#7c4522",
                           width=2)
        room_boxes = {"living": (hx1 + 8, 66, hx2 - 8, 198),
                      "bed": (hx1 + 8, 206, hx2 - 8, 336)}
        for lamp, (x1, y1, x2, y2) in room_boxes.items():
            on = self.actual[lamp]
            if on:
                room_fill = "#fff2b8"
            elif ambient < DARK_THRESHOLD:
                room_fill = "#2a3550"          # 天黑且灯灭:房间黑漆漆
            elif ambient > BRIGHT_THRESHOLD:
                room_fill = "#f4f8fd"
            else:
                room_fill = "#cfd6e4"
            c.create_rectangle(x1, y1, x2, y2, fill=room_fill, outline="#a08556")
            name_fill = "#d5deee" if (not on and ambient < DARK_THRESHOLD) else "#5b7186"
            c.create_text(x1 + 34, y1 + 12, text=LAMP_NAMES[lamp][:2],
                          font=f9, fill=name_fill)
            # 吊灯:灯罩 + 灯泡(亮时加两圈光晕)
            cx = (x1 + x2) // 2
            c.create_line(cx, y1, cx, y1 + 26, fill="#7d8a96", width=2)
            bulb_y = y1 + 40
            if on:
                c.create_oval(cx - 34, bulb_y - 30, cx + 34, bulb_y + 38,
                              fill="#ffe98c", outline="")
                c.create_oval(cx - 22, bulb_y - 19, cx + 22, bulb_y + 26,
                              fill="#ffd94f", outline="")
            c.create_polygon(cx - 16, y1 + 26, cx + 16, y1 + 26, cx + 8, y1 + 14,
                             cx - 8, y1 + 14, fill="#7a3db8", outline="#4d2478")
            c.create_oval(cx - 9, bulb_y - 9, cx + 9, bulb_y + 9,
                          fill="#fff2a0" if on else "#9aa7b5",
                          outline="#8a7a20" if on else "#66727e", width=2)
            c.create_text(cx, y2 - 12, text="真实状态:%s" % ("亮 💡" if on else "灭"),
                          font=f9,
                          fill="#b8860b" if on else name_fill)
            # 小程序图标与真实状态不一致的警示(状态回传丢失的后果)
            if self.app_state[lamp] != on and not self._lamp_busy(lamp) \
                    and self.pending[lamp] is None:
                c.create_text(cx, y2 - 30, text="⚠ 与手机图标不一致!",
                              font=f8, fill="#e5484d")

        # ------------------ 中:图例 + 环境 + 指令生命周期 ------------------
        mx = 196
        c.create_text(mx, 26, text="图例:", anchor="w", fill="#5b7186", font=f9)
        legend = [("#f59e0b", "开关灯指令(小程序→控制器)"),
                  ("#2eb872", "状态回传(控制器→小程序)"),
                  ("#9aa7b5", "排队中(断网)"),
                  ("#e5484d", "丢失 / 过期 / 被拒")]
        for i, (color, text) in enumerate(legend):
            y = 42 + i * 18
            c.create_rectangle(mx, y - 6, mx + 12, y + 6, fill=color, outline="")
            c.create_text(mx + 18, y, text=text, anchor="w", fill="#5b7186", font=f8)

        # 环境光照:太阳/月亮 + 说明
        sky_y = 132
        if ambient >= 50:
            c.create_oval(mx + 2, sky_y - 13, mx + 28, sky_y + 13,
                          fill="#ffd23f", outline="#f0a820", width=2)
            sky_word = "白天"
        elif ambient >= DARK_THRESHOLD:
            c.create_oval(mx + 2, sky_y - 13, mx + 28, sky_y + 13,
                          fill="#f5c98b", outline="#d09a4e", width=2)
            sky_word = "傍晚"
        else:
            c.create_oval(mx + 2, sky_y - 13, mx + 28, sky_y + 13,
                          fill="#e8eef5", outline="#9aa7b5", width=2)
            c.create_oval(mx + 10, sky_y - 13, mx + 34, sky_y + 11,
                          fill="#f2edfa", outline="")
            sky_word = "天黑"
        c.create_text(mx + 40, sky_y,
                      text="环境光照 %d%%(%s)" % (ambient, sky_word),
                      anchor="w", fill="#20344b", font=f9)
        c.create_text(mx, sky_y + 24, anchor="w", font=f8,
                      text="网络:%s   账号:%s" % ("❌ 断开" if offline else "✅ 正常",
                                                  self.var_account.get()),
                      fill="#e5484d" if offline else "#5b7186")

        # 最近一条指令的生命周期轨迹
        c.create_text(mx, 186, text="最近一条指令的生命周期:", anchor="w",
                      fill="#7a3db8", font=f9)
        if self.last_traced is not None:
            m = self.last_traced
            c.create_text(mx, 206, anchor="nw", width=252, font=f8, fill="#20344b",
                          text="指令#%d「%s」(%s)\n%s"
                               % (m["id"], m["label"], m["account"],
                                  " → ".join(m["trace"])))
        else:
            c.create_text(mx, 206, anchor="nw", width=252, font=f8, fill="#8a97a5",
                          text="(还没有指令。点手机上的按钮试试!)")

        # 勾选中的规则提示
        rules_on = []
        if self.var_rule_dark.get():
            rules_on.append("天黑开客厅灯")
        if self.var_rule_dawn.get():
            rules_on.append("天亮关所有灯")
        if self.var_rule_saver.get():
            rules_on.append("长亮节能")
        c.create_text(mx, 296, anchor="nw", width=252, font=f8, fill="#7a3db8",
                      text="平台上的自动化规则:%s"
                           % ("、".join(rules_on) if rules_on else "(未勾选)"))

        # ------------------ 下:消息链路四节点 ------------------
        xs = [90, 258, 426, 594]
        down_y, up_y = 386, 466
        c.create_line(xs[0], down_y, xs[3], down_y, fill="#f5c98b",
                      width=2, dash=(5, 3), arrow="last")
        c.create_line(xs[3], up_y, xs[0], up_y, fill="#9adbb8",
                      width=2, dash=(5, 3), arrow="last")
        c.create_text(xs[0] - 55, down_y, text="指令", fill="#f59e0b",
                      anchor="w", font=f8)
        c.create_text(xs[0] - 55, up_y, text="回传", fill="#2eb872",
                      anchor="w", font=f8)
        # 网络段标注:只有这一段会丢包/断网
        c.create_line(xs[0], 356, xs[2], 356, fill="#c9b6e4", width=1)
        c.create_text((xs[0] + xs[2]) // 2, 348,
                      text="⇠ 网络段(会丢包/断网)⇢", fill="#9a86b8", font=f8)
        # 控制器连到房子:本地可靠线路
        c.create_line(xs[3] + 20, 400, hx2 - 40, 346, fill="#7c4522",
                      width=2, dash=(3, 2))

        queue_n = sum(1 for m in self.messages if m["queued"] and not m["done"])
        node_status = [
            "防抖:%s" % ("开" if self.var_debounce.get() else "关"),
            ("断网 队列%d" % queue_n) if offline else "畅通",
            "权限校验+规则",
            "在线",
        ]
        for i, (x, name) in enumerate(zip(xs, NODE_NAMES)):
            err = (i == 1 and offline)
            c.create_rectangle(x - 46, 402, x + 46, 434,
                               fill="#fdeaea" if err else "white",
                               outline="#e5484d" if err else "#7a3db8", width=2)
            c.create_text(x, 418, text=name, fill="#20344b", font=fb)
            c.create_text(x, 444, text=node_status[i],
                          fill="#e5484d" if err else "#5b7186", font=f8)

        # ---- 消息小圆点(按 hop 在两节点之间插值定位)----
        for m in self.messages:
            frac = m["hop"] / 3.0
            x = xs[0] + (xs[3] - xs[0]) * frac
            y = down_y if m["dir"] == "down" else up_y
            if m["done"]:
                fill = {"ok": "#2eb872", "lost": "#e5484d", "expired": "#e5484d",
                        "rejected": "#e5484d"}[m["result"]]
            elif m["queued"]:
                fill = "#9aa7b5"
            else:
                fill = "#f59e0b" if m["dir"] == "down" else "#2eb872"
            c.create_oval(x - 7, y - 7, x + 7, y + 7,
                          fill=fill, outline="white", width=2)
            label_y = y - 14 if m["dir"] == "down" else y + 12
            suffix = {"lost": "(丢失)", "expired": "(过期)",
                      "rejected": "(被拒)"}.get(m["result"], "")
            c.create_text(x, label_y, text=m["label"] + suffix, fill=fill, font=f8)

        # ---- 状态栏与统计 ----
        self.lbl_status.configure(
            text="🕒 周期 %d   |   客厅灯:%s / 手机图标:%s   |   卧室灯:%s / 手机图标:%s   |   "
                 "网络:%s   |   账号:%s   |   光照:%d%%"
                 % (self.tick,
                    "亮" if self.actual["living"] else "灭",
                    "开" if self.app_state["living"] else "关",
                    "亮" if self.actual["bed"] else "灭",
                    "开" if self.app_state["bed"] else "关",
                    "断开" if offline else "正常",
                    self.var_account.get(), ambient))
        self.lbl_stats.configure(
            text="发出指令数:%d    成功执行:%d\n被平台拒绝:%d    丢失/过期:%d\n规则触发数:%d"
                 % (self.stats["cmd"], self.stats["success"],
                    self.stats["rejected"], self.stats["lost"],
                    self.stats["rule"]))

    # ===========================================================
    # 导出:日志 CSV / 小结 TXT(写到脚本目录,文件名带时间戳不覆盖)
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
        path = self._unique_path("家居控制日志", ".csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["周期", "类型", "内容", "客厅灯真实", "卧室灯真实",
                             "小程序图标"])
            for r in self.log_rows:
                writer.writerow([r["tick"], r["type"], r["content"],
                                 r["living"], r["bed"], r["app"]])
        self.add_log("系统", "日志已导出:%s(共%d条)"
                     % (os.path.basename(path), len(self.log_rows)))
        return path

    def export_report(self):
        """生成实验小结 TXT:参数、统计、最近日志和留给学生填写的思考题"""
        lines = [
            "=" * 46,
            "  智能家居控制与规则模拟器 · 实验小结",
            "=" * 46,
            "课程:清华版《信息科技》五年级下册 第3单元 第2课",
            "      智能家居背后的技术原理——小程序控制开关灯",
            "生成时间:%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "模拟进度:第 %d 个周期" % self.tick,
            "",
            "一、当前实验参数",
            "  网络延迟:%d 档 | 丢包率:%d%% | 网络:%s"
            % (self.var_latency.get(), self.var_loss.get(),
               "断开" if self.var_offline.get() else "正常"),
            "  防抖:%s | 登录账号:%s | 环境光照:%d%%"
            % ("开启" if self.var_debounce.get() else "关闭",
               self.var_account.get(), self.var_ambient.get()),
            "  自动化规则:天黑开客厅灯[%s] 天亮关所有灯[%s] 长亮节能[%s]"
            % ("√" if self.var_rule_dark.get() else "×",
               "√" if self.var_rule_dawn.get() else "×",
               "√" if self.var_rule_saver.get() else "×"),
            "",
            "二、实验统计",
            "  发出指令数:%d" % self.stats["cmd"],
            "  成功执行数:%d" % self.stats["success"],
            "  被平台拒绝数:%d(权限校验)" % self.stats["rejected"],
            "  丢失/过期数:%d(丢包与断网排队超时)" % self.stats["lost"],
            "  规则触发数:%d" % self.stats["rule"],
            "  结束时:客厅灯%s(手机图标%s) 卧室灯%s(手机图标%s)"
            % ("亮" if self.actual["living"] else "灭",
               "开" if self.app_state["living"] else "关",
               "亮" if self.actual["bed"] else "灭",
               "开" if self.app_state["bed"] else "关"),
            "",
            "三、最近日志(最多 30 条)",
        ]
        for r in self.log_rows[-30:]:
            lines.append("  [周期%03d] [%s] %s" % (r["tick"], r["type"], r["content"]))
        lines += [
            "",
            "四、我的思考(请同学们补充完成)",
            "  1. 一条开灯指令要经过哪几站才能让灯亮起来?",
            "     ________________________________________",
            "  2. 状态回传丢失时,手机图标和灯为什么会不一致?怎么解决?",
            "     ________________________________________",
            "  3. 为什么访客账号不能开灯?权限校验放在哪个节点最合适?",
            "     ________________________________________",
            "  4. 防抖有什么用?我设计的自动化规则是:当____________时,自动____________。",
            "",
            "(本小结由本机离线生成,未上传任何数据)",
        ]
        path = self._unique_path("家居实验小结", ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.add_log("系统", "实验小结已导出:%s" % os.path.basename(path))
        return path

    # ===========================================================
    # 导入示例场景 JSON
    # ===========================================================
    def import_scene(self, path=None, choice=None):
        """
        导入示例场景 JSON。
        path:文件路径,不传则弹出文件选择框;
        choice:场景序号(0起),不传且文件里有多组场景时弹出选择窗口。
        """
        if path is None:
            path = filedialog.askopenfilename(
                title="选择示例场景文件",
                initialdir=SCRIPT_DIR,
                filetypes=[("JSON 场景文件", "*.json"), ("所有文件", "*.*")])
            if not path:
                return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scenes = data.get("场景列表")
            if not isinstance(scenes, list) or not scenes:
                raise ValueError("文件中没有找到「场景列表」")
        except Exception as exc:
            messagebox.showerror("导入失败",
                                 "无法读取场景文件:\n%s\n\n请确认选择的是本工具的示例场景 JSON。" % exc,
                                 parent=self.root)
            return False

        if choice is not None:
            self._apply_scene(scenes[choice])
            return True
        if len(scenes) == 1:
            self._apply_scene(scenes[0])
            return True
        # 多组场景:弹出选择窗口,让学生挑一组
        self._show_scene_chooser(scenes)
        return True

    def _show_scene_chooser(self, scenes):
        """弹出一个小窗口列出所有场景,双击或点「载入」应用所选场景"""
        win = tk.Toplevel(self.root)
        win.title("选择要导入的家居场景")
        win.geometry("480x310")
        win.transient(self.root)
        tk.Label(win, text="文件中包含多组示例场景,请选择一组:",
                 anchor="w").pack(fill="x", padx=10, pady=(10, 4))
        lb = tk.Listbox(win, height=6)
        for scn in scenes:
            lb.insert("end", " %s —— %s" % (scn.get("名称", "未命名"),
                                            scn.get("说明", "")[:30]))
        lb.pack(fill="both", expand=True, padx=10)
        lb.selection_set(0)

        desc = tk.Label(win, text="", anchor="w", justify="left",
                        fg="#5b7186", wraplength=450)
        desc.pack(fill="x", padx=10, pady=4)

        def show_desc(_event=None):
            sel = lb.curselection()
            if sel:
                desc.configure(text=scenes[sel[0]].get("说明", ""))

        def do_load(_event=None):
            sel = lb.curselection()
            if sel:
                self._apply_scene(scenes[sel[0]])
                win.destroy()

        lb.bind("<<ListboxSelect>>", show_desc)
        lb.bind("<Double-Button-1>", do_load)
        show_desc()
        row = tk.Frame(win)
        row.pack(pady=6)
        tk.Button(row, text="✔ 载入所选场景", bg="#2eb872", fg="white",
                  command=do_load).pack(side="left", padx=4)
        tk.Button(row, text="取消", command=win.destroy).pack(side="left", padx=4)

    def _apply_scene(self, scn):
        """把一组场景写入各参数变量,并按场景给定的灯初始状态重摆房间"""
        params = scn.get("参数", {})
        name = scn.get("名称", "未命名")
        self.pause()
        # 参数与开关
        if "网络延迟" in params:
            self.var_latency.set(int(params["网络延迟"]))
        if "丢包率" in params:
            self.var_loss.set(int(params["丢包率"]))
        if "环境光照" in params:
            self.var_ambient.set(int(params["环境光照"]))
        if "断网" in params:
            self.var_offline.set(bool(params["断网"]))
        if "防抖" in params:
            self.var_debounce.set(bool(params["防抖"]))
        if params.get("账号") in ("家人", "访客"):
            self.var_account.set(params["账号"])
        # 自动化规则勾选
        if "天黑自动开灯" in params:
            self.var_rule_dark.set(bool(params["天黑自动开灯"]))
        if "天亮自动关灯" in params:
            self.var_rule_dawn.set(bool(params["天亮自动关灯"]))
        if "长亮节能" in params:
            self.var_rule_saver.set(bool(params["长亮节能"]))
        # 灯的初始状态(真实与小程序图标一致地重摆)
        for lamp, key in (("living", "客厅灯"), ("bed", "卧室灯")):
            if key in params:
                on = (params[key] == "开")
                self.actual[lamp] = on
                self.app_state[lamp] = on
                self.on_since[lamp] = self.tick if on else None
            self.pending[lamp] = None
        # 清空在途消息,给新场景一个干净的链路
        self.messages = []
        self.last_traced = None
        self.add_log("调参", "已导入示例场景「%s」:延迟%d档,丢包%d%%,断网%s,防抖%s,"
                     "账号%s,光照%d%%"
                     % (name, self.var_latency.get(), self.var_loss.get(),
                        "是" if self.var_offline.get() else "否",
                        "开" if self.var_debounce.get() else "关",
                        self.var_account.get(), self.var_ambient.get()))
        tip = scn.get("说明", "")
        if tip:
            self.add_log("系统", "场景提示:%s" % tip)
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
        win.title("帮助 · 智能家居控制与规则模拟器")
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
    SmartHomeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
