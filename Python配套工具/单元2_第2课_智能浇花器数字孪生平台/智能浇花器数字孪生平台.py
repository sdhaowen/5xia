# -*- coding: utf-8 -*-
"""
智能浇花器数字孪生平台
======================
配套教材:清华大学出版社《信息科技》五年级下册
          第2单元 第2课《物联网浇花器的实现——远程控制系统》(教材 P49—61)

工具定位:
    在电脑上模拟一个"物联网浇花器"的数字孪生(虚拟花盆 + 消息传输通道)。
    学生可以观察远程浇水指令怎样经过 手机 → 网络 → 物联网平台 → 控制器 → 水泵
    五个节点逐跳传输,体验网络延迟、丢包、断网排队、指令过期与防重复保护,
    并通过调节参数设计自己的自动浇水规则。

技术说明(写给老师):
    * 仅使用 Python 标准库(tkinter / ttk / json / csv / random / os / datetime),
      无需安装任何第三方库,可在 Windows 上离线运行。
    * 模拟引擎用 root.after() 定时驱动,没有使用线程;
      关闭窗口时会正确取消 after 任务,不会有残留进程。
    * 模拟逻辑与本课配套 HTML 工具《智能浇花器数字孪生实验室》保持一致:
        - 1 个模拟周期 = 模拟世界的 10 分钟,一天 = 144 个周期,时钟从第1天 08:00 开始;
        - 不浇水时土壤湿度每周期下降 0.9%;
        - 浇水时每周期湿度 +8%(上限100),水箱 -3%(下限0);
        - 自动规则:湿度低于阈值 且 冷却结束 且 未超过每日安全上限 → 自动浇水;
        - 消息在"网络段"可能丢失;断网时消息排队,排队超过 18 个周期(3小时)
          即判定过期,控制器拒绝执行;短时间内重复的浇水指令可被"防重复保护"忽略。
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
TICK_MINUTES = 10          # 1 个模拟周期 = 模拟世界的 10 分钟
TICKS_PER_DAY = 144        # 一天 = 144 个周期(24小时 × 6)
QUEUE_EXPIRE_TICKS = 18    # 断网排队超过 18 个周期(3小时)判定指令过期
DEDUP_WINDOW_TICKS = 2     # 防重复保护:相同指令在 2 个周期内只执行一次
SOIL_DRY_PER_TICK = 0.9    # 不浇水时每周期湿度下降(%)
SOIL_RISE_PER_TICK = 8     # 浇水时每周期湿度上升(%)
TANK_COST_PER_TICK = 3     # 浇水时每周期水箱消耗(%)
NODE_NAMES = ["手机", "网络", "平台", "控制器", "水泵"]  # 消息通道五节点

# 脚本所在目录:导出文件、示例参数文件都放在这里
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 帮助窗口显示的使用说明(与 使用说明.txt 内容一致的精简版)
HELP_TEXT = """【智能浇花器数字孪生平台 · 快速帮助】

一、界面分区
  ① 场景区(左上):虚拟花盆、植物(颜色和姿态随湿度变化)、水箱液位,
     以及下方的消息通道:手机→网络→平台→控制器→水泵。
     橙色圆点 = 下行浇水指令;绿色圆点 = 上行湿度数据;
     灰色 = 断网排队中;红色 = 丢失或过期。
  ② 参数区(右上):6 个滑块 + 2 个开关,拖动后立即生效。
  ③ 运行控制区(右中):开始 / 暂停 / 单步 / 重置 / 手动浇水 / 断网切换。
  ④ 状态与日志区(左下):模拟时钟、当前湿度、水箱、今日浇水次数和滚动日志。
  ⑤ 结果区(右下):统计数据和 导出日志CSV / 导出报告TXT /
     导入示例参数 / 帮助 四个按钮。

二、基本玩法
  1. 点「开始」让模拟时间流动(1 周期 = 模拟 10 分钟)。
  2. 点「手动浇水」,观察指令小圆点从手机逐跳走到水泵,水泵才开始浇水。
  3. 勾选「自动浇水模式」,调节湿度阈值等参数,让植物自己保持健康。
  4. 把「网络延迟」「丢包率」调大,或点「断网切换」,观察消息会发生什么。
  5. 点「导出日志CSV」「导出报告TXT」保存实验记录(文件在本程序所在文件夹)。

三、自动浇水规则(和教材一致)
  当 土壤湿度 < 湿度阈值,并且 冷却时间已结束,并且 今日浇水次数未超过
  每日安全上限 时,控制器自动开泵浇水一次。

四、植物健康区间
  土壤湿度 40%~70% 最健康;低于 20% 快干死;高于 85% 有烂根风险。

更多内容请阅读同文件夹中的《使用说明.txt》。"""


class WateringApp:
    """智能浇花器数字孪生平台主程序(单窗口 Tkinter 应用)"""

    # ===========================================================
    # 初始化
    # ===========================================================
    def __init__(self, root):
        self.root = root
        root.title("智能浇花器数字孪生平台 · 清华版《信息科技》五下 第2单元第2课")
        root.geometry("1120x780")
        root.minsize(1000, 700)

        # ---- 模拟引擎状态 ----
        self.running = False        # 是否正在连续运行
        self.after_id = None        # root.after 的任务编号,关闭窗口时要取消
        self.tick_interval_ms = 600  # 每个模拟周期的真实间隔(毫秒)

        self.tick = 0               # 已经过的模拟周期数
        self.soil = 50.0            # 土壤湿度(%)
        self.tank = 100.0           # 水箱余量(%)
        self.watering_left = 0      # 剩余浇水周期数(>0 表示水泵开着)
        self.cooldown = 0           # 冷却剩余周期数
        self.today_count = 0        # 今日已浇水次数
        self.offline = False        # 网络是否断开

        self.messages = []          # 正在传输的消息列表(字典)
        self.msg_id = 0             # 消息自增编号
        self.recent_cmd = None      # 最近一条已执行的指令内容(用于防重复)
        self.recent_cmd_tick = -99  # 最近指令执行时的周期号

        # ---- 统计数据(结果区显示、导出报告用)----
        self.stats = {"water": 0, "msg": 0, "lost": 0,
                      "soil_sum": 0.0, "soil_n": 0}
        self.log_rows = []          # 日志记录列表,导出 CSV 用

        # ---- 可调参数(与界面滑块/开关绑定的 Tk 变量)----
        self.var_threshold = tk.IntVar(value=35)   # 湿度阈值(%)
        self.var_duration = tk.IntVar(value=20)    # 每次浇水时长(分钟)
        self.var_cooldown = tk.IntVar(value=60)    # 冷却时间(分钟)
        self.var_max_daily = tk.IntVar(value=4)    # 每日安全上限(次)
        self.var_latency = tk.IntVar(value=0)      # 网络延迟(每跳额外等待周期数)
        self.var_loss = tk.IntVar(value=0)         # 丢包率(%)
        self.var_auto = tk.BooleanVar(value=False)   # 自动浇水模式
        self.var_dedup = tk.BooleanVar(value=True)   # 防重复保护

        self.help_win = None        # 帮助窗口(避免重复打开)

        self._build_ui()
        # 窗口关闭时先停止模拟、取消 after 任务,再销毁窗口
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.add_log("系统", "欢迎使用!点「开始」运行模拟,点「帮助」查看玩法。")
        self._render()

    # ===========================================================
    # 界面搭建
    # ===========================================================
    def _build_ui(self):
        # 中文界面字体:Windows 上用微软雅黑,其他系统自动回退到默认字体
        base_font = ("Microsoft YaHei UI", 10)
        self.root.option_add("*Font", base_font)

        # ---- 顶部标题 ----
        header = tk.Frame(self.root, bg="#1a5cb8")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text="💧 智能浇花器数字孪生平台",
                 font=("Microsoft YaHei UI", 16, "bold"),
                 bg="#1a5cb8", fg="white").pack(side="left", padx=14, pady=6)
        tk.Label(header,
                 text="第2单元 第2课 物联网浇花器的实现——远程控制系统 · 完全离线 · 数据仅存本机",
                 bg="#1a5cb8", fg="#d8e8ff").pack(side="left", padx=6)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_rowconfigure(2, weight=2)

        # ================= ① 场景区(Canvas) =================
        scene_frame = tk.LabelFrame(self.root, text="① 场景区:数字孪生花盆 + 消息传输通道",
                                    padx=4, pady=4)
        scene_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        scene_frame.grid_rowconfigure(0, weight=1)
        scene_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(scene_frame, width=680, height=470,
                                bg="#eef6ff", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # ================= 右侧面板:参数区 + 运行控制区 =================
        right = tk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)

        # ---- ② 参数区 ----
        param_frame = tk.LabelFrame(right, text="② 参数区(拖动滑块立即生效)",
                                    padx=8, pady=2)
        param_frame.pack(fill="x")

        def add_scale(text, var, frm, to, step, unit, tip):
            """添加一行带说明的滑块;数值变化时写一条调参日志"""
            row = tk.Frame(param_frame)
            row.pack(fill="x")
            tk.Label(row, text=text, width=16, anchor="w").pack(side="left")
            scale = tk.Scale(row, variable=var, from_=frm, to=to,
                             resolution=step, orient="horizontal",
                             length=170, showvalue=True,
                             command=lambda v, t=text, u=unit: self._on_param_change(t, v, u))
            scale.pack(side="left", fill="x", expand=True)
            tk.Label(row, text=unit, width=4, anchor="w").pack(side="left")
            return scale

        add_scale("湿度阈值(低于就浇)", self.var_threshold, 15, 60, 5, "%",
                  "湿度低于该值时自动浇水")
        add_scale("每次浇水时长", self.var_duration, 10, 60, 10, "分钟",
                  "浇得越久湿度涨得越多,也越耗水")
        add_scale("冷却时间", self.var_cooldown, 30, 240, 30, "分钟",
                  "两次浇水之间的最小间隔")
        add_scale("每日安全上限", self.var_max_daily, 1, 8, 1, "次",
                  "一天最多浇几次,防止指令出错浇过头")
        add_scale("网络延迟", self.var_latency, 0, 3, 1, "档",
                  "每一跳额外等待的周期数,0=正常")
        add_scale("丢包率", self.var_loss, 0, 80, 10, "%",
                  "消息在网络段丢失的概率")

        check_row = tk.Frame(param_frame)
        check_row.pack(fill="x", pady=(2, 4))
        tk.Checkbutton(check_row, text="自动浇水模式", variable=self.var_auto,
                       command=self._on_auto_change).pack(side="left")
        tk.Checkbutton(check_row, text="防重复保护", variable=self.var_dedup,
                       command=self._on_dedup_change).pack(side="left", padx=12)

        # ---- ③ 运行控制区 ----
        ctrl_frame = tk.LabelFrame(right, text="③ 运行控制区", padx=8, pady=6)
        ctrl_frame.pack(fill="x", pady=(6, 0))
        row1 = tk.Frame(ctrl_frame)
        row1.pack(fill="x")
        self.btn_start = tk.Button(row1, text="▶ 开始", width=8,
                                   bg="#2eb872", fg="white",
                                   activebackground="#1e8f56",
                                   command=self.start)
        self.btn_start.pack(side="left", padx=2, pady=2)
        self.btn_pause = tk.Button(row1, text="⏸ 暂停", width=8,
                                   command=self.pause)
        self.btn_pause.pack(side="left", padx=2)
        tk.Button(row1, text="⏭ 单步", width=8,
                  command=self.step_once).pack(side="left", padx=2)
        tk.Button(row1, text="🔄 重置", width=8,
                  command=self.reset).pack(side="left", padx=2)
        row2 = tk.Frame(ctrl_frame)
        row2.pack(fill="x")
        tk.Button(row2, text="📱 手动浇水(发送远程指令)",
                  bg="#2b7de9", fg="white", activebackground="#1a5cb8",
                  command=self.manual_water).pack(side="left", padx=2, pady=2,
                                                  fill="x", expand=True)
        self.btn_offline = tk.Button(row2, text="🔌 断开网络", width=12,
                                     command=self.toggle_offline)
        self.btn_offline.pack(side="left", padx=2)

        # ---- ⑤ 结果区 ----
        result_frame = tk.LabelFrame(right, text="⑤ 结果区:统计与导出", padx=8, pady=6)
        result_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.lbl_stats = tk.Label(result_frame, justify="left", anchor="w",
                                  text="", fg="#20344b")
        self.lbl_stats.pack(fill="x")
        btns = tk.Frame(result_frame)
        btns.pack(fill="x", pady=4)
        tk.Button(btns, text="📥 导出日志CSV",
                  command=self.export_csv).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="📄 导出报告TXT",
                  command=self.export_report).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="📂 导入示例参数",
                  command=self.import_params).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="❓ 帮助",
                  command=self.show_help).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)
        tk.Label(result_frame, fg="#5b7186", justify="left", anchor="w",
                 text="导出文件保存在本程序所在文件夹,\n文件名自动加时间戳,不会覆盖旧文件。"
                 ).pack(fill="x")

        # ================= ④ 状态与日志区 =================
        log_frame = tk.LabelFrame(self.root, text="④ 状态与日志区", padx=6, pady=4)
        log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew",
                       padx=8, pady=(0, 8))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        # 状态栏:一行实时数据
        self.lbl_status = tk.Label(log_frame, anchor="w", fg="#1a5cb8",
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
        # 不同类型日志用不同颜色,方便学生找到关键事件
        self.log_text.tag_configure("浇水", foreground="#7fe3ad")
        self.log_text.tag_configure("网络", foreground="#ffb35c")
        self.log_text.tag_configure("安全", foreground="#ff8f94")
        self.log_text.tag_configure("调参", foreground="#9fc7ff")

    # ===========================================================
    # 模拟时钟工具
    # ===========================================================
    def clock_str(self, tick=None):
        """把周期号换算成"第X天 HH:MM"(每天从 08:00 开始,与 HTML 版一致)"""
        if tick is None:
            tick = self.tick
        day = tick // TICKS_PER_DAY + 1
        minutes = (tick % TICKS_PER_DAY) * TICK_MINUTES
        hour = (8 + minutes // 60) % 24
        return "第%d天 %02d:%02d" % (day, hour, minutes % 60)

    # ===========================================================
    # 日志
    # ===========================================================
    def add_log(self, kind, content, dev="—"):
        """追加一条日志:同时写入内存列表(供导出)和界面 Text(供查看)"""
        row = {"time": self.clock_str(), "type": kind, "content": content,
               "soil": "%d%%" % round(self.soil), "tank": "%d%%" % round(self.tank),
               "dev": dev}
        self.log_rows.append(row)
        if len(self.log_rows) > 1000:      # 防止长时间运行占用过多内存
            self.log_rows.pop(0)
        line = "[%s] [%s] %s(湿度%s 水箱%s)\n" % (
            row["time"], kind, content, row["soil"], row["tank"])
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

    def _on_auto_change(self):
        on = self.var_auto.get()
        self.add_log("调参", "自动浇水模式 %s" % ("开启:控制器将按规则自动浇水" if on
                                                 else "关闭:浇水要靠「手动浇水」按钮"))

    def _on_dedup_change(self):
        on = self.var_dedup.get()
        self.add_log("调参", "防重复保护 %s" % ("开启" if on else "关闭(小心重复指令浇两次水!)"))

    # ===========================================================
    # 运行控制:开始 / 暂停 / 单步 / 重置 / 手动浇水 / 断网
    # ===========================================================
    def start(self):
        """开始(或继续)连续运行"""
        if self.running:
            return
        self.running = True
        self.btn_start.configure(state="disabled")
        self.add_log("系统", "模拟开始运行(1 周期 = 模拟 10 分钟)")
        self._schedule_next()

    def pause(self):
        """暂停连续运行(不清除任何状态)"""
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(state="normal")
        self._cancel_after()
        self.add_log("系统", "模拟已暂停,可用「单步」逐周期观察")

    def step_once(self):
        """单步:先暂停,再推进一个周期,方便逐步观察消息移动"""
        if self.running:
            self.pause()
        self._tick_once()

    def reset(self):
        """重置:回到初始状态(参数滑块保持不变,日志保留)"""
        self.pause()
        self.tick = 0
        self.soil = 50.0
        self.tank = 100.0
        self.watering_left = 0
        self.cooldown = 0
        self.today_count = 0
        self.offline = False
        self.messages = []
        self.recent_cmd = None
        self.recent_cmd_tick = -99
        self.stats = {"water": 0, "msg": 0, "lost": 0,
                      "soil_sum": 0.0, "soil_n": 0}
        self.btn_offline.configure(text="🔌 断开网络")
        self.add_log("系统", "已重置:湿度50%、水箱100%、统计清零(参数滑块保持不变)")
        self._render()

    def manual_water(self):
        """手动浇水:从手机端发出一条下行浇水指令"""
        label = "浇水%d分钟" % self.var_duration.get()
        self.send_message(label, "down", "water")
        self.add_log("下行", "手机发送浇水指令「%s」" % label, dev="发送中")
        if not self.running:
            self.add_log("系统", "提示:当前是暂停状态,点「单步」或「开始」让指令走起来")

    def toggle_offline(self):
        """断网切换:断网时消息在网络段排队,恢复后继续(太久会过期)"""
        self.offline = not self.offline
        self.btn_offline.configure(text="🔗 恢复网络" if self.offline else "🔌 断开网络")
        if self.offline:
            self.add_log("网络", "网络断开!此后发送的消息会排队等待", dev="离线")
        else:
            self.add_log("网络", "网络恢复!排队消息继续发送,排队超3小时的指令会被判过期", dev="在线")
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
        """推进一个模拟周期:时间流动、土壤变化、自动规则、消息传输"""
        self.tick += 1

        # ---- 新的一天:今日浇水计数清零 ----
        if self.tick % TICKS_PER_DAY == 0:
            self.today_count = 0
            self.add_log("系统", "新的一天开始,今日浇水计数清零")

        # ---- 土壤湿度与水箱 ----
        if self.watering_left > 0 and self.tank > 0:
            # 水泵开着:湿度上升、水箱消耗
            self.watering_left -= 1
            self.soil = min(100.0, self.soil + SOIL_RISE_PER_TICK)
            self.tank = max(0.0, self.tank - TANK_COST_PER_TICK)
            if self.watering_left == 0:
                self.add_log("浇水", "浇水结束,水泵关闭", dev="水泵关闭")
        else:
            # 水泵关着:土壤自然变干
            self.soil = max(0.0, self.soil - SOIL_DRY_PER_TICK)

        if self.cooldown > 0:
            self.cooldown -= 1

        # 统计平均湿度
        self.stats["soil_sum"] += self.soil
        self.stats["soil_n"] += 1

        # ---- 自动浇水规则(与教材一致的三个条件)----
        if (self.var_auto.get() and self.watering_left == 0
                and self.soil < self.var_threshold.get()
                and self.cooldown == 0
                and self.today_count < self.var_max_daily.get()):
            self._exec_water("自动规则", None)
            self.add_log("浇水", "自动规则触发:湿度%d%% < 阈值%d%%,冷却已过、未超上限"
                         % (round(self.soil), self.var_threshold.get()))

        # ---- 传感器定时汇报(每 12 周期 = 2 小时,上行数据)----
        if self.tick % 12 == 0:
            self.send_message("湿度%d%%" % round(self.soil), "up", "data")

        self._advance_messages()
        self._render()

    # ===========================================================
    # 消息系统:手机→网络→平台→控制器→水泵(hop 0→4);上行反向(4→0)
    # ===========================================================
    def send_message(self, label, direction, kind):
        """创建一条消息。direction: 'down'=下行指令, 'up'=上行数据"""
        self.stats["msg"] += 1
        self.msg_id += 1
        msg = {
            "id": self.msg_id, "label": label, "dir": direction, "kind": kind,
            "hop": 0 if direction == "down" else 4,  # 当前所在节点编号
            "wait": 0,            # 延迟造成的额外等待周期
            "queued": False,      # 是否因断网排队
            "done": False,        # 是否已结束(送达/丢失/过期)
            "done_age": 0,        # 结束后再显示几个周期(动画淡出)
            "result": "",         # 结束原因,用于着色
            "payload_tick": self.tick,  # 发出时的周期号,用于判断过期
        }
        self.messages.append(msg)
        return msg

    def _finish_msg(self, msg, result):
        """标记消息结束:result 取值 ok(送达)/lost(丢失)/expired(过期)/ignored(被忽略)"""
        msg["done"] = True
        msg["result"] = result

    def _advance_messages(self):
        """每周期让所有在途消息前进一跳(受延迟/丢包/断网影响),逻辑与 HTML 版一致"""
        for m in self.messages:
            if m["done"]:
                m["done_age"] += 1     # 已结束的消息保留几帧用于显示颜色
                continue

            # 延迟:每一跳走完后要等 wait 个周期
            if m["wait"] > 0:
                m["wait"] -= 1
                continue

            # 断网排队中:等网络恢复;恢复时检查是否过期
            if m["queued"]:
                if self.offline:
                    continue
                m["queued"] = False
                if self.tick - m["payload_tick"] > QUEUE_EXPIRE_TICKS:
                    # 排队太久(超过模拟3小时):过期指令被控制器拒绝——安全机制
                    self.stats["lost"] += 1
                    self._finish_msg(m, "expired")
                    self.add_log("安全", "指令「%s」排队太久已过期,控制器拒绝执行" % m["label"],
                                 dev="安全机制生效")
                    continue

            step = 1 if m["dir"] == "down" else -1
            # "网络段" = 手机↔网络↔平台之间,只有这一段会丢包/断网
            in_net_seg = (m["dir"] == "down" and m["hop"] < 2) or \
                         (m["dir"] == "up" and m["hop"] > 2)

            if in_net_seg and self.offline:
                m["queued"] = True
                continue
            if in_net_seg and random.random() < self.var_loss.get() / 100.0:
                # 丢包:消息半路失踪,接收方永远收不到
                self.stats["lost"] += 1
                self._finish_msg(m, "lost")
                self.add_log("网络", "消息「%s」在网络中丢失!" % m["label"], dev="丢包")
                continue

            # 正常前进一跳
            m["hop"] += step
            m["wait"] = self.var_latency.get()

            if m["dir"] == "down" and m["hop"] >= 4:
                self._deliver_command(m)       # 下行指令到达水泵端
            elif m["dir"] == "up" and m["hop"] <= 0:
                self._finish_msg(m, "ok")      # 上行数据到达手机
                self.add_log("上行", "手机收到传感器汇报「%s」" % m["label"], dev="已送达")

        # 清理:结束超过 3 个周期的消息从列表移除
        self.messages = [m for m in self.messages
                         if not (m["done"] and m["done_age"] > 3)]

    def _deliver_command(self, msg):
        """下行指令到达控制器/水泵端:先做防重复检查,再执行"""
        if (self.var_dedup.get() and msg["kind"] == "water"
                and self.recent_cmd == msg["label"]
                and self.tick - self.recent_cmd_tick <= DEDUP_WINDOW_TICKS):
            # 防重复保护:同样内容、间隔极短的指令只执行一次
            self._finish_msg(msg, "ignored")
            self.add_log("安全", "防重复保护:忽略了重复指令「%s」" % msg["label"],
                         dev="安全机制生效")
            return
        self.recent_cmd = msg["label"]
        self.recent_cmd_tick = self.tick
        if msg["kind"] == "water":
            self._exec_water("手机指令", msg)

    def _exec_water(self, source, msg):
        """控制器执行浇水:先检查每日上限、冷却时间、水箱,全通过才开泵"""
        if self.today_count >= self.var_max_daily.get():
            if msg:
                self._finish_msg(msg, "ignored")
            self.add_log("安全", "今日已浇%d次,达到安全上限,拒绝浇水" % self.today_count,
                         dev="安全机制生效")
            return
        if self.cooldown > 0:
            if msg:
                self._finish_msg(msg, "ignored")
            self.add_log("安全", "距上次浇水不足冷却时间(还剩%d分钟),拒绝浇水"
                         % (self.cooldown * TICK_MINUTES), dev="冷却中")
            return
        if self.tank <= 0:
            if msg:
                self._finish_msg(msg, "lost")
            self.add_log("安全", "水箱空了,无法浇水!请点「重置」重新装满", dev="水箱空")
            return
        if msg:
            self._finish_msg(msg, "ok")
        # 开泵:换算成周期数(10分钟 = 1周期)
        self.watering_left = max(1, round(self.var_duration.get() / TICK_MINUTES))
        self.cooldown = max(0, round(self.var_cooldown.get() / TICK_MINUTES))
        self.today_count += 1
        self.stats["water"] += 1
        self.add_log("浇水", "%s → 水泵开启,浇水%d分钟(今日第%d次)"
                     % (source, self.var_duration.get(), self.today_count),
                     dev="水泵开启")

    # ===========================================================
    # 场景绘制(Canvas 每周期全部重画)
    # ===========================================================
    def _render(self):
        """刷新场景画面、状态栏和统计数据"""
        c = self.canvas
        c.delete("all")
        soil = self.soil
        watering = self.watering_left > 0 and self.tank > 0

        # ---- 图例 ----
        c.create_rectangle(455, 14, 469, 28, fill="#f59e0b", outline="")
        c.create_text(474, 21, text="下行指令(手机→水泵)", anchor="w",
                      fill="#5b7186", font=("Microsoft YaHei UI", 9))
        c.create_rectangle(455, 34, 469, 48, fill="#2eb872", outline="")
        c.create_text(474, 41, text="上行数据(传感器→手机)", anchor="w",
                      fill="#5b7186", font=("Microsoft YaHei UI", 9))
        c.create_rectangle(455, 54, 469, 68, fill="#9aa7b5", outline="")
        c.create_text(474, 61, text="排队中(断网)", anchor="w",
                      fill="#5b7186", font=("Microsoft YaHei UI", 9))
        c.create_rectangle(455, 74, 469, 88, fill="#e5484d", outline="")
        c.create_text(474, 81, text="丢失 / 过期", anchor="w",
                      fill="#5b7186", font=("Microsoft YaHei UI", 9))

        # ---- 植物状态文字与外观(颜色/姿态随湿度变化)----
        if soil < 20:
            state, color = "快干死了!", "#e5484d"
            stem_color, leaf_color = "#8a6d3b", "#b0885a"
        elif soil < 40:
            state, color = "有点渴", "#f59e0b"
            stem_color, leaf_color = "#a8a12a", "#c9c34a"
        elif soil <= 70:
            state, color = "健康", "#2eb872"
            stem_color, leaf_color = "#1e8f56", "#2eb872"
        elif soil <= 85:
            state, color = "有点湿", "#8b5cf6"
            stem_color, leaf_color = "#1e6e46", "#2a9d67"
        else:
            state, color = "涝了,有烂根风险!", "#8b5cf6"
            stem_color, leaf_color = "#5a4a9e", "#7a5cd6"
        c.create_text(150, 100, text="植物:%s" % state, fill=color,
                      font=("Microsoft YaHei UI", 11, "bold"))

        # 茎:湿度越低越弯(用折线模拟"蔫了")
        if soil < 20:
            stem_pts = [150, 252, 143, 224, 130, 212]
        elif soil < 40:
            stem_pts = [150, 252, 147, 210, 141, 182]
        else:
            stem_pts = [150, 252, 150, 210, 150, 170]
        c.create_line(*stem_pts, width=5, fill=stem_color,
                      smooth=True, capstyle="round")
        top_x, top_y = stem_pts[-2], stem_pts[-1]
        # 叶子:两片椭圆
        c.create_oval(top_x - 34, top_y + 18, top_x - 4, top_y + 36,
                      fill=leaf_color, outline=stem_color)
        c.create_oval(top_x + 4, top_y + 26, top_x + 34, top_y + 44,
                      fill=leaf_color, outline=stem_color)
        # 花朵:健康时开红花,干枯时只剩灰色小苞
        if 40 <= soil <= 70:
            for dx, dy in ((-10, 0), (10, 0), (0, -10), (0, 10)):
                c.create_oval(top_x + dx - 7, top_y + dy - 7,
                              top_x + dx + 7, top_y + dy + 7,
                              fill="#ff7d8a", outline="#e5484d")
            c.create_oval(top_x - 6, top_y - 6, top_x + 6, top_y + 6,
                          fill="#ffd23f", outline="#f59e0b")
        else:
            c.create_oval(top_x - 6, top_y - 6, top_x + 6, top_y + 6,
                          fill="#c9c9c9" if soil < 40 else "#b7a6ec",
                          outline="#999999")

        # ---- 浇水水滴动画(水泵开着时显示,位置随周期数轻微变化)----
        if watering:
            offset = (self.tick % 3) * 6
            for i in range(3):
                dx = -18 + i * 18
                y0 = 218 + offset + i * 4
                c.create_oval(148 + dx, y0, 156 + dx, y0 + 12,
                              fill="#2b7de9", outline="#1a5cb8")
            c.create_text(230, 232, text="浇水中", fill="#2b7de9",
                          font=("Microsoft YaHei UI", 10, "bold"))

        # ---- 花盆(内部蓝色水位 = 土壤湿度)----
        c.create_rectangle(90, 242, 210, 254, fill="#a0522d", outline="#5e2f0d")
        c.create_polygon(95, 254, 205, 254, 190, 335, 110, 335,
                         fill="#8b4513", outline="#5e2f0d")
        # 盆内干土背景
        c.create_rectangle(112, 258, 188, 333, fill="#c8a165", outline="")
        # 湿度水位(带网点的蓝色,模拟半透明)
        wet_h = int(75 * soil / 100.0)
        if wet_h > 0:
            c.create_rectangle(112, 333 - wet_h, 188, 333,
                               fill="#2b7de9", stipple="gray50", outline="")
        c.create_text(150, 352, text="土壤湿度 %d%%" % round(soil),
                      fill=color, font=("Microsoft YaHei UI", 10, "bold"))

        # ---- 水箱(右侧,液位 = 剩余水量)----
        c.create_text(272, 140, text="水箱", fill="#20344b",
                      font=("Microsoft YaHei UI", 10, "bold"))
        c.create_rectangle(245, 150, 300, 335, fill="#f2f7fd", outline="#5b7186", width=2)
        tank_h = int(183 * self.tank / 100.0)
        if tank_h > 0:
            c.create_rectangle(247, 333 - tank_h, 298, 333,
                               fill="#2b7de9", outline="")
        c.create_text(272, 352, text="%d%%" % round(self.tank),
                      fill="#1a5cb8", font=("Microsoft YaHei UI", 10, "bold"))

        # ---- 消息传输通道:五个节点 ----
        xs = [80, 205, 330, 455, 580]
        down_y, up_y = 378, 452     # 上面一条线走下行指令,下面一条走上行数据
        c.create_line(xs[0], down_y, xs[4], down_y, fill="#f5c98b",
                      width=2, dash=(5, 3), arrow="last")
        c.create_line(xs[4], up_y, xs[0], up_y, fill="#9adbb8",
                      width=2, dash=(5, 3), arrow="last")

        node_status = [
            "待命",
            "断网" if self.offline else "畅通",
            "队列%d" % sum(1 for m in self.messages if m["queued"] and not m["done"]),
            "在线",
            "浇水中" if watering else "关闭",
        ]
        for i, (x, name) in enumerate(zip(xs, NODE_NAMES)):
            err = (i == 1 and self.offline)
            box_fill = "#fdeaea" if err else "white"
            box_line = "#e5484d" if err else "#2b7de9"
            c.create_rectangle(x - 40, 390, x + 40, 422,
                               fill=box_fill, outline=box_line, width=2)
            c.create_text(x, 406, text=name, fill="#20344b",
                          font=("Microsoft YaHei UI", 11, "bold"))
            c.create_text(x, 434, text=node_status[i],
                          fill="#e5484d" if err else "#5b7186",
                          font=("Microsoft YaHei UI", 9))

        # ---- 消息小圆点(按 hop 在两节点之间插值定位)----
        for m in self.messages:
            frac = m["hop"] / 4.0
            x = xs[0] + (xs[4] - xs[0]) * frac
            y = down_y if m["dir"] == "down" else up_y
            if m["done"]:
                fill = {"ok": "#2eb872", "lost": "#e5484d",
                        "expired": "#e5484d", "ignored": "#9aa7b5"}[m["result"]]
            elif m["queued"]:
                fill = "#9aa7b5"
            else:
                fill = "#f59e0b" if m["dir"] == "down" else "#2eb872"
            c.create_oval(x - 7, y - 7, x + 7, y + 7,
                          fill=fill, outline="white", width=2)
            label_y = y - 14 if m["dir"] == "down" else y + 14
            suffix = {"lost": "(丢失)", "expired": "(过期)",
                      "ignored": "(忽略)"}.get(m["result"], "")
            c.create_text(x, label_y, text=m["label"] + suffix, fill=fill,
                          font=("Microsoft YaHei UI", 8))

        # ---- 状态栏与统计 ----
        self.lbl_status.configure(
            text="🕒 %s   |   土壤湿度:%d%%   |   水箱:%d%%   |   今日浇水:%d次   |   "
                 "冷却剩余:%d分钟   |   网络:%s   |   水泵:%s"
                 % (self.clock_str(), round(soil), round(self.tank),
                    self.today_count, self.cooldown * TICK_MINUTES,
                    "断开" if self.offline else "正常",
                    "浇水中" if watering else "关闭"))
        avg = ("%d%%" % round(self.stats["soil_sum"] / self.stats["soil_n"])
               if self.stats["soil_n"] else "—")
        self.lbl_stats.configure(
            text="累计浇水次数:%d        发送消息总数:%d\n丢失/过期消息:%d        平均土壤湿度:%s"
                 % (self.stats["water"], self.stats["msg"],
                    self.stats["lost"], avg))

    # ===========================================================
    # 导出:日志 CSV / 报告 TXT(写到脚本目录,文件名带时间戳不覆盖)
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
        path = self._unique_path("浇花器日志", ".csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["模拟时间", "类型", "内容", "土壤湿度", "水箱", "设备状态"])
            for r in self.log_rows:
                writer.writerow([r["time"], r["type"], r["content"],
                                 r["soil"], r["tank"], r["dev"]])
        self.add_log("系统", "日志已导出:%s(共%d条)"
                     % (os.path.basename(path), len(self.log_rows)))
        return path

    def export_report(self):
        """生成实验报告 TXT:参数、统计、最近日志和留给学生填写的思考题"""
        avg = ("%d%%" % round(self.stats["soil_sum"] / self.stats["soil_n"])
               if self.stats["soil_n"] else "—")
        lines = [
            "=" * 46,
            "  智能浇花器数字孪生平台 · 实验报告",
            "=" * 46,
            "课程:清华版《信息科技》五年级下册 第2单元 第2课",
            "      物联网浇花器的实现——远程控制系统",
            "生成时间:%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "模拟进度:%s(共 %d 个周期,每周期=模拟10分钟)" % (self.clock_str(), self.tick),
            "",
            "一、当前控制参数",
            "  湿度阈值:%d%%(土壤湿度低于该值时自动浇水)" % self.var_threshold.get(),
            "  每次浇水时长:%d 分钟" % self.var_duration.get(),
            "  冷却时间:%d 分钟(两次浇水的最小间隔)" % self.var_cooldown.get(),
            "  每日安全上限:%d 次" % self.var_max_daily.get(),
            "  网络延迟:%d 档 | 丢包率:%d%%" % (self.var_latency.get(), self.var_loss.get()),
            "  自动浇水模式:%s | 防重复保护:%s"
            % ("开启" if self.var_auto.get() else "关闭",
               "开启" if self.var_dedup.get() else "关闭"),
            "",
            "二、实验统计",
            "  累计浇水次数:%d" % self.stats["water"],
            "  发送消息总数:%d" % self.stats["msg"],
            "  丢失/过期消息:%d" % self.stats["lost"],
            "  平均土壤湿度:%s" % avg,
            "  当前土壤湿度:%d%% | 水箱余量:%d%% | 今日浇水:%d 次"
            % (round(self.soil), round(self.tank), self.today_count),
            "",
            "三、最近日志(最多 30 条)",
        ]
        for r in self.log_rows[-30:]:
            lines.append("  [%s] [%s] %s(湿度%s 水箱%s)"
                         % (r["time"], r["type"], r["content"], r["soil"], r["tank"]))
        lines += [
            "",
            "四、我的思考(请同学们补充完成)",
            "  1. 我设计的自动浇水规则是:当________________________时,就浇水____分钟。",
            "  2. 实验中我遇到的网络问题(延迟/丢包/断网):________________________",
            "  3. 防重复保护和每日安全上限为什么重要?________________________",
            "  4. 我的改进想法:________________________",
            "",
            "(本报告由本机离线生成,未上传任何数据)",
        ]
        path = self._unique_path("浇花器实验报告", ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.add_log("系统", "实验报告已导出:%s" % os.path.basename(path))
        return path

    # ===========================================================
    # 导入示例参数 JSON
    # ===========================================================
    def import_params(self, path=None, choice=None):
        """
        导入示例参数 JSON。
        path:文件路径,不传则弹出文件选择框;
        choice:配置序号(0起),不传且文件里有多组配置时弹出选择窗口。
        """
        if path is None:
            path = filedialog.askopenfilename(
                title="选择示例参数文件",
                initialdir=SCRIPT_DIR,
                filetypes=[("JSON 参数文件", "*.json"), ("所有文件", "*.*")])
            if not path:
                return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            configs = data.get("配置列表")
            if not isinstance(configs, list) or not configs:
                raise ValueError("文件中没有找到「配置列表」")
        except Exception as exc:
            messagebox.showerror("导入失败",
                                 "无法读取参数文件:\n%s\n\n请确认选择的是本工具的示例参数 JSON。" % exc,
                                 parent=self.root)
            return False

        if choice is not None:
            self._apply_config(configs[choice])
            return True
        if len(configs) == 1:
            self._apply_config(configs[0])
            return True
        # 多组配置:弹出选择窗口,让学生挑一组
        self._show_config_chooser(configs)
        return True

    def _show_config_chooser(self, configs):
        """弹出一个小窗口列出所有配置,双击或点「载入」应用所选配置"""
        win = tk.Toplevel(self.root)
        win.title("选择要导入的参数配置")
        win.geometry("460x300")
        win.transient(self.root)
        tk.Label(win, text="文件中包含多组示例参数,请选择一组:",
                 anchor="w").pack(fill="x", padx=10, pady=(10, 4))
        lb = tk.Listbox(win, height=6)
        for cfg in configs:
            lb.insert("end", " %s —— %s" % (cfg.get("名称", "未命名"),
                                            cfg.get("说明", "")[:30]))
        lb.pack(fill="both", expand=True, padx=10)
        lb.selection_set(0)

        desc = tk.Label(win, text="", anchor="w", justify="left",
                        fg="#5b7186", wraplength=430)
        desc.pack(fill="x", padx=10, pady=4)

        def show_desc(_event=None):
            sel = lb.curselection()
            if sel:
                desc.configure(text=configs[sel[0]].get("说明", ""))

        def do_load(_event=None):
            sel = lb.curselection()
            if sel:
                self._apply_config(configs[sel[0]])
                win.destroy()

        lb.bind("<<ListboxSelect>>", show_desc)
        lb.bind("<Double-Button-1>", do_load)
        show_desc()
        row = tk.Frame(win)
        row.pack(pady=6)
        tk.Button(row, text="✔ 载入所选配置", bg="#2eb872", fg="white",
                  command=do_load).pack(side="left", padx=4)
        tk.Button(row, text="取消", command=win.destroy).pack(side="left", padx=4)

    def _apply_config(self, cfg):
        """把一组配置写入各参数变量;若带初始湿度/水箱,则同时重置场景"""
        params = cfg.get("参数", {})
        name = cfg.get("名称", "未命名")
        mapping = [
            ("湿度阈值", self.var_threshold),
            ("浇水时长", self.var_duration),
            ("冷却时间", self.var_cooldown),
            ("每日上限", self.var_max_daily),
            ("网络延迟", self.var_latency),
            ("丢包率", self.var_loss),
        ]
        for key, var in mapping:
            if key in params:
                var.set(int(params[key]))
        if "自动浇水" in params:
            self.var_auto.set(bool(params["自动浇水"]))
        if "防重复保护" in params:
            self.var_dedup.set(bool(params["防重复保护"]))
        # 可选:初始场景(如"干旱挑战"从低湿度、小水箱开始)
        if "初始湿度" in params or "初始水箱" in params:
            self.pause()
            self.soil = float(params.get("初始湿度", self.soil))
            self.tank = float(params.get("初始水箱", self.tank))
            self.watering_left = 0
            self.cooldown = 0
        self.add_log("调参", "已导入示例配置「%s」:阈值%d%%,时长%d分钟,冷却%d分钟,"
                     "上限%d次,延迟%d档,丢包%d%%,自动模式%s"
                     % (name, self.var_threshold.get(), self.var_duration.get(),
                        self.var_cooldown.get(), self.var_max_daily.get(),
                        self.var_latency.get(), self.var_loss.get(),
                        "开" if self.var_auto.get() else "关"))
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
        win.title("帮助 · 智能浇花器数字孪生平台")
        win.geometry("560x520")
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
    WateringApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
