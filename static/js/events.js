/* ==========================================================================
   TECHNOVANA — events.js
   Instant client-side search and category filtering for the event directory.

   The server already renders the correct result set (so the page works with
   JavaScript disabled). This script filters the rendered list immediately and
   keeps the address bar in sync so a filtered view can be shared.
   ========================================================================== */

(function () {
  'use strict';

  var form = document.getElementById('event-filters');
  var grid = document.getElementById('event-results');
  if (!form || !grid) { return; }

  var searchInput = document.getElementById('event-search');
  var sortSelect = document.getElementById('event-sort');
  var statusLine = document.getElementById('filter-status');
  var chips = Array.prototype.slice.call(form.querySelectorAll('.chip[data-category]'));
  var items = Array.prototype.slice.call(grid.querySelectorAll('.event-result'));
  var total = items.length;

  var activeCategory = 'all';
  var activeChip = chips.filter(function (chip) {
    return chip.getAttribute('aria-pressed') === 'true';
  })[0];
  if (activeChip) { activeCategory = activeChip.getAttribute('data-category'); }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function matches(item) {
    var term = searchInput ? searchInput.value.trim().toLowerCase() : '';
    var category = item.getAttribute('data-category') || '';
    var title = item.getAttribute('data-title') || '';
    var description = item.getAttribute('data-description') || '';

    var categoryOk = activeCategory === 'all' ||
      category === activeCategory.toLowerCase();
    var termOk = !term ||
      title.indexOf(term) !== -1 ||
      category.indexOf(term) !== -1 ||
      description.indexOf(term) !== -1;

    return categoryOk && termOk;
  }

  function apply() {
    var visible = 0;

    items.forEach(function (item) {
      var show = matches(item);
      item.hidden = !show;
      if (show) { visible += 1; }
    });

    var empty = document.getElementById('event-empty');
    if (empty) { empty.hidden = visible !== 0; }
    grid.hidden = visible === 0;

    if (statusLine) {
      var html = 'Showing <strong>' + visible + '</strong> of ' + total + ' competitions';
      if (searchInput && searchInput.value.trim()) {
        html += ' matching “' + escapeHtml(searchInput.value.trim()) + '”';
      }
      if (activeCategory !== 'all') {
        html += ' in ' + escapeHtml(activeCategory);
      }
      html += '.';
      statusLine.innerHTML = html + ' ';
    }
  }

  function syncUrl() {
    if (!window.history || !window.history.replaceState) { return; }
    var params = new URLSearchParams();
    if (searchInput && searchInput.value.trim()) {
      params.set('q', searchInput.value.trim());
    }
    if (activeCategory !== 'all') { params.set('category', activeCategory); }
    if (sortSelect && sortSelect.value && sortSelect.value !== 'title') {
      params.set('sort', sortSelect.value);
    }
    var query = params.toString();
    window.history.replaceState(
      {}, '', window.location.pathname + (query ? '?' + query : '')
    );
  }

  /* --- Search ------------------------------------------------------ */
  if (searchInput) {
    var timer;
    searchInput.addEventListener('input', function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        apply();
        syncUrl();
      }, 110);
    });

    searchInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        apply();
        syncUrl();
      }
    });
  }

  /* --- Category chips --------------------------------------------- */
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (other) { other.setAttribute('aria-pressed', 'false'); });
      chip.setAttribute('aria-pressed', 'true');
      activeCategory = chip.getAttribute('data-category') || 'all';
      apply();
      syncUrl();
    });
  });

  /* --- Sorting is done on the server ------------------------------- */
  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      form.submit();
    });
  }

  apply();
})();
