/* SpendSense Before You Spend Live Calculator (Integer minor-unit math, zero floats for money) */
(function () {
  var lastExplainPayload = null;
  var explainTimer = null;

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

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

  async function requestAiExplanation() {
    var card = document.getElementById("bys-ai-card");
    if (!card || !lastExplainPayload) return;

    var loadingEl = document.getElementById("bys-ai-loading");
    var errorEl = document.getElementById("bys-ai-error");
    var textEl = document.getElementById("bys-ai-text");
    var badgeEl = document.getElementById("bys-offline-badge");

    if (errorEl) errorEl.hidden = true;
    if (loadingEl) loadingEl.hidden = false;
    if (textEl) textEl.hidden = true;

    try {
      var resp = await fetch("/api/ai/explain-affordability", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": getCsrfToken(),
        },
        body: JSON.stringify(lastExplainPayload),
      });
      var data = {};
      try { data = await resp.json(); } catch (err) {}
      if (loadingEl) loadingEl.hidden = true;
      if (!resp.ok) {
        if (errorEl) errorEl.hidden = false;
        if (textEl) textEl.hidden = false;
        return;
      }
      if (textEl && data.explanation) {
        textEl.textContent = data.explanation;
      }
      if (textEl) textEl.hidden = false;
      if (badgeEl) {
        badgeEl.hidden = !data.offline_mode;
      }
    } catch (err) {
      if (loadingEl) loadingEl.hidden = true;
      if (errorEl) errorEl.hidden = false;
      if (textEl) textEl.hidden = false;
    }
  }

  function scheduleAiExplanation(delayMs) {
    if (!document.getElementById("bys-ai-card")) return;
    if (explainTimer) clearTimeout(explainTimer);
    explainTimer = setTimeout(requestAiExplanation, delayMs);
  }

  function setMarkerLabelPosition(labelEl, pct) {
    if (!labelEl) return;
    labelEl.classList.remove("runway-marker-label-end", "runway-marker-label-start");
    if (pct > 65) labelEl.classList.add("runway-marker-label-end");
    else if (pct < 28) labelEl.classList.add("runway-marker-label-start");
  }

  function updateSimulator(prefix) {
    var balanceEl = document.getElementById(prefix + "-balance");
    var essentialsEl = document.getElementById(prefix + "-essentials");
    var purchaseEl = document.getElementById(prefix + "-purchase");
    var daysEl = document.getElementById(prefix + "-days");
    var thresholdEl = document.getElementById(prefix + "-threshold");
    var currencyEl = document.getElementById(prefix + "-currency");
    if (!balanceEl || !essentialsEl || !purchaseEl || !daysEl || !currencyEl) return;

    var errBanner = document.getElementById(prefix + "-bys-error");
    var errText = document.getElementById(prefix + "-bys-error-text");
    var rawBal = Number(balanceEl.value || 0);
    var rawEss = Number(essentialsEl.value || 0);
    var rawPur = Number(purchaseEl.value || 0);
    var rawThresh = Number(thresholdEl ? thresholdEl.value : 0);
    var rawDays = parseInt(daysEl.value || "0", 10);
    if (rawBal < 0 || rawEss < 0 || rawPur < 0 || rawThresh < 0 || !rawDays || rawDays < 1) {
      if (errText) errText.textContent = "Please enter non-negative amounts and at least 1 day until next income.";
      if (errBanner) errBanner.hidden = false;
    } else if (errBanner) {
      errBanner.hidden = true;
    }

    var opt = currencyEl.options[currencyEl.selectedIndex];
    var code = opt.value;
    var symbol = opt.getAttribute("data-symbol") || code;
    var locale = opt.getAttribute("data-locale") || "en-US";
    var precision = parseInt(opt.getAttribute("data-precision") || "2", 10);
    var rate = parseFloat(opt.getAttribute("data-rate") || "1");

    // Sync input prefixes
    document.querySelectorAll("#" + prefix + "-bys-form .input-prefix").forEach(function (el) {
      el.textContent = symbol;
    });

    var balanceMinor = Math.max(toMinor(balanceEl.value, precision), 0);
    var essentialsMinor = Math.max(toMinor(essentialsEl.value, precision), 0);
    var purchaseMinor = Math.max(toMinor(purchaseEl.value, precision), 0);
    var days = Math.max(rawDays || 1, 1);
    var thresholdMinor = Math.max(toMinor(thresholdEl ? thresholdEl.value : "100", precision), 0);

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

    var safeFormatted = formatMinor(res.safeToSpend, code, locale, precision);
    var leftFormatted = formatMinor(res.leftAfter, code, locale, precision);
    var dailyAfterFormatted = formatMinor(res.dailyAfter, code, locale, precision);
    var dailyBeforeFormatted = formatMinor(res.dailyBefore, code, locale, precision);
    var balanceFormatted = formatMinor(balanceMinor, code, locale, precision);
    var essentialsFormatted = formatMinor(essentialsMinor, code, locale, precision);
    var purchaseFormatted = formatMinor(purchaseMinor, code, locale, precision);
    var thresholdFormatted = formatMinor(thresholdMinor, code, locale, precision);

    var safeEl = document.getElementById(prefix + "-safe-val");
    var leftEl = document.getElementById(prefix + "-left-val");
    var dailyEl = document.getElementById(prefix + "-daily-val");
    if (safeEl) safeEl.textContent = safeFormatted;
    if (leftEl) leftEl.textContent = leftFormatted;
    if (dailyEl) dailyEl.textContent = dailyAfterFormatted + "/day";

    if (prefix === "mini") {
      var threshLabel = document.getElementById("mini-threshold-label");
      if (threshLabel) threshLabel.textContent = thresholdFormatted;
    }

    if (prefix === "full") {
      var itemInput = document.getElementById("full-item");
      var itemName = (itemInput && itemInput.value.trim()) || "this purchase";
      var itemPreview = document.getElementById("full-item-preview");
      if (itemPreview) itemPreview.textContent = itemName;

      var barBeforeVal = document.getElementById("full-bar-before-val");
      var barAfterVal = document.getElementById("full-bar-after-val");
      var barAfter = document.getElementById("full-bar-after");
      if (barBeforeVal) barBeforeVal.textContent = dailyBeforeFormatted + "/day";
      if (barAfterVal) barAfterVal.textContent = dailyAfterFormatted + "/day";
      if (barAfter) {
        var pct = res.dailyBefore > 0 ? Math.max(Math.min(Math.round((res.dailyAfter / res.dailyBefore) * 100), 100), 4) : 0;
        barAfter.style.width = (res.leftAfter < 0 ? 0 : pct) + "%";
        barAfter.className = "progress-fill" + (res.tone !== "ok" ? " tone-" + res.tone : "");
      }

      // Live Money Runway impact marker
      var fullForm = document.getElementById("full-bys-form");
      var baseCur = (fullForm && fullForm.getAttribute("data-base-currency")) || code;
      var baseAvgDaily = parseInt((fullForm && fullForm.getAttribute("data-avg-daily-minor")) || "0", 10);
      var baseRate = 1;
      for (var i = 0; i < currencyEl.options.length; i++) {
        if (currencyEl.options[i].value === baseCur) {
          baseRate = parseFloat(currencyEl.options[i].getAttribute("data-rate") || "1");
          break;
        }
      }
      var scaledAvgDaily = baseAvgDaily > 0 ? Math.max(Math.round(baseAvgDaily * (rate / baseRate)), 1) : 100;
      var safeBefore = Math.max(res.safeToSpend, 0);
      var safeAfter = Math.max(res.leftAfter, 0);
      var beforeDays = Math.round(safeBefore / scaledAvgDaily);
      var afterDays = Math.round(safeAfter / scaledAvgDaily);
      var spanDays = Math.max(days + 6, beforeDays + 2, afterDays + 2, 16);
      var incomePct = Math.min(Math.max(Math.round((days / spanDays) * 100), 15), 92);
      var beforePct = Math.min(Math.max(Math.round((beforeDays / spanDays) * 100), 8), 96);
      var afterPct = Math.min(Math.max(Math.round((afterDays / spanDays) * 100), 8), 96);

      var rStatus = "At risk";
      var rTone = "danger";
      var rHeadline = "Projected to run short " + Math.max(days - afterDays, 1) + " days early";
      if (afterDays >= days) {
        rStatus = "Safe";
        rTone = "ok";
        rHeadline = "Your money lasts " + (afterDays - days) + " days past next allowance";
      } else if (days - afterDays <= 3) {
        rStatus = "Watch";
        rTone = "warn";
        rHeadline = "Runs out " + (days - afterDays) + " day(s) before next allowance";
      }

      var rFill = document.getElementById("bys-runway-fill");
      var rBeforeMarker = document.getElementById("bys-runway-before-marker");
      var rBeforeLabel = document.getElementById("bys-runway-before-label");
      var rIncomeMarker = document.getElementById("bys-runway-income-marker");
      var rIncomeLabel = document.getElementById("bys-runway-income-label");
      var rAfterMarker = document.getElementById("bys-runway-after-marker");
      var rAfterLabel = document.getElementById("bys-runway-after-label");
      var rHeadlineEl = document.getElementById("bys-runway-headline");
      var rPill = document.getElementById("bys-runway-status-pill");
      var rPillText = document.getElementById("bys-runway-status-text");

      if (rFill) {
        rFill.style.width = afterPct + "%";
        rFill.className = "runway-fill tone-" + rTone;
      }
      if (rBeforeMarker) rBeforeMarker.style.left = beforePct + "%";
      if (rBeforeLabel) {
        rBeforeLabel.textContent = "Now · " + beforeDays + "d";
        setMarkerLabelPosition(rBeforeLabel, beforePct);
      }
      if (rIncomeMarker) rIncomeMarker.style.left = incomePct + "%";
      if (rIncomeLabel) {
        rIncomeLabel.textContent = "Income · " + days + "d";
        setMarkerLabelPosition(rIncomeLabel, incomePct);
      }
      if (rAfterMarker) rAfterMarker.style.left = afterPct + "%";
      if (rAfterLabel) {
        rAfterLabel.textContent = "After purchase · " + afterDays + "d";
        setMarkerLabelPosition(rAfterLabel, afterPct);
      }
      if (rHeadlineEl) rHeadlineEl.textContent = rHeadline;
      if (rPill) rPill.className = "pill pill-" + rTone;
      if (rPillText) rPillText.textContent = rStatus + " (" + afterDays + "d)";

      var calcSafe = document.getElementById("calc-safe");
      var calcLeft = document.getElementById("calc-left");
      var calcDaily = document.getElementById("calc-daily");
      var calcFloor = document.getElementById("calc-floor");
      if (calcSafe) calcSafe.textContent = balanceFormatted + " − " + essentialsFormatted + " = " + safeFormatted;
      if (calcLeft) calcLeft.textContent = safeFormatted + " − " + purchaseFormatted + " = " + leftFormatted;
      if (calcDaily) calcDaily.textContent = dailyAfterFormatted + "/day (" + days + "d)";
      if (calcFloor) calcFloor.textContent = thresholdFormatted + "/day";

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

      lastExplainPayload = {
        item: itemName.slice(0, 120),
        verdict: res.verdict,
        balance_formatted: balanceFormatted,
        essentials_formatted: essentialsFormatted,
        purchase_formatted: purchaseFormatted,
        safe_to_spend_formatted: safeFormatted,
        left_after_buying_formatted: leftFormatted,
        daily_before_formatted: dailyBeforeFormatted,
        daily_after_formatted: dailyAfterFormatted,
        tight_threshold_formatted: thresholdFormatted,
        days: days,
      };
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
        if (prefix === "full") scheduleAiExplanation(1000);
      });
      var currencyEl = document.getElementById(prefix + "-currency");
      if (currencyEl) {
        currencyEl.addEventListener("change", function () {
          scaleDefaultsForCurrency(prefix);
          if (prefix === "full") scheduleAiExplanation(600);
        });
      }
      updateSimulator(prefix);
    });

    var explainBtn = document.getElementById("bys-explain-btn");
    if (explainBtn) {
      explainBtn.addEventListener("click", requestAiExplanation);
      requestAiExplanation();
    }

    var saveGoalBtn = document.getElementById("save-as-goal-btn");
    var goalBanner = document.getElementById("goal-saved-banner");
    var goalText = document.getElementById("goal-saved-text");
    if (saveGoalBtn && goalBanner) {
      saveGoalBtn.addEventListener("click", async function () {
        var item = ((document.getElementById("full-item") || {}).value || "").trim() || "Saved purchase";
        var target = (document.getElementById("full-purchase") || {}).value || "0";
        if (Number(target) <= 0) {
          if (goalText) goalText.textContent = "Enter a positive purchase price first to save it as a goal.";
          goalBanner.hidden = false;
          return;
        }
        saveGoalBtn.disabled = true;
        var nextMonth = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
        try {
          var resp = await fetch("/api/goals/create", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": getCsrfToken(),
            },
            body: JSON.stringify({
              title: item,
              target: target,
              saved: 0,
              deadline: nextMonth,
              note: "Saved from Before You Spend",
            }),
          });
          saveGoalBtn.disabled = false;
          if (resp.ok) {
            if (goalText) goalText.textContent = '"' + item + '" saved to your Goals!';
            goalBanner.hidden = false;
          } else {
            if (goalText) goalText.textContent = 'Could not save goal right now. Visit Goals to add "' + item + '".';
            goalBanner.hidden = false;
          }
        } catch (err) {
          saveGoalBtn.disabled = false;
          if (goalText) goalText.textContent = "Network error while saving goal.";
          goalBanner.hidden = false;
        }
      });
    }
  });
})();
