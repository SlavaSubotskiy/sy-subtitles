// Mock Vimeo Player SDK for E2E testing.
// Intercepts the real player.js and provides controllable time simulation.
window.Vimeo = {
  Player: class {
    constructor(element) {
      this._currentTime = 0;
      this._callbacks = {};
      // Replace the iframe with a visible div that honors the real CSS
      // layout around it (width/height inherited via 100% from the mount).
      // A tiny min-height keeps the mock reachable even when the mount
      // point has collapsed due to a layout bug — but tests that assert
      // on dimensions can still detect the collapse.
      var div = document.createElement('div');
      div.id = 'mock-player';
      div.style.cssText = 'width:100%;height:100%;min-height:40px;background:#222;display:flex;align-items:center;justify-content:center;color:#666;font-size:14px;';
      div.textContent = 'Mock Vimeo Player';
      if (element && element.parentNode) {
        // Do NOT override the parent's inline style — let CSS decide the
        // box so regressions in layout surface through the mock.
        element.parentNode.replaceChild(div, element);
      } else {
        document.body.appendChild(div);
      }
      window._vimeoPlayer = this;
    }
    ready() { return Promise.resolve(); }
    pause() { this._paused = true; return Promise.resolve(); }
    play() { this._paused = false; return Promise.resolve(); }
    getPaused() { return Promise.resolve(this._paused !== false); }
    setCurrentTime(sec) { this._currentTime = sec; return Promise.resolve(); }
    on(event, callback) {
      this._callbacks[event] = this._callbacks[event] || [];
      this._callbacks[event].push(callback);
    }
    getCurrentTime() { return Promise.resolve(this._currentTime); }
    // Test helper: set time and fire timeupdate
    _setTime(seconds) {
      this._currentTime = seconds;
      var cbs = this._callbacks['timeupdate'] || [];
      for (var i = 0; i < cbs.length; i++) {
        cbs[i]({ seconds: seconds, duration: 3600 });
      }
    }
  }
};
