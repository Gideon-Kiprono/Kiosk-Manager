// Tiny enhancements. The site works without JavaScript; this adds chart tooltips and printing.
(function () {
  var chart = document.querySelector(".chart");
  if (chart) {
    var tip = document.createElement("div");
    tip.className = "tooltip";
    tip.hidden = true;
    chart.appendChild(tip);

    function show(bar) {
      var box = chart.getBoundingClientRect();
      var rect = bar.querySelector(".hit").getBoundingClientRect();
      tip.textContent = bar.getAttribute("data-tip");
      tip.hidden = false;
      var left = rect.left - box.left + rect.width / 2 - tip.offsetWidth / 2;
      left = Math.max(0, Math.min(left, box.width - tip.offsetWidth));
      tip.style.left = left + "px";
      tip.style.top = Math.max(0, rect.top - box.top - tip.offsetHeight - 4) + "px";
    }
    function hide() { tip.hidden = true; }

    chart.querySelectorAll(".bar").forEach(function (bar) {
      bar.addEventListener("pointerenter", function () { show(bar); });
      bar.addEventListener("pointerleave", hide);
      bar.addEventListener("focus", function () { show(bar); });
      bar.addEventListener("blur", hide);
      bar.addEventListener("click", function () { show(bar); });   // tap on phones
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") hide(); });
    document.addEventListener("click", function (e) { if (!e.target.closest(".bar")) hide(); });
  }

  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () { window.print(); });
  });
})();
