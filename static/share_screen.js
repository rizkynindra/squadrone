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

let mediaStream = null;
let capturedFrame = null;
let detectionActive = false;
let detectionInProgress = false;
let animationFrameId = null;
let lastDetectionTime = 0;
let frameCount = 0;
let lastFpsUpdateTime = 0;
let alarmActive = false;

// Add this line for the alarm sound
const humanDetectionAudio = new Audio('/audio/Danger Alarm.mp3');
// Detection throttle settings
const MIN_DETECTION_INTERVAL = 100; // ms between detection requests

startButton.addEventListener('click', async () => {
    try {
        statusElement.textContent = 'Requesting screen access...';

        // Request screen capture
        mediaStream = await navigator.mediaDevices.getDisplayMedia({
            video: {
                cursor: "always"
            },
            audio: false
        });

        // Connect the media stream to the video element
        screenVideo.srcObject = mediaStream;

        // Wait for video to be loaded
        screenVideo.onloadedmetadata = () => {
            // Set canvas dimensions to match video
            detectionCanvas.width = screenVideo.videoWidth;
            detectionCanvas.height = screenVideo.videoHeight;
        };

        // Enable buttons
        startButton.disabled = true;
        stopButton.disabled = false;
        startDetectionButton.disabled = false;

        statusElement.textContent = 'Screen sharing active';

        // Listen for the end of stream
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
    statusElement.textContent = 'Real-time detection active';

    // Start the detection loop
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

    // Reset alarm
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

    // Draw the current video frame on a temporary canvas
    ctx.drawImage(screenVideo, 0, 0, canvas.width, canvas.height);

    // Store the captured frame as data URL - use lower quality for better performance
    capturedFrame = canvas.toDataURL('image/jpeg', 0.7);
    return true;
}

async function detectObjects() {
    if (!capturedFrame || detectionInProgress) {
        return;
    }

    try {
        detectionInProgress = true;

        // Send the captured frame to your Flask backend
        const response = await fetch('/detect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image: capturedFrame
            })
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
            // Display detection results
            displayDetectionResults(result);

            // Store the latest detections to be drawn in the detectLoop
            latestDetections = result.detections;

            // Check alarm status from server
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

// Add a global variable to store latest detections
let latestDetections = [];

function detectLoop() {
    if (!detectionActive) return;

    // Calculate FPS
    frameCount++;
    const now = performance.now();
    const elapsed = now - lastFpsUpdateTime;

    if (elapsed >= 1000) { // Update FPS once per second
        const fps = Math.round((frameCount / elapsed) * 1000);
        fpsCounter.textContent = `${fps} FPS`;
        frameCount = 0;
        lastFpsUpdateTime = now;
    }

    // Clear canvas and update the video display
    const ctx = detectionCanvas.getContext('2d');
    ctx.clearRect(0, 0, detectionCanvas.width, detectionCanvas.height);
    ctx.drawImage(screenVideo, 0, 0, detectionCanvas.width, detectionCanvas.height);

    // Draw detection boxes from the latest results
    if (latestDetections && latestDetections.length) {
        drawDetectionBoxes(latestDetections);
    }

    // Check if we should send a new detection request
    if (!detectionInProgress && now - lastDetectionTime >= MIN_DETECTION_INTERVAL) {
        if (captureVideoFrame()) {
            lastDetectionTime = now;
            detectObjects();
        }
    }

    // Continue the loop
    animationFrameId = requestAnimationFrame(detectLoop);
}

// Add function to handle alarm status
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
    alarmActive = true;
    humanAlarm.classList.add('alarm-active');

    // Play alarm sound
    humanDetectionAudio.play().catch(err => console.log('Audio play error:', err));
}

function resetAlarm() {
    alarmActive = false;
    humanAlarm.classList.remove('alarm-active');
    humanDetectionAudio.pause();
    humanDetectionAudio.currentTime = 0;

    // Reset on server side too
    fetch('/reset_alarm', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    }).catch(err => console.log('Error resetting alarm on server:', err));
}

function displayDetectionResults(result) {
    let html = '<h3>Detection Results</h3>';

    if (result.detections && result.detections.length) {
        html += '<ul>';
        result.detections.forEach(detection => {
            html += `<li>${detection.class} (${(detection.confidence * 100).toFixed(2)}%)</li>`;
        });
        html += '</ul>';
    } else {
        html += '<p>No objects detected.</p>';
    }

    detectionResults.innerHTML = html;
}

function drawDetectionBoxes(detections) {
    if (!detections || !detections.length) return;

    const canvas = detectionCanvas;
    const ctx = canvas.getContext('2d');

    // Draw detection boxes
    detections.forEach(detection => {
        const { box, class: className, confidence } = detection;
        const [x1, y1, x2, y2] = box;

        ctx.strokeStyle = 'lime';
        ctx.lineWidth = 3;
        ctx.strokeRect(x1, y1, x2-x1, y2-y1);

        // Draw label
        ctx.fillStyle = 'lime';
        ctx.font = '16px Arial';
        const label = `${className} ${(confidence * 100).toFixed(1)}%`;
        const textWidth = ctx.measureText(label).width;

        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(x1, y1 - 25, textWidth + 10, 25);

        ctx.fillStyle = 'white';
        ctx.fillText(label, x1 + 5, y1 - 7);
    });
}
