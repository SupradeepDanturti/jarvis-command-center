// Original interface glyphs. Brand artwork is served from local SVG assets.
const glyphPaths={
  home:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  gaming:'<path d="M7 6h10c3 0 5 12 3 13-2 1-4-3-5-3H9c-1 0-3 4-5 3C2 18 4 6 7 6Z"/><path d="M7 9v6m-3-3h6m5-2h.01M18 13h.01"/>',
  hardware:'<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3"/>',
  graphs:'<path d="M3 3v18h18M5 15l4-6 4 4 7-8"/>',
  apps:'<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><path d="M17 14v6m-3-3h6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  ambient:'<circle cx="12" cy="12" r="4"/><ellipse cx="12" cy="12" rx="11" ry="5" transform="rotate(-35 12 12)"/>',
  system:'<path d="m9 3 1 3h4l1-3 3 2-1 3 2 3 3 1v3l-3 1-2 3 1 3-3 1-1-3h-4l-1 3-3-1 1-3-2-3-3-1v-3l3-1 2-3-1-3Z" transform="translate(0 -1) scale(.95)"/><circle cx="12" cy="12" r="3"/>',
  devices:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  fullscreen:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  files:'<path d="M3 7V5h6l2 3h10v12H3Z"/>',
  terminal:'<path d="m5 7 5 5-5 5m8 0h6"/>',
  play:'<path d="m9 5 11 7-11 7Z"/>',
  pause:'<path d="M8 5v14m8-14v14"/>',
  previous:'<path d="M5 5v14m14-14L8 12l11 7Z"/>',
  next:'<path d="M19 5v14M5 5l11 7-11 7Z"/>',
  mute:'<path d="M10 4 5 9H2v6h3l5 5Zm5 5 6 6m0-6-6 6"/>',
  'volume-down':'<path d="m11 5-5 4H3v6h3l5 4Z"/><path d="M16 9a5 5 0 0 1 0 6"/>',
  'volume-up':'<path d="m11 5-5 4H3v6h3l5 4Z"/><path d="M16 9a5 5 0 0 1 0 6m3-10a9 9 0 0 1 0 14"/>',
  minus:'<path d="M5 12h14"/>',
  plus:'<path d="M5 12h14m-7-7v14"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>'
};
function glyph(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyphPaths[name]||glyphPaths.apps}</svg>`}
