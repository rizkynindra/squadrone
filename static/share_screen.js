const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const startDetectionButton = document.getElementById('startDetectionButton');
const pauseDetectionButton = document.getElementById('pauseDetectionButton');
const screenVideo = document.getElementById('screenVideo');
const statusElement = document.getElementById('status');
const detectionCanvas = document.getElementById('detectionCanvas');
const detectionResults = document.getElementById('detectionResults');
const fpsCounter = document.getElementById('fpsCounter');
const humanAlarm = document.getElementById('humanAlarm');
const toggleBoundingBoxButton = document.getElementById('toggleBoundingBoxButton');

let mediaStream = null;
let capturedFrame = null;
let detectionActive = false;
let detectionInProgress = false;
let animationFrameId = null;
let lastDetectionTime = 0;
let frameCount = 0;
let lastFpsUpdateTime = 0;
let alarmActive = false;
let alarmTimeoutId = null;
let showAllBoundingBoxes = false;
let latestDetections = [];

toggleBoundingBoxButton.addEventListener('click', function() {
    showAllBoundingBoxes = !showAllBoundingBoxes;
    this.textContent = showAllBoundingBoxes ? 'Show Only "manusia"' : 'Show All';
});

const humanDetectionAudio = new Audio('/audio/Danger Alarm.mp3');
const MIN_DETECTION_INTERVAL = 100; // ms between detection requests

startButton.addEventListener('click', async () => {
    try {
        statusElement.textContent = 'Requesting screen access...';

        mediaStream = await navigator.mediaDevices.getDisplayMedia({
            video: { cursor: "always" },
            audio: false
        });

        screenVideo.srcObject = mediaStream;

        screenVideo.onloadedmetadata = () => {
            detectionCanvas.width = screenVideo.videoWidth;
            detectionCanvas.height = screenVideo.videoHeight;
        };

        startButton.disabled = true;
        stopButton.disabled = false;
        startDetectionButton.disabled = false;
        toggleBoundingBoxButton.disabled = false;

        statusElement.textContent = 'Screen sharing active';

        mediaStream.getVideoTracks()[0].addEventListener('ended', () => {
            stopScreenSharing();
        });

    } catch (error) {
        console.error('Error accessing screen:', error);
        statusElement.textContent = `Error: ${error.message || 'Could not access screen'}`;
    }
});

stopButton.addEventListener('click', stopScreenSharing);

function stopScreenSharing() {
    stopDetection();

    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        screenVideo.srcObject = null;
    }

    startButton.disabled = false;
    stopButton.disabled = true;
    startDetectionButton.disabled = true;
    pauseDetectionButton.disabled = true;
    toggleBoundingBoxButton.disabled = true;
    statusElement.textContent = 'Screen sharing stopped';
}

startDetectionButton.addEventListener('click', startDetection);
pauseDetectionButton.addEventListener('click', pauseDetection);

function startDetection() {
    if (!screenVideo.srcObject) {
        statusElement.textContent = 'No video stream available';
        return;
    }

    detectionActive = true;
    startDetectionButton.disabled = true;
    pauseDetectionButton.disabled = false;
    toggleBoundingBoxButton.disabled = false;
    statusElement.textContent = 'Real-time detection active';

    lastFpsUpdateTime = performance.now();
    frameCount = 0;
    detectLoop();
}

function pauseDetection() {
    detectionActive = false;
    startDetectionButton.disabled = false;
    pauseDetectionButton.disabled = true;
    statusElement.textContent = 'Detection paused';

    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }

    if (alarmActive) {
        resetAlarm();
    }
}

function stopDetection() {
    detectionActive = false;
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
}

function captureVideoFrame() {
    if (!screenVideo.srcObject) {
        return false;
    }

    const canvas = document.createElement('canvas');
    canvas.width = detectionCanvas.width;
    canvas.height = detectionCanvas.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(screenVideo, 0, 0, canvas.width, canvas.height);
    capturedFrame = canvas.toDataURL('image/jpeg', 0.7);
    return true;
}

async function detectObjects() {
    if (!capturedFrame || detectionInProgress) {
        return;
    }

    try {
        detectionInProgress = true;

        const response = await fetch('/detect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: capturedFrame })
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
            displayDetectionResults(result);
            latestDetections = result.detections;
            handleAlarmStatus(result.alarm);
        } else {
            throw new Error(result.error || 'Detection failed');
        }

    } catch (error) {
        console.error('Error in detection:', error);
        statusElement.textContent = `Error: ${error.message}`;
    } finally {
        detectionInProgress = false;
    }
}

function detectLoop() {
    if (!detectionActive) return;

    frameCount++;
    const now = performance.now();
    const elapsed = now - lastFpsUpdateTime;

    if (elapsed >= 1000) {
        const fps = Math.round((frameCount / elapsed) * 1000);
        fpsCounter.textContent = `${fps} FPS`;
        frameCount = 0;
        lastFpsUpdateTime = now;
    }

    const ctx = detectionCanvas.getContext('2d');
    ctx.clearRect(0, 0, detectionCanvas.width, detectionCanvas.height);
    ctx.drawImage(screenVideo, 0, 0, detectionCanvas.width, detectionCanvas.height);

    if (latestDetections && latestDetections.length) {
        drawDetectionBoxes(latestDetections);
    }

    if (!detectionInProgress && now - lastDetectionTime >= MIN_DETECTION_INTERVAL) {
        if (captureVideoFrame()) {
            lastDetectionTime = now;
            detectObjects();
        }
    }

    animationFrameId = requestAnimationFrame(detectLoop);
}

function handleAlarmStatus(alarmStatus) {
    if (alarmStatus.active) {
        if (!alarmActive) {
            triggerAlarm();
        }
    } else {
        if (alarmActive) {
            resetAlarm();
        }
    }
}

function triggerAlarm() {
    if (alarmActive) return;
    alarmActive = true;
    humanAlarm.classList.add('alarm-active');
    humanDetectionAudio.currentTime = 0;
    humanDetectionAudio.play().catch(err => console.log('Audio play error:', err));

    // stop alarm after 3 seconds
    if (alarmTimeoutId) clearTimeout(alarmTimeoutId);
    alarmTimeoutId = setTimeout(() => {
        resetAlarm();
    }, 3000);
}

function resetAlarm() {
    alarmActive = false;
    humanAlarm.classList.remove('alarm-active');
    humanDetectionAudio.pause();
    humanDetectionAudio.currentTime = 0;
    if (alarmTimeoutId) {
        clearTimeout(alarmTimeoutId);
        alarmTimeoutId = null;
    }

    fetch('/reset_alarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    }).catch(err => console.log('Error resetting alarm on server:', err));
}

function displayDetectionResults(result) {
    let html = '<h3>Detection Results</h3>';

    const manusiaDetections = result.detections
        ? result.detections.filter(detection => detection.class === 'manusia')
        : [];

    const now = new Date();
    const pad = n => n.toString().padStart(2, '0');
    const detection_time = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;


    if (manusiaDetections.length) {
        html += '<ul>';
        manusiaDetections.forEach(detection => {
            html += `Detected <strong>${detection.class} at ${detection_time} with confidence (${(detection.confidence * 100).toFixed(2)}%)</strong>`;
        });
        html += '</ul>';
    } else {
        html += '<p>No manusia detected.</p>';
    }

    detectionResults.innerHTML = html;
}

function drawDetectionBoxes(detections) {
    if (!detections || !detections.length) return;

    const canvas = detectionCanvas;
    const ctx = canvas.getContext('2d');

    detections.forEach(detection => {
        if (showAllBoundingBoxes || detection.class === 'manusia') {
            const { box, class: className, confidence } = detection;
            const [x1, y1, x2, y2] = box;

            ctx.strokeStyle = 'lime';
            ctx.lineWidth = 3;
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

            ctx.font = '16px Arial';
            const label = `${className} ${(confidence * 100).toFixed(1)}%`;
            const textWidth = ctx.measureText(label).width;

            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.fillRect(x1, y1 - 25, textWidth + 10, 25);

            ctx.fillStyle = 'white';
            ctx.fillText(label, x1 + 5, y1 - 7);
        }
    });
}