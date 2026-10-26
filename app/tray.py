# -*- coding: utf-8 -*-
"""托盘图标与菜单。pystray 在自己的线程里跑，回调只投递命令，不直接碰界面。"""

import threading

import pystray
from PIL import Image, ImageDraw


def _image(color=(31, 111, 235, 255)):
    """画一个简单的圆点图标。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 58, 58), fill=color)
    draw.ellipse((26, 18, 38, 30), fill=(255, 255, 255, 235))
    return img


class Tray:
    def __init__(self, on_show, on_act, on_quit, logbook=None, tooltip="自动续跑助手"):
        self.log = logbook
        self._on_show = on_show
        self._on_act = on_act
        self._on_quit = on_quit
        self._icon = None
        self._thread = None
        self._tooltip = tooltip

    def _build(self):
        menu = pystray.Menu(
            pystray.MenuItem("显示仪表盘", self._show, default=True),
            pystray.MenuItem("立即续跑", self._act),
            pystray.MenuItem("退出", self._quit),
        )
        self._icon = pystray.Icon("AutoResume", _image(), self._tooltip, menu)

    def start(self):
        """启动托盘线程。失败返回 False，调用方退回普通窗口关闭行为。"""
        try:
            self._build()
            self._thread = threading.Thread(target=self._icon.run, daemon=True,
                                            name="tray")
            self._thread.start()
            return True
        except Exception as exc:
            if self.log:
                self.log.write("warn", "tray_start_fail", detail=repr(exc))
            return False

    def stop(self):
        try:
            if self._icon is not None:
                self._icon.stop()
        except Exception:
            pass

    def set_tooltip(self, text):
        try:
            if self._icon is not None:
                self._icon.title = text[:120]
        except Exception:
            pass

    # 回调运行在托盘线程，只投递命令
    def _show(self, icon=None, item=None):
        self._on_show()

    def _act(self, icon=None, item=None):
        self._on_act()

    def _quit(self, icon=None, item=None):
        self._on_quit()
