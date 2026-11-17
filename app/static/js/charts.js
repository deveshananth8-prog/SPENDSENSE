/* SpendSense Home Chart (Chart.js reading live CSS variables) */
(function () {
  var homeChart = null;

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function buildChart() {
    var canvas = document.getElementById("homeSpendingChart");
    var payload = window.SPENDSENSE_HOME_CHART;
    if (!canvas || !payload || typeof Chart === "undefined") return;

    var palette = [
      cssVar("--primary"),
      cssVar("--ok"),
      cssVar("--warn"),
      cssVar("--lavender"),
      cssVar("--butter"),
      cssVar("--danger"),
      cssVar("--ink-muted"),
    ];
    var textColor = cssVar("--ink");
    var mutedColor = cssVar("--ink-muted");
    var borderColor = cssVar("--surface");

    if (homeChart) {
      homeChart.destroy();
    }

    homeChart = new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: payload.labels,
        datasets: [
          {
            data: payload.values_major,
            backgroundColor: payload.labels.map(function (_, i) {
              return palette[i % palette.length];
            }),
            borderColor: borderColor,
            borderWidth: 2,
            hoverOffset: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "64%",
        plugins: {
          legend: {
            position: "right",
            labels: {
              color: textColor,
              boxWidth: 12,
              boxHeight: 12,
              padding: 14,
              font: {
                family: cssVar("--font-body") || "sans-serif",
                size: 12.5,
              },
            },
          },
          tooltip: {
            backgroundColor: cssVar("--surface-2"),
            titleColor: textColor,
            bodyColor: textColor,
            borderColor: cssVar("--border"),
            borderWidth: 1,
            callbacks: {
              label: function (ctx) {
                var formatted = payload.formatted && payload.formatted[ctx.dataIndex];
                return " " + ctx.label + ": " + (formatted || ctx.parsed);
              },
            },
          },
        },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", buildChart);
  window.addEventListener("spendsense:themechange", function () {
    if (homeChart) buildChart();
  });
})();
