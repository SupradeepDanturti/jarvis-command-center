# Local artwork and logo sources

- `frontend/assets/g16-mark.svg`, `frontend/favicon.svg`, and `frontend/icons.js`: original G16 project emblem and interface glyphs.
- `frontend/ambient-art.js`: original deterministic orbital artwork. `scripts/render-ambient.cjs` renders it to the included 1280×720, silent 16-second `event-horizon.webm` loop and JPEG poster. Neon drift and Aurora are original CSS scenes in `frontend/theme.css`. No third-party video or social-media clip is embedded.
- Steam, Discord, Spotify, Brave, YouTube, and OBS glyphs: [Simple Icons](https://github.com/simple-icons/simple-icons), pinned to revision `1089fb7d2bf0e323f834c205ab76265005a6d5e8`. Downloaded SVG paths are preserved and given brand-color fills. The upstream CC0 license is included at `frontend/assets/icons/SIMPLE-ICONS-LICENSE.md`. Brand marks identify their corresponding launch targets; ownership remains with the respective brands. See the upstream [disclaimer](https://github.com/simple-icons/simple-icons/blob/1089fb7d2bf0e323f834c205ab76265005a6d5e8/DISCLAIMER.md).
- Game artwork is read from the laptop's existing Steam cache through authenticated routes. These images and installation records are not copied into the repository. Other games use original fallback covers.

All dashboard assets are served locally. No CDN, external font, video stream, or third-party tracking request is needed to view the dashboard.
