/* Funciones comunes. Los datos (salidas, contacto) los arma el servidor en /js/data.js */
(function (V) {
  V.hoy = function () { var d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  V.diasHasta = function (iso) { return Math.round((new Date(iso + "T00:00:00") - V.hoy()) / 86400000); };
  /* Salidas vigentes: las vencidas desaparecen solas. */
  V.vigentes = function (empresa) {
    return V.salidas.filter(function (s) { return V.diasHasta(s.fecha) >= 0 && (!empresa || s.empresa === empresa); })
      .sort(function (a, b) { return a.fecha < b.fecha ? -1 : 1; });
  };
  V.porId = function (id) { return V.salidas.filter(function (s) { return s.id === id; })[0]; };
  V.waLink = function (texto) { return "https://wa.me/" + V.whatsapp + "?text=" + encodeURIComponent(texto || "Hola! Quiero consultar por un viaje"); };
  V.estadoTxt = { ultimos: "Últimos cupos", agotado: "Agotado", preventa: "Preventa", disponible: "" };
  V.esc = function (t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
})(window.VDV);
