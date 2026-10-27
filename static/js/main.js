/* ==========================================================================
   TECHNOVANA — main.js
   Shared front-end behaviour. Everything here is progressive enhancement: the
   site stays fully usable if this file fails to load.
   ========================================================================== */

(function () {
  'use strict';

  /* ------------------------------------------------------------------
     Mobile navigation
     ------------------------------------------------------------------ */
  var toggle = document.getElementById('nav-toggle');
  var drawer = document.getElementById('mobile-nav');

  if (toggle && drawer) {
    var setDrawer = function (open) {
      drawer.classList.toggle('is-open', open);
      drawer.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    };

    toggle.addEventListener('click', function () {
      setDrawer(drawer.hidden);
    });

    drawer.addEventListener('click', function (event) {
      if (event.target.closest('a')) { setDrawer(false); }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !drawer.hidden) {
        setDrawer(false);
        toggle.focus();
      }
    });

    window.addEventListener('resize', function () {
      if (window.innerWidth > 1024 && !drawer.hidden) { setDrawer(false); }
    });
  }

  /* ------------------------------------------------------------------
     Back to top
     ------------------------------------------------------------------ */
  var toTop = document.getElementById('to-top');

  if (toTop) {
    var updateToTop = function () {
      toTop.classList.toggle('is-visible', window.scrollY > 600);
    };
    window.addEventListener('scroll', updateToTop, { passive: true });
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    updateToTop();
  }

  /* ------------------------------------------------------------------
     Accessible FAQ disclosures
     ------------------------------------------------------------------ */
  document.querySelectorAll('[data-faq]').forEach(function (group) {
    var triggers = group.querySelectorAll('.faq-item__trigger');

    triggers.forEach(function (trigger) {
      trigger.addEventListener('click', function () {
        var panel = document.getElementById(trigger.getAttribute('aria-controls'));
        if (!panel) { return; }
        var expanded = trigger.getAttribute('aria-expanded') === 'true';
        trigger.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        panel.hidden = expanded;
      });
    });
  });

  /* ------------------------------------------------------------------
     Flash messages fade out after a while
     ------------------------------------------------------------------ */
  var flashes = document.querySelectorAll('.flash');
  if (flashes.length) {
    window.setTimeout(function () {
      flashes.forEach(function (flash) {
        flash.style.transition = 'opacity 300ms ease';
        flash.style.opacity = '0';
        window.setTimeout(function () { flash.remove(); }, 320);
      });
    }, 8000);
  }
})();
