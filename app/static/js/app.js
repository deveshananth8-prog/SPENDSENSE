/* SpendSense Global UI Interactions (Stage 1) */
(function () {
  function initIcons() {
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      lucide.createIcons();
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
    document.addEventListener("click", function (e) {
      var openTrigger = e.target.closest("[data-modal-open]");
      if (openTrigger) {
        var targetId = openTrigger.getAttribute("data-modal-open");
        var modal = document.getElementById(targetId);
        if (modal) {
          modal.hidden = false;
          var firstInput = modal.querySelector("input, select, button");
          if (firstInput) firstInput.focus();
        }
        return;
      }

      var closeTrigger = e.target.closest("[data-modal-close]");
      if (closeTrigger) {
        var closeId = closeTrigger.getAttribute("data-modal-close");
        var m = document.getElementById(closeId);
        if (m) m.hidden = true;
        return;
      }

      if (e.target.classList.contains("modal-backdrop")) {
        e.target.hidden = true;
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        document.querySelectorAll(".modal-backdrop:not([hidden])").forEach(function (m) {
          m.hidden = true;
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

      function closeDropdown() {
        dropdown.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
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
          closeDropdown();

          // On Profile page, show 3-option switch preview when switching away from INR
          if (prefix === "profile-cp") {
            var preview = document.getElementById("currency-switch-preview");
            var newCode = document.getElementById("cp-new-code");
            if (preview && newCode) {
              newCode.textContent = code;
              preview.hidden = code === "INR";
            }
          }
        });
      });

      document.addEventListener("click", function (e) {
        if (!dropdown.hidden && !root.contains(e.target)) {
          closeDropdown();
        }
      });
    });
  }

  /* Money Buddy Notebook Interactions */
  function initMoneyBuddy() {
    var chipsWrap = document.getElementById("buddy-chips");
    var askForm = document.getElementById("buddy-ask-form");
    var notebook = document.getElementById("buddy-notebook");
    if (!chipsWrap || !notebook) return;

    function renderEntry(question, answer, nextStep, whyList) {
      var qEl = document.getElementById("buddy-q");
      var aEl = document.getElementById("buddy-a");
      var nEl = document.getElementById("buddy-next");
      var wEl = document.getElementById("buddy-why-list");
      if (qEl) qEl.textContent = question;
      if (aEl) aEl.textContent = answer;
      if (nEl) nEl.textContent = nextStep;
      if (wEl) {
        wEl.innerHTML = "";
        whyList.forEach(function (line) {
          var li = document.createElement("li");
          li.textContent = line;
          wEl.appendChild(li);
        });
      }
    }

    chipsWrap.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-chip-id]");
      if (!chip) return;
      chipsWrap.querySelectorAll("[data-chip-id]").forEach(function (c) {
        c.classList.remove("is-active");
      });
      chip.classList.add("is-active");

      var why = [];
      try {
        why = JSON.parse(chip.getAttribute("data-chip-why") || "[]");
      } catch (err) {}
      renderEntry(
        chip.getAttribute("data-chip-question"),
        chip.getAttribute("data-chip-answer"),
        chip.getAttribute("data-chip-next"),
        why
      );
    });

    if (askForm) {
      askForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var input = document.getElementById("buddy-input");
        var q = (input && input.value.trim()) || "";
        if (!q) return;
        renderEntry(
          q,
          "Based on Riya's November snapshot, your safe-to-spend balance is ₹1,630.00 after reserving ₹850.00 for hostel essentials, giving you ₹135.83/day over the next 12 days.",
          "Try testing any specific purchase in Before You Spend before paying.",
          [
            "Current balance: ₹2,480.00",
            "Upcoming essentials: ₹850.00",
            "Safe-to-spend: ₹1,630.00",
            "Live Gemini AI answers connect in Stage 4.",
          ]
        );
        input.value = "";
      });
    }
  }

  /* Expenses Search, Filter, Quick Add & Modal CRUD UI */
  function initExpenses() {
    var tbody = document.getElementById("expenses-tbody");
    if (!tbody) return;

    var searchInput = document.getElementById("expense-search");
    var catSelect = document.getElementById("expense-category-filter");
    var tableWrap = document.getElementById("expenses-table-wrap");
    var emptyState = document.getElementById("expenses-empty-state");
    var countLabel = document.getElementById("expenses-count-label");
    var totalLabel = document.getElementById("expenses-total-label");

    function formatInrMinor(minor) {
      return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        minimumFractionDigits: 2,
      }).format(minor / 100);
    }

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
        var matchSearch = !q || merchant.includes(q) || note.includes(q);
        var matchCat = cat === "all" || rowCat === cat;
        var show = matchSearch && matchCat;
        row.hidden = !show;
        if (show) {
          visible += 1;
          totalMinor += parseInt(row.getAttribute("data-amount-minor") || "0", 10);
        }
      });

      if (tableWrap) tableWrap.hidden = visible === 0;
      if (emptyState) emptyState.hidden = visible > 0;
      if (countLabel) countLabel.textContent = visible + (visible === 1 ? " entry" : " entries");
      if (totalLabel) totalLabel.textContent = formatInrMinor(totalMinor);
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

    // Loading & Error Preview Toggles
    var loadBtn = document.getElementById("toggle-loading-demo");
    var errBtn = document.getElementById("toggle-error-demo");
    var loadBox = document.getElementById("expenses-loading-state");
    var errBox = document.getElementById("expenses-error-state");
    var dismissErr = document.getElementById("dismiss-error-demo");

    if (loadBtn && loadBox) {
      loadBtn.addEventListener("click", function () {
        loadBox.hidden = !loadBox.hidden;
      });
    }
    if (errBtn && errBox) {
      errBtn.addEventListener("click", function () {
        errBox.hidden = !errBox.hidden;
      });
    }
    if (dismissErr && errBox) {
      dismissErr.addEventListener("click", function () {
        errBox.hidden = true;
      });
    }

    // Quick Add SMS / "chai 20" parser UI
    var qaForm = document.getElementById("quick-add-form");
    var qaInput = document.getElementById("quick-add-input");
    var qaPreview = document.getElementById("quick-add-preview");
    var qaMerchant = document.getElementById("qa-merchant");
    var qaAmount = document.getElementById("qa-amount");
    var qaCategory = document.getElementById("qa-category");
    var sampleSmsBtn = document.getElementById("fill-sms-sample-btn");

    if (sampleSmsBtn && qaInput) {
      sampleSmsBtn.addEventListener("click", function () {
        qaInput.value = "Rs 245.00 debited from a/c **4192 via UPI to Zomato on 17-Nov";
        qaInput.focus();
      });
    }

    function parseQuickText(text) {
      var amtMatch = text.match(/(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)/i);
      var amount = amtMatch ? Math.round(parseFloat(amtMatch[1])) : 50;
      var lower = text.toLowerCase();
      var cat = "Other";
      if (lower.includes("chai") || lower.includes("zomato") || lower.includes("swiggy") || lower.includes("mess")) {
        cat = "Food & Mess";
      } else if (lower.includes("metro") || lower.includes("bus") || lower.includes("uber")) {
        cat = "Travel";
      } else if (lower.includes("jio") || lower.includes("recharge") || lower.includes("airtel")) {
        cat = "Bills & Recharge";
      }
      var merchant = text.replace(/(?:rs\.?|inr|₹)?\s*\d+(?:\.\d{1,2})?/gi, "").replace(/debited.*to\s+/i, "").trim();
      if (!merchant) merchant = "Quick expense";
      return { merchant: merchant.slice(0, 48), amount: amount, category: cat };
    }

    if (qaForm && qaInput && qaPreview) {
      qaForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var val = qaInput.value.trim();
        if (!val) return;
        var parsed = parseQuickText(val);
        if (qaMerchant) qaMerchant.value = parsed.merchant;
        if (qaAmount) qaAmount.value = parsed.amount;
        if (qaCategory) qaCategory.value = parsed.category;
        qaPreview.hidden = false;
      });
    }

    function appendExpenseRow(merchant, amountMajor, category, dateStr, note) {
      var id = Date.now();
      var minor = Math.round(Number(amountMajor) * 100);
      var tr = document.createElement("tr");
      tr.setAttribute("data-expense-row", "");
      tr.setAttribute("data-id", String(id));
      tr.setAttribute("data-merchant", merchant);
      tr.setAttribute("data-note", note || "Added in Stage 1 preview");
      tr.setAttribute("data-category", category);
      tr.setAttribute("data-date", dateStr);
      tr.setAttribute("data-amount-minor", String(minor));

      tr.innerHTML =
        '<td class="num" style="white-space:nowrap;"></td>' +
        '<td><div style="font-weight:600;"></div><div style="font-size:0.82rem;color:var(--ink-muted);"></div></td>' +
        "<td></td>" +
        '<td style="color:var(--ink-muted);">UPI</td>' +
        '<td class="num money" style="font-weight:600;"></td>' +
        '<td class="num"><div class="row-actions">' +
        '<button type="button" class="icon-btn" data-delete-expense="' + id + '" aria-label="Delete ' + merchant + '">' +
        '<i data-lucide="trash-2" aria-hidden="true" width="15" height="15"></i></button></div></td>';

      var cells = tr.querySelectorAll("td");
      cells[0].textContent = dateStr;
      cells[1].children[0].textContent = merchant;
      cells[1].children[1].textContent = note || "Added in Stage 1 preview";
      cells[2].textContent = category;
      cells[4].textContent = formatInrMinor(minor);

      tbody.prepend(tr);
      initIcons();
      applyFilters();
    }

    var qaConfirm = document.getElementById("qa-confirm-btn");
    var qaCancel = document.getElementById("qa-cancel-btn");
    if (qaConfirm && qaPreview) {
      qaConfirm.addEventListener("click", function () {
        appendExpenseRow(
          (qaMerchant && qaMerchant.value.trim()) || "Quick expense",
          (qaAmount && qaAmount.value) || 20,
          (qaCategory && qaCategory.value) || "Other",
          "2026-11-17",
          "Quick Add entry"
        );
        qaPreview.hidden = true;
        if (qaInput) qaInput.value = "";
      });
    }
    if (qaCancel && qaPreview) {
      qaCancel.addEventListener("click", function () {
        qaPreview.hidden = true;
      });
    }

    tbody.addEventListener("click", function (e) {
      var delBtn = e.target.closest("[data-delete-expense]");
      if (delBtn) {
        var row = delBtn.closest("[data-expense-row]");
        if (row) {
          row.remove();
          applyFilters();
        }
        return;
      }
      var editBtn = e.target.closest("[data-edit-expense]");
      if (editBtn) {
        var row = editBtn.closest("[data-expense-row]");
        var modal = document.getElementById("add-expense-modal");
        if (row && modal) {
          document.getElementById("modal-exp-id").value = row.getAttribute("data-id") || "";
          document.getElementById("modal-exp-merchant").value = row.getAttribute("data-merchant") || "";
          document.getElementById("modal-exp-amount").value = Math.round(parseInt(row.getAttribute("data-amount-minor") || "0", 10) / 100);
          document.getElementById("modal-exp-date").value = row.getAttribute("data-date") || "2026-11-17";
          document.getElementById("modal-exp-category").value = row.getAttribute("data-category") || "Other";
          document.getElementById("modal-exp-note").value = row.getAttribute("data-note") || "";
          modal.hidden = false;
        }
      }
    });

    var expModalForm = document.getElementById("expense-modal-form");
    if (expModalForm) {
      expModalForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var existingId = document.getElementById("modal-exp-id").value;
        var merchant = document.getElementById("modal-exp-merchant").value.trim();
        var amount = document.getElementById("modal-exp-amount").value;
        var dateStr = document.getElementById("modal-exp-date").value;
        var cat = document.getElementById("modal-exp-category").value;
        var note = document.getElementById("modal-exp-note").value.trim();
        if (!merchant || !amount) return;

        if (existingId) {
          var existingRow = tbody.querySelector('[data-id="' + existingId + '"]');
          if (existingRow) existingRow.remove();
        }
        appendExpenseRow(merchant, amount, cat, dateStr, note);
        document.getElementById("modal-exp-id").value = "";
        expModalForm.reset();
        document.getElementById("add-expense-modal").hidden = true;
      });
    }
  }

  /* Goals Modal UI Preview */
  function initGoalsModal() {
    var form = document.getElementById("goal-modal-form");
    var grid = document.getElementById("goals-grid");
    if (!form || !grid) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var title = document.getElementById("goal-title-input").value.trim();
      var target = Number(document.getElementById("goal-target-input").value || 0);
      var saved = Number(document.getElementById("goal-saved-input").value || 0);
      var dateStr = document.getElementById("goal-date-input").value;
      if (!title || target <= 0) return;

      var pct = Math.min(Math.round((saved / target) * 100), 100);
      var fmt = function (v) {
        return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(v);
      };

      var card = document.createElement("article");
      card.className = "card";
      card.style.cssText = "display:flex;flex-direction:column;justify-content:space-between;gap:16px;";
      card.innerHTML =
        '<div><div class="meta-line" style="margin-bottom:6px;"><span>Target date · ' +
        dateStr +
        '</span></div><h2 style="font-size:1.25rem;margin-bottom:6px;"></h2><p style="font-size:0.88rem;color:var(--ink-muted);">Added in Stage 1 preview</p></div>' +
        '<div><div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">' +
        '<span class="money" style="font-family:var(--font-display);font-size:1.4rem;font-weight:600;">' +
        fmt(saved) +
        '</span><span class="money" style="font-size:0.85rem;color:var(--ink-muted);">of ' +
        fmt(target) +
        " (" +
        pct +
        '%)</span></div><div class="progress-wrap"><div class="progress-track"><div class="progress-fill tone-primary" style="width:' +
        pct +
        '%;"></div></div></div><div style="margin-top:10px;font-size:0.84rem;color:var(--ink-muted);">' +
        fmt(Math.max(target - saved, 0)) +
        " still to go</div></div>";
      card.querySelector("h2").textContent = title;
      grid.appendChild(card);
      form.reset();
      document.getElementById("add-goal-modal").hidden = true;
    });
  }

  /* Profile Avatar Preview & Auth Form Feedback */
  function initProfileAndAuth() {
    var fileInput = document.getElementById("avatar-file-input");
    var preview = document.getElementById("profile-avatar-preview");
    var removeBtn = document.getElementById("avatar-remove-btn");

    if (fileInput && preview) {
      fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function (ev) {
          preview.innerHTML = '<span class="avatar avatar-lg"><img src="' + ev.target.result + '" alt="Riya Sharma" /></span>';
        };
        reader.readAsDataURL(file);
      });
    }

    if (removeBtn && preview) {
      removeBtn.addEventListener("click", function () {
        preview.innerHTML = '<span class="avatar avatar-lg" aria-label="Riya Sharma"><span>RS</span></span>';
        if (fileInput) fileInput.value = "";
      });
    }

    var signinForm = document.getElementById("signin-form");
    if (signinForm) {
      signinForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var fb = document.getElementById("signin-feedback");
        var txt = document.getElementById("signin-feedback-text");
        if (fb && txt) {
          txt.textContent = "Sign in connects in Stage 2. Click 'Try the demo as Riya' below to explore the app now.";
          fb.hidden = false;
        }
      });
    }

    var signupForm = document.getElementById("signup-form");
    if (signupForm) {
      signupForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var fb = document.getElementById("signup-feedback");
        var txt = document.getElementById("signup-feedback-text");
        if (fb && txt) {
          txt.textContent = "Account creation connects in Stage 2. Click 'Try the demo first' below to explore the app now.";
          fb.hidden = false;
        }
      });
    }
  }

  /* Subtle Count-Up on Balance (respects prefers-reduced-motion) */
  function initCountUp() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.querySelectorAll("[data-countup]").forEach(function (el) {
      var targetMinor = parseInt(el.getAttribute("data-countup") || "0", 10);
      if (!targetMinor) return;
      var duration = 220;
      var start = performance.now();
      function step(now) {
        var t = Math.min((now - start) / duration, 1);
        var eased = 1 - Math.pow(1 - t, 3);
        var current = Math.round(targetMinor * (0.85 + 0.15 * eased));
        el.textContent = new Intl.NumberFormat("en-IN", {
          style: "currency",
          currency: "INR",
          minimumFractionDigits: 2,
        }).format(current / 100);
        if (t < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initIcons();
    initUserMenu();
    initModals();
    initCurrencyPickers();
    initMoneyBuddy();
    initExpenses();
    initGoalsModal();
    initProfileAndAuth();
    initCountUp();
  });
})();
