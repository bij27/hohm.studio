import {
    PoseLandmarker,
    FilesetResolver,
    DrawingUtils
} from "https://cdn.skypack.dev/@mediapipe/tasks-vision@0.10.0";

const webcamElement = document.getElementById('webcam');
const startBtn = document.getElementById('start-cal-btn');
const countdownEl = document.getElementById('countdown');
const progressBar = document.getElementById('progress-bar');
const statusMsg = document.getElementById('status-msg');
const overlayCanvas = document.getElementById('landmark-overlay');
const overlayCtx = overlayCanvas.getContext('2d');

let isCalibrating = false;
let calibrationFrames = 0;
const TOTAL_FRAMES = 30; // 30 frames for a solid profile
let calSocket = null;
let poseLandmarker = undefined;
let animationFrameId = null;

async function initMediaPipe() {
    const vision = await FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm"
    );
    poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
        baseOptions: {
            modelAssetPath: `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`,
            delegate: "GPU"
        },
        runningMode: "VIDEO",
        numPoses: 1
    });
    console.log("Pose Landmarker Initialized");
}

async function setupWebcam() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { width: 1280, height: 720 } 
        });
        webcamElement.srcObject = stream;
        webcamElement.onloadedmetadata = () => {
            overlayCanvas.width = webcamElement.videoWidth;
            overlayCanvas.height = webcamElement.videoHeight;
        };
        return true;
    } catch (err) {
        console.error("Error accessing webcam:", err);
        return false;
    }
}

function connectWS() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    calSocket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    
    calSocket.onopen = () => {
        startBtn.disabled = false;
        startBtn.innerHTML = '<i data-lucide="target" style="margin-right: 8px;"></i>Start Calibration';
        statusMsg.innerText = "Ready to calibrate";
        if (window.lucide) window.lucide.createIcons();
    };

    calSocket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'calibration_progress') {
            updateProgress(message.data.count);
        } else if (message.type === 'calibration_complete') {
            onCalibrationComplete(message.data.profile);
        } else if (message.type === 'calibration_warning') {
            statusMsg.innerText = message.data.message;
            statusMsg.style.color = 'var(--color-bad)';
        }
    };
}

function updateProgress(count) {
    calibrationFrames = count;
    const pct = (count / TOTAL_FRAMES) * 100;
    progressBar.style.width = `${pct}%`;
}

function drawLandmarks(results) {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    if (!results.landmarks || results.landmarks.length === 0) return;

    const landmarks = results.landmarks[0];
    const w = overlayCanvas.width;
    const h = overlayCanvas.height;

    overlayCtx.strokeStyle = "#00FF00";
    overlayCtx.lineWidth = 2;
    // Simple drawing for calibration
    landmarks.forEach(p => {
        if (p.visibility > 0.5) {
            overlayCtx.beginPath();
            overlayCtx.arc(p.x * w, p.y * h, 3, 0, 2 * Math.PI);
            overlayCtx.fill();
        }
    });
}

async function startCalibration() {
    if (isCalibrating) return;
    isCalibrating = true;
    startBtn.disabled = true;
    
    for (let i = 3; i > 0; i--) {
        countdownEl.innerText = i;
        await new Promise(r => setTimeout(r, 1000));
    }
    countdownEl.innerText = 'GO!';
    setTimeout(() => countdownEl.innerText = '', 1000);

    let lastSendTime = 0;
    const SEND_INTERVAL = 100; // 10 fps for calibration

    const predict = () => {
        if (!isCalibrating) return;

        const results = poseLandmarker.detectForVideo(webcamElement, performance.now());
        drawLandmarks(results);

        if (results.landmarks && results.landmarks.length > 0 && performance.now() - lastSendTime > SEND_INTERVAL) {
            const simpleLandmarks = {};
            results.landmarks[0].forEach((lm, idx) => {
                simpleLandmarks[idx] = { x: lm.x, y: lm.y, z: lm.z, visibility: lm.visibility };
            });

            calSocket.send(JSON.stringify({
                action: 'calibrate_landmarks',
                landmarks: simpleLandmarks
            }));
            lastSendTime = performance.now();
        }

        animationFrameId = requestAnimationFrame(predict);
    };
    predict();
}

function onCalibrationComplete(profile) {
    isCalibrating = false;
    cancelAnimationFrame(animationFrameId);
    statusMsg.innerText = 'Calibration Complete! Saving...';
    
    fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile)
    }).then(() => {
        window.location.href = '/monitor';
    });
}

startBtn.addEventListener('click', startCalibration);

(async () => {
    const pyReady = await setupWebcam();
    if (pyReady) {
        statusMsg.innerText = "Loading AI models...";
        await initMediaPipe();
        connectWS();
    }
})();
