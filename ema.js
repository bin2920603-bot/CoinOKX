(function () {
  var trend = {};

  function mark() {
    document.querySelectorAll("td.coin").forEach(function (td) {
      var symEl = td.querySelector(".sym");
      if (!symEl) return;
      var t = trend["OKX-" + symEl.textContent.trim()];
      var dot = td.querySelector(".ema-dot");
      if (!t) {
        if (dot) dot.remove();
        return;
      }
      if (!dot) {
        dot = document.createElement("span");
        dot.className = "ema-dot";
        dot.style.cssText = "font-size:10px;margin-right:4px;";
        td.insertBefore(dot, td.firstChild);
      }
      dot.textContent = t === "up" ? "🟢" : "🔴";
      dot.title = t === "up" ? "EMA 정배열" : "EMA 역배열";
    });
  }

  function load() {
    fetch("data/ema.json?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (j) { trend = j.trend || {}; mark(); })
      .catch(function () {});
  }

  var box = document.getElementById("scroll");
  if (box) new MutationObserver(mark).observe(box, { childList: true });
  load();
  setInterval(load, 300000);
})();
