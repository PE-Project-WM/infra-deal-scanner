// Northing: small progressive enhancements. Every page works without this file.
(function () {
  // Mobile menu
  var btn = document.getElementById('menu'), nav = document.getElementById('nav');
  if (btn && nav) btn.addEventListener('click', function () {
    var open = nav.classList.toggle('open');
    btn.setAttribute('aria-expanded', String(open));
  });

  // Ranking filters: rows carry data-* attributes; selects hide rows that do not match
  var table = document.getElementById('ranking');
  if (table) {
    var selects = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
    var search = document.getElementById('f-search');
    var count = document.getElementById('f-count');
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var empty = document.getElementById('f-empty');
    var apply = function () {
      var q = search ? search.value.trim().toLowerCase() : '';
      var shown = 0;
      rows.forEach(function (r) {
        var ok = selects.every(function (s) { return !s.value || r.dataset[s.dataset.filter] === s.value; });
        if (ok && q) ok = r.dataset.name.indexOf(q) !== -1;
        r.hidden = !ok; if (ok) shown++;
      });
      if (count) count.textContent = shown + ' of ' + rows.length + ' shown';
      if (empty) empty.hidden = shown !== 0;
    };
    selects.forEach(function (s) { s.addEventListener('change', apply); });
    if (search) search.addEventListener('input', apply);
    var params = new URLSearchParams(location.search);
    selects.forEach(function (s) { var v = params.get(s.dataset.filter); if (v) s.value = v; });
    apply();
  }

  // Links from the old single-page site (#overview, #sector-fibre ...) go to the new pages
  var h = location.hash.slice(1), root = document.documentElement.dataset.root || './';
  var old = {overview: 'rankings/', summary: '', findings: 'rankings/', companies: 'rankings/', price: 'price-check/',
             'price-section': 'price-check/', market: 'market/', method: 'methodology/', sectors: 'sectors/'};
  if (document.body.dataset.page === 'home' && h) {
    if (h.indexOf('sector-') === 0) location.replace(root + 'sectors/' + h.slice(7) + '/');
    else if (old[h]) location.replace(root + old[h]);
  }
})();
