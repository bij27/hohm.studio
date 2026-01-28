/**
 * Yoga Session Controller
 * Handles pose detection, matching, timing, and session flow
 */

class YogaSession {
    constructor() {
        this.poses = [];
        this.sessionQueue = [];
        this.currentPoseIndex = 0;
        this.currentPose = null;

        this.sessionDuration = 0;
        this.sessionElapsed = 0;
        this.poseTimeRemaining = 0;

        this.isRunning = false;
        this.isPaused = false;

        this.poseLandmarker = null;
        this.webcamRunning = false;
        this.lastVideoTime = -1;
        this.currentLandmarks = null;

        this.voiceEnabled = true;
        this.musicEnabled = false;
        this.lastFeedbackTime = 0;

        this.elements = {
            video: document.getElementById('webcam'),
            canvas: document.getElementById('landmark-overlay'),
            sessionTimer: document.getElementById('session-timer'),
            poseTimer: document.getElementById('pose-timer'),
            matchScore: document.getElementById('match-score'),
            feedbackMessage: document.getElementById('feedback-message'),
            poseName: document.getElementById('current-pose-name'),
            poseSanskrit: document.getElementById('current-pose-sanskrit'),
            poseInstructions: document.getElementById('pose-instructions'),
            poseQueue: document.getElementById('pose-queue'),
            sessionProgress: document.getElementById('session-progress'),
            loadingOverlay: document.getElementById('loading-overlay'),
            pauseBtn: document.getElementById('pause-btn'),
            endBtn: document.getElementById('end-btn'),
            soundToggle: document.getElementById('sound-toggle'),
            musicToggle: document.getElementById('music-toggle'),
            musicVolume: document.getElementById('music-volume')
        };

        this.init();
    }

    async init() {
        try {
            // Load pose data
            const response = await fetch('/static/data/yoga/poses.json');
            const data = await response.json();
            this.poses = data.poses;

            // Parse URL params
            const params = new URLSearchParams(window.location.search);
            const mode = params.get('mode') || 'ai';

            if (mode === 'custom') {
                const poseIds = params.get('poses')?.split(',') || [];
                this.sessionQueue = poseIds.map(id => this.poses.find(p => p.id === id)).filter(Boolean);
            } else {
                const duration = parseInt(params.get('duration')) || 30;
                const focus = params.get('focus') || 'all';
                this.sessionQueue = this.generateSession(duration, focus);
            }

            if (this.sessionQueue.length === 0) {
                alert('No poses available for this session');
                window.location.href = '/yoga';
                return;
            }

            // Calculate total session duration
            this.sessionDuration = this.sessionQueue.reduce((sum, pose) => sum + pose.duration_seconds[0], 0);

            // Initialize MediaPipe
            await this.initPoseDetection();

            // Start webcam
            await this.startWebcam();

            // Setup event listeners
            this.setupEventListeners();

            // Hide loading, start session
            this.elements.loadingOverlay.style.display = 'none';
            this.startSession();

        } catch (error) {
            console.error('Failed to initialize yoga session:', error);
            alert('Failed to start session. Please try again.');
            window.location.href = '/yoga';
        }
    }

    generateSession(durationMinutes, focus) {
        const totalSeconds = durationMinutes * 60;
        let availablePoses = [...this.poses];

        // Filter by focus if specified
        if (focus !== 'all') {
            availablePoses = availablePoses.filter(p => p.focus.includes(focus));
        }

        if (availablePoses.length === 0) {
            availablePoses = [...this.poses];
        }

        // Build session with warm-up, main, cool-down structure
        const session = [];
        let currentDuration = 0;

        // Categorize poses
        const beginnerPoses = availablePoses.filter(p => p.difficulty === 'beginner');
        const intermediatePoses = availablePoses.filter(p => p.difficulty === 'intermediate');
        const advancedPoses = availablePoses.filter(p => p.difficulty === 'advanced');

        // Warm-up (20% of session) - easier poses
        const warmupTarget = totalSeconds * 0.2;
        while (currentDuration < warmupTarget && beginnerPoses.length > 0) {
            const pose = beginnerPoses.splice(Math.floor(Math.random() * beginnerPoses.length), 1)[0];
            session.push({ ...pose, phase: 'warmup' });
            currentDuration += pose.duration_seconds[0];
        }

        // Main flow (60% of session) - mix of difficulties
        const mainTarget = totalSeconds * 0.8;
        const mainPoses = [...intermediatePoses, ...advancedPoses, ...beginnerPoses];
        while (currentDuration < mainTarget && mainPoses.length > 0) {
            const pose = mainPoses.splice(Math.floor(Math.random() * mainPoses.length), 1)[0];
            session.push({ ...pose, phase: 'main' });
            currentDuration += pose.duration_seconds[0];
        }

        // Cool-down (20% of session) - relaxing poses
        const cooldownPoses = availablePoses.filter(p =>
            p.focus.includes('relaxation') || p.category === 'seated'
        );
        while (currentDuration < totalSeconds && cooldownPoses.length > 0) {
            const pose = cooldownPoses.splice(Math.floor(Math.random() * cooldownPoses.length), 1)[0];
            session.push({ ...pose, phase: 'cooldown' });
            currentDuration += pose.duration_seconds[0];
        }

        return session;
    }

    async initPoseDetection() {
        const { PoseLandmarker, FilesetResolver } = window.tasksVision;

        const vision = await FilesetResolver.forVisionTasks(
            "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm"
        );

        this.poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
            baseOptions: {
                modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
                delegate: "GPU"
            },
            runningMode: "VIDEO",
            numPoses: 1
        });
    }

    async startWebcam() {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 1280, height: 720 }
        });
        this.elements.video.srcObject = stream;

        return new Promise((resolve) => {
            this.elements.video.onloadedmetadata = () => {
                this.elements.canvas.width = this.elements.video.videoWidth;
                this.elements.canvas.height = this.elements.video.videoHeight;
                resolve();
            };
        });
    }

    setupEventListeners() {
        this.elements.pauseBtn.addEventListener('click', () => this.togglePause());
        this.elements.endBtn.addEventListener('click', () => this.endSession());
        this.elements.soundToggle.addEventListener('click', () => this.toggleVoice());
        this.elements.musicToggle.addEventListener('click', () => this.toggleMusic());
        this.elements.musicVolume.addEventListener('input', (e) => this.setMusicVolume(e.target.value));
    }

    startSession() {
        this.isRunning = true;
        this.currentPoseIndex = 0;
        this.loadPose(0);
        this.updateQueueDisplay();
        this.runDetectionLoop();
        this.runTimerLoop();

        // Announce session start
        this.speak("Welcome to your yoga session. Let's begin.");
    }

    loadPose(index) {
        if (index >= this.sessionQueue.length) {
            this.completeSession();
            return;
        }

        this.currentPose = this.sessionQueue[index];
        this.poseTimeRemaining = this.currentPose.duration_seconds[0];

        // Update UI
        this.elements.poseName.textContent = this.currentPose.name;
        this.elements.poseSanskrit.textContent = this.currentPose.sanskrit;
        this.elements.poseInstructions.innerHTML = this.currentPose.instructions
            .map(inst => `<li>${inst}</li>`)
            .join('');

        this.updateQueueDisplay();

        // Announce pose
        this.speak(`${this.currentPose.name}. ${this.currentPose.instructions[0]}`);
    }

    updateQueueDisplay() {
        const queueHtml = this.sessionQueue.map((pose, i) => {
            let className = 'queue-item';
            if (i < this.currentPoseIndex) className += ' completed';
            if (i === this.currentPoseIndex) className += ' current';

            return `
                <div class="${className}">
                    <span>${pose.name}</span>
                    <span class="queue-duration">${pose.duration_seconds[0]}s</span>
                </div>
            `;
        }).join('');

        this.elements.poseQueue.innerHTML = queueHtml;
    }

    runDetectionLoop() {
        if (!this.isRunning) return;

        const video = this.elements.video;
        const canvas = this.elements.canvas;
        const ctx = canvas.getContext('2d');

        if (video.currentTime !== this.lastVideoTime && video.readyState >= 2) {
            this.lastVideoTime = video.currentTime;

            const results = this.poseLandmarker.detectForVideo(video, performance.now());

            // Clear canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (results.landmarks && results.landmarks.length > 0) {
                this.currentLandmarks = results.landmarks[0];

                // Draw landmarks
                this.drawLandmarks(ctx, this.currentLandmarks);

                // Calculate pose match
                const matchScore = this.calculatePoseMatch(this.currentLandmarks);
                this.elements.matchScore.textContent = `${Math.round(matchScore)}%`;

                // Update score color
                if (matchScore >= 80) {
                    this.elements.matchScore.style.color = '#7c9a92';
                } else if (matchScore >= 60) {
                    this.elements.matchScore.style.color = '#d4a574';
                } else {
                    this.elements.matchScore.style.color = '#c97b7b';
                }

                // Provide feedback if needed
                this.provideFeedback(matchScore);
            }
        }

        requestAnimationFrame(() => this.runDetectionLoop());
    }

    drawLandmarks(ctx, landmarks) {
        const { DrawingUtils } = window.tasksVision;
        const drawingUtils = new DrawingUtils(ctx);

        // Draw connections
        drawingUtils.drawConnectors(
            landmarks,
            PoseLandmarker.POSE_CONNECTIONS,
            { color: '#7c9a92', lineWidth: 2 }
        );

        // Draw landmarks
        drawingUtils.drawLandmarks(landmarks, {
            color: '#a8c5be',
            lineWidth: 1,
            radius: 4
        });
    }

    calculatePoseMatch(userLandmarks) {
        if (!this.currentPose || !this.currentPose.reference_angles) {
            return 0;
        }

        const refAngles = this.currentPose.reference_angles;
        const userAngles = this.calculateAngles(userLandmarks);

        let totalDiff = 0;
        let angleCount = 0;

        for (const [key, refAngle] of Object.entries(refAngles)) {
            if (refAngle !== null && userAngles[key] !== undefined) {
                // Normalize angle difference (handle wrap-around)
                let diff = Math.abs(refAngle - userAngles[key]);
                if (diff > 180) diff = 360 - diff;

                totalDiff += diff;
                angleCount++;
            }
        }

        if (angleCount === 0) return 0;

        // Convert to percentage (0 diff = 100%, 90 diff = 0%)
        const avgDiff = totalDiff / angleCount;
        const score = Math.max(0, 100 - (avgDiff / 90 * 100));

        return score;
    }

    calculateAngles(landmarks) {
        const getAngle = (a, b, c) => {
            const radians = Math.atan2(c.y - b.y, c.x - b.x) - Math.atan2(a.y - b.y, a.x - b.x);
            let angle = Math.abs(radians * 180 / Math.PI);
            if (angle > 180) angle = 360 - angle;
            return angle;
        };

        // MediaPipe landmark indices
        const LEFT_SHOULDER = 11, RIGHT_SHOULDER = 12;
        const LEFT_ELBOW = 13, RIGHT_ELBOW = 14;
        const LEFT_WRIST = 15, RIGHT_WRIST = 16;
        const LEFT_HIP = 23, RIGHT_HIP = 24;
        const LEFT_KNEE = 25, RIGHT_KNEE = 26;
        const LEFT_ANKLE = 27, RIGHT_ANKLE = 28;

        return {
            left_elbow_angle: getAngle(landmarks[LEFT_SHOULDER], landmarks[LEFT_ELBOW], landmarks[LEFT_WRIST]),
            right_elbow_angle: getAngle(landmarks[RIGHT_SHOULDER], landmarks[RIGHT_ELBOW], landmarks[RIGHT_WRIST]),
            left_shoulder_angle: getAngle(landmarks[LEFT_ELBOW], landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP]),
            right_shoulder_angle: getAngle(landmarks[RIGHT_ELBOW], landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP]),
            left_knee_angle: getAngle(landmarks[LEFT_HIP], landmarks[LEFT_KNEE], landmarks[LEFT_ANKLE]),
            right_knee_angle: getAngle(landmarks[RIGHT_HIP], landmarks[RIGHT_KNEE], landmarks[RIGHT_ANKLE]),
            left_hip_angle: getAngle(landmarks[LEFT_SHOULDER], landmarks[LEFT_HIP], landmarks[LEFT_KNEE]),
            right_hip_angle: getAngle(landmarks[RIGHT_SHOULDER], landmarks[RIGHT_HIP], landmarks[RIGHT_KNEE])
        };
    }

    provideFeedback(matchScore) {
        const now = Date.now();
        if (now - this.lastFeedbackTime < 5000) return; // Throttle feedback

        if (matchScore < 50) {
            this.showFeedback("Try to match the pose more closely");
            this.speak("Adjust your position");
            this.lastFeedbackTime = now;
        } else if (matchScore >= 80 && this.poseTimeRemaining > 5) {
            // Good match feedback occasionally
            if (Math.random() < 0.1) {
                this.speak("Great form!");
            }
        }
    }

    showFeedback(message) {
        this.elements.feedbackMessage.textContent = message;
        this.elements.feedbackMessage.style.display = 'block';
        setTimeout(() => {
            this.elements.feedbackMessage.style.display = 'none';
        }, 3000);
    }

    runTimerLoop() {
        if (!this.isRunning) return;

        setInterval(() => {
            if (this.isPaused) return;

            // Update session timer
            this.sessionElapsed++;
            this.elements.sessionTimer.textContent = this.formatTime(this.sessionElapsed);

            // Update progress bar
            const progress = (this.sessionElapsed / this.sessionDuration) * 100;
            this.elements.sessionProgress.style.width = `${Math.min(100, progress)}%`;

            // Update pose timer
            this.poseTimeRemaining--;
            this.elements.poseTimer.textContent = `0:${String(Math.max(0, this.poseTimeRemaining)).padStart(2, '0')}`;

            // Countdown announcements
            if (this.poseTimeRemaining === 10) {
                this.speak("10 seconds remaining");
            } else if (this.poseTimeRemaining === 3) {
                this.speak("3, 2, 1");
            }

            // Move to next pose
            if (this.poseTimeRemaining <= 0) {
                this.currentPoseIndex++;
                this.loadPose(this.currentPoseIndex);
            }
        }, 1000);
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    togglePause() {
        this.isPaused = !this.isPaused;
        this.elements.pauseBtn.textContent = this.isPaused ? 'Resume' : 'Pause';
        if (this.isPaused) {
            this.speak("Session paused");
        } else {
            this.speak("Session resumed");
        }
    }

    toggleVoice() {
        this.voiceEnabled = !this.voiceEnabled;
        this.elements.soundToggle.classList.toggle('active', this.voiceEnabled);
    }

    toggleMusic() {
        this.musicEnabled = !this.musicEnabled;
        this.elements.musicToggle.classList.toggle('active', this.musicEnabled);
        // TODO: Implement actual music playback
    }

    setMusicVolume(value) {
        // TODO: Implement volume control
        console.log('Music volume:', value);
    }

    speak(text) {
        if (!this.voiceEnabled) return;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        speechSynthesis.speak(utterance);
    }

    endSession() {
        if (confirm('End this session early?')) {
            this.isRunning = false;
            window.location.href = '/yoga';
        }
    }

    completeSession() {
        this.isRunning = false;
        this.speak("Congratulations! You've completed your yoga session. Namaste.");

        setTimeout(() => {
            alert('Session complete! Great job!');
            window.location.href = '/yoga';
        }, 2000);
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    new YogaSession();
});
