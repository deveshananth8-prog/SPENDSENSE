/* SpendSense Global UI & Stage 4 AI Interactions */
(function () {
  function initIcons() {
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      lucide.createIcons();
    }
  }

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  async function apiPostJson(url, payload) {
    var resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": getCsrfToken(),
      },
      body: JSON.stringify(payload || {}),
    });
    var data = {};
    try {
      data = await resp.json();
    } catch (err) {}
    return { ok: resp.ok, status: resp.status, data: data };
  }

  function decimalsForCurrency(currencyCode) {
    var code = (currencyCode || "INR").toUpperCase();
    if (code === "JPY" || code === "KRW" || code === "VND") return 0;
    if (code === "KWD" || code === "BHD" || code === "OMR") return 3;
    return 2;
  }

  function formatCurrencyMinor(minor, currencyCode, locale) {
    var code = (currencyCode || "INR").toUpperCase();
    var loc = (locale || "en-IN").replace("_", "-");
    var digits = decimalsForCurrency(code);
    var major = minor / Math.pow(10, digits);
    try {
      return new Intl.NumberFormat(loc, {
        style: "currency",
        currency: code,
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(major);
    } catch (err) {
      return code + " " + major.toFixed(digits);
    }
  }

  /* User Menu Dropdown */
  function initUserMenu() {
    var btn = document.getElementById("user-menu-btn");
    var menu = document.getElementById("user-menu-dropdown");
    if (!btn || !menu) return;

    function closeMenu() {
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = !menu.hidden;
      menu.hidden = open;
      btn.setAttribute("aria-expanded", open ? "false" : "true");
    });

    document.addEventListener("click", function (e) {
      if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) {
        closeMenu();
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !menu.hidden) {
        closeMenu();
        btn.focus();
      }
    });
  }

  /* Modals */
  function initModals() {
    var lastTrigger = null;

    function closeModal(modal) {
      if (!modal) return;
      modal.hidden = true;
      if (lastTrigger && document.contains(lastTrigger)) {
        lastTrigger.focus();
      }
      lastTrigger = null;
    }

    document.addEventListener("click", function (e) {
      var openTrigger = e.target.closest("[data-modal-open]");
      if (openTrigger) {
        var targetId = openTrigger.getAttribute("data-modal-open");
        var modal = document.getElementById(targetId);
        if (modal) {
          lastTrigger = openTrigger;
          modal.hidden = false;
          var firstInput = modal.querySelector("input:not([type=hidden]), select, button");
          if (firstInput) firstInput.focus();
        }
        return;
      }

      var closeTrigger = e.target.closest("[data-modal-close]");
      if (closeTrigger) {
        var closeId = closeTrigger.getAttribute("data-modal-close");
        closeModal(document.getElementById(closeId));
        return;
      }

      if (e.target.classList.contains("modal-backdrop")) {
        closeModal(e.target);
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        document.querySelectorAll(".modal-backdrop:not([hidden])").forEach(function (m) {
          closeModal(m);
        });
      }
    });
  }

  /* Searchable CurrencyPicker Macro */
  function initCurrencyPickers() {
    document.querySelectorAll("[data-currency-picker]").forEach(function (root) {
      var prefix = root.getAttribute("data-currency-picker");
      var trigger = document.getElementById(prefix + "-trigger");
      var dropdown = document.getElementById(prefix + "-dropdown");
      var searchInput = document.getElementById(prefix + "-search");
      var hiddenVal = document.getElementById(prefix + "-value");
      var labelSpan = document.getElementById(prefix + "-selected-label");
      var options = Array.from(root.querySelectorAll(".currency-option"));
      if (!trigger || !dropdown || !searchInput) return;

      function closeDropdown(restoreFocus) {
        dropdown.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        if (restoreFocus) trigger.focus();
      }

      trigger.addEventListener("click", function (e) {
        e.stopPropagation();
        var isOpen = !dropdown.hidden;
        dropdown.hidden = isOpen;
        trigger.setAttribute("aria-expanded", isOpen ? "false" : "true");
        if (!isOpen) {
          searchInput.value = "";
          options.forEach(function (opt) { opt.hidden = false; });
          searchInput.focus();
        }
      });

      searchInput.addEventListener("input", function () {
        var q = searchInput.value.trim().toLowerCase();
        options.forEach(function (opt) {
          var code = (opt.getAttribute("data-code") || "").toLowerCase();
          var name = (opt.getAttribute("data-name") || "").toLowerCase();
          opt.hidden = !(code.includes(q) || name.includes(q));
        });
      });

      dropdown.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          e.stopPropagation();
          closeDropdown(true);
        }
      });

      options.forEach(function (opt) {
        opt.addEventListener("click", function () {
          var code = opt.getAttribute("data-code");
          var symbol = opt.getAttribute("data-symbol");
          var name = opt.getAttribute("data-name");
          if (hiddenVal) hiddenVal.value = code;
          if (labelSpan) labelSpan.textContent = code + " (" + symbol + ") — " + name;
          options.forEach(function (o) {
            o.classList.remove("is-selected");
            o.setAttribute("aria-selected", "false");
          });
          opt.classList.add("is-selected");
          opt.setAttribute("aria-selected", "true");
          closeDropdown(true);
          root.dispatchEvent(new CustomEvent("spendsense:currencyselected", { detail: { code: code } }));
        });
      });

      document.addEventListener("click", function (e) {
        if (!dropdown.hidden && !root.contains(e.target)) {
          closeDropdown(false);
        }
      });
    });
  }

  /* Home Progressive AI Narrative */
  function initHomeAi() {
    var card = document.getElementById("home-summary-card");
    var summaryEl = document.getElementById("home-monthly-summary");
    if (!card || !summaryEl) return;

    var skeleton = document.getElementById("home-summary-skeleton");
    var errBanner = document.getElementById("home-ai-error");
    var badge = document.getElementById("home-ai-badge");

    if (skeleton) {
      skeleton.hidden = false;
      summaryEl.hidden = true;
    }
    if (errBanner) errBanner.hidden = true;

    apiPostJson("/api/ai/home-narrative", {})
      .then(function (res) {
        if (skeleton) skeleton.hidden = true;
        summaryEl.hidden = false;
        if (!res.ok) {
          if (errBanner) errBanner.hidden = false;
          return;
        }
        var data = res.data;
        if (data.monthly_summary) {
          summaryEl.textContent = data.monthly_summary;
        }
        if (badge) {
          badge.hidden = !data.offline_mode;
        }
        if (Array.isArray(data.insights)) {
          data.insights.forEach(function (ins) {
            var cardEl = document.querySelector('[data-insight-id="' + ins.id + '"]');
            if (!cardEl) return;
            var bodyEl = cardEl.querySelector("[data-insight-body]");
            if (bodyEl && ins.body) bodyEl.textContent = ins.body;
            var actionEl = cardEl.querySelector("[data-insight-action]");
            if (actionEl && ins.buddy_question) {
              actionEl.setAttribute("href", "/money-buddy?q=" + encodeURIComponent(ins.buddy_question));
            }
          });
        }
      })
      .catch(function () {
        if (skeleton) skeleton.hidden = true;
        summaryEl.hidden = false;
        if (errBanner) errBanner.hidden = false;
      });
  }

  /* Money Buddy Notebook (Stage 4 Live AI + Offline Grounded Fallback) */
  function initMoneyBuddy() {
    var chipsWrap = document.getElementById("buddy-chips");
    var askForm = document.getElementById("buddy-ask-form");
    var notebook = document.getElementById("buddy-notebook");
    if (!chipsWrap || !notebook) return;

    var loadingEl = document.getElementById("buddy-loading");
    var activeEntry = document.getElementById("buddy-active-entry");
    var errorEl = document.getElementById("buddy-error");
    var errorText = document.getElementById("buddy-error-text");
    var errorDismiss = document.getElementById("buddy-error-dismiss");
    var pageOfflineBadge = document.getElementById("buddy-offline-badge");
    var entryOfflineBadge = document.getElementById("buddy-entry-offline");
    var inputEl = document.getElementById("buddy-input");
    var submitBtn = document.getElementById("buddy-submit-btn");

    if (errorDismiss && errorEl) {
      errorDismiss.addEventListener("click", function () {
        errorEl.hidden = true;
      });
    }

    function renderEntry(question, answer, nextStep, whyList, offlineMode) {
      var qEl = document.getElementById("buddy-q");
      var aEl = document.getElementById("buddy-a");
      var nEl = document.getElementById("buddy-next");
      var wEl = document.getElementById("buddy-why-list");
      if (qEl) qEl.textContent = question;
      if (aEl) aEl.textContent = answer;
      if (nEl) nEl.textContent = nextStep;
      if (wEl) {
        wEl.innerHTML = "";
        (whyList || []).forEach(function (line) {
          var li = document.createElement("li");
          li.textContent = line;
          wEl.appendChild(li);
        });
      }
      if (pageOfflineBadge) pageOfflineBadge.hidden = !offlineMode;
      if (entryOfflineBadge) entryOfflineBadge.hidden = !offlineMode;
    }

    async function askBuddy(question, clearInputAfter) {
      var clean = (question || "").trim();
      if (!clean) return;
      if (errorEl) errorEl.hidden = true;
      if (loadingEl) loadingEl.hidden = false;
      if (activeEntry) activeEntry.hidden = true;
      if (submitBtn) submitBtn.disabled = true;

      try {
        var res = await apiPostJson("/api/ai/money-buddy", { question: clean });
        if (loadingEl) loadingEl.hidden = true;
        if (activeEntry) activeEntry.hidden = false;
        if (submitBtn) submitBtn.disabled = false;

        if (!res.ok) {
          if (errorText) errorText.textContent = res.data.detail || "Could not get an answer right now. Please try again.";
          if (errorEl) errorEl.hidden = false;
          return;
        }
        renderEntry(
          clean,
          res.data.answer,
          res.data.next_step,
          res.data.why || [],
          Boolean(res.data.offline_mode)
        );
        if (clearInputAfter && inputEl) {
          inputEl.value = "";
        }
      } catch (err) {
        if (loadingEl) loadingEl.hidden = true;
        if (activeEntry) activeEntry.hidden = false;
        if (submitBtn) submitBtn.disabled = false;
        if (errorText) errorText.textContent = "Network error while asking Money Buddy. Please try again.";
        if (errorEl) errorEl.hidden = false;
      }
    }

    chipsWrap.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-chip-id]");
      if (!chip) return;
      chipsWrap.querySelectorAll("[data-chip-id]").forEach(function (c) {
        c.classList.remove("is-active");
      });
      chip.classList.add("is-active");
      var qText = chip.getAttribute("data-chip-question") || "";
      askBuddy(qText, false);
    });

    if (askForm) {
      askForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var q = (inputEl && inputEl.value.trim()) || "";
        if (!q) return;
        chipsWrap.querySelectorAll("[data-chip-id]").forEach(function (c) {
          c.classList.remove("is-active");
        });
        askBuddy(q, true);
      });
    }

    // Support ?q=... prefill from Home insight cards ("What can I do?")
    try {
      var params = new URLSearchParams(window.location.search);
      var prefill = (params.get("q") || "").trim();
      if (prefill) {
        if (inputEl) inputEl.value = prefill;
        chipsWrap.querySelectorAll("[data-chip-id]").forEach(function (c) {
          c.classList.remove("is-active");
        });
        askBuddy(prefill, false);
      }
    } catch (err) {}
  }

  /* Expenses Search, Filter, Stage 4 Quick Add (SMS / Natural Text / Screenshot) & Category Suggestion */
  function initExpenses() {
    var tbody = document.getElementById("expenses-tbody");
    if (!tbody) return;

    var root = document.getElementById("expenses-page-root");
    var userCurrency = (root && root.getAttribute("data-user-currency")) || "INR";
    var userLocale = (root && root.getAttribute("data-user-locale")) || "en_IN";

    var searchInput = document.getElementById("expense-search");
    var catSelect = document.getElementById("expense-category-filter");
    var tableWrap = document.getElementById("expenses-table-wrap");
    var emptyState = document.getElementById("expenses-empty-state");
    var countLabel = document.getElementById("expenses-count-label");
    var totalLabel = document.getElementById("expenses-total-label");

    function applyFilters() {
      var q = (searchInput && searchInput.value.trim().toLowerCase()) || "";
      var cat = (catSelect && catSelect.value) || "all";
      var rows = Array.from(tbody.querySelectorAll("[data-expense-row]"));
      var visible = 0;
      var totalMinor = 0;

      rows.forEach(function (row) {
        var merchant = (row.getAttribute("data-merchant") || "").toLowerCase();
        var note = (row.getAttribute("data-note") || "").toLowerCase();
        var rowCat = row.getAttribute("data-category") || "";
        var rowType = row.getAttribute("data-type") || "expense";
        var matchSearch = !q || merchant.includes(q) || note.includes(q);
        var matchCat = cat === "all" || rowCat === cat;
        var show = matchSearch && matchCat;
        row.hidden = !show;
        if (show) {
          visible += 1;
          if (rowType !== "income") {
            totalMinor += parseInt(row.getAttribute("data-amount-minor") || "0", 10);
          }
        }
      });

      if (tableWrap) tableWrap.hidden = visible === 0;
      if (emptyState) emptyState.hidden = visible > 0;
      if (countLabel) countLabel.textContent = visible + (visible === 1 ? " entry" : " entries");
      if (totalLabel) totalLabel.textContent = formatCurrencyMinor(totalMinor, userCurrency, userLocale);
    }

    if (searchInput) searchInput.addEventListener("input", applyFilters);
    if (catSelect) catSelect.addEventListener("change", applyFilters);

    var clearBtn = document.getElementById("clear-expense-filters");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (searchInput) searchInput.value = "";
        if (catSelect) catSelect.value = "all";
        applyFilters();
      });
    }

    var errBox = document.getElementById("expenses-error-state");
    var errBoxText = document.getElementById("expenses-error-text");
    var dismissErr = document.getElementById("dismiss-error-demo");

    function showTableError(msg) {
      if (errBoxText) errBoxText.textContent = msg;
      if (errBox) errBox.hidden = false;
    }

    if (dismissErr && errBox) {
      dismissErr.addEventListener("click", function () {
        errBox.hidden = true;
      });
    }

    function updateExpenseRowDom(tr, item) {
      var id = item.id;
      var rowCurrency = item.currency || userCurrency;
      var digits = decimalsForCurrency(rowCurrency);
      var minor = item.amount_minor !== undefined ? item.amount_minor : Math.round(Number(item.amount) * Math.pow(10, digits));
      var rowType = item.type || "expense";
      var rowMethod = item.method || "UPI";
      var formattedAmt = item.amount_formatted || formatCurrencyMinor(minor, rowCurrency, userLocale);

      tr.setAttribute("data-expense-row", "");
      tr.setAttribute("data-id", String(id));
      tr.setAttribute("data-merchant", item.merchant);
      tr.setAttribute("data-note", item.note || "");
      tr.setAttribute("data-category", item.category);
      tr.setAttribute("data-date", item.date);
      tr.setAttribute("data-amount-minor", String(minor));
      tr.setAttribute("data-currency", rowCurrency);
      tr.setAttribute("data-type", rowType);

      var cells = tr.querySelectorAll("td");
      cells[0].textContent = item.date;
      cells[1].children[0].textContent = item.merchant;
      cells[1].children[1].textContent = item.note || "";
      cells[2].textContent = item.category;
      cells[3].textContent = rowMethod;
      cells[4].textContent = formattedAmt;

      var editButton = tr.querySelector("[data-edit-expense]");
      var delButton = tr.querySelector("[data-delete-expense]");
      if (editButton) {
        editButton.setAttribute("data-edit-expense", String(id));
        editButton.setAttribute("aria-label", "Edit " + item.merchant);
      }
      if (delButton) {
        delButton.setAttribute("data-delete-expense", String(id));
        delButton.setAttribute("aria-label", "Delete " + item.merchant);
      }
    }

    function appendExpenseRow(item) {
      var id = item.id || Date.now();
      var tr = document.createElement("tr");
      tr.innerHTML =
        '<td class="num" style="white-space:nowrap;"></td>' +
        '<td><div style="font-weight:600;"></div><div style="font-size:0.82rem;color:var(--ink-muted);"></div></td>' +
        "<td></td>" +
        '<td style="color:var(--ink-muted);"></td>' +
        '<td class="num money" style="font-weight:600;"></td>' +
        '<td class="num"><div class="row-actions">' +
        '<button type="button" class="icon-btn" data-edit-expense="' + id + '" aria-label="Edit">' +
        '<i data-lucide="pencil" aria-hidden="true" width="15" height="15"></i></button>' +
        '<button type="button" class="icon-btn" data-delete-expense="' + id + '" aria-label="Delete">' +
        '<i data-lucide="trash-2" aria-hidden="true" width="15" height="15"></i></button></div></td>';

      updateExpenseRowDom(tr, item);
      tbody.prepend(tr);
      initIcons();
      applyFilters();
    }

    // Quick Add (Stage 4: SMS, natural text, screenshot vision, currency mismatch prompt, DB persistence)
    var qaForm = document.getElementById("quick-add-form");
    var qaInput = document.getElementById("quick-add-input");
    var qaPreview = document.getElementById("quick-add-preview");
    var qaLoading = document.getElementById("qa-loading");
    var qaError = document.getElementById("qa-error");
    var qaErrorText = document.getElementById("qa-error-text");
    var qaErrorDismiss = document.getElementById("qa-error-dismiss");
    var qaSavedBanner = document.getElementById("qa-saved-banner");
    var qaSavedText = document.getElementById("qa-saved-text");
    var qaOfflineBadge = document.getElementById("qa-offline-badge");
    var qaPreviewOffline = document.getElementById("qa-preview-offline");

    var qaMerchant = document.getElementById("qa-merchant");
    var qaAmount = document.getElementById("qa-amount");
    var qaCurrency = document.getElementById("qa-currency");
    var qaCategory = document.getElementById("qa-category");
    var qaDate = document.getElementById("qa-date");
    var qaType = document.getElementById("qa-type");
    var qaMismatchBox = document.getElementById("qa-currency-mismatch-box");
    var qaMismatchDetected = document.getElementById("qa-mismatch-detected");
    var qaMismatchConfirmCode = document.getElementById("qa-mismatch-confirm-code");
    var qaCurrencyConfirm = document.getElementById("qa-currency-confirm");

    var sampleSmsBtn = document.getElementById("fill-sms-sample-btn");
    var screenshotBtn = document.getElementById("qa-screenshot-btn");
    var screenshotInput = document.getElementById("qa-screenshot-input");

    if (sampleSmsBtn && qaInput) {
      sampleSmsBtn.addEventListener("click", function () {
        qaInput.value = "Rs 245.00 debited from a/c **4192 via UPI to Zomato on 17-Nov";
        qaInput.focus();
      });
    }

    if (qaErrorDismiss && qaError) {
      qaErrorDismiss.addEventListener("click", function () {
        qaError.hidden = true;
      });
    }

    function showQaError(msg) {
      if (qaErrorText) qaErrorText.textContent = msg;
      if (qaError) qaError.hidden = false;
    }

    function syncCurrencyMismatchUI() {
      if (!qaCurrency || !qaMismatchBox) return;
      var selected = (qaCurrency.value || userCurrency).toUpperCase();
      var mismatch = selected !== userCurrency.toUpperCase();
      qaMismatchBox.hidden = !mismatch;
      if (mismatch) {
        if (qaMismatchDetected) qaMismatchDetected.textContent = selected;
        if (qaMismatchConfirmCode) qaMismatchConfirmCode.textContent = selected;
      } else if (qaCurrencyConfirm) {
        qaCurrencyConfirm.checked = false;
      }
    }

    if (qaCurrency) {
      qaCurrency.addEventListener("change", function () {
        if (qaCurrencyConfirm) qaCurrencyConfirm.checked = false;
        syncCurrencyMismatchUI();
      });
    }

    function populateQuickPreview(data) {
      if (qaMerchant) qaMerchant.value = data.merchant || "";
      if (qaAmount) qaAmount.value = data.amount || "";
      if (qaCurrency && data.currency) qaCurrency.value = data.currency;
      if (qaCategory && data.category) qaCategory.value = data.category;
      if (qaDate && data.date) qaDate.value = data.date;
      if (qaType && data.type) qaType.value = data.type;
      if (qaCurrencyConfirm) qaCurrencyConfirm.checked = false;
      if (qaPreviewOffline) qaPreviewOffline.hidden = !data.offline_mode;
      if (qaOfflineBadge) qaOfflineBadge.hidden = !data.offline_mode;
      syncCurrencyMismatchUI();
      if (qaPreview) qaPreview.hidden = false;
    }

    if (qaForm && qaInput) {
      qaForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        var val = qaInput.value.trim();
        if (!val) {
          showQaError("Please type an expense like 'chai 20' or paste a bank/UPI SMS.");
          return;
        }
        if (qaError) qaError.hidden = true;
        if (qaSavedBanner) qaSavedBanner.hidden = true;
        if (qaPreview) qaPreview.hidden = true;
        if (qaLoading) qaLoading.hidden = false;

        try {
          var res = await apiPostJson("/api/ai/quick-add/parse", { text: val });
          if (qaLoading) qaLoading.hidden = true;
          if (!res.ok) {
            showQaError(res.data.detail || "Could not find a valid amount in that text.");
            return;
          }
          populateQuickPreview(res.data);
        } catch (err) {
          if (qaLoading) qaLoading.hidden = true;
          showQaError("Network error while parsing your input. Please try again.");
        }
      });
    }

    if (screenshotBtn && screenshotInput) {
      screenshotBtn.addEventListener("click", function () {
        screenshotInput.click();
      });

      screenshotInput.addEventListener("change", async function () {
        var file = screenshotInput.files && screenshotInput.files[0];
        if (!file) return;
        if (file.size > 4 * 1024 * 1024) {
          showQaError("Screenshot must be 4 MB or smaller.");
          screenshotInput.value = "";
          return;
        }
        if (qaError) qaError.hidden = true;
        if (qaSavedBanner) qaSavedBanner.hidden = true;
        if (qaPreview) qaPreview.hidden = true;
        if (qaLoading) qaLoading.hidden = false;

        var fd = new FormData();
        fd.append("screenshot", file);
        try {
          var resp = await fetch("/api/ai/quick-add/screenshot", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() },
            body: fd,
          });
          var data = {};
          try { data = await resp.json(); } catch (err) {}
          if (qaLoading) qaLoading.hidden = true;
          screenshotInput.value = "";

          if (!resp.ok) {
            if (data.offline_mode && qaOfflineBadge) qaOfflineBadge.hidden = false;
            showQaError(data.detail || "Could not read a transaction from that screenshot.");
            return;
          }
          populateQuickPreview(data);
        } catch (err) {
          if (qaLoading) qaLoading.hidden = true;
          screenshotInput.value = "";
          showQaError("Network error while scanning screenshot. Please try pasting SMS text instead.");
        }
      });
    }

    var qaConfirm = document.getElementById("qa-confirm-btn");
    var qaCancel = document.getElementById("qa-cancel-btn");
    if (qaConfirm && qaPreview) {
      qaConfirm.addEventListener("click", async function () {
        var merchantVal = (qaMerchant && qaMerchant.value.trim()) || "";
        var amountVal = (qaAmount && qaAmount.value) || "";
        var currencyVal = (qaCurrency && qaCurrency.value) || userCurrency;
        var categoryVal = (qaCategory && qaCategory.value) || "Other";
        var dateVal = (qaDate && qaDate.value) || "";
        var typeVal = (qaType && qaType.value) || "expense";
        var confirmedMismatch = Boolean(qaCurrencyConfirm && qaCurrencyConfirm.checked);

        if (qaError) qaError.hidden = true;
        if (currencyVal.toUpperCase() !== userCurrency.toUpperCase() && !confirmedMismatch) {
          syncCurrencyMismatchUI();
          showQaError("Please tick the confirmation box to save in " + currencyVal + " instead of " + userCurrency + ".");
          if (qaCurrencyConfirm) qaCurrencyConfirm.focus();
          return;
        }

        qaConfirm.disabled = true;
        try {
          var res = await apiPostJson("/api/expenses/quick-save", {
            merchant: merchantVal,
            amount: amountVal,
            currency: currencyVal,
            category: categoryVal,
            date: dateVal,
            type: typeVal,
            confirm_currency_mismatch: confirmedMismatch,
          });
          qaConfirm.disabled = false;
          if (!res.ok) {
            if (res.status === 409 && qaMismatchBox) {
              qaMismatchBox.hidden = false;
            }
            showQaError(res.data.detail || "Could not save transaction. Check all fields and try again.");
            return;
          }
          appendExpenseRow(res.data);
          qaPreview.hidden = true;
          if (qaInput) qaInput.value = "";
          if (qaSavedText) {
            qaSavedText.textContent = "Saved " + res.data.amount_formatted + " for " + res.data.merchant + " (" + res.data.category + " remembered).";
          }
          if (qaSavedBanner) qaSavedBanner.hidden = false;
        } catch (err) {
          qaConfirm.disabled = false;
          showQaError("Network error while saving transaction. Please try again.");
        }
      });
    }
    if (qaCancel && qaPreview) {
      qaCancel.addEventListener("click", function () {
        qaPreview.hidden = true;
        if (qaError) qaError.hidden = true;
      });
    }

    // Live AI Category Suggestion while typing in Add Expense modal
    var modalMerchant = document.getElementById("modal-exp-merchant");
    var modalNote = document.getElementById("modal-exp-note");
    var modalCat = document.getElementById("modal-exp-category");
    var catHintBox = document.getElementById("modal-cat-suggestion");
    var catHintText = document.getElementById("modal-cat-suggestion-text");
    var catOfflineBadge = document.getElementById("modal-cat-offline");
    var manualCategoryChosen = false;
    var suggestTimer = null;

    if (modalCat) {
      modalCat.addEventListener("change", function () {
        manualCategoryChosen = true;
      });
    }

    var modalExpErr = document.getElementById("modal-exp-error");
    var modalExpErrText = document.getElementById("modal-exp-error-text");

    function showModalExpError(msg) {
      if (modalExpErrText) modalExpErrText.textContent = msg;
      if (modalExpErr) modalExpErr.hidden = false;
    }

    document.querySelectorAll('[data-modal-open="add-expense-modal"]').forEach(function (trigger) {
      trigger.addEventListener("click", function () {
        manualCategoryChosen = false;
        document.getElementById("modal-exp-id").value = "";
        if (catHintBox) catHintBox.hidden = true;
        if (modalExpErr) modalExpErr.hidden = true;
      });
    });

    function triggerCategorySuggest() {
      var desc = (((modalMerchant && modalMerchant.value) || "") + " " + ((modalNote && modalNote.value) || "")).trim();
      if (desc.length < 3) {
        if (catHintBox) catHintBox.hidden = true;
        return;
      }
      if (suggestTimer) clearTimeout(suggestTimer);
      suggestTimer = setTimeout(async function () {
        try {
          var res = await apiPostJson("/api/ai/suggest-category", { description: desc.slice(0, 200) });
          if (!res.ok || !res.data.category) return;
          if (!manualCategoryChosen && modalCat) {
            modalCat.value = res.data.category;
          }
          if (catHintText && catHintBox) {
            var via = res.data.source === "memory" ? " (remembered)" : (res.data.source === "ai" ? " (AI suggested)" : " (keyword match)");
            catHintText.textContent = "Suggested category: " + res.data.category + via;
            catHintBox.hidden = false;
          }
          if (catOfflineBadge) {
            catOfflineBadge.hidden = !res.data.offline_mode;
          }
        } catch (err) {}
      }, 450);
    }

    if (modalMerchant) modalMerchant.addEventListener("input", triggerCategorySuggest);
    if (modalNote) modalNote.addEventListener("input", triggerCategorySuggest);

    tbody.addEventListener("click", async function (e) {
      var delBtn = e.target.closest("[data-delete-expense]");
      if (delBtn) {
        var row = delBtn.closest("[data-expense-row]");
        var delId = delBtn.getAttribute("data-delete-expense");
        if (row && delId) {
          delBtn.disabled = true;
          try {
            var res = await apiPostJson("/api/expenses/" + delId + "/delete", {});
            if (!res.ok) {
              delBtn.disabled = false;
              showTableError(res.data.detail || "Could not delete that expense.");
              return;
            }
            row.remove();
            applyFilters();
          } catch (err) {
            delBtn.disabled = false;
            showTableError("Network error while deleting expense. Please try again.");
          }
        }
        return;
      }
      var editBtn = e.target.closest("[data-edit-expense]");
      if (editBtn) {
        var editRow = editBtn.closest("[data-expense-row]");
        var modal = document.getElementById("add-expense-modal");
        if (editRow && modal) {
          manualCategoryChosen = true;
          if (modalExpErr) modalExpErr.hidden = true;
          var rowCur = editRow.getAttribute("data-currency") || userCurrency;
          var digits = decimalsForCurrency(rowCur);
          var minorVal = parseInt(editRow.getAttribute("data-amount-minor") || "0", 10);
          var majorNum = minorVal / Math.pow(10, digits);
          var majorStr = digits === 0 ? String(Math.round(majorNum)) : majorNum.toFixed(digits).replace(/\.00+$/, "");

          document.getElementById("modal-exp-id").value = editRow.getAttribute("data-id") || "";
          document.getElementById("modal-exp-merchant").value = editRow.getAttribute("data-merchant") || "";
          document.getElementById("modal-exp-amount").value = majorStr;
          document.getElementById("modal-exp-date").value = editRow.getAttribute("data-date") || "";
          document.getElementById("modal-exp-category").value = editRow.getAttribute("data-category") || "Other";
          document.getElementById("modal-exp-note").value = editRow.getAttribute("data-note") || "";
          modal.hidden = false;
          document.getElementById("modal-exp-merchant").focus();
        }
      }
    });

    var expModalForm = document.getElementById("expense-modal-form");
    if (expModalForm) {
      expModalForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        if (modalExpErr) modalExpErr.hidden = true;
        var existingId = document.getElementById("modal-exp-id").value;
        var merchant = document.getElementById("modal-exp-merchant").value.trim();
        var amount = document.getElementById("modal-exp-amount").value;
        var dateStr = document.getElementById("modal-exp-date").value;
        var cat = document.getElementById("modal-exp-category").value;
        var note = document.getElementById("modal-exp-note").value.trim();

        if (!merchant) {
          showModalExpError("Please enter a merchant or title.");
          return;
        }
        if (!amount || Number(amount) <= 0) {
          showModalExpError("Please enter a valid positive amount.");
          return;
        }
        if (!dateStr) {
          showModalExpError("Please choose a date.");
          return;
        }

        try {
          if (existingId) {
            var upd = await apiPostJson("/api/expenses/" + existingId + "/update", {
              merchant: merchant,
              amount: amount,
              category: cat,
              date: dateStr,
              note: note,
            });
            if (!upd.ok) {
              showModalExpError(upd.data.detail || "Could not save changes.");
              return;
            }
            var existingRow = tbody.querySelector('[data-id="' + existingId + '"]');
            if (existingRow) {
              updateExpenseRowDom(existingRow, upd.data);
              applyFilters();
            }
          } else {
            var res = await apiPostJson("/api/expenses/quick-save", {
              merchant: merchant,
              amount: amount,
              currency: userCurrency,
              category: cat,
              date: dateStr,
              type: "expense",
              confirm_currency_mismatch: false,
            });
            if (!res.ok) {
              showModalExpError(res.data.detail || "Could not save expense.");
              return;
            }
            appendExpenseRow(res.data);
          }
          document.getElementById("modal-exp-id").value = "";
          expModalForm.reset();
          document.getElementById("add-expense-modal").hidden = true;
        } catch (err) {
          showModalExpError("Network error while saving expense. Please try again.");
        }
      });
    }
  }

  /* Budgets Modal DB Persistence */
  function initBudgetsModal() {
    var form = document.getElementById("budget-modal-form");
    if (!form) return;
    var errBox = document.getElementById("budget-modal-error");
    var errText = document.getElementById("budget-modal-error-text");
    var saveBtn = document.getElementById("budget-save-btn");

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (errBox) errBox.hidden = true;
      var category = document.getElementById("budget-cat-select").value;
      var limitVal = document.getElementById("budget-limit-input").value;
      if (limitVal === "" || Number(limitVal) < 0) {
        if (errText) errText.textContent = "Please enter a non-negative monthly limit.";
        if (errBox) errBox.hidden = false;
        return;
      }
      if (saveBtn) saveBtn.disabled = true;
      try {
        var res = await apiPostJson("/api/budgets/update", { category: category, limit: limitVal });
        if (saveBtn) saveBtn.disabled = false;
        if (!res.ok) {
          if (errText) errText.textContent = res.data.detail || "Could not update budget limit.";
          if (errBox) errBox.hidden = false;
          return;
        }
        window.location.reload();
      } catch (err) {
        if (saveBtn) saveBtn.disabled = false;
        if (errText) errText.textContent = "Network error while saving budget. Please try again.";
        if (errBox) errBox.hidden = false;
      }
    });
  }

  /* Goals Modal DB Persistence */
  function initGoalsModal() {
    var form = document.getElementById("goal-modal-form");
    if (!form) return;
    var errBox = document.getElementById("goal-modal-error");
    var errText = document.getElementById("goal-modal-error-text");
    var saveBtn = document.getElementById("goal-save-btn");

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (errBox) errBox.hidden = true;
      var title = document.getElementById("goal-title-input").value.trim();
      var target = document.getElementById("goal-target-input").value;
      var saved = document.getElementById("goal-saved-input").value || "0";
      var dateStr = document.getElementById("goal-date-input").value;
      if (!title || Number(target) <= 0 || Number(saved) < 0) {
        if (errText) errText.textContent = "Please enter a goal name, positive target, and non-negative saved amount.";
        if (errBox) errBox.hidden = false;
        return;
      }
      if (saveBtn) saveBtn.disabled = true;
      try {
        var res = await apiPostJson("/api/goals/create", {
          title: title,
          target: target,
          saved: saved,
          deadline: dateStr,
          note: "Personal savings goal",
        });
        if (saveBtn) saveBtn.disabled = false;
        if (!res.ok) {
          if (errText) errText.textContent = res.data.detail || "Could not create goal.";
          if (errBox) errBox.hidden = false;
          return;
        }
        window.location.reload();
      } catch (err) {
        if (saveBtn) saveBtn.disabled = false;
        if (errText) errText.textContent = "Network error while creating goal. Please try again.";
        if (errBox) errBox.hidden = false;
      }
    });
  }

  /* Profile Avatar Auto-Submit & Currency Conversion Preview */
  function initProfileAndAuth() {
    var fileInput = document.getElementById("avatar-file-input");
    var uploadForm = document.getElementById("avatar-upload-form");

    if (fileInput && uploadForm) {
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files[0]) {
          uploadForm.submit();
        }
      });
    }

    var previewBtn = document.getElementById("preview-currency-btn");
    var targetInput = document.getElementById("profile-cp-value");
    var previewPanel = document.getElementById("currency-preview-panel");
    var previewRate = document.getElementById("currency-preview-rate");
    var previewRows = document.getElementById("currency-preview-rows");
    var previewErr = document.getElementById("currency-preview-error");
    var previewErrText = document.getElementById("currency-preview-error-text");

    if (previewBtn && targetInput && previewPanel && previewRows) {
      previewBtn.addEventListener("click", async function () {
        if (previewErr) previewErr.hidden = true;
        previewBtn.disabled = true;
        try {
          var res = await apiPostJson("/profile/currency/preview", {
            target_currency: targetInput.value || "INR",
          });
          previewBtn.disabled = false;
          if (!res.ok) {
            if (previewErrText) previewErrText.textContent = res.data.detail || "Could not preview currency conversion.";
            if (previewErr) previewErr.hidden = false;
            return;
          }
          if (previewRate) {
            previewRate.textContent = res.data.rate_display + " (as of " + res.data.as_of + ")";
          }
          previewRows.innerHTML = "";
          (res.data.rows || []).forEach(function (row) {
            var tr = document.createElement("tr");
            var tdLabel = document.createElement("td");
            var tdBefore = document.createElement("td");
            var tdAfter = document.createElement("td");
            tdLabel.textContent = row.label;
            tdBefore.textContent = row.before;
            tdBefore.className = "num money";
            tdAfter.textContent = row.after;
            tdAfter.className = "num money";
            tdAfter.style.fontWeight = "600";
            tr.appendChild(tdLabel);
            tr.appendChild(tdBefore);
            tr.appendChild(tdAfter);
            previewRows.appendChild(tr);
          });
          previewPanel.hidden = false;
        } catch (err) {
          previewBtn.disabled = false;
          if (previewErrText) previewErrText.textContent = "Network error while loading conversion preview.";
          if (previewErr) previewErr.hidden = false;
        }
      });
    }
  }

  /* Subtle Count-Up on Balance (respects user currency & prefers-reduced-motion) */
  function initCountUp() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.querySelectorAll("[data-countup]").forEach(function (el) {
      var targetMinor = parseInt(el.getAttribute("data-countup") || "0", 10);
      var code = el.getAttribute("data-currency") || "INR";
      var locale = el.getAttribute("data-locale") || "en_IN";
      var finalText = el.textContent;
      if (!targetMinor || targetMinor <= 0) return;
      var duration = 220;
      var start = performance.now();
      function step(now) {
        var t = Math.min((now - start) / duration, 1);
        if (t >= 1) {
          el.textContent = finalText;
          return;
        }
        var eased = 1 - Math.pow(1 - t, 3);
        var current = Math.round(targetMinor * (0.85 + 0.15 * eased));
        el.textContent = formatCurrencyMinor(current, code, locale);
        requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initIcons();
    initUserMenu();
    initModals();
    initCurrencyPickers();
    initHomeAi();
    initMoneyBuddy();
    initExpenses();
    initBudgetsModal();
    initGoalsModal();
    initProfileAndAuth();
    initCountUp();
  });
})();
