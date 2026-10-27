# Event imagery

This folder is **optional**. Every event illustration on the website is
generated as original inline SVG (see `templates/components/artwork.html`), so
the site looks complete without a single bitmap file.

If the organisers later want a photograph or a poster for a competition:

1. Drop the file into this folder, for example `prompt-wars.jpg`.
2. Set the event's `"image"` field in `data/events.json` to the path below
   `static/images/`, e.g. `"events/prompt-wars.jpg"`.
3. The event page renders that image instead of the generated artwork.

Recommended: keep files under 200 KB, use a 3:2 aspect ratio, and always keep
the generated fallback so a missing file never breaks the layout.
