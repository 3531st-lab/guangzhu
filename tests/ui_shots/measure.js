// Import in a browser task or paste this function into CUA's read-only evaluate.
// This file does not connect to the user's browser, launch Playwright, or create model runs.
export function measurePage() {
  const root = document.documentElement, body = document.body;
  return {url:location.href,theme:root.dataset.theme,width:innerWidth,height:innerHeight,
    overflowX:Math.max(0,root.scrollWidth-innerWidth,body.scrollWidth-innerWidth),
    overflowY:Math.max(0,root.scrollHeight-innerHeight,body.scrollHeight-innerHeight),
    iframeCount:document.querySelectorAll('#agh').length,
    route:location.hash,connection:document.getElementById('connection')?.textContent ?? '',
    visibleApprovalHints:[...document.querySelectorAll('.banner.warn')]
      .filter(el => el.getClientRects().length && el.textContent.includes('等你批准'))
      .map(el => el.textContent.trim())};
}
export const matrix = {
  viewports:[[1440,900],[1920,1080],[1536,834],[1280,680],[390,844]],
  themes:['light','dark'],
  routes:['new','form','run','result/PROJECT','records','replay/RUN'],
  runStates:['running','approval','checkpoint','finished']
};
