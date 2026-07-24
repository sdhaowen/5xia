# -*- coding: utf-8 -*-
"""
物联网连接与消息流模拟器
========================
配套教材:清华大学出版社《信息科技》五年级下册
          第1单元 第2课《智能穿戴设备与物联网——物物相联的实现过程》(教材 P12—20)

工具定位:
    在电脑上模拟一块"智能手表"把运动数据送上物联网的完整过程。
    学生可以观察每一条心率/步数数据怎样经过
        人体数据 → 传感器 → 智能手表 → 无线网络 → 物联网平台 → 家人手机
    六个节点逐跳传输,每一跳对应一个动作:采集 → 打包 → 发送 → 存储 → 推送,
    并动手实验两个核心现象:
      ① 手表离线(飞行模式)时,数据滞留在手表的"待同步队列"里;
         恢复联网后,队列里的数据会自动补传到平台和家人手机;
      ② 无线信号很弱时,数据包移动变慢,还可能在半路丢失,
         丢失的数据会自动放回队列重发。

与教材四层体系架构的对应关系(供老师讲解时对照):
    传感器            —— 感知控制层(获取人体运动、心率等数据)
    智能手表+无线网络 —— 数据传输层(把数据传到互联网上)
    物联网平台        —— 数据处理层(存储、分析数据)
    家人手机          —— 应用决策层(把结果推送给用户使用)

技术说明(写给老师):
    * 仅使用 Python 标准库(tkinter / ttk / json / csv / random / os / datetime),
      无需安装任何第三方库,可在 Windows 上离线运行。
    * 模拟引擎用 root.after() 定时驱动,没有使用线程;
      关闭窗口时会正确取消 after 任务,不会有残留进程。
    * 模拟规则:
        - 1 个模拟周期 = 模拟世界的 1 秒,模拟时钟从 第1天 08:00:00 开始;
        - 每隔"采样频率"秒,传感器采集一次当前心率和累计步数,
          经过"采集→打包"两跳送进手表的待同步队列;
        - 手表联网时,每个周期最多从队列取出 1 条数据发送
          (同时在途的数据包最多 2 个,方便看清动画);
        - "无线网络段"(手表→无线网络→物联网平台)受信号强度影响:
            信号 ≥80%:每跳不额外等待,基本不丢包;
            信号越弱:每跳额外等待越久(最多 4 个周期),丢包率越高(最高约 65%);
        - 数据包丢失后,数据会放回队列开头自动重发(丢包数 +1);
        - 手表离线时,新数据留在队列;已经出发、还没到平台的数据包
          也会退回队列;恢复联网后按顺序自动补传;
        - 心率随"运动强度"滑块变化(静止约 70,剧烈运动可到 180 左右),
          步数按运动强度逐秒增加。
    * 所有数据都是虚拟生成的,不采集真实儿童健康信息;
      不联网、不上传;导出文件写入本脚本所在目录,
      文件名自动加时间戳,不覆盖已有文件。
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
NODE_NAMES = ["人体数据", "传感器", "智能手表", "无线网络", "物联网平台", "家人手机"]
# 每一跳(两个节点之间)对应的动作,共 5 跳
HOP_ACTIONS = ["采集", "打包", "发送", "存储", "推送"]
# 每个节点对应的教材体系架构层(人体数据、智能手表用 — 表示衔接位置)
NODE_LAYERS = ["—", "感知控制层", "数据传输层", "数据传输层", "数据处理层", "应用决策层"]
MAX_INFLIGHT = 2        # 同时在途的"同步数据包"上限(太多会看不清动画)
DONE_SHOW_TICKS = 3     # 数据包结束(送达/丢失)后再显示几个周期,方便看清颜色

# 脚本所在目录:导出文件、示例场景文件都放在这里
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 帮助窗口显示的使用说明(与 使用说明.txt 内容一致的精简版)
HELP_TEXT = """【物联网连接与消息流模拟器 · 快速帮助】

一、界面分区
  ① 场景区(左上):上方是虚拟智能手表表盘(实时心率、累计步数、
     联网状态、待同步队列);下方是物联网链路六节点:
     人体数据→传感器→智能手表→无线网络→物联网平台→家人手机。
     数据包小圆点沿链路逐跳移动,圆点上方标注当前动作:
     采集 / 打包 / 发送 / 存储 / 推送。
     蓝色圆点 = 采集中的数据;橙色圆点 = 正在同步的数据;
     红色 = 丢失(会自动重发);绿色 = 已送达家人手机。
     每个节点右上角有状态灯:绿=正常,橙=信号弱,红=离线,灰=待命。
  ② 参数区(右上):采样频率、网络信号强度、运动强度 3 个滑块 +
     「联网」开关,调整后立即生效。
  ③ 运行控制区(右中):开始 / 暂停 / 单步 / 重置。
  ④ 状态与日志区(下方):模拟时间、最新心率、累计步数、
     在线/离线状态、待同步队列数和彩色滚动日志。
  ⑤ 结果区(右下):已采集/已同步/丢包/待同步统计,以及
     导出日志CSV / 导出小结TXT / 导入场景JSON / 帮助 四个按钮。

二、基本玩法
  1. 点「开始」,看数据包从人体出发,一跳一跳走到家人手机。
  2. 点「单步」可以一个周期一个周期地慢慢看,看清每一跳的动作。
  3. 取消勾选「联网」(相当于打开飞行模式),观察数据滞留在
     手表的"待同步队列"里,队列数字越变越大;
     再勾上「联网」,观察队列里的数据自动补传,队列数字变小。
  4. 把「网络信号强度」调到很低(如 15%),观察数据包走得变慢,
     还会变红丢失;丢失的数据会自动放回队列重发,丢包数增加。
  5. 拖动「运动强度」,观察手表上的心率、步数怎么变化。
  6. 实验结束,点「导出日志CSV」「导出小结TXT」保存记录
     (文件在本程序所在文件夹,文件名自动加时间戳)。

三、和教材的对应(四层体系架构)
  传感器 = 感知控制层;智能手表和无线网络 = 数据传输层;
  物联网平台 = 数据处理层;家人手机 = 应用决策层。

更多内容请阅读同文件夹中的《使用说明.txt》。"""


class IoTFlowApp:
    """物联网连接与消息流模拟器主程序(单窗口 Tkinter 应用)"""

    # ===========================================================
    # 初始化
    # ===========================================================
    def __init__(self, root):
        self.root = root
        root.title("物联网连接与消息流模拟器 · 清华版《信息科技》五下 第1单元第2课")
        root.geometry("1120x780")
        root.minsize(1000, 700)

        # ---- 模拟引擎状态 ----
        self.running = False          # 是否正在连续运行
        self.after_id = None          # root.after 的任务编号,关闭窗口时要取消
        self.tick_interval_ms = 500   # 每个模拟周期的真实间隔(毫秒)

        self.tick = 0                 # 已经过的模拟周期数(1 周期 = 模拟 1 秒)
        self.heart_rate = 72.0        # 当前心率(次/分),随运动强度平滑变化
        self.steps = 0.0              # 累计步数(用浮点累加,显示时取整)
        self.offline = False          # 手表是否离线(True = 飞行模式)

        self.queue = []               # 手表的"待同步队列":还没送到平台的数据记录
        self.packets = []             # 正在链路上移动的数据包(动画用)
        self.data_id = 0              # 数据记录自增编号

        # ---- 统计数据(结果区显示、导出小结用)----
        self.stats = {
            "collected": 0,   # 已采集条数(数据进入手表队列)
            "synced": 0,      # 已同步条数(数据送达家人手机)
            "lost": 0,        # 丢包次数(每丢一次计一次,重发成功不减)
            "resend": 0,      # 重发次数
        }
        self.platform_count = 0       # 平台已存储条数(节点状态显示用)
        self.log_rows = []            # 日志记录列表,导出 CSV 用

        # ---- 可调参数(与界面滑块/开关绑定的 Tk 变量)----
        self.var_sample = tk.IntVar(value=3)     # 采样频率:每 N 秒采集一次
        self.var_signal = tk.IntVar(value=90)    # 网络信号强度(%)
        self.var_sport = tk.IntVar(value=3)      # 运动强度(0=静止,10=剧烈)
        self.var_online = tk.BooleanVar(value=True)  # 联网开关(取消勾选=离线)

        self.help_win = None          # 帮助窗口(避免重复打开)

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
        header = tk.Frame(self.root, bg="#155e9c")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text="⌚ 物联网连接与消息流模拟器",
                 font=("Microsoft YaHei UI", 16, "bold"),
                 bg="#155e9c", fg="white").pack(side="left", padx=14, pady=6)
        tk.Label(header,
                 text="第1单元 第2课 智能穿戴设备与物联网——物物相联的实现过程 · 完全离线 · 数据全部虚拟生成",
                 bg="#155e9c", fg="#cfe6ff").pack(side="left", padx=6)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_rowconfigure(2, weight=2)

        # ================= ① 场景区(Canvas) =================
        scene_frame = tk.LabelFrame(self.root,
                                    text="① 场景区:智能手表 + 物联网链路(六节点消息流)",
                                    padx=4, pady=4)
        scene_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        scene_frame.grid_rowconfigure(0, weight=1)
        scene_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(scene_frame, width=700, height=470,
                                bg="#eef6ff", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # ================= 右侧面板:参数区 + 运行控制区 + 结果区 =================
        right = tk.Frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)

        # ---- ② 参数区 ----
        param_frame = tk.LabelFrame(right, text="② 参数区(调整后立即生效)",
                                    padx=8, pady=2)
        param_frame.pack(fill="x")

        def add_scale(text, var, frm, to, step, unit):
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

        add_scale("采样频率(每几秒采1次)", self.var_sample, 1, 10, 1, "秒")
        add_scale("网络信号强度", self.var_signal, 0, 100, 5, "%")
        add_scale("运动强度", self.var_sport, 0, 10, 1, "档")

        # 联网/离线开关:核心实验开关,取消勾选 = 飞行模式
        check_row = tk.Frame(param_frame)
        check_row.pack(fill="x", pady=(2, 2))
        tk.Checkbutton(check_row, text="联网(取消勾选 = 离线/飞行模式)",
                       variable=self.var_online,
                       command=self._on_online_change).pack(side="left")
        tk.Label(param_frame, fg="#5b7186", anchor="w", justify="left",
                 text="提示:信号越弱,数据包走得越慢、越容易丢失;\n"
                      "离线时数据会留在手表的「待同步队列」里。"
                 ).pack(fill="x", pady=(0, 4))

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
        tk.Label(ctrl_frame, fg="#5b7186", anchor="w",
                 text="1 周期 = 模拟 1 秒;「单步」适合看清每一跳的动作"
                 ).pack(fill="x")

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
        tk.Button(btns, text="📄 导出小结TXT",
                  command=self.export_report).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        tk.Button(btns, text="📂 导入场景JSON",
                  command=self.import_scenario).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
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
        self.lbl_status = tk.Label(log_frame, anchor="w", fg="#155e9c",
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
        self.log_text.tag_configure("采集", foreground="#8fd0ff")
        self.log_text.tag_configure("同步", foreground="#7fe3ad")
        self.log_text.tag_configure("网络", foreground="#ffb35c")
        self.log_text.tag_configure("丢包", foreground="#ff8f94")
        self.log_text.tag_configure("调参", foreground="#c9b6ff")

    # ===========================================================
    # 模拟时钟工具
    # ===========================================================
    def clock_str(self, tick=None):
        """把周期号换算成"第X天 HH:MM:SS"(1 周期 = 模拟 1 秒,从 08:00:00 开始)"""
        if tick is None:
            tick = self.tick
        total = 8 * 3600 + tick          # 从早上 8 点开始计秒
        day = total // 86400 + 1
        rem = total % 86400
        return "第%d天 %02d:%02d:%02d" % (day, rem // 3600,
                                          rem % 3600 // 60, rem % 60)

    # ===========================================================
    # 日志
    # ===========================================================
    def add_log(self, kind, content):
        """追加一条日志:同时写入内存列表(供导出)和界面 Text(供查看)"""
        row = {"time": self.clock_str(), "type": kind, "content": content,
               "hr": "%d" % round(self.heart_rate),
               "steps": "%d" % int(self.steps),
               "queue": "%d" % len(self.queue)}
        self.log_rows.append(row)
        if len(self.log_rows) > 1000:      # 防止长时间运行占用过多内存
            self.log_rows.pop(0)
        line = "[%s] [%s] %s(心率%s 步数%s 待同步%s)\n" % (
            row["time"], kind, content, row["hr"], row["steps"], row["queue"])
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

    def _on_online_change(self):
        """联网开关:这是本课最核心的实验开关"""
        self.offline = not self.var_online.get()
        if self.offline:
            self.add_log("网络", "手表已离线(飞行模式)!新数据将留在「待同步队列」等待补传")
        else:
            n = len(self.queue)
            if n:
                self.add_log("网络", "手表恢复联网!队列中 %d 条数据将按顺序自动补传" % n)
            else:
                self.add_log("网络", "手表恢复联网,数据可以正常同步了")
        self._render()

    # ===========================================================
    # 信号强度 → 传输速度与丢包率(本课"信号弱"实验的核心换算)
    # ===========================================================
    def _hop_wait(self):
        """信号越弱,每一跳要额外等待的周期数越多(数据包走得越慢)"""
        s = self.var_signal.get()
        if s >= 80:
            return 0
        if s >= 60:
            return 1
        if s >= 40:
            return 2
        if s >= 20:
            return 3
        return 4

    def _loss_prob(self):
        """信号越弱,数据包在无线段丢失的概率越高"""
        s = self.var_signal.get()
        if s >= 80:
            return 0.0
        if s >= 60:
            return 0.05
        if s >= 40:
            return 0.15
        if s >= 20:
            return 0.35
        return 0.65

    # ===========================================================
    # 运行控制:开始 / 暂停 / 单步 / 重置
    # ===========================================================
    def start(self):
        """开始(或继续)连续运行"""
        if self.running:
            return
        self.running = True
        self.btn_start.configure(state="disabled")
        self.add_log("系统", "模拟开始运行(1 周期 = 模拟 1 秒)")
        self._schedule_next()

    def pause(self):
        """暂停连续运行(不清除任何状态)"""
        if not self.running:
            return
        self.running = False
        self.btn_start.configure(state="normal")
        self._cancel_after()
        self.add_log("系统", "模拟已暂停,可用「单步」逐周期观察每一跳")

    def step_once(self):
        """单步:先暂停,再推进一个周期,方便逐跳观察数据包移动"""
        if self.running:
            self.pause()
        self._tick_once()

    def reset(self):
        """重置:回到初始状态(参数滑块保持不变,日志保留)"""
        self.pause()
        self.tick = 0
        self.heart_rate = 72.0
        self.steps = 0.0
        self.queue = []
        self.packets = []
        self.platform_count = 0
        self.stats = {"collected": 0, "synced": 0, "lost": 0, "resend": 0}
        self.add_log("系统", "已重置:时钟归零、队列清空、统计清零(参数滑块保持不变)")
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
        """推进一个模拟周期:人体数据变化 → 定时采样 → 队列发送 → 数据包移动"""
        self.tick += 1

        # ---- ① 人体数据变化(虚拟生成,不涉及真实健康信息)----
        sport = self.var_sport.get()
        # 目标心率随运动强度上升(静止约70,10档剧烈运动约180),再加一点随机波动
        target_hr = 70 + sport * 11 + random.uniform(-4, 4)
        # 心率不会瞬间跳变,每秒向目标值靠近一点,模拟真实生理变化
        self.heart_rate += (target_hr - self.heart_rate) * 0.3
        self.heart_rate = max(55.0, min(190.0, self.heart_rate))
        # 步数:运动强度越大,每秒走的步数越多(0档=静止不走)
        self.steps += sport * 0.6

        # ---- ② 传感器定时采样:每隔"采样频率"秒生成一条采集数据包 ----
        if self.tick % self.var_sample.get() == 0:
            self.data_id += 1
            record = {"id": self.data_id,
                      "hr": round(self.heart_rate),
                      "steps": int(self.steps),
                      "time": self.clock_str(),
                      "retries": 0}
            # 采集数据包从"人体数据"节点(hop 0)出发,经 采集→打包 两跳进手表
            self.packets.append(self._new_packet(record, stage="collect", hop=0))

        # ---- ③ 手表发送:联网时每周期最多取 1 条队列数据出发同步 ----
        inflight = sum(1 for p in self.packets
                       if p["stage"] == "sync" and not p["done"])
        if (not self.offline) and self.queue and inflight < MAX_INFLIGHT:
            record = self.queue.pop(0)
            pkt = self._new_packet(record, stage="sync", hop=2)
            # 信号弱时,数据包一出发就要多等几个周期(第一跳"发送"变慢)
            pkt["wait"] = self._hop_wait()
            self.packets.append(pkt)
            if record["retries"] > 0:
                self.add_log("同步", "数据#%d 重发中(第%d次尝试)"
                             % (record["id"], record["retries"] + 1))
            elif record.get("was_offline"):
                self.add_log("同步", "补传:离线期间的数据#%d 出发前往平台" % record["id"])

        # ---- ④ 所有在途数据包前进一跳 ----
        self._advance_packets()
        self._render()

    # ===========================================================
    # 数据包系统:沿六节点链路逐跳移动
    #   collect 阶段:人体数据(0)→传感器(1)→智能手表(2),不受网络影响
    #   sync 阶段:智能手表(2)→无线网络(3)→物联网平台(4)→家人手机(5)
    #             其中 2→3、3→4 是"无线段",受信号强度和离线影响
    # ===========================================================
    def _new_packet(self, record, stage, hop):
        """创建一个数据包(动画对象),record 是它携带的数据记录"""
        return {
            "record": record,
            "stage": stage,       # collect=采集阶段, sync=同步阶段
            "hop": hop,           # 当前所在节点编号(0~5)
            "wait": 0,            # 信号弱造成的额外等待周期
            "done": False,        # 是否已结束(送达/丢失/退回)
            "done_age": 0,        # 结束后再显示几个周期(动画淡出)
            "result": "",         # 结束原因:ok=送达, lost=丢失, back=退回队列
        }

    def _advance_packets(self):
        """每周期让所有在途数据包前进一跳(受信号/离线影响)"""
        for p in self.packets:
            if p["done"]:
                p["done_age"] += 1     # 已结束的数据包保留几帧用于显示颜色
                continue

            rec = p["record"]

            # ---- 同步阶段的数据包遇到"突然离线":退回手表队列 ----
            # (还没存到平台的数据不能凭空消失,要回到队列等恢复联网)
            if p["stage"] == "sync" and self.offline and p["hop"] < 4:
                p["done"] = True
                p["result"] = "back"
                rec["was_offline"] = True
                self.queue.insert(0, rec)
                self.add_log("网络", "数据#%d 传到一半遇到离线,退回待同步队列" % rec["id"])
                continue

            # ---- 信号弱造成的额外等待(数据包"走得慢") ----
            if p["wait"] > 0:
                p["wait"] -= 1
                continue

            # ---- 无线段丢包判定(手表→网络、网络→平台 两跳) ----
            if p["stage"] == "sync" and p["hop"] in (2, 3):
                if random.random() < self._loss_prob():
                    # 丢包:这一跳没走成,数据放回队列开头,稍后自动重发
                    p["done"] = True
                    p["result"] = "lost"
                    rec["retries"] += 1
                    self.stats["lost"] += 1
                    self.stats["resend"] += 1
                    self.queue.insert(0, rec)
                    self.add_log("丢包", "数据#%d 在无线网络中丢失(信号%d%%),已放回队列准备重发"
                                 % (rec["id"], self.var_signal.get()))
                    continue

            # ---- 正常前进一跳 ----
            p["hop"] += 1
            # 到达"无线网络"节点后,下一跳(存储)仍在无线段,继续按信号强度等待
            if p["stage"] == "sync" and p["hop"] == 3:
                p["wait"] = self._hop_wait()

            if p["stage"] == "collect" and p["hop"] >= 2:
                # 采集数据包到达手表:完成"采集→打包",进入待同步队列
                p["done"] = True
                p["result"] = "ok"
                self.queue.append(rec)
                self.stats["collected"] += 1
                self.add_log("采集", "传感器采集数据#%d:心率%d 步数%d,已打包进手表队列"
                             % (rec["id"], rec["hr"], rec["steps"]))
            elif p["stage"] == "sync" and p["hop"] == 4:
                # 到达物联网平台:数据被"存储"
                self.platform_count += 1
                self.add_log("同步", "数据#%d 已到达物联网平台并存储" % rec["id"])
            elif p["stage"] == "sync" and p["hop"] >= 5:
                # 到达家人手机:完成"推送",同步成功
                p["done"] = True
                p["result"] = "ok"
                self.stats["synced"] += 1
                self.add_log("同步", "数据#%d 已推送到家人手机(心率%d 步数%d)✔"
                             % (rec["id"], rec["hr"], rec["steps"]))

        # 清理:结束超过 DONE_SHOW_TICKS 个周期的数据包从列表移除
        self.packets = [p for p in self.packets
                        if not (p["done"] and p["done_age"] > DONE_SHOW_TICKS)]

    # ===========================================================
    # 场景绘制(Canvas 每周期全部重画)
    # ===========================================================
    def _render(self):
        """刷新场景画面、状态栏和统计数据"""
        c = self.canvas
        c.delete("all")
        hr = round(self.heart_rate)
        steps = int(self.steps)
        signal = self.var_signal.get()
        sport = self.var_sport.get()
        sport_name = ("静止" if sport == 0 else
                      "散步" if sport <= 3 else
                      "快走" if sport <= 6 else
                      "跑步" if sport <= 8 else "冲刺")

        # ---- 图例(右上角) ----
        legend = [("#2b7de9", "采集中的数据(人体→手表)"),
                  ("#f59e0b", "同步中的数据(手表→手机)"),
                  ("#e5484d", "丢失(自动放回队列重发)"),
                  ("#2eb872", "已送达家人手机")]
        for i, (color, text) in enumerate(legend):
            y = 16 + i * 20
            c.create_rectangle(470, y, 484, y + 14, fill=color, outline="")
            c.create_text(489, y + 7, text=text, anchor="w",
                          fill="#5b7186", font=("Microsoft YaHei UI", 9))

        # ---- 虚拟智能手表表盘(左上) ----
        # 表带
        c.create_rectangle(150, 20, 200, 200, fill="#3a4a5c", outline="#26313d")
        # 表体(圆角矩形用两个矩形+四个圆近似,简单起见画一个大圆)
        c.create_oval(85, 40, 265, 200, fill="#20344b", outline="#155e9c", width=4)
        c.create_text(175, 68, text=self.clock_str(), fill="#8fd0ff",
                      font=("Microsoft YaHei UI", 9))
        # 心形图标随周期"跳动"(运动越剧烈跳得越明显)
        beat = 3 if (self.tick % 2 == 0 and sport > 0) else 0
        hx, hy = 130, 105
        r = 9 + beat
        c.create_oval(hx - r, hy - r, hx, hy, fill="#ff5c6c", outline="")
        c.create_oval(hx, hy - r, hx + r, hy, fill="#ff5c6c", outline="")
        c.create_polygon(hx - r, hy - 2, hx + r, hy - 2, hx, hy + r + 3,
                         fill="#ff5c6c", outline="")
        c.create_text(198, 102, text="%d" % hr, fill="white",
                      font=("Microsoft YaHei UI", 22, "bold"))
        c.create_text(198, 124, text="次/分", fill="#9fb6cc",
                      font=("Microsoft YaHei UI", 8))
        c.create_text(175, 148, text="👣 步数 %d" % steps, fill="#d9e4f0",
                      font=("Microsoft YaHei UI", 10))
        # 联网状态与待同步队列
        net_color = "#e5484d" if self.offline else "#2eb872"
        net_text = "离线(飞行模式)" if self.offline else "已联网"
        c.create_oval(120, 168, 132, 180, fill=net_color, outline="white")
        c.create_text(138, 174, text=net_text, anchor="w", fill=net_color,
                      font=("Microsoft YaHei UI", 9, "bold"))
        c.create_text(175, 218, text="运动状态:%s(强度%d档)" % (sport_name, sport),
                      fill="#20344b", font=("Microsoft YaHei UI", 10))

        # ---- 手表旁的"待同步队列"可视化(数据没同步不会丢,都在这排队) ----
        qn = len(self.queue)
        c.create_text(330, 60, text="待同步队列:%d 条" % qn,
                      fill="#b8860b" if qn else "#5b7186", anchor="w",
                      font=("Microsoft YaHei UI", 11, "bold"))
        # 队列画成一摞小方块(最多画 12 个,再多用 +N 表示)
        show_n = min(qn, 12)
        for i in range(show_n):
            x0 = 332 + (i % 6) * 24
            y0 = 74 + (i // 6) * 22
            c.create_rectangle(x0, y0, x0 + 20, y0 + 16,
                               fill="#ffe2a8", outline="#b8860b")
            c.create_text(x0 + 10, y0 + 8, text="📦",
                          font=("Microsoft YaHei UI", 7))
        if qn > 12:
            c.create_text(338 + 6 * 24, 104, text="+%d" % (qn - 12), anchor="w",
                          fill="#b8860b", font=("Microsoft YaHei UI", 10, "bold"))
        if self.offline and qn:
            c.create_text(330, 130, anchor="w", fill="#e5484d",
                          text="离线中:数据滞留在手表里,恢复联网后会自动补传",
                          font=("Microsoft YaHei UI", 9))

        # ---- 信号强度指示(五格信号条) ----
        c.create_text(330, 165, text="信号:", anchor="w", fill="#20344b",
                      font=("Microsoft YaHei UI", 10))
        bars = 0 if self.offline else (signal + 19) // 20   # 0~5格
        for i in range(5):
            x0 = 375 + i * 14
            h = 6 + i * 5
            filled = i < bars
            c.create_rectangle(x0, 172 - h, x0 + 10, 172,
                               fill="#2eb872" if filled else "#d5dee8",
                               outline="#9fb6cc")
        c.create_text(455, 165, anchor="w",
                      text="无信号" if self.offline else "%d%%" % signal,
                      fill="#e5484d" if (self.offline or signal < 20) else "#20344b",
                      font=("Microsoft YaHei UI", 10))

        # ---- 物联网链路:六个节点 ----
        xs = [62, 178, 294, 410, 526, 640]
        line_y = 300
        c.create_line(xs[0], line_y, xs[5], line_y, fill="#9fb6cc",
                      width=2, dash=(5, 3), arrow="last")
        # 每一跳中点标注动作名称(采集/打包/发送/存储/推送)
        for i, act in enumerate(HOP_ACTIONS):
            mx = (xs[i] + xs[i + 1]) / 2
            c.create_text(mx, line_y - 46, text=act, fill="#155e9c",
                          font=("Microsoft YaHei UI", 9, "bold"))
            c.create_text(mx, line_y - 34, text="▼", fill="#c3d3e4",
                          font=("Microsoft YaHei UI", 7))

        # 节点状态灯颜色与状态文字
        weak = signal < 20
        light_colors = [
            "#2eb872",                                          # 人体数据:一直活动
            "#2eb872",                                          # 传感器:正常
            "#f59e0b" if qn else "#2eb872",                     # 手表:有积压→橙
            "#e5484d" if self.offline else ("#f59e0b" if weak else "#2eb872"),
            "#9aa7b5" if self.offline else "#2eb872",           # 平台:离线时收不到
            "#9aa7b5" if self.offline else "#2eb872",           # 手机:离线时收不到
        ]
        node_status = [
            sport_name,
            "每%d秒采1次" % self.var_sample.get(),
            "队列%d条" % qn,
            "离线" if self.offline else ("信号弱%d%%" % signal if weak else "信号%d%%" % signal),
            "已存%d条" % self.platform_count,
            "已收%d条" % self.stats["synced"],
        ]
        node_icons = ["🏃", "📡", "⌚", "📶", "☁", "📱"]
        for i, (x, name) in enumerate(zip(xs, NODE_NAMES)):
            err = (i == 3 and self.offline)
            box_fill = "#fdeaea" if err else "white"
            box_line = "#e5484d" if err else "#2b7de9"
            c.create_rectangle(x - 50, line_y - 24, x + 50, line_y + 24,
                               fill=box_fill, outline=box_line, width=2)
            c.create_text(x - 30, line_y - 10, text=node_icons[i],
                          font=("Microsoft YaHei UI", 11))
            c.create_text(x + 8, line_y - 10, text=name, fill="#20344b",
                          font=("Microsoft YaHei UI", 10, "bold"))
            c.create_text(x, line_y + 12, text=node_status[i],
                          fill="#e5484d" if err else "#5b7186",
                          font=("Microsoft YaHei UI", 8))
            # 状态灯(节点右上角小圆):绿=正常 橙=积压/弱 红=离线 灰=待命
            c.create_oval(x + 38, line_y - 22, x + 48, line_y - 12,
                          fill=light_colors[i], outline="white", width=1)

        # ---- 教材四层体系架构标注(节点下方) ----
        layer_y = line_y + 44
        layers = [(1, 1, "感知控制层", "#2eb872"),
                  (2, 3, "数据传输层", "#f59e0b"),
                  (4, 4, "数据处理层", "#8b5cf6"),
                  (5, 5, "应用决策层", "#2b7de9")]
        for i0, i1, name, color in layers:
            x0, x1 = xs[i0] - 50, xs[i1] + 50
            c.create_line(x0, layer_y, x1, layer_y, fill=color, width=3)
            c.create_text((x0 + x1) / 2, layer_y + 13, text=name, fill=color,
                          font=("Microsoft YaHei UI", 9, "bold"))
        c.create_text(xs[0], layer_y + 13, text="(数据来源)", fill="#9fb6cc",
                      font=("Microsoft YaHei UI", 8))

        # ---- 在途数据包小圆点(按 hop 定位,多个包错开位置) ----
        offset_idx = 0
        for p in self.packets:
            hop = min(p["hop"], 5)
            x = xs[hop]
            y = line_y - 62 - (offset_idx % 3) * 20
            offset_idx += 1
            rec = p["record"]
            if p["done"]:
                fill = {"ok": "#2eb872", "lost": "#e5484d",
                        "back": "#9aa7b5"}[p["result"]]
            elif p["stage"] == "collect":
                fill = "#2b7de9"
            else:
                fill = "#f59e0b"
            c.create_oval(x - 8, y - 8, x + 8, y + 8,
                          fill=fill, outline="white", width=2)
            # 圆点旁标注:当前动作 + 数据编号(丢失/退回时标注原因)
            if p["done"] and p["result"] == "lost":
                label = "#%d 丢失!" % rec["id"]
            elif p["done"] and p["result"] == "back":
                label = "#%d 退回队列" % rec["id"]
            elif p["done"]:
                label = "#%d 完成" % rec["id"]
            else:
                act = HOP_ACTIONS[min(hop, 4)]
                label = "%s #%d" % (act, rec["id"])
                if p["wait"] > 0:
                    label += "(慢)"
            c.create_text(x, y - 16, text=label, fill=fill,
                          font=("Microsoft YaHei UI", 8))

        # ---- 底部提示 ----
        c.create_text(350, 452, fill="#9fb6cc", font=("Microsoft YaHei UI", 9),
                      text="一条数据的旅程:采集 → 打包 → (联网时)发送 → 存储 → 推送;离线时它会在手表队列里耐心等待")

        # ---- 状态栏与统计 ----
        self.lbl_status.configure(
            text="🕒 %s   |   最新心率:%d 次/分   |   累计步数:%d   |   状态:%s   |   "
                 "待同步队列:%d 条   |   信号:%s"
                 % (self.clock_str(), hr, steps,
                    "离线" if self.offline else "在线",
                    qn, "—" if self.offline else "%d%%" % signal))
        self.lbl_stats.configure(
            text="已采集:%d 条      已同步:%d 条\n丢包:%d 次(重发%d次)      待同步:%d 条"
                 % (self.stats["collected"], self.stats["synced"],
                    self.stats["lost"], self.stats["resend"], qn))

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
        path = self._unique_path("物联网消息流日志", ".csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["模拟时间", "类型", "内容", "心率", "步数", "待同步数"])
            for r in self.log_rows:
                writer.writerow([r["time"], r["type"], r["content"],
                                 r["hr"], r["steps"], r["queue"]])
        self.add_log("系统", "日志已导出:%s(共%d条)"
                     % (os.path.basename(path), len(self.log_rows)))
        return path

    def export_report(self):
        """生成实验小结 TXT:参数、统计、最近日志和留给学生填写的思考题"""
        lines = [
            "=" * 46,
            "  物联网连接与消息流模拟器 · 实验小结",
            "=" * 46,
            "课程:清华版《信息科技》五年级下册 第1单元 第2课",
            "      智能穿戴设备与物联网——物物相联的实现过程",
            "生成时间:%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "模拟进度:%s(共 %d 个周期,每周期=模拟1秒)" % (self.clock_str(), self.tick),
            "",
            "一、当前实验参数",
            "  采样频率:每 %d 秒采集 1 次" % self.var_sample.get(),
            "  网络信号强度:%d%%" % self.var_signal.get(),
            "  运动强度:%d 档" % self.var_sport.get(),
            "  联网状态:%s" % ("离线(飞行模式)" if self.offline else "在线"),
            "",
            "二、实验统计",
            "  已采集数据:%d 条(传感器采集并打包进手表)" % self.stats["collected"],
            "  已同步数据:%d 条(成功推送到家人手机)" % self.stats["synced"],
            "  丢包次数:%d 次(信号弱时数据在无线段丢失)" % self.stats["lost"],
            "  重发次数:%d 次(丢失的数据自动放回队列重发)" % self.stats["resend"],
            "  待同步队列:%d 条(还留在手表里没送出去的数据)" % len(self.queue),
            "  平台已存储:%d 条" % self.platform_count,
            "  最新心率:%d 次/分 | 累计步数:%d"
            % (round(self.heart_rate), int(self.steps)),
            "",
            "三、数据的完整旅程(对照教材四层体系架构)",
            "  人体数据 →[采集]→ 传感器(感知控制层)",
            "  →[打包]→ 智能手表 →[发送]→ 无线网络(数据传输层)",
            "  →[存储]→ 物联网平台(数据处理层)",
            "  →[推送]→ 家人手机(应用决策层)",
            "",
            "四、最近日志(最多 30 条)",
        ]
        for r in self.log_rows[-30:]:
            lines.append("  [%s] [%s] %s(心率%s 步数%s 待同步%s)"
                         % (r["time"], r["type"], r["content"],
                            r["hr"], r["steps"], r["queue"]))
        lines += [
            "",
            "五、我的思考(请同学们补充完成)",
            "  1. 手表离线时,采集到的数据去哪里了?________________________",
            "  2. 恢复联网后,我观察到:________________________",
            "  3. 信号很弱时,数据包发生了什么变化?________________________",
            "  4. 想一想:为什么丢失的数据要\"重发\"而不是直接放弃?",
            "     ________________________",
            "  5. 物联网的四层体系架构分别对应本工具的哪些节点?",
            "     ________________________",
            "",
            "(本小结由本机离线生成,所有数据均为虚拟模拟,未上传任何信息)",
        ]
        path = self._unique_path("物联网实验小结", ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.add_log("系统", "实验小结已导出:%s" % os.path.basename(path))
        return path

    # ===========================================================
    # 导入示例场景 JSON
    # ===========================================================
    def import_scenario(self, path=None, choice=None):
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
            scenarios = data.get("场景列表")
            if not isinstance(scenarios, list) or not scenarios:
                raise ValueError("文件中没有找到「场景列表」")
        except Exception as exc:
            messagebox.showerror("导入失败",
                                 "无法读取场景文件:\n%s\n\n请确认选择的是本工具的示例场景 JSON。" % exc,
                                 parent=self.root)
            return False

        if choice is not None:
            self._apply_scenario(scenarios[choice])
            return True
        if len(scenarios) == 1:
            self._apply_scenario(scenarios[0])
            return True
        # 多组场景:弹出选择窗口,让学生挑一组
        self._show_scenario_chooser(scenarios)
        return True

    def _show_scenario_chooser(self, scenarios):
        """弹出一个小窗口列出所有场景,双击或点「载入」应用所选场景"""
        win = tk.Toplevel(self.root)
        win.title("选择要导入的模拟场景")
        win.geometry("460x300")
        win.transient(self.root)
        tk.Label(win, text="文件中包含多组模拟场景,请选择一组:",
                 anchor="w").pack(fill="x", padx=10, pady=(10, 4))
        lb = tk.Listbox(win, height=6)
        for sc in scenarios:
            lb.insert("end", " %s —— %s" % (sc.get("名称", "未命名"),
                                            sc.get("说明", "")[:30]))
        lb.pack(fill="both", expand=True, padx=10)
        lb.selection_set(0)

        desc = tk.Label(win, text="", anchor="w", justify="left",
                        fg="#5b7186", wraplength=430)
        desc.pack(fill="x", padx=10, pady=4)

        def show_desc(_event=None):
            sel = lb.curselection()
            if sel:
                desc.configure(text=scenarios[sel[0]].get("说明", ""))

        def do_load(_event=None):
            sel = lb.curselection()
            if sel:
                self._apply_scenario(scenarios[sel[0]])
                win.destroy()

        lb.bind("<<ListboxSelect>>", show_desc)
        lb.bind("<Double-Button-1>", do_load)
        show_desc()
        row = tk.Frame(win)
        row.pack(pady=6)
        tk.Button(row, text="✔ 载入所选场景", bg="#2eb872", fg="white",
                  command=do_load).pack(side="left", padx=4)
        tk.Button(row, text="取消", command=win.destroy).pack(side="left", padx=4)

    def _apply_scenario(self, scenario):
        """把一组场景参数写入各控件变量,并同步联网/离线状态"""
        params = scenario.get("参数", {})
        name = scenario.get("名称", "未命名")
        if "采样频率" in params:
            self.var_sample.set(int(params["采样频率"]))
        if "信号强度" in params:
            self.var_signal.set(int(params["信号强度"]))
        if "运动强度" in params:
            self.var_sport.set(int(params["运动强度"]))
        if "联网" in params:
            online = bool(params["联网"])
            self.var_online.set(online)
            self.offline = not online
        self.add_log("调参", "已导入场景「%s」:采样每%d秒1次,信号%d%%,运动%d档,%s"
                     % (name, self.var_sample.get(), self.var_signal.get(),
                        self.var_sport.get(),
                        "离线(飞行模式)" if self.offline else "联网"))
        hint = scenario.get("说明")
        if hint:
            self.add_log("系统", "场景提示:%s" % hint)
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
        win.title("帮助 · 物联网连接与消息流模拟器")
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
    IoTFlowApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
