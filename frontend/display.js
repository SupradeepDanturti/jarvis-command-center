// Local browser dimensions only; no device identifiers or laptop credentials.
function displayDetails() {
  return {
    width: innerWidth,
    height: innerHeight,
    visibleWidth: Math.round(visualViewport?.width ?? innerWidth),
    visibleHeight: Math.round(visualViewport?.height ?? innerHeight),
    scale: devicePixelRatio,
    mode: document.fullscreenElement ? 'Fullscreen' : 'Normal browser',
    orientation: innerWidth >= innerHeight ? 'Landscape' : 'Portrait',
  };
}
function displaySettings() {
  const size = displayDetails();
  return `<div class="detail-row"><span>Display size</span><strong id="display-size">${size.width} × ${size.height}</strong></div><div class="detail-row"><span>Display mode</span><strong id="display-mode">${size.orientation} · ${size.mode}</strong></div><p class="section-note">This browser’s available space. Copy these details to help adjust the tablet layout.</p><div class="page-actions"><button id="copy-display-details">Copy display details</button></div>`;
}
function updateDisplayDetails() {
  const size = displayDetails();
  const value = document.querySelector('#display-size');
  const mode = document.querySelector('#display-mode');
  if (value) value.textContent = `${size.width} × ${size.height}`;
  if (mode) mode.textContent = `${size.orientation} · ${size.mode}`;
}
async function copyDisplayDetails() {
  const size = displayDetails();
  const text = `Jarvis display details\nDisplay size: ${size.width} × ${size.height} CSS px\nVisible area: ${size.visibleWidth} × ${size.visibleHeight} CSS px\nMode: ${size.orientation} · ${size.mode}\nPixel scale: ${size.scale}×`;
  if (!navigator.clipboard?.writeText) throw new Error(`Copy is unavailable. Display size: ${size.width} × ${size.height}.`);
  await navigator.clipboard.writeText(text);
  toast('Display details copied, sir. Paste them into the chat.');
}
let displayReportTimer;
async function reportDisplayDetails() {
  if (!state.paired || document.visibilityState !== 'visible') return;
  try {
    await fetch('/api/device/display', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(displayDetails()) });
  } catch { /* The next connection or heartbeat retries without interrupting controls. */ }
}
function displayChanged() {
  updateDisplayDetails();
  clearTimeout(displayReportTimer);
  displayReportTimer = setTimeout(reportDisplayDetails, 250);
}
function displayReportSummary(report) {
  if (!report) return '';
  const freshness = Date.now() / 1000 - report.reported_at < 90 ? 'Live display' : 'Last display report';
  return `${freshness}: ${report.width} × ${report.height} · ${report.orientation} · ${report.mode}`;
}
window.addEventListener('resize', displayChanged);
window.visualViewport?.addEventListener('resize', displayChanged);
document.addEventListener('fullscreenchange', displayChanged);
document.addEventListener('visibilitychange', displayChanged);
setInterval(reportDisplayDetails, 30000);
