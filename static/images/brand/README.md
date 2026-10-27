# Brand imagery

The Technovana mark is a small geometric composition built from the brand
palette: an orange square, a lime square, a cobalt circle and an ink-navy
corner line.

* `favicon.svg` — the browser tab icon (referenced by `templates/base.html`).
* The same artwork is rendered inline by
  `templates/components/artwork.html` (`wordmark()`), so the header mark never
  depends on a network request.

Keep additions small and in SVG format so the mark stays sharp at every size.
