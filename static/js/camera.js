// Enhances any <input type="file" class="photo-input"> with a "Take Photo"
// button that captures from the webcam and drops the image into the input.
(function () {
    function enhance(input) {
        if (input.dataset.cameraReady) return;
        input.dataset.cameraReady = "1";

        const wrap = document.createElement('div');
        wrap.className = 'camera-wrap';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-outline btn-sm';
        btn.textContent = '📷 Take Photo';

        const preview = document.createElement('img');
        preview.className = 'camera-preview';
        preview.style.display = 'none';

        input.after(wrap);
        wrap.appendChild(btn);
        wrap.appendChild(preview);

        // Show a preview when a file is picked normally too
        input.addEventListener('change', () => {
            if (input.files && input.files[0]) {
                preview.src = URL.createObjectURL(input.files[0]);
                preview.style.display = 'block';
            }
        });

        btn.addEventListener('click', () => openCamera(input, preview));
    }

    function openCamera(input, preview) {
        const modal = document.createElement('div');
        modal.className = 'camera-modal';
        modal.innerHTML = `
            <div class="camera-box">
                <video autoplay playsinline class="camera-video"></video>
                <div class="camera-actions">
                    <button type="button" class="btn btn-primary" data-act="shoot">📸 Capture</button>
                    <button type="button" class="btn btn-outline" data-act="cancel">Cancel</button>
                </div>
                <div class="camera-error" style="display:none"></div>
            </div>`;
        document.body.appendChild(modal);

        const video = modal.querySelector('video');
        const errBox = modal.querySelector('.camera-error');
        let stream = null;

        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
            .then(s => { stream = s; video.srcObject = s; })
            .catch(err => {
                errBox.style.display = 'block';
                errBox.textContent = 'Could not open camera: ' + err.message +
                    '. You can still use "Choose File" to upload a photo.';
            });

        function close() {
            if (stream) stream.getTracks().forEach(t => t.stop());
            modal.remove();
        }

        modal.addEventListener('click', (e) => {
            const act = e.target.dataset.act;
            if (act === 'cancel' || e.target === modal) { close(); return; }
            if (act === 'shoot') {
                const canvas = document.createElement('canvas');
                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 480;
                canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
                canvas.toBlob(blob => {
                    const file = new File([blob], 'camera-photo.jpg', { type: 'image/jpeg' });
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    input.files = dt.files;
                    preview.src = URL.createObjectURL(blob);
                    preview.style.display = 'block';
                    close();
                }, 'image/jpeg', 0.9);
            }
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('input.photo-input').forEach(enhance);
    });
})();
