/* SpendSense Before You Spend Live Calculator (Integer minor-unit math, zero floats for money) */
(function () {
  function toMinor(majorStr, precision) {
    var cleaned = String(majorStr || "0").trim();
    if (!cleaned || isNaN(Number(cleaned))) return 0;
    var neg = cleaned.startsWith("-");
    if (neg) cleaned = cleaned.slice(1);
    var parts = cleaned.split(".");
    var whole = parts[0].replace(/\D/g, "") || "0";
    var frac = (parts[1] || "").replace(/\D/g, "");
    while (frac.length < precision) frac += "0";
    frac = frac.slice(0, precision);
    var total = parseInt(whole, 10) * Math.pow(10, precision) + (precision > 0 ? parseInt(frac || "0", 10) : 0);
    return neg ? -total : total;
  }

  function formatMinor(minor, code, locale, precision) {
    var scale = Math.pow(10, precision);
    var major = minor / scale;
    try {
      return new Intl.NumberFormat(locale.replace("_", "-"), {
        style: "currency",
        currency: code,
        minimumFractionDigits: precision,
        maximumFractionDigits: precision,
      }).format(major);
    } catch (e) {
      return code + " " + major.toFixed(precision);
    }
  }

  function roundDiv(num, den) {
    if (den <= 0) return num;
    return Math.round(num / den);
  }

  function evaluateAffordability(balanceMinor, essentialsMinor, purchaseMinor, days, thresholdMinor, code, locale, precision) {
    var safeDays = Math.max(days, 1);
    var safeToSpend = balanceMinor - essentialsMinor;
    var leftAfter = safeToSpend - purchaseMinor;
    var dailyBefore = roundDiv(safeToSpend, safeDays);
    var dailyAfter = roundDiv(leftAfter, safeDays);

    var verdict = "Comfortable";
    var tone = "ok";
    var summary = "You stay well above your daily comfort floor until your next allowance.";

    if (leftAfter < 0) {
      verdict = "Not now";
      tone = "danger";
      summary = "This purchase dips into money set aside for upcoming essentials.";
    } else if (dailyAfter < thresholdMinor) {
      verdict = "Tight";
      tone = "warn";
      summary = "You can buy it, but your daily buffer drops below " + formatMinor(thresholdMinor, code, locale, precision) + "/day.";
    }

    var waitDays = 0;
    var waitUntilIncome = false;
    if (verdict !== "Comfortable") {
      var found = null;
      for (var n = 1; n < safeDays; n++) {
        var rem = Math.max(safeDays - n, 1);
        var cand = roundDiv(leftAfter, rem);
        if (leftAfter >= 0 && cand >= thresholdMinor) {
          found = n;
          break;
        }
      }
      waitDays = found !== null ? found : safeDays;
      waitUntilIncome = found === null;
    }

    var minNeeded = thresholdMinor * safeDays;
    var cheaperMax = Math.max(safeToSpend - minNeeded, 0);
    var firstPay = Math.floor(purchaseMinor / 2);
    var dailyFirst = roundDiv(safeToSpend - firstPay, safeDays);

    return {
      safeToSpend: safeToSpend,
      leftAfter: leftAfter,
      dailyBefore: dailyBefore,
      dailyAfter: dailyAfter,
      verdict: verdict,
      tone: tone,
      summary: summary,
      waitDays: waitDays,
      waitUntilIncome: waitUntilIncome,
      cheaperMax: cheaperMax,
      firstPay: firstPay,
      dailyFirst: dailyFirst,
    };
  }

  function updateSimulator(prefix) {
    var balanceEl = document.getElementById(prefix + "-balance");
    var essentialsEl = document.getElementById(prefix + "-essentials");
    var purchaseEl = document.getElementById(prefix + "-purchase");
    var daysEl = document.getElementById(prefix + "-days");
    var thresholdEl = document.getElementById(prefix + "-threshold");
    var currencyEl = document.getElementById(prefix + "-currency");
    if (!balanceEl || !essentialsEl || !purchaseEl || !daysEl || !currencyEl) return;

    var opt = currencyEl.options[currencyEl.selectedIndex];
    var code = opt.value;
    var symbol = opt.getAttribute("data-symbol") || code;
    var locale = opt.getAttribute("data-locale") || "en-US";
    var precision = parseInt(opt.getAttribute("data-precision") || "2", 10);

    // Sync input prefixes
    document.querySelectorAll("#" + prefix + "-bys-form .input-prefix").forEach(function (el) {
      el.textContent = symbol;
    });

    var balanceMinor = toMinor(balanceEl.value, precision);
    var essentialsMinor = toMinor(essentialsEl.value, precision);
    var purchaseMinor = toMinor(purchaseEl.value, precision);
    var days = Math.max(parseInt(daysEl.value || "1", 10) || 1, 1);
    var thresholdMinor = toMinor(thresholdEl ? thresholdEl.value : "100", precision);

    var res = evaluateAffordability(balanceMinor, essentialsMinor, purchaseMinor, days, thresholdMinor, code, locale, precision);

    var box = document.getElementById(prefix + "-verdict-box");
    var label = document.getElementById(prefix + "-verdict-label");
    var pill = document.getElementById(prefix + "-verdict-pill");
    var pillText = document.getElementById(prefix + "-verdict-pill-text");
    var summary = document.getElementById(prefix + "-verdict-summary");

    if (box) box.className = "verdict-box tone-" + res.tone;
    if (pill) pill.className = "pill pill-" + res.tone;
    if (label) label.textContent = res.verdict;
    if (pillText) pillText.textContent = res.verdict;
    if (summary) summary.textContent = res.summary;

    var safeEl = document.getElementById(prefix + "-safe-val");
    var leftEl = document.getElementById(prefix + "-left-val");
    var dailyEl = document.getElementById(prefix + "-daily-val");
    if (safeEl) safeEl.textContent = formatMinor(res.safeToSpend, code, locale, precision);
    if (leftEl) leftEl.textContent = formatMinor(res.leftAfter, code, locale, precision);
    if (dailyEl) dailyEl.textContent = formatMinor(res.dailyAfter, code, locale, precision) + "/day";

    if (prefix === "mini") {
      var threshLabel = document.getElementById("mini-threshold-label");
      if (threshLabel) threshLabel.textContent = formatMinor(thresholdMinor, code, locale, precision);
    }

    if (prefix === "full") {
      var itemInput = document.getElementById("full-item");
      var itemPreview = document.getElementById("full-item-preview");
      if (itemInput && itemPreview) itemPreview.textContent = itemInput.value.trim() || "this purchase";

      var barBeforeVal = document.getElementById("full-bar-before-val");
      var barAfterVal = document.getElementById("full-bar-after-val");
      var barAfter = document.getElementById("full-bar-after");
      if (barBeforeVal) barBeforeVal.textContent = formatMinor(res.dailyBefore, code, locale, precision) + "/day";
      if (barAfterVal) barAfterVal.textContent = formatMinor(res.dailyAfter, code, locale, precision) + "/day";
      if (barAfter) {
        var pct = res.dailyBefore > 0 ? Math.max(Math.min(Math.round((res.dailyAfter / res.dailyBefore) * 100), 100), 4) : 0;
        barAfter.style.width = (res.leftAfter < 0 ? 0 : pct) + "%";
        barAfter.className = "progress-fill" + (res.tone !== "ok" ? " tone-" + res.tone : "");
      }

      var calcSafe = document.getElementById("calc-safe");
      var calcLeft = document.getElementById("calc-left");
      var calcDaily = document.getElementById("calc-daily");
      var calcFloor = document.getElementById("calc-floor");
      if (calcSafe) {
        calcSafe.textContent =
          formatMinor(balanceMinor, code, locale, precision) +
          " − " +
          formatMinor(essentialsMinor, code, locale, precision) +
          " = " +
          formatMinor(res.safeToSpend, code, locale, precision);
      }
      if (calcLeft) {
        calcLeft.textContent =
          formatMinor(res.safeToSpend, code, locale, precision) +
          " − " +
          formatMinor(purchaseMinor, code, locale, precision) +
          " = " +
          formatMinor(res.leftAfter, code, locale, precision);
      }
      if (calcDaily) calcDaily.textContent = formatMinor(res.dailyAfter, code, locale, precision) + "/day (" + days + "d)";
      if (calcFloor) calcFloor.textContent = formatMinor(thresholdMinor, code, locale, precision) + "/day";

      var waitTitle = document.getElementById("alt-wait-title");
      var cheaperVal = document.getElementById("alt-cheaper-val");
      var splitPart = document.getElementById("alt-split-part");
      var splitDaily = document.getElementById("alt-split-daily");
      if (waitTitle) {
        waitTitle.textContent =
          res.waitDays === 0
            ? "Buy anytime"
            : res.waitUntilIncome
              ? "Wait " + res.waitDays + " days (next income)"
              : "Wait " + res.waitDays + " days";
      }
      if (cheaperVal) cheaperVal.textContent = formatMinor(res.cheaperMax, code, locale, precision);
      if (splitPart) splitPart.textContent = formatMinor(res.firstPay, code, locale, precision);
      if (splitDaily) splitDaily.textContent = formatMinor(res.dailyFirst, code, locale, precision) + "/day";
    }
  }

  function scaleDefaultsForCurrency(prefix) {
    var currencyEl = document.getElementById(prefix + "-currency");
    if (!currencyEl) return;
    var opt = currencyEl.options[currencyEl.selectedIndex];
    var rate = parseFloat(opt.getAttribute("data-rate") || "1");
    var precision = parseInt(opt.getAttribute("data-precision") || "2", 10);

    function roundSensible(inrVal) {
      var scaled = inrVal * rate;
      if (precision === 0) return Math.max(Math.round(scaled / 10) * 10, 1);
      if (scaled >= 100) return Math.round(scaled);
      if (scaled >= 10) return Math.round(scaled);
      return Number(scaled.toFixed(precision === 3 ? 2 : 1));
    }

    var balanceEl = document.getElementById(prefix + "-balance");
    var essentialsEl = document.getElementById(prefix + "-essentials");
    var purchaseEl = document.getElementById(prefix + "-purchase");
    var thresholdEl = document.getElementById(prefix + "-threshold");

    if (balanceEl) balanceEl.value = roundSensible(2480);
    if (essentialsEl) essentialsEl.value = roundSensible(850);
    if (purchaseEl) purchaseEl.value = roundSensible(prefix === "mini" ? 499 : 1199);
    if (thresholdEl) thresholdEl.value = roundSensible(100);
    updateSimulator(prefix);
  }

  document.addEventListener("DOMContentLoaded", function () {
    ["mini", "full"].forEach(function (prefix) {
      var form = document.getElementById(prefix + "-bys-form");
      if (!form) return;
      form.addEventListener("input", function () {
        updateSimulator(prefix);
      });
      var currencyEl = document.getElementById(prefix + "-currency");
      if (currencyEl) {
        currencyEl.addEventListener("change", function () {
          scaleDefaultsForCurrency(prefix);
        });
      }
      updateSimulator(prefix);
    });

    var saveGoalBtn = document.getElementById("save-as-goal-btn");
    var goalBanner = document.getElementById("goal-saved-banner");
    var goalText = document.getElementById("goal-saved-text");
    if (saveGoalBtn && goalBanner) {
      saveGoalBtn.addEventListener("click", function () {
        var item = (document.getElementById("full-item") || {}).value || "This purchase";
        if (goalText) goalText.textContent = '"' + item + '" saved to your Stage 1 goal preview.';
        goalBanner.hidden = false;
      });
    }
  });
})();
