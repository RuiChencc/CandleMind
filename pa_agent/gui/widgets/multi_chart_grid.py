"""Multi-chart strip: compact mini charts for watchlist symbols."""
from __future__ import annotations

import logging
import threading
from typing import Any

import pyqtgraph as pg
from PyQt6.QtCore import QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QSizePolicy, QHBoxLayout, QWidget

from pa_agent.data.eastmoney_source import EastMoneySource

logger = logging.getLogger(__name__)

_COLOR_UP = QColor(0, 184, 148)     # teal
_COLOR_DOWN = QColor(255, 82, 82)   # red
_BG = "#06080c"


class MiniChartWidget(pg.PlotWidget):
    clicked = pyqtSignal(str)

    def __init__(self, symbol: str) -> None:
        super().__init__()
        self._symbol = symbol
        self._bars: list[dict] = []
        self.setBackground(_BG)
        self.setFixedHeight(38)
        self.setFixedWidth(100)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.getPlotItem().hideAxis("left")
        self.getPlotItem().hideAxis("bottom")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.scene().installEventFilter(self)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if event.type() == event.Type.MouseButtonPress:
            self.clicked.emit(self._symbol)
            return True
        return super().eventFilter(obj, event)

    def set_bars(self, bars: list[dict]) -> None:
        self._bars = bars
        self.clear()
        if not bars or len(bars) < 2:
            return
        x = list(range(len(bars)))
        closes = [b["close"] for b in bars]
        y_min, y_max = min(closes), max(closes)
        span = y_max - y_min or 0.001
        self.setXRange(-1, len(bars))
        self.setYRange(y_min - span * 0.15, y_max + span * 0.15)

        for i, bar in enumerate(bars):
            color = _COLOR_UP if bar["close"] >= bar["open"] else _COLOR_DOWN
            body_top, body_bottom = max(bar["open"], bar["close"]), min(bar["open"], bar["close"])
            h = body_top - body_bottom or 0.0005
            rect_item = pg.QtWidgets.QGraphicsRectItem(QRectF(i - 0.32, body_bottom, 0.64, h))
            rect_item.setPen(pg.mkPen(color, width=1))
            rect_item.setBrush(pg.mkBrush(color))
            self.addItem(rect_item)
            if bar["high"] > body_top:
                line = pg.QtWidgets.QGraphicsLineItem(i, body_top, i, bar["high"])
                line.setPen(pg.mkPen(color, width=1))
                self.addItem(line)
            if bar["low"] < body_bottom:
                line = pg.QtWidgets.QGraphicsLineItem(i, body_bottom, i, bar["low"])
                line.setPen(pg.mkPen(color, width=1))
                self.addItem(line)

        label = pg.TextItem(
            f"{self._symbol}\n{closes[-1]:.2f}",
            color=(232, 234, 237),
            anchor=(0, 1),
        )
        label.setPos(2, y_max + span * 0.08)
        self.addItem(label)


class MultiChartGrid(QWidget):
    symbol_clicked = pyqtSignal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._charts: dict[str, MiniChartWidget] = {}
        self._layout = QHBoxLayout(self)
        self._layout.setSpacing(2)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.addStretch()
        self._data_source = EastMoneySource()
        self._data_source.connect()
        self.setFixedHeight(44)
        self._loading: set[str] = set()
        self.setStyleSheet("background-color: #0c111a; border-top: 1px solid #1d2638;")

    def update_symbols(self, symbols: list[str]) -> None:
        current = set(self._charts.keys())
        wanted = set(symbols[:8])
        for sym in current - wanted:
            self._charts[sym].deleteLater()
            del self._charts[sym]
        for sym in wanted - current:
            chart = MiniChartWidget(sym)
            chart.clicked.connect(self.symbol_clicked.emit)
            self._charts[sym] = chart
            self._layout.addWidget(chart)
        for sym in wanted:
            if sym not in self._loading:
                self._load_data(sym)

    def _load_data(self, symbol: str) -> None:
        if symbol in self._loading:
            return
        self._loading.add(symbol)

        def _fetch():
            try:
                self._data_source.subscribe(symbol, "1d")
                bars = self._data_source.latest_snapshot(30)
                if bars:
                    rows = [{"open": b.open, "high": b.high, "low": b.low, "close": b.close}
                             for b in reversed(bars[-30:])]
                else:
                    rows = []
            except Exception:
                rows = []
            self._loading.discard(symbol)
            QTimer.singleShot(0, lambda: self._on_data_loaded(symbol, rows))

        t = threading.Thread(target=_fetch, daemon=True)
        t.start()

    def _on_data_loaded(self, symbol: str, rows: list[dict]) -> None:
        chart = self._charts.get(symbol)
        if chart:
            chart.set_bars(rows)