/* SpendSense Theme Manager (Light / Dark / System) */
(function () {
  var STORAGE_KEY = "spendsense_theme";
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function resolveTheme(pref) {
    if (pref === "light" || pref === "dark") return pref;
    return media && media.matches ? "dark" : "light";
  }

  function applyTheme(pref) {
    var normalized = pref === "light" || pref === "dark" || pref === "system" ? pref : "system";
    var resolved = resolveTheme(normalized);
    document.documentElement.setAttribute("data-theme", resolved);
    document.documentElement.setAttribute("data-theme-pref", normalized);
    try {
      localStorage.setItem(STORAGE_KEY, normalized);
    } catch (e) {}

    var buttons = document.querySelectorAll("[data-theme-choice]");
    buttons.forEach(function (btn) {
      var active = btn.getAttribute("data-theme-choice") === normalized;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });

    window.dispatchEvent(new CustomEvent("spendsense:themechange", { detail: { theme: resolved, pref: normalized } }));
  }

  function initThemeControls() {
    var currentPref = "system";
    try {
      currentPref = localStorage.getItem(STORAGE_KEY) || "system";
    } catch (e) {}
    applyTheme(currentPref);

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-theme-choice]");
      if (btn) {
        applyTheme(btn.getAttribute("data-theme-choice"));
        return;
      }
      var cycleBtn = e.target.closest("#public-theme-cycle");
      if (cycleBtn) {
        var activeResolved = document.documentElement.getAttribute("data-theme") || "light";
        applyTheme(activeResolved === "dark" ? "light" : "dark");
      }
    });

    if (media && media.addEventListener) {
      media.addEventListener("change", function () {
        var pref = document.documentElement.getAttribute("data-theme-pref") || "system";
        if (pref === "system") applyTheme("system");
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initThemeControls);
  } else {
    initThemeControls();
  }
})();
