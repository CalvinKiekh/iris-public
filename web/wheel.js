/* One-dimensional navigation.
 *
 * The RayNeo IO is driven by a scroll wheel plus a confirm press, so every
 * screen has to be reachable as a flat list: wheel moves a focus ring,
 * press activates. Building it now - rather than after the SDK lands -
 * keeps us from designing screens that only a touchscreen can operate.
 *
 * Today it binds to the mouse wheel and the arrow keys. When the SDK
 * arrives, only `attachInput` needs a second implementation.
 */
(function () {
  const SELECTOR = '.row, .askbtns button, .shortcut, #sc-close, ' +
                   '#send, #mic, #quick, #stop, #back';
  let items = [];
  let idx = -1;
  let enabled = false;

  function visible(el) {
    if (el.disabled || el.closest('.hidden')) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function refresh() {
    items = Array.from(document.querySelectorAll(SELECTOR)).filter(visible);
    if (idx >= items.length) idx = items.length - 1;
    paint();
  }

  function paint() {
    document.querySelectorAll('.wheel-focus').forEach((e) => e.classList.remove('wheel-focus'));
    const el = items[idx];
    if (!el) return;
    el.classList.add('wheel-focus');
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function move(delta) {
    if (!items.length) refresh();
    if (!items.length) return;
    enabled = true;
    document.body.classList.add('wheel-mode');
    idx = (idx + delta + items.length) % items.length;
    paint();
  }

  function activate() {
    const el = items[idx];
    if (!el) return;
    el.click();
    // The list usually changes after a press; re-read it on the next frame.
    requestAnimationFrame(refresh);
  }

  /* Pending confirmations jump the queue: on glasses you want the wheel to
     land on "Erlauben" the moment it appears, not ten cards further up. */
  function focusFirst(selector) {
    refresh();
    const target = items.findIndex((el) => el.matches(selector));
    if (target >= 0) { idx = target; enabled = true;
      document.body.classList.add('wheel-mode'); paint(); }
  }

  function attachInput() {
    let acc = 0;
    window.addEventListener('wheel', (e) => {
      acc += e.deltaY;
      const step = 40;                      // one detent, not one pixel
      while (Math.abs(acc) >= step) {
        move(acc > 0 ? 1 : -1);
        acc -= Math.sign(acc) * step;
      }
    }, { passive: true });

    window.addEventListener('keydown', (e) => {
      const typing = document.activeElement &&
                     document.activeElement.tagName === 'TEXTAREA';
      if (e.key === 'ArrowDown' && !typing) { e.preventDefault(); move(1); }
      else if (e.key === 'ArrowUp' && !typing) { e.preventDefault(); move(-1); }
      else if (e.key === 'Enter' && enabled && !typing) { e.preventDefault(); activate(); }
      else if (e.key === 'Escape') {
        enabled = false; idx = -1;
        document.body.classList.remove('wheel-mode');
        paint();
      }
    });

    // Touching the screen hands control back to the finger.
    window.addEventListener('pointerdown', () => {
      enabled = false;
      document.body.classList.remove('wheel-mode');
      document.querySelectorAll('.wheel-focus').forEach((e) => e.classList.remove('wheel-focus'));
    });

    new MutationObserver(() => { if (enabled) refresh(); })
      .observe(document.body, { childList: true, subtree: true });
  }

  window.Wheel = { refresh, move, activate, focusFirst, attachInput,
                   get enabled() { return enabled; } };
  window.addEventListener('DOMContentLoaded', attachInput);
})();
