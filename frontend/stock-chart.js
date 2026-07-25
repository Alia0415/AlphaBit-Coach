const COLORS = Object.freeze({
  background: "#ffffff",
  text: "#9f9f9a",
  grid: "#efefec",
  border: "#d9d9d3",
  up: "#111111",
  down: "#111111",
  line: "#111111",
  ma5: "#111111",
  ma10: "#6b6b6b",
  ma20: "#b5b5b0",
});

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatNumber(value, digits = 2) {
  const number = finite(value);
  return number === null
    ? "—"
    : number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function formatTime(time) {
  if (typeof time === "string") return time;
  if (typeof time === "number") {
    return new Date(time * 1000).toLocaleString("zh-CN", {
      hour12: false,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  if (time && typeof time === "object") {
    return `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`;
  }
  return "—";
}

export class StockChart {
  constructor(container, tooltip) {
    this.container = container;
    this.tooltip = tooltip;
    this.chart = null;
    this.resizeObserver = null;
    this.windowResize = null;
  }

  render(payload) {
    this.destroy();
    const library = globalThis.LightweightCharts;
    if (!library?.createChart) {
      throw new Error("图表库加载失败");
    }
    const isIntraday = payload?.period === "1m";
    const data = isIntraday ? payload?.line : payload?.candles;
    if (!Array.isArray(data) || !data.length) {
      throw new Error("暂无可绘制的行情数据");
    }

    const width = Math.max(320, this.container.clientWidth || 720);
    const height = Math.max(380, this.container.clientHeight || 470);
    const chart = library.createChart(this.container, {
      width,
      height,
      autoSize: false,
      layout: {
        background: { type: "solid", color: COLORS.background },
        textColor: COLORS.text,
        attributionLogo: true,
        panes: {
          separatorColor: COLORS.border,
          separatorHoverColor: COLORS.line,
          enableResize: true,
        },
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      crosshair: { mode: library.CrosshairMode?.Normal ?? 0 },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: {
        borderColor: COLORS.border,
        timeVisible: isIntraday,
        secondsVisible: false,
        rightOffset: 3,
        barSpacing: isIntraday ? 5 : 8,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      localization: { locale: "zh-CN" },
    });
    this.chart = chart;

    let primarySeries;
    if (isIntraday) {
      primarySeries = chart.addSeries(library.LineSeries, {
        color: COLORS.line,
        lineWidth: 2,
        crosshairMarkerVisible: true,
        priceLineVisible: true,
      });
      primarySeries.setData(payload.line);
    } else {
      primarySeries = chart.addSeries(library.CandlestickSeries, {
        upColor: "#ffffff",
        downColor: COLORS.down,
        borderUpColor: COLORS.up,
        borderDownColor: COLORS.down,
        wickUpColor: COLORS.up,
        wickDownColor: COLORS.down,
      });
      primarySeries.setData(payload.candles);
    }

    const volumeSeries = chart.addSeries(
      library.HistogramSeries,
      {
        priceFormat: { type: "volume" },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    );
    const volumeData = isIntraday
      ? (payload.volume || []).map((point) => ({
          time: point.time,
          value: point.value,
          color: point.direction === "down" ? "rgba(17,17,17,0.62)" : "rgba(17,17,17,0.22)",
        }))
      : payload.candles.map((candle) => ({
          time: candle.time,
          value: candle.volume,
          color: candle.close >= candle.open ? "rgba(17,17,17,0.22)" : "rgba(17,17,17,0.62)",
        }));
    volumeSeries.setData(volumeData);

    if (!isIntraday) {
      [
        ["ma5", COLORS.ma5],
        ["ma10", COLORS.ma10],
        ["ma20", COLORS.ma20],
      ].forEach(([key, color]) => {
        const values = payload.indicators?.[key];
        if (!Array.isArray(values) || !values.length) return;
        const series = chart.addSeries(library.LineSeries, {
          color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        series.setData(values);
      });
    }

    this.subscribeTooltip(primarySeries, volumeSeries, isIntraday);
    try {
      const panes = chart.panes();
      panes[0]?.setStretchFactor(4);
      panes[1]?.setStretchFactor(1);
    } catch (_) {
      // Older compatible builds still render both panes without stretch tuning.
    }
    chart.timeScale().fitContent();
    this.observeSize();
  }

  subscribeTooltip(primarySeries, volumeSeries, isIntraday) {
    this.chart.subscribeCrosshairMove((param) => {
      if (!param?.time || !param.point) {
        this.tooltip.hidden = true;
        return;
      }
      const primary = param.seriesData?.get(primarySeries);
      const volume = param.seriesData?.get(volumeSeries);
      if (!primary) {
        this.tooltip.hidden = true;
        return;
      }
      const lines = [formatTime(param.time)];
      if (isIntraday) {
        lines.push(`价格 ${formatNumber(primary.value)}`);
      } else {
        lines.push(
          `开 ${formatNumber(primary.open)}  高 ${formatNumber(primary.high)}`,
          `低 ${formatNumber(primary.low)}  收 ${formatNumber(primary.close)}`,
        );
      }
      lines.push(`成交量 ${formatNumber(volume?.value, 0)}`);
      this.tooltip.textContent = lines.join("\n");
      this.tooltip.hidden = false;
      const left = Math.min(param.point.x + 18, this.container.clientWidth - 170);
      const top = Math.max(8, param.point.y - 18);
      this.tooltip.style.transform = `translate(${Math.max(8, left)}px, ${top}px)`;
    });
  }

  observeSize() {
    const resize = () => {
      if (!this.chart) return;
      this.chart.resize(
        Math.max(320, this.container.clientWidth || 720),
        Math.max(380, this.container.clientHeight || 470),
      );
    };
    if ("ResizeObserver" in globalThis) {
      this.resizeObserver = new ResizeObserver(resize);
      this.resizeObserver.observe(this.container);
    } else {
      this.windowResize = resize;
      window.addEventListener("resize", resize);
    }
  }

  fitContent() {
    this.chart?.timeScale().fitContent();
  }

  destroy() {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.windowResize) {
      window.removeEventListener("resize", this.windowResize);
      this.windowResize = null;
    }
    this.tooltip.hidden = true;
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }
    this.container.innerHTML = "";
  }
}
