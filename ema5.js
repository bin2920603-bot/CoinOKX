(function () {
  var trend = {};
  var ICON = { up: "🟩", down: "🟥", early: "🟨" };
  var TIP = {
    up: "5분봉 EMA 정배열",
    down: "5분봉 EMA 역배열",
    early: "EMA7이 EMA20을 막 위로 넘음 (배열 되어가는 중)"
  };

  function mark() {
    document.querySelectorAll("td.coin").forEach(function (td) {
      var symEl = td.querySelector(".sym");
      var link = td.querySelector("a");
      if (!symEl || !link) return;
      var t = trend["OKX-" + symEl.textContent.trim()];
      var dot = td.querySelector(".ema5-dot");
      if (!t || !ICON[t]) {
        if (dot) dot.remove();
        return;
      }
      if (!dot) {
        dot = document.createElement("span");
        dot.className = "ema5-dot";
        dot.style.cssText = "font-size:10px;margin-right:4px;";
        td.insertBefore(dot, link);
      }
      dot.textContent = ICON[t];
      dot.title = TIP[t];
    });
  }

  function load() {
    fetch("data/ema5.json?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (j) { trend = j.trend || {}; mark(); })
      .catch(function () {});
  }

  var box = document.getElementById("scroll");
  if (box) new MutationObserver(mark).observe(box, { childList: true });
  load();
  setInterval(load, 120000);
})();
