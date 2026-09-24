// In-page replacements for window.confirm / window.alert.
//
// Native dialogs are unreliable once the page has requested fullscreen (the
// kiosk does, on the first tap): depending on the browser they can be
// suppressed, appear off-screen, or exit fullscreen. This modal lives inside
// the page itself, so it always renders on top of the fullscreen document.
//
//   ttvConfirm(message, { confirmLabel, cancelLabel }) -> Promise<boolean>
//   ttvAlert(message, { confirmLabel })                -> Promise<void>
(function () {
  if (window.ttvConfirm) return; // loaded more than once (wizard + kiosk shell): keep the first

  function open(message, opts) {
    const options = Object.assign({ confirmLabel: 'OK', cancelLabel: 'Cancel', showCancel: true }, opts);

    return new Promise((resolve) => {
      const previouslyFocused = document.activeElement;

      const overlay = document.createElement('div');
      overlay.className = 'ttv-dialog-overlay';

      const box = document.createElement('div');
      box.className = 'ttv-dialog';
      box.setAttribute('role', options.showCancel ? 'dialog' : 'alertdialog');
      box.setAttribute('aria-modal', 'true');

      const text = document.createElement('p');
      text.className = 'ttv-dialog-message';
      text.textContent = message;
      box.appendChild(text);

      const actions = document.createElement('div');
      actions.className = 'ttv-dialog-actions';

      let cancelBtn = null;
      if (options.showCancel) {
        cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'big-btn ttv-dialog-cancel';
        cancelBtn.textContent = options.cancelLabel;
        actions.appendChild(cancelBtn);
      }

      const confirmBtn = document.createElement('button');
      confirmBtn.type = 'button';
      confirmBtn.className = 'big-btn';
      confirmBtn.textContent = options.confirmLabel;
      actions.appendChild(confirmBtn);

      box.appendChild(actions);
      overlay.appendChild(box);

      function close(result) {
        document.removeEventListener('keydown', onKey, true);
        overlay.remove();
        if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
        resolve(result);
      }

      function onKey(e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          close(false);
        }
      }

      confirmBtn.addEventListener('click', () => close(true));
      if (cancelBtn) cancelBtn.addEventListener('click', () => close(false));
      // Tapping the dim backdrop counts as cancel (never as confirm).
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close(false);
      });
      document.addEventListener('keydown', onKey, true);

      // Appended to <body>, which sits inside the fullscreen <html> element.
      document.body.appendChild(overlay);
      // Default focus goes to the safe choice so a stray Enter can't lock in.
      (cancelBtn || confirmBtn).focus();
    });
  }

  window.ttvConfirm = (message, opts) => open(message, Object.assign({}, opts, { showCancel: true }));
  window.ttvAlert = (message, opts) => open(message, Object.assign({}, opts, { showCancel: false })).then(() => undefined);
})();
