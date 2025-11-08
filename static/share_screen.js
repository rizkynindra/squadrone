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
let manusiaLogs = [];

const humanDetectionAudio = new Audio('/audio/star_trek.mp3');
const MIN_DETECTION_INTERVAL = 10000; // ms between detection requests

toggleBoundingBoxButton.addEventListener('click', function() {
    showAllBoundingBoxes = !showAllBoundingBoxes;
    this.textContent = showAllBoundingBoxes ? 'Show Only "manusia"' : 'Show All';
});

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
            // Alarm logic: check for 'manusia' detection
            const manusiaDetected = result.detections && result.detections.some(d => d.class === 'manusia');
            if (manusiaDetected) {
                playAlarmFor3Seconds();
                document.getElementById('clearLogButton').disabled = false;
                document.getElementById('clearLogButton').addEventListener('click', function() {
                manusiaLogs = [];
                detectionResults.innerHTML = '<h3>Detection Results</h3><p>No manusia detected.</p>';
                this.disabled = true;
                });
            }
        } else {
            document.getElementById('clearLogButton').disabled = true;
            throw new Error(result.error || 'Detection failed');
        }

        // Enable/disable panic button based on human_detected flag
        const panicBtn = document.getElementById('panic-btn');
        if (panicBtn) {
            panicBtn.disabled = !result.human_detected;
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

// Alarm logic: always play for 3 seconds per detection
function playAlarmFor3Seconds() {
    if (alarmTimeoutId) return; // Prevent overlapping alarms

    humanAlarm.classList.add('alarm-active');
    humanDetectionAudio.currentTime = 0;
    humanDetectionAudio.play().catch(err => console.log('Audio play error:', err));

    alarmTimeoutId = setTimeout(() => {
        humanAlarm.classList.remove('alarm-active');
        humanDetectionAudio.pause();
        humanDetectionAudio.currentTime = 0;
        alarmTimeoutId = null;
    }, 1);
}

// Display detection results, focusing on 'manusia' class array version
function displayDetectionResults(result) {
    let html = '<h3>Detection Results</h3>';

    const manusiaDetections = result.detections
        ? result.detections.filter(detection => detection.class === 'manusia')
        : [];

    const now = new Date();
    const pad = n => n.toString().padStart(2, '0');
    const detection_time = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

    if (manusiaDetections.length) {
        manusiaDetections.forEach(detection => {
            const log = `Detected <strong>${detection.class} at ${detection_time} with confidence (${(detection.confidence * 100).toFixed(2)}%)</strong>`;
            manusiaLogs.push(log);
        });
    }

    if (manusiaLogs.length) {
        html += '<ul>';
        manusiaLogs.forEach(log => {
            html += `<li>${log}</li>`;
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

// Panic button handler
document.addEventListener('DOMContentLoaded', function() {
    const panicBtn = document.getElementById('panic-btn');
    if (panicBtn) {
        panicBtn.disabled = true;
        panicBtn.addEventListener('click', function() {
            fetch('/panic', { method: 'POST' })
                .then(res => res.json())
                .then(data => alert(data.message || data.error));
        });
    }
});

