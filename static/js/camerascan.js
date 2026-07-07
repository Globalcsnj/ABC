// Phone/webcam barcode scanning using the browser's built-in BarcodeDetector.
// Calls window.onCameraScan(code) for each new barcode read.
(function () {
    let stream = null, running = false, lastCode = '', lastTime = 0;

    async function start() {
        if (!('BarcodeDetector' in window)) {
            alert("This browser can't scan with the camera. Use Chrome on Android, " +
                  "or type/scan with the USB scanner. (You can still use 'Choose File'.)");
            return;
        }
        const modal = document.createElement('div');
        modal.className = 'camera-modal';
        modal.innerHTML = `
            <div class="camera-box">
                <video autoplay playsinline class="camera-video"></video>
                <div class="scan-reticle"></div>
                <div class="camera-scan-status" id="camScanStatus">Point at a barcode…</div>
                <div class="camera-actions">
                    <button type="button" class="btn btn-outline" data-act="close">Done</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        const video = modal.querySelector('video');
        const status = modal.querySelector('#camScanStatus');

        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
            video.srcObject = stream;
        } catch (err) {
            status.textContent = 'Could not open camera: ' + err.message;
            return;
        }

        const detector = new BarcodeDetector({
            formats: ['code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e', 'itf', 'codabar']
        });
        running = true;

        async function tick() {
            if (!running) return;
            try {
                const codes = await detector.detect(video);
                if (codes.length) {
                    const code = codes[0].rawValue;
                    const now = Date.now();
                    // Ignore repeats of the same code within 2.5s
                    if (code && (code !== lastCode || now - lastTime > 2500)) {
                        lastCode = code; lastTime = now;
                        status.textContent = '✓ ' + code;
                        if (navigator.vibrate) navigator.vibrate(80);
                        if (window.onCameraScan) window.onCameraScan(code);
                    }
                }
            } catch (e) { /* keep going */ }
            requestAnimationFrame(tick);
        }
        tick();

        modal.addEventListener('click', (e) => {
            if (e.target.dataset.act === 'close' || e.target === modal) stop(modal);
        });
    }

    function stop(modal) {
        running = false;
        if (stream) stream.getTracks().forEach(t => t.stop());
        if (modal) modal.remove();
    }

    window.startCameraScan = start;
})();
