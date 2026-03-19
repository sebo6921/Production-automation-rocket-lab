from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics
from typing import Dict, List, Tuple
from colours import DEVICE_COLOURS
import math

BACKGROUND   = QColor("#1e1e1e")
AXIS_COLOUR  = QColor("#888888")
GRID_COLOUR  = QColor("#2e2e2e")
TEXT_COLOUR  = QColor("#cccccc")
MARGIN_LEFT  = 65   # room for Y-axis labels
MARGIN_RIGHT = 20
MARGIN_TOP   = 20
MARGIN_BOT   = 45   # room for X-axis labels + legend


class LivePlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # series: label -> {"times": [...], "mv": [...], "ma": [...], "colours": (mv_col, ma_col)}
        self._series: Dict[str, dict] = {}
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAutoFillBackground(False)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_series(self, label: str, mv_colour: str, ma_colour: str) -> None:
        self._series[label] = {
            "times":   [],
            "mv":      [],
            "ma":      [],
            "colours": (mv_colour, ma_colour),
            "active":  True,
        }

    def update_series(self, label: str, times: List[float],
                      mv: List[float], ma: List[float]) -> None:
        if label not in self._series:
            return
        self._series[label]["times"] = times
        self._series[label]["mv"]    = mv
        self._series[label]["ma"]    = ma
        self.update()   # schedules a repaint on the Qt event loop

    def remove_series(self, label: str) -> None:
        self._series.pop(label, None)
        self.update()

    def mark_series_inactive(self, label: str) -> None:
        if label in self._series:
            self._series[label]["active"] = False
            self.update()

    def clear_all(self) -> None:
        self._series.clear()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        plot_x = MARGIN_LEFT
        plot_y = MARGIN_TOP
        plot_w = w - MARGIN_LEFT - MARGIN_RIGHT
        plot_h = h - MARGIN_TOP  - MARGIN_BOT

        if plot_w < 10 or plot_h < 10:
            return

        painter.fillRect(self.rect(), BACKGROUND)

        all_times, all_vals = self._collect_all_data()
        t_min, t_max = self._range(all_times, 0, 1000)
        v_min, v_max = self._padded_range(all_vals)

        self._draw_grid(painter, plot_x, plot_y, plot_w, plot_h, t_min, t_max, v_min, v_max)
        self._draw_axes(painter, plot_x, plot_y, plot_w, plot_h, t_min, t_max, v_min, v_max)

        painter.setClipRect(QRect(plot_x, plot_y, plot_w, plot_h))

        for label, data in self._series.items():
            times = data["times"]
            mv    = data["mv"]
            ma    = data["ma"]
            mv_col, ma_col = data["colours"]

            if len(times) >= 2:
                alpha = 255 if data["active"] else 80
                self._draw_line(painter, times, mv, mv_col,
                                plot_x, plot_y, plot_w, plot_h,
                                t_min, t_max, v_min, v_max, alpha)
                self._draw_line(painter, times, ma, ma_col,
                                plot_x, plot_y, plot_w, plot_h,
                                t_min, t_max, v_min, v_max, alpha)

        painter.setClipping(False)

        self._draw_legend(painter, plot_x + 8, plot_y + 8)

        painter.end()

    def _draw_line(self, painter, times, values, colour,
                   px, py, pw, ph, t_min, t_max, v_min, v_max, alpha=255):
        c = QColor(colour)
        c.setAlpha(alpha)
        pen = QPen(c)
        pen.setWidth(2)
        painter.setPen(pen)

        t_span = t_max - t_min or 1
        v_span = v_max - v_min or 1

        prev = None
        for t, v in zip(times, values):
            x = px + int((t - t_min) / t_span * pw)
            y = py + ph - int((v - v_min) / v_span * ph)
            pt = QPoint(x, y)
            if prev is not None:
                painter.drawLine(prev, pt)
            prev = pt

    def _draw_grid(self, painter, px, py, pw, ph, t_min, t_max, v_min, v_max):
        pen = QPen(GRID_COLOUR)
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)

        for tick in self._ticks(t_min, t_max, 6):
            x = px + int((tick - t_min) / (t_max - t_min or 1) * pw)
            painter.drawLine(x, py, x, py + ph)

        for tick in self._ticks(v_min, v_max, 5):
            y = py + ph - int((tick - v_min) / (v_max - v_min or 1) * ph)
            painter.drawLine(px, y, px + pw, y)

    def _draw_axes(self, painter, px, py, pw, ph, t_min, t_max, v_min, v_max):
        painter.setPen(QPen(AXIS_COLOUR))
        painter.drawRect(px, py, pw, ph)

        font = QFont("Monospace", 8)
        painter.setFont(font)
        painter.setPen(QPen(TEXT_COLOUR))
        fm = QFontMetrics(font)

        for tick in self._ticks(t_min, t_max, 6):
            x = px + int((tick - t_min) / (t_max - t_min or 1) * pw)
            painter.drawLine(x, py + ph, x, py + ph + 4)
            label = f"{int(tick)}"
            lw = fm.horizontalAdvance(label)
            painter.drawText(x - lw // 2, py + ph + 16, label)

        x_title = "Time (ms)"
        tw = fm.horizontalAdvance(x_title)
        painter.drawText(px + pw // 2 - tw // 2, py + ph + 36, x_title)

        for tick in self._ticks(v_min, v_max, 5):
            y = py + ph - int((tick - v_min) / (v_max - v_min or 1) * ph)
            painter.drawLine(px - 4, y, px, y)
            label = f"{tick:.0f}"
            lw = fm.horizontalAdvance(label)
            painter.drawText(px - lw - 6, y + fm.ascent() // 2, label)

        painter.save()
        painter.translate(12, py + ph // 2)
        painter.rotate(-90)
        y_title = "mV / mA"
        tw = fm.horizontalAdvance(y_title)
        painter.drawText(-tw // 2, 0, y_title)
        painter.restore()

    def _draw_legend(self, painter, x, y):
        if not self._series:
            return

        font = QFont("Monospace", 8)
        painter.setFont(font)
        fm = QFontMetrics(font)
        line_h = fm.height() + 4
        swatch = 16

        row = 0
        for label, data in self._series.items():
            mv_col, ma_col = data["colours"]
            short = label.split("—")[0].strip() 

            painter.fillRect(x, y + row * line_h, swatch, fm.height() - 2, QColor(mv_col))
            painter.setPen(QPen(TEXT_COLOUR))
            painter.drawText(x + swatch + 4, y + row * line_h + fm.ascent(), f"{short} mV")
            row += 1

            painter.fillRect(x, y + row * line_h, swatch, fm.height() - 2, QColor(ma_col))
            painter.setPen(QPen(TEXT_COLOUR))
            painter.drawText(x + swatch + 4, y + row * line_h + fm.ascent(), f"{short} mA")
            row += 1

    def _collect_all_data(self) -> Tuple[List[float], List[float]]:
        all_times = [t for s in self._series.values() for t in s["times"]]
        all_vals  = [v for s in self._series.values() for v in s["mv"]] + \
                    [v for s in self._series.values() for v in s["ma"]]
        return all_times, all_vals

    def _range(self, data, default_min, default_max):
        if not data:
            return default_min, default_max
        return min(data), max(data)

    def _padded_range(self,data, padding=0.1):
        if not data:
            return 0, 1
        lo, hi = min(data), max(data)
        span = hi - lo or 1
        return lo - span * padding, hi + span * padding

    def _ticks(self,lo, hi, count=6):
        span = hi - lo
        if span <= 0:
            return [lo]
        raw_step = span / count
        magnitude = 10 ** math.floor(math.log10(raw_step))
        step = round(raw_step / magnitude) * magnitude
        step = max(step, magnitude)
        first = math.ceil(lo / step) * step
        ticks = []
        t = first
        while t <= hi + step * 0.01:
            ticks.append(round(t, 10))
            t += step
        return ticks