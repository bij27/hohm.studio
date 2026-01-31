/**
 * Yoga Session Controller v3
 * Unified Flow Model with server-side manifests, skeleton interpolation,
 * bilateral symmetry, and synchronized state machine.
 */

// Session states for the unified flow model
const SessionState = {
    LOADING: 'loading',
    CALIBRATING: 'calibrating',
    COUNTDOWN: 'countdown',
    // Per-segment states
    INSTRUCTIONS: 'instructions',
    TRANSITIONING: 'transitioning',
    ESTABLISHING: 'establishing',
    ACTIVE_HOLD: 'active',  // Keep 'active' for backwards compatibility
    // Session-level
    PAUSED: 'paused',
    COMPLETE: 'complete',
    // Legacy states (for backwards compatibility)
    INTRO: 'intro',
    POSITIONING: 'positioning',
    TRANSITION: 'transition'
};

class YogaSession {
    constructor() {
        this.poses = [];
        this.sessionQueue = [];
        this.currentPoseIndex = 0;
        this.currentPose = null;

        // === NEW: Manifest-based session ===
        this.manifest = null;
        this.currentSegmentIndex = 0;
        this.currentSegment = null;
        this.useManifest = false;  // Flag to use new manifest system

        // === NEW: Interpolation ===
        this.interpolator = null;
        this.ghostRenderer = null;
        this.interpolationManager = null;

        // Timing
        this.sessionDuration = 0;
        this.sessionElapsed = 0;
        this.poseTimeRemaining = 0;
        this.poseTimeTotal = 0;
        this.goodFormTime = 0;
        this.matchScore = 0;

        // === NEW: Segment timing ===
        this.segmentState = SessionState.LOADING;
        this.establishingStartTime = null;
        this.establishingTimeoutMs = 10000;
        this.formMatchThreshold = 0.45;

        // State
        this.state = 'loading'; // loading, calibrating, countdown, active, paused, complete
        this.isFormGood = false;

        // Form quality tracking for end grade
        this.formTimeTracking = {
            perfect: 0,    // 85%+
            good: 0,       // 70-85%
            okay: 0,       // 50-70%
            needsWork: 0   // <50%
        };
        this.currentFormLevel = 'needsWork';

        // Per-pose performance tracking for session report
        this.posePerformance = [];
        this.currentPoseFormTime = {
            perfect: 0,
            good: 0,
            okay: 0,
            needsWork: 0
        };

        // Variation tracking - tracks which variation user matches best
        this.currentMatchedVariation = null;  // { id, name, matchCount }
        this.variationMatchCounts = {};       // { variationId: frameCount }

        this.introPlayed = false;
        this.poseTimerStarted = false;
        this.instructionTimeRemaining = 0;
        this.instructionTimerActive = false;
        this.audioComplete = false;
        this.formCalibrated = false;

        // Pose detection
        this.poseLandmarker = null;
        this.lastVideoTime = -1;
        this.currentLandmarks = null;
        this.smoothedLandmarks = null;
        this.smoothingFactor = 0.25; // Match posture system: 25% new data, 75% old - smoother tracking

        // Target pose smoothing
        this.smoothedTargetPosition = null;
        this.targetSmoothingFactor = 0.15; // Even smoother for target overlay (less responsive, more stable)
        this.targetPoseWarmupFrames = 0;   // Warmup counter - require stable frames before showing skeleton
        this.audioUnlocked = false;        // Track if audio has been unlocked by user gesture

        // Settings
        this.voiceEnabled = true;
        this.ambientEnabled = false;
        this.voiceVolume = 0.8;
        this.ambientVolume = 0.3;

        // Calibration
        this.calibrationFrames = 0;

        // Remote control
        this.roomCode = null;
        this.ws = null;
        this.lastStateBroadcast = 0;

        // Voice script
        this.voiceScript = [];
        this.isVoicePlaying = false;
        this.currentAmbientTrack = 'permafrost';
        this.ambientTracks = {};
        this.crossfadeDuration = 3000; // 3 second crossfade
        this.ambientAudio2 = null; // Second audio element for crossfade
        this.poseMidpointPlayed = false;
        this.lastCorrectionTime = 0; // Debounce for voice corrections

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
            calibrationOverlay: document.getElementById('calibration-overlay'),
            countdownOverlay: document.getElementById('countdown-overlay'),
            countdownNumber: document.getElementById('countdown-number'),
            pauseBtn: document.getElementById('pause-btn'),
            endBtn: document.getElementById('end-btn'),
            startBtn: document.getElementById('start-btn'),
            soundToggle: document.getElementById('sound-toggle'),
            musicToggle: document.getElementById('music-toggle'),
            musicVolume: document.getElementById('music-volume'),
            calibrationStatus: document.getElementById('calibration-status'),
            formStatus: document.getElementById('form-status'),
            sessionCodePanel: document.getElementById('session-code-panel'),
            roomCode: document.getElementById('room-code'),
            qrCodeImg: document.getElementById('qr-code-img'),
            // Audio elements
            voiceAudio: document.getElementById('voice-audio'),
            ambientAudio: document.getElementById('ambient-audio'),
            voiceToggle: document.getElementById('voice-toggle'),
            ambientToggle: document.getElementById('ambient-toggle'),
            voiceVolumeSlider: document.getElementById('voice-volume'),
            ambientVolumeSlider: document.getElementById('ambient-volume'),
            ambientTracks: document.getElementById('ambient-tracks')
        };

        this.init();
    }

    // ========== REMOTE CONTROL ==========

    async createRoom() {
        try {
            const response = await fetch('/api/yoga/room', { method: 'POST' });
            const data = await response.json();
            this.roomCode = data.code;

            // Display room code
            if (this.elements.roomCode) {
                this.elements.roomCode.textContent = this.roomCode;
            }

            // Generate QR code with secure token URL as data URL image
            if (data.qr_url && this.elements.qrCodeImg) {
                if (typeof QRCode !== 'undefined') {
                    QRCode.toDataURL(data.qr_url, {
                        width: 150,
                        margin: 1,
                        color: {
                            dark: '#1a1a2e',
                            light: '#ffffff'
                        }
                    }, (error, url) => {
                        if (error) {
                            console.error('QR Code error:', error);
                            this.elements.qrCodeImg.style.display = 'none';
                        } else {
                            this.elements.qrCodeImg.src = url;
                        }
                    });
                } else {
                    console.error('QRCode library not loaded');
                    this.elements.qrCodeImg.style.display = 'none';
                }
            }

            // Connect WebSocket
            this.connectWebSocket();
        } catch (error) {
            console.error('Failed to create room:', error);
        }
    }

    connectWebSocket() {
        if (!this.roomCode) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${window.location.host}/ws/yoga/desktop/${this.roomCode}`);

        this.ws.onopen = () => {
            console.log('WebSocket connected, room:', this.roomCode);
            this.broadcastState();
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            // Try to reconnect after 3 seconds
            setTimeout(() => this.connectWebSocket(), 3000);
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleRemoteCommand(message);
        };
    }

    handleRemoteCommand(message) {
        // Handle command type messages
        if (message.type === 'command') {
            switch (message.command) {
                case 'start':
                    // Allow starting from phone without requiring calibration
                    if (this.state === 'calibrating') {
                        this.startCountdown();
                    }
                    break;
                case 'pause':
                    if (this.state === 'active') {
                        this.togglePause();
                    }
                    break;
                case 'resume':
                    if (this.state === 'paused') {
                        this.togglePause();
                    }
                    break;
                case 'skip':
                    if (this.state === 'active') {
                        this.currentPoseIndex++;
                        this.loadPose(this.currentPoseIndex);
                    }
                    break;
                case 'end':
                    this.state = 'complete';
                    if (this.timerInterval) clearInterval(this.timerInterval);
                    window.location.href = '/yoga';
                    break;
                case 'toggle_voice':
                    this.toggleVoiceGuide();
                    break;
                case 'toggle_ambient':
                    this.toggleAmbient();
                    break;
                case 'skip_establishing':
                    // Accessibility: force start timer from remote when in establishing state
                    if (this.state === 'establishing' || this.segmentState === 'establishing') {
                        console.log('[REMOTE] Skip establishing requested');
                        this.setSegmentState(SessionState.ACTIVE_HOLD);
                        this.poseTimerStarted = true;
                    }
                    break;
            }
        }

        // Handle audio volume messages
        if (message.type === 'voice_volume') {
            this.setVoiceVolume(message.value);
            if (this.elements.voiceVolumeSlider) {
                this.elements.voiceVolumeSlider.value = message.value;
            }
        }

        if (message.type === 'ambient_volume') {
            this.setAmbientVolume(message.value);
            if (this.elements.ambientVolumeSlider) {
                this.elements.ambientVolumeSlider.value = message.value;
            }
        }

        // Handle ambient track change from remote
        if (message.type === 'ambient_track') {
            const trackId = message.track;
            console.log('[REMOTE] Ambient track change:', trackId);
            this.setAmbientTrack(trackId);
        }

        // Handle remote device connection - hide session code panel
        if (message.type === 'remote_connected') {
            console.log('[REMOTE] Phone connected, hiding session code');
            if (this.elements.sessionCodePanel) {
                this.elements.sessionCodePanel.classList.add('hidden');
            }
        }

        // Handle remote device disconnection - show session code again if no remotes
        if (message.type === 'remote_disconnected') {
            console.log('[REMOTE] Phone disconnected, remotes remaining:', message.remoteCount);
            if (message.remoteCount === 0 && this.elements.sessionCodePanel) {
                // Only show session code again during calibration phase
                if (this.state === 'calibrating') {
                    this.elements.sessionCodePanel.classList.remove('hidden');
                }
            }
        }
    }

    broadcastState() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

        const now = Date.now();
        // Throttle broadcasts to max 10 per second
        if (now - this.lastStateBroadcast < 100) return;
        this.lastStateBroadcast = now;

        const state = {
            status: this.state,
            currentPose: this.currentPose ? {
                name: this.currentPose.name,
                sanskrit: this.currentPose.sanskrit,
                instructions: this.currentPose.instructions,
                image: this.currentPose.image
            } : null,
            poseIndex: this.currentPoseIndex,
            totalPoses: this.sessionQueue.length,
            matchScore: this.matchScore,
            poseTimeRemaining: this.poseTimeRemaining,
            sessionElapsed: this.sessionElapsed,
            isFormGood: this.isFormGood,
            poseTimerStarted: this.poseTimerStarted,
            formLevel: this.currentFormLevel,
            // New manifest-based fields
            segmentIndex: this.currentSegmentIndex,
            segmentState: this.segmentState,
            totalSegments: this.manifest?.segments?.length || this.sessionQueue.length,
            currentSegment: this.currentSegment ? {
                poseId: this.currentSegment.poseId,
                side: this.currentSegment.side,
                isBridge: this.currentSegment.isBridge,
                setId: this.currentSegment.setId
            } : null,
            interpolationProgress: this.interpolator ? this.interpolator.getProgress() : 0,
            audioPlaying: this.isVoicePlaying
        };

        this.ws.send(JSON.stringify({
            type: 'state_update',
            state: state
        }));
    }

    broadcastCountdown(value) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

        this.ws.send(JSON.stringify({
            type: 'state_update',
            state: {
                status: 'countdown',
                countdownValue: value
            }
        }));
    }

    // ========== AUDIO SYSTEM ==========

    async loadAudioResources() {
        // Load ambient track URLs
        try {
            const response = await fetch('/static/data/yoga/ambient.json');
            const data = await response.json();
            data.tracks.forEach(track => {
                this.ambientTracks[track.id] = track.url;
            });
            console.log('[AUDIO] Loaded ambient tracks:', Object.keys(this.ambientTracks));
        } catch (error) {
            console.warn('[AUDIO] Failed to load ambient tracks:', error);
        }

        // Set initial volumes
        if (this.elements.voiceAudio) {
            this.elements.voiceAudio.volume = this.voiceVolume;
        }
        if (this.elements.ambientAudio) {
            this.elements.ambientAudio.volume = this.ambientVolume;
        }
    }

    // === NEW: MANIFEST-BASED SESSION GENERATION ===

    async generateManifest(durationMins, focus, difficulty, poseIds = null) {
        try {
            console.log('[MANIFEST] Generating manifest...');
            const response = await fetch('/api/yoga/manifest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    duration: durationMins,
                    focus: focus,
                    difficulty: difficulty,
                    poses: poseIds
                })
            });

            if (!response.ok) {
                throw new Error(`Manifest API returned ${response.status}`);
            }

            const data = await response.json();
            this.manifest = data.manifest;

            if (!data.valid) {
                console.warn('[MANIFEST] Validation errors:', data.errors);
            }

            console.log(`[MANIFEST] Generated ${this.manifest.segments?.length || 0} segments`);
            console.log('[MANIFEST] Timing config:', this.manifest.timing);

            // Apply timing config from manifest
            if (this.manifest.timing) {
                this.establishingTimeoutMs = this.manifest.timing.establishingTimeoutMs || 10000;
                this.formMatchThreshold = this.manifest.timing.formMatchThreshold || 0.45;
            }

            return this.manifest;
        } catch (error) {
            console.warn('[MANIFEST] Failed to generate manifest:', error);
            return null;
        }
    }

    initInterpolation() {
        // Initialize interpolation system if available
        if (window.YogaInterpolation) {
            this.interpolationManager = new window.YogaInterpolation.InterpolationManager();
            console.log('[INTERPOLATION] Manager initialized');

            // Initialize ghost renderer for target pose during transitions
            const ctx = this.elements.canvas?.getContext('2d');
            if (ctx) {
                this.ghostRenderer = new window.YogaInterpolation.GhostSkeletonRenderer(ctx, {
                    color: 'rgba(0, 255, 255, 0.85)',  // Bright cyan to match target pose
                    lineWidth: 5,
                    fadeInDuration: 500,
                    fadeOutDuration: 300
                });
            }
        } else {
            console.warn('[INTERPOLATION] YogaInterpolation not available - using instant transitions');
        }
    }

    // === SEGMENT-BASED STATE MACHINE ===

    async loadSegment(segmentIndex) {
        if (!this.manifest || !this.manifest.segments) {
            console.warn('[SEGMENT] No manifest available, falling back to legacy');
            return this.loadPose(segmentIndex);
        }

        if (segmentIndex >= this.manifest.segments.length) {
            console.log('[SEGMENT] All segments complete');
            return this.completeSession();
        }

        this.currentSegmentIndex = segmentIndex;
        this.currentSegment = this.manifest.segments[segmentIndex];
        const segment = this.currentSegment;

        console.log(`\n========== LOADING SEGMENT ${segmentIndex}/${this.manifest.segments.length} ==========`);
        console.log(`Pose: ${segment.name}, Side: ${segment.side || 'none'}, Bridge: ${segment.isBridge}`);

        // Find matching pose in legacy poses array for UI compatibility
        this.currentPose = this.poses.find(p => p.id === segment.poseId) || {
            id: segment.poseId,
            name: segment.name,
            sanskrit: segment.sanskrit,
            instructions: segment.instructions || [],
            image: segment.image,
            reference_landmarks: segment.landmarks?.active,
            reference_angles: segment.angles?.active
        };
        this.currentPoseIndex = segmentIndex;

        // Reset timing
        this.poseTimeTotal = Math.floor(segment.holdDurationMs / 1000);
        this.poseTimeRemaining = this.poseTimeTotal;
        this.goodFormTime = 0;
        this.poseMidpointPlayed = false;
        this.poseTimerStarted = false;
        this.establishingStartTime = null;

        // Reset smoothing and warmup for target pose overlay
        this.smoothedLandmarks = null;
        this.smoothedTargetPosition = null;
        this.targetPoseWarmupFrames = 0;  // Require new warmup before showing skeleton

        // Check if this is a rotation switch (right side to left side)
        const isRotationStart = segment.isRotationStart && segment.rotationSide === 'left';
        if (isRotationStart) {
            console.log('[ROTATION] Switching to LEFT side');
        }

        // Update UI
        this.updateSegmentUI(segment);

        // Start interpolation immediately (continuous flow)
        const prevSegment = segmentIndex > 0 ? this.manifest.segments[segmentIndex - 1] : null;
        if (prevSegment && this.interpolationManager) {
            // Start skeleton morphing in background - don't wait
            this.runInterpolation(prevSegment, segment);
        }

        // === STATE: INSTRUCTIONS ===
        // Voice plays WHILE user is getting into position (form detection ON)
        this.setSegmentState(SessionState.INSTRUCTIONS);
        console.log(`[STATE] INSTRUCTIONS - Voice plays while user gets into position`);

        // Track that we're waiting for calibration
        this.audioComplete = false;
        this.formCalibrated = false;
        this.establishingStartTime = Date.now();

        // Play pose introduction voice
        this.playPoseStart(segmentIndex).then(() => {
            this.audioComplete = true;
            console.log('[VOICE] Audio complete, checking form...');
            this.checkReadyForHold();
        }).catch(err => {
            console.warn('[VOICE] Error:', err);
            this.audioComplete = true;
            this.checkReadyForHold();
        });

        // Form detection is now active - timer will start when:
        // 1. Audio is complete AND
        // 2. Form matches threshold (or timeout)
        // This is checked in runTimerLoop via checkReadyForHold()
    }

    checkReadyForHold() {
        // Called when audio completes or form matches
        if (this.audioComplete && this.formCalibrated) {
            // Both conditions met - start the hold timer
            console.log('[STATE] Ready for hold - starting timer');
            this.setSegmentState(SessionState.ACTIVE_HOLD);
            this.poseTimerStarted = true;
        }
    }

    async runInterpolation(fromSegment, toSegment) {
        if (!this.interpolationManager) {
            return Promise.resolve();
        }

        const fromLandmarks = fromSegment.landmarks?.active || [];
        const toLandmarks = toSegment.landmarks?.active || [];
        const durationMs = toSegment.interpolation?.durationMs || 3000;
        const easing = toSegment.interpolation?.easing || 'easeInOut';

        console.log(`[INTERPOLATION] Starting: ${durationMs}ms, easing: ${easing}`);

        return new Promise((resolve) => {
            this.interpolator = this.interpolationManager.create(
                'main',
                fromLandmarks,
                toLandmarks,
                durationMs,
                easing
            );

            this.interpolator.onComplete = () => {
                console.log('[INTERPOLATION] Complete');
                this.interpolator = null;
                resolve();
            };

            // Run interpolation loop
            const interpolationLoop = () => {
                if (!this.interpolator || this.interpolator.isFinished()) {
                    resolve();
                    return;
                }

                this.interpolationManager.updateAll();
                requestAnimationFrame(interpolationLoop);
            };

            interpolationLoop();
        });
    }

    setSegmentState(newState) {
        const oldState = this.segmentState;
        this.segmentState = newState;
        this.state = newState;  // Keep legacy state in sync

        console.log(`[STATE] ${oldState} -> ${newState}`);
        this.broadcastState();
    }

    updateSegmentUI(segment) {
        // Update pose name with side indicator
        let displayName = segment.name;
        if (segment.side) {
            displayName += ` (${segment.side.charAt(0).toUpperCase() + segment.side.slice(1)})`;
        }
        if (segment.isBridge) {
            displayName += ' [transition]';
        }

        this.elements.poseName.textContent = displayName;
        this.elements.poseSanskrit.textContent = segment.sanskrit || '';
        this.elements.poseInstructions.innerHTML = (segment.instructions || [])
            .map(inst => `<li>${inst}</li>`)
            .join('');

        // Show pose image
        const poseImage = document.getElementById('pose-reference-image');
        if (poseImage && segment.image) {
            poseImage.src = segment.image;
            poseImage.style.display = 'block';
        }

        this.updateQueueDisplay();
    }

    // Check if we should transition from ESTABLISHING to ACTIVE_HOLD
    checkEstablishingTransition() {
        if (this.segmentState !== SessionState.ESTABLISHING) return;

        const elapsedMs = Date.now() - (this.establishingStartTime || Date.now());
        const formScore = this.matchScore / 100;

        // Transition to ACTIVE_HOLD if:
        // 1. Form score meets threshold, OR
        // 2. Establishing timeout exceeded (accessibility)
        if (formScore >= this.formMatchThreshold || elapsedMs >= this.establishingTimeoutMs) {
            if (formScore >= this.formMatchThreshold) {
                console.log(`[STATE] Form matched! Score: ${Math.round(this.matchScore)}%`);
            } else {
                console.log(`[STATE] Establishing timeout - auto-starting (accessibility)`);
            }

            this.setSegmentState(SessionState.ACTIVE_HOLD);
            this.poseTimerStarted = true;
        }
    }

    async generateVoiceScript() {
        try {
            const params = new URLSearchParams(window.location.search);

            // Use manifest segments if available, otherwise fall back to sessionQueue
            let posesForVoice;
            if (this.useManifest && this.manifest?.segments) {
                console.log('%c[VOICE] ========== USING MANIFEST SEGMENTS ==========', 'color: #7c9a92; font-weight: bold');
                console.log('[VOICE] Manifest segments:', this.manifest.segments.length);

                // Convert manifest segments to voice script format
                posesForVoice = this.manifest.segments.map((seg, i) => {
                    // Find the original pose data for instructions
                    const originalPose = this.poses.find(p => p.id === seg.poseId) || {};

                    console.log(`[VOICE] Segment ${i}: ${seg.name} (side=${seg.side || 'none'}, rotation=${seg.rotationSide || 'none'})`);

                    return {
                        id: seg.poseId,
                        name: seg.name,
                        duration_seconds: [Math.floor(seg.holdDurationMs / 1000)],
                        instructions: seg.instructions || originalPose.instructions || [],
                        phase: seg.isBridge ? 'transition' : 'main',
                        side: seg.side,  // Pass side info for bilateral voice cues
                        isRotationStart: seg.isRotationStart || false,
                        rotationSide: seg.rotationSide || null,
                        isFirstInRotation: seg.isFirstInRotation || false,
                        isLastInRotation: seg.isLastInRotation || false
                    };
                });
            } else {
                // Legacy: use sessionQueue
                console.log('%c[VOICE] ========== USING LEGACY SESSION QUEUE ==========', 'color: #c97b7b; font-weight: bold');
                console.log('[VOICE] sessionQueue length:', this.sessionQueue.length);
                this.sessionQueue.forEach((p, i) => {
                    console.log(`[VOICE] Queue[${i}]: ${p.name}`);
                });

                posesForVoice = this.sessionQueue.map(p => ({
                    id: p.id,
                    name: p.name,
                    duration_seconds: p.duration_seconds,
                    instructions: p.instructions,
                    phase: p.phase
                }));
            }

            const sessionData = {
                duration: parseInt(params.get('duration')) || 30,
                focus: params.get('focus') || 'all',
                poses: posesForVoice,
                style: this.manifest?.timing?.sessionStyle || params.get('style') || 'vinyasa',
                breathCues: this.manifest?.timing?.breathCues ?? true
            };

            console.log('%c[VOICE] ========== GENERATING VOICE SCRIPT ==========', 'color: #d4a574; font-weight: bold; font-size: 14px');
            console.log('[VOICE] Session:', sessionData.duration, 'min,', sessionData.focus, 'focus');
            console.log('[VOICE] Poses to send:', sessionData.poses.length);
            sessionData.poses.forEach((p, i) => {
                console.log(`[VOICE] Pose ${i}: ${p.name} - ${p.instructions?.length || 0} instructions`);
                if (p.instructions) {
                    p.instructions.forEach((inst, j) => {
                        console.log(`  [${j}]: "${inst.substring(0, 50)}..."`);
                    });
                }
            });
            console.log('[VOICE] Full payload:', JSON.stringify(sessionData, null, 2).substring(0, 2000));

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);  // 30 second timeout

            const response = await fetch('/api/yoga/voice-script', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sessionData),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`Voice API returned ${response.status}`);
            }

            const data = await response.json();
            this.voiceScript = data.script || [];

            if (this.voiceScript.length === 0) {
                console.warn('[VOICE] Voice script is empty - session will run without voice guidance');
                this.showToast('Voice guidance unavailable - continuing without audio', 'warning');
            }

            console.log('%c[VOICE] ========== VOICE SCRIPT LOADED ==========', 'color: #7c9a92; font-weight: bold; font-size: 14px');
            console.log(`[VOICE] Total phrases: ${this.voiceScript.length}`);

            // Log breakdown by timing
            const timings = {};
            this.voiceScript.forEach(item => {
                timings[item.timing] = (timings[item.timing] || 0) + 1;
            });
            console.log('[VOICE] Breakdown by timing:', timings);

            // Log breakdown by pose
            const byPose = {};
            this.voiceScript.forEach(item => {
                if (item.pose_index !== undefined) {
                    byPose[item.pose_index] = (byPose[item.pose_index] || 0) + 1;
                }
            });
            console.log('[VOICE] Items per pose:', byPose);

            // Log instruction count per pose
            const instructionsPerPose = {};
            this.voiceScript.filter(i => i.type === 'pose_instruction').forEach(item => {
                instructionsPerPose[item.pose_index] = (instructionsPerPose[item.pose_index] || 0) + 1;
            });
            console.log('[VOICE] Instructions per pose:', instructionsPerPose);
            console.log('%c[VOICE] ==========================================', 'color: #7c9a92; font-weight: bold');
        } catch (error) {
            console.warn('Failed to generate voice script:', error);
            this.voiceScript = [];

            // Show user-friendly error but don't block session
            if (error.name === 'AbortError') {
                this.showToast('Voice guidance timed out - continuing without audio', 'warning');
            } else {
                this.showToast('Voice guidance unavailable - continuing without audio', 'warning');
            }
        }
    }

    getScriptItemsForTiming(timing, poseIndex = null) {
        // Guard against null/undefined voiceScript
        if (!this.voiceScript || !Array.isArray(this.voiceScript)) {
            console.warn('[VOICE] voiceScript not available');
            return [];
        }
        return this.voiceScript.filter(item => {
            if (!item) return false;  // Skip null/undefined items
            if (item.timing !== timing) return false;
            if (poseIndex !== null && item.pose_index !== undefined && item.pose_index !== poseIndex) return false;
            return true;
        });
    }

    /**
     * Unlock audio playback by initiating a play action during a user gesture.
     * This is required by browser autoplay policies - audio.play() must be called
     * directly within a user-initiated event handler (click, touch, etc.)
     */
    unlockAudio() {
        // Prevent multiple unlock attempts
        if (this.audioUnlocked) {
            console.log('[AUDIO] Already unlocked, skipping');
            return;
        }

        console.log('[AUDIO] Unlocking audio on user gesture...');

        // Minimal silent WAV data URL (works in all browsers)
        const silentAudio = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';

        // Unlock voice audio
        if (this.elements.voiceAudio) {
            const audio = this.elements.voiceAudio;
            audio.volume = 0;  // Silent
            audio.src = silentAudio;

            // Play and immediately pause to unlock
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    audio.pause();
                    audio.volume = this.voiceVolume ?? 0.8;  // Fallback if undefined
                    audio.src = '';  // Clear the silent audio
                    console.log('[AUDIO] Voice audio unlocked successfully');
                    this.audioUnlocked = true;
                }).catch(err => {
                    console.warn('[AUDIO] Could not unlock voice audio:', err.message);
                    // Still mark as attempted to prevent repeated failures
                    this.audioUnlocked = true;
                });
            }
        }

        // Also unlock ambient audio if present
        if (this.elements.ambientAudio) {
            const ambient = this.elements.ambientAudio;
            ambient.volume = 0;
            ambient.src = silentAudio;  // Must set src before play
            const ambientPlayPromise = ambient.play();
            if (ambientPlayPromise !== undefined) {
                ambientPlayPromise.then(() => {
                    ambient.pause();
                    ambient.volume = this.ambientVolume ?? 0.3;  // Fallback if undefined
                    ambient.src = '';  // Clear silent audio
                    console.log('[AUDIO] Ambient audio unlocked successfully');
                }).catch(err => {
                    console.warn('[AUDIO] Could not unlock ambient audio:', err.message);
                });
            }
        }
    }

    async playVoiceItem(item) {
        if (!this.voiceEnabled) {
            console.log('[VOICE] Disabled, skipping:', item.text?.substring(0, 30));
            return;
        }
        if (!item.audio_url) {
            console.warn('[VOICE] No audio URL for:', item.text?.substring(0, 30));
            return;
        }
        if (!this.elements.voiceAudio) {
            console.error('[VOICE] Audio element not found!');
            return;
        }

        return new Promise((resolve) => {
            const audio = this.elements.voiceAudio;
            let resolved = false;

            const safeResolve = (reason) => {
                if (!resolved) {
                    resolved = true;
                    this.isVoicePlaying = false;
                    audio.onended = null;
                    audio.onerror = null;
                    audio.oncanplaythrough = null;
                    audio.onloadeddata = null;
                    clearTimeout(timeout);
                    console.log(`[VOICE] Audio done: ${reason} - "${item.text?.substring(0, 30)}..."`);
                    resolve();
                }
            };

            // Timeout fallback - if audio doesn't complete within 30 seconds, skip it
            const timeout = setTimeout(() => {
                console.warn('[VOICE] Audio timeout after 30s:', item.text?.substring(0, 30));
                audio.pause();
                safeResolve('timeout');
            }, 30000);

            this.isVoicePlaying = true;

            // Set up handlers BEFORE setting src
            audio.onended = () => {
                safeResolve('ended');
            };

            audio.onerror = (e) => {
                console.warn('[VOICE] Audio error:', e.type, item.audio_url);
                safeResolve('error');
            };

            // Use loadeddata event - fires when first frame is available
            audio.onloadeddata = () => {
                audio.onloadeddata = null;
                console.log('[VOICE] Audio loaded, starting playback...');
                audio.play().then(() => {
                    console.log('[VOICE] Now playing:', item.text?.substring(0, 40));
                }).catch((err) => {
                    console.warn('[VOICE] Play failed:', err.message);
                    safeResolve('play-failed');
                });
            };

            // Set source and start loading
            console.log('[VOICE] Loading:', item.audio_url);
            audio.src = item.audio_url;
            audio.volume = this.voiceVolume;
            audio.load();
        });
    }

    async playVoiceSequence(items) {
        // Guard against null/undefined items
        if (!items || !Array.isArray(items)) {
            console.warn('[VOICE] Invalid items array:', items);
            return;
        }

        if (items.length === 0) {
            console.log('[VOICE] Empty sequence, nothing to play');
            return;
        }

        console.log(`%c[VOICE] Playing sequence: ${items.length} items`, 'color: #7c9a92; font-weight: bold');

        // Log all items we're about to play
        items.forEach((item, i) => {
            console.log(`  [${i + 1}] ${item?.type || 'unknown'}: "${item?.text?.substring(0, 60) || '(no text)'}..."`);
        });

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (!this.voiceEnabled) {
                console.log('%c[VOICE] Voice disabled, stopping sequence', 'color: #c97b7b');
                break;
            }
            const startTime = Date.now();
            console.log(`%c[VOICE] Playing ${i + 1}/${items.length}: "${item.text?.substring(0, 50)}..."`, 'color: #d4a574');

            await this.playVoiceItem(item);

            const elapsed = Date.now() - startTime;
            console.log(`%c[VOICE] Finished ${i + 1}/${items.length} in ${elapsed}ms`, 'color: #7c9a92');

            // Brief pause between phrases (100ms for natural flow)
            await new Promise(r => setTimeout(r, 100));
        }
        console.log('%c[VOICE] Sequence complete!', 'color: #7c9a92; font-weight: bold');
    }

    async playSessionStart() {
        const items = this.getScriptItemsForTiming('session_start');
        console.log(`Playing session start: ${items.length} items`);
        if (items.length === 0) {
            console.warn('No session start items found in voice script');
        }
        await this.playVoiceSequence(items);
        console.log('Session start voice complete');
    }

    async playPoseStart(poseIndex) {
        console.log(`%c[VOICE] === POSE ${poseIndex} START ===`, 'color: #7c9a92; font-weight: bold; font-size: 14px');

        // Get all items for this pose
        const allPoseItems = this.voiceScript.filter(item => item.pose_index === poseIndex);
        console.log(`[VOICE] Total items for pose ${poseIndex}: ${allPoseItems.length}`);
        console.log(`[VOICE] Breakdown:`, allPoseItems.reduce((acc, item) => {
            acc[item.timing] = (acc[item.timing] || 0) + 1;
            return acc;
        }, {}));

        // Play pose intro and ALL instructions
        const startItems = this.voiceScript.filter(item =>
            item.timing === 'pose_start' && item.pose_index === poseIndex
        );
        console.log(`%c[VOICE] Found ${startItems.length} pose_start items to play:`, 'color: #d4a574');
        startItems.forEach((item, i) => {
            console.log(`  [${i}] type=${item.type}, step=${item.step ?? 'n/a'}: "${item.text?.substring(0, 50)}..."`);
        });

        if (startItems.length === 0) {
            console.warn('[VOICE] WARNING: No pose_start items found for pose', poseIndex);
        }

        await this.playVoiceSequence(startItems);

        // Then play the hold cues (non-blocking so timer can start)
        const holdItems = this.voiceScript.filter(item =>
            item.timing === 'pose_holding' && item.pose_index === poseIndex
        );
        if (holdItems.length > 0) {
            console.log(`%c[VOICE] Playing ${holdItems.length} hold cue(s) for pose ${poseIndex}`, 'color: #d4a574');
            this.playVoiceSequence(holdItems).catch(err => console.warn('Hold cue error:', err));
        }
    }

    async playPoseMidpoint(poseIndex) {
        const items = this.voiceScript.filter(item =>
            item.timing === 'pose_midpoint' && item.pose_index === poseIndex
        );
        if (items.length > 0 && !this.isVoicePlaying) {
            console.log(`%c[VOICE] Playing ${items.length} midpoint cue(s) for pose ${poseIndex}`, 'color: #d4a574');
            await this.playVoiceSequence(items);
        }
    }

    async playPoseEnd(poseIndex) {
        const items = this.voiceScript.filter(item =>
            item.timing === 'pose_end' && item.pose_index === poseIndex
        );
        await this.playVoiceSequence(items);
    }

    async playSessionEnd() {
        const items = this.getScriptItemsForTiming('session_end');
        await this.playVoiceSequence(items);
    }

    startAmbientAudio() {
        if (!this.elements.ambientAudio) {
            console.warn('[AMBIENT] Audio element not found');
            return;
        }
        if (!this.ambientEnabled) {
            console.log('[AMBIENT] Not enabled, skipping');
            return;
        }

        const trackUrl = this.ambientTracks[this.currentAmbientTrack];
        console.log('[AMBIENT] Starting track:', this.currentAmbientTrack, 'URL:', trackUrl);
        console.log('[AMBIENT] All available tracks:', JSON.stringify(this.ambientTracks, null, 2));

        if (trackUrl) {
            const audio = this.elements.ambientAudio;

            // Reset the audio element
            audio.pause();
            audio.currentTime = 0;

            // Set up event handlers BEFORE setting src
            audio.onloadeddata = () => {
                console.log('[AMBIENT] Audio data loaded, duration:', audio.duration);
            };

            audio.oncanplaythrough = () => {
                console.log('[AMBIENT] Can play through, starting playback...');
                audio.play()
                    .then(() => {
                        console.log('[AMBIENT] Now playing:', this.currentAmbientTrack);
                    })
                    .catch(e => {
                        console.warn('[AMBIENT] Play failed:', e.message);
                        // User interaction might be needed
                        console.log('[AMBIENT] Try clicking the ambient toggle button again');
                    });
            };

            audio.onerror = (e) => {
                const error = audio.error;
                console.error('[AMBIENT] Audio error:', {
                    code: error?.code,
                    message: error?.message,
                    mediaError: error
                });
                console.log('[AMBIENT] Failed URL:', trackUrl);
                this.showAudioError('Ambient audio not available. Add audio files to /static/audio/ambient/');
                this.ambientEnabled = false;
                this.elements.ambientToggle?.classList.remove('active');
            };

            // Set source and load
            audio.src = trackUrl;
            audio.volume = this.ambientVolume;
            audio.crossOrigin = 'anonymous';  // Enable CORS
            console.log('[AMBIENT] Loading audio from:', trackUrl);
            audio.load();
        } else {
            console.warn('[AMBIENT] No URL for track:', this.currentAmbientTrack);
            console.log('[AMBIENT] Available tracks:', Object.keys(this.ambientTracks));
        }
    }

    stopAmbientAudio() {
        if (this.elements.ambientAudio) {
            this.elements.ambientAudio.pause();
            this.elements.ambientAudio.currentTime = 0;
        }
    }

    setAmbientTrack(trackId) {
        console.log('[AMBIENT] Changing track to:', trackId);

        // Update UI
        document.querySelectorAll('.ambient-track').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.track === trackId);
        });

        // Crossfade to new track if audio is playing
        if (this.ambientEnabled && this.elements.ambientAudio && !this.elements.ambientAudio.paused) {
            this.crossfadeToTrack(trackId);
        } else {
            this.currentAmbientTrack = trackId;
            if (this.ambientEnabled) {
                this.startAmbientAudio();
            }
        }

        // Broadcast to remote
        this.broadcastState();
    }

    crossfadeToTrack(newTrackId) {
        const trackUrl = this.ambientTracks[newTrackId];
        if (!trackUrl) {
            console.warn('[AMBIENT] Track not found:', newTrackId);
            return;
        }

        const oldAudio = this.elements.ambientAudio;
        const oldVolume = oldAudio.volume;

        // Create new audio element for crossfade
        const newAudio = document.createElement('audio');
        newAudio.loop = true;
        newAudio.volume = 0;
        newAudio.src = trackUrl;

        console.log('[AMBIENT] Crossfading from', this.currentAmbientTrack, 'to', newTrackId);

        newAudio.oncanplaythrough = () => {
            newAudio.play().then(() => {
                // Perform crossfade over duration
                const steps = 30;
                const stepDuration = this.crossfadeDuration / steps;
                const volumeStep = oldVolume / steps;
                let step = 0;

                const fadeInterval = setInterval(() => {
                    step++;

                    // Fade out old, fade in new
                    oldAudio.volume = Math.max(0, oldVolume - (volumeStep * step));
                    newAudio.volume = Math.min(oldVolume, volumeStep * step);

                    if (step >= steps) {
                        clearInterval(fadeInterval);
                        oldAudio.pause();
                        oldAudio.src = '';

                        // Swap audio elements
                        this.elements.ambientAudio = newAudio;
                        this.currentAmbientTrack = newTrackId;
                        console.log('[AMBIENT] Crossfade complete to:', newTrackId);
                    }
                }, stepDuration);
            }).catch(e => {
                console.warn('[AMBIENT] Crossfade play failed:', e.message);
            });
        };

        newAudio.onerror = () => {
            console.error('[AMBIENT] Failed to load new track for crossfade');
            this.showAudioError('Failed to load track');
        };

        newAudio.load();
    }

    toggleVoiceGuide() {
        this.voiceEnabled = !this.voiceEnabled;
        this.elements.voiceToggle?.classList.toggle('active', this.voiceEnabled);

        if (!this.voiceEnabled && this.elements.voiceAudio) {
            this.elements.voiceAudio.pause();
        }
    }

    toggleAmbient() {
        this.ambientEnabled = !this.ambientEnabled;
        this.elements.ambientToggle?.classList.toggle('active', this.ambientEnabled);

        if (this.ambientEnabled) {
            this.startAmbientAudio();
        } else {
            this.stopAmbientAudio();
        }

        // Broadcast to remote
        this.broadcastState();
    }

    showAudioError(message) {
        // Show a temporary toast notification for audio errors
        console.warn('[AUDIO]', message);
        const existing = document.querySelector('.audio-error-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'audio-error-toast';
        toast.style.cssText = `
            position: fixed;
            bottom: 100px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(201, 123, 123, 0.9);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 0.9rem;
            z-index: 1000;
            animation: fadeIn 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    setVoiceVolume(value) {
        this.voiceVolume = value / 100;
        if (this.elements.voiceAudio) {
            this.elements.voiceAudio.volume = this.voiceVolume;
        }
    }

    setAmbientVolume(value) {
        this.ambientVolume = value / 100;
        if (this.elements.ambientAudio) {
            this.elements.ambientAudio.volume = this.ambientVolume;
        }
    }

    async init() {
        try {
            // Helper to update loading message
            const updateLoadingStatus = (message) => {
                const loadingText = document.querySelector('#loading-overlay .loading-text');
                if (loadingText) loadingText.textContent = message;
                console.log(`[INIT] ${message}`);
            };

            updateLoadingStatus('Loading poses...');

            // Load pose data
            const response = await fetch('/static/data/yoga/poses.json');
            const data = await response.json();
            this.poses = data.poses;

            console.log('%c[INIT] ========== POSES LOADED ==========', 'color: #7c9a92; font-weight: bold');
            console.log('[INIT] Total poses:', this.poses.length);
            this.poses.forEach((p, i) => {
                console.log(`[INIT] Pose ${i}: ${p.name} - ${p.instructions?.length || 0} instructions`);
            });

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

            // Initialize MediaPipe (may take a while on slow connections)
            updateLoadingStatus('Loading AI model...');
            await this.initPoseDetection();

            // Start webcam
            updateLoadingStatus('Starting camera...');
            await this.startWebcam();

            // Load audio resources
            updateLoadingStatus('Loading audio...');
            await this.loadAudioResources();

            // Initialize interpolation system
            this.initInterpolation();

            // Try to generate manifest (new system)
            // Note: params already declared above, reuse it
            updateLoadingStatus('Generating session...');
            const manifestDuration = parseInt(params.get('duration')) || 30;
            const manifestFocus = params.get('focus') || 'all';
            const manifestDifficulty = params.get('difficulty') || 'beginner';

            // Generate manifest for new flow
            if (mode === 'custom') {
                const manifestPoseIds = params.get('poses')?.split(',') || [];
                await this.generateManifest(manifestDuration, manifestFocus, manifestDifficulty, manifestPoseIds);
            } else {
                await this.generateManifest(manifestDuration, manifestFocus, manifestDifficulty);
            }

            // Enable manifest mode if we got a valid manifest
            if (this.manifest && this.manifest.segments && this.manifest.segments.length > 0) {
                this.useManifest = true;
                console.log('[INIT] Using manifest-based flow');
            } else {
                console.log('[INIT] Falling back to legacy flow');
            }

            // Generate voice script (may take a while)
            updateLoadingStatus('Preparing voice guidance...');
            await this.generateVoiceScript();

            // Setup event listeners
            this.setupEventListeners();

            // Create room for remote control
            updateLoadingStatus('Creating session...');
            await this.createRoom();

            // Hide loading, show calibration
            this.elements.loadingOverlay.style.display = 'none';
            this.showCalibration();

        } catch (error) {
            console.error('Failed to initialize yoga session:', error);
            // Don't use alert - use our error overlay
            this.showErrorOverlay(
                'Session Failed to Start',
                error.message || 'An error occurred while loading the session. Please refresh and try again.'
            );
        }
    }

    generateSession(durationMinutes, focus) {
        console.log('%c[SESSION] ========== GENERATING SESSION ==========', 'color: #d4a574; font-weight: bold');
        console.log('[SESSION] Duration:', durationMinutes, 'min, Focus:', focus);

        const totalSeconds = durationMinutes * 60;
        let availablePoses = [...this.poses];

        if (focus !== 'all') {
            availablePoses = availablePoses.filter(p => p.focus.includes(focus));
        }

        if (availablePoses.length === 0) {
            availablePoses = [...this.poses];
        }

        console.log('[SESSION] Available poses:', availablePoses.length);
        availablePoses.forEach((p, i) => {
            console.log(`[SESSION] Available ${i}: ${p.name} - ${p.instructions?.length || 0} instructions`);
        });

        const session = [];
        let currentDuration = 0;

        const beginnerPoses = availablePoses.filter(p => p.difficulty === 'beginner');
        const intermediatePoses = availablePoses.filter(p => p.difficulty === 'intermediate');
        const advancedPoses = availablePoses.filter(p => p.difficulty === 'advanced');

        // Warm-up (20%)
        const warmupTarget = totalSeconds * 0.2;
        const warmupPoses = [...beginnerPoses];
        while (currentDuration < warmupTarget && warmupPoses.length > 0) {
            const pose = warmupPoses.splice(Math.floor(Math.random() * warmupPoses.length), 1)[0];
            const sessionPose = { ...pose, phase: 'warmup' };
            console.log(`[SESSION] Added warmup: ${sessionPose.name} - ${sessionPose.instructions?.length || 0} instructions`);
            session.push(sessionPose);
            currentDuration += pose.duration_seconds[0];
        }

        // Main flow (60%)
        const mainTarget = totalSeconds * 0.8;
        const mainPoses = [...intermediatePoses, ...advancedPoses, ...beginnerPoses];
        while (currentDuration < mainTarget && mainPoses.length > 0) {
            const pose = mainPoses.splice(Math.floor(Math.random() * mainPoses.length), 1)[0];
            const sessionPose = { ...pose, phase: 'main' };
            console.log(`[SESSION] Added main: ${sessionPose.name} - ${sessionPose.instructions?.length || 0} instructions`);
            session.push(sessionPose);
            currentDuration += pose.duration_seconds[0];
        }

        // Cool-down (20%)
        const cooldownPoses = availablePoses.filter(p =>
            p.focus.includes('relaxation') || p.category === 'seated'
        );
        while (currentDuration < totalSeconds && cooldownPoses.length > 0) {
            const pose = cooldownPoses.splice(Math.floor(Math.random() * cooldownPoses.length), 1)[0];
            const sessionPose = { ...pose, phase: 'cooldown' };
            console.log(`[SESSION] Added cooldown: ${sessionPose.name} - ${sessionPose.instructions?.length || 0} instructions`);
            session.push(sessionPose);
            currentDuration += pose.duration_seconds[0];
        }

        console.log('%c[SESSION] ========== SESSION COMPLETE ==========', 'color: #d4a574; font-weight: bold');
        console.log('[SESSION] Total poses in session:', session.length);
        session.forEach((p, i) => {
            console.log(`[SESSION] Final ${i}: ${p.name} (${p.phase}) - ${p.instructions?.length || 0} instructions`);
        });

        return session;
    }

    async initPoseDetection() {
        // Wait for MediaPipe to load with timeout
        let attempts = 0;
        const maxAttempts = 100;  // 10 seconds max wait

        while (!window.tasksVision && attempts < maxAttempts) {
            await new Promise(r => setTimeout(r, 100));
            attempts++;
        }

        if (!window.tasksVision) {
            // Show user-friendly error
            this.showErrorOverlay(
                'AI Model Failed to Load',
                'Could not load pose detection. This may be due to a slow connection or ad blocker. Please refresh and try again.'
            );
            throw new Error('MediaPipe failed to load after 10 seconds');
        }

        const { PoseLandmarker, FilesetResolver } = window.tasksVision;

        try {
            const vision = await Promise.race([
                FilesetResolver.forVisionTasks(
                    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm"
                ),
                new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('Vision WASM load timeout')), 30000)
                )
            ]);

            this.poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
                baseOptions: {
                    modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
                    delegate: "GPU"
                },
                runningMode: "VIDEO",
                numPoses: 1
            });
        } catch (error) {
            console.error('[POSE] Failed to initialize pose detection:', error);
            this.showErrorOverlay(
                'Pose Detection Failed',
                'Could not initialize pose detection. Please refresh the page and try again.'
            );
            throw error;
        }
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
        this.elements.startBtn?.addEventListener('click', () => this.startCountdown());
        this.elements.pauseBtn?.addEventListener('click', () => this.togglePause());
        this.elements.endBtn?.addEventListener('click', () => this.endSession());

        // Audio controls
        this.elements.voiceToggle?.addEventListener('click', () => this.toggleVoiceGuide());
        this.elements.ambientToggle?.addEventListener('click', () => this.toggleAmbient());
        this.elements.voiceVolumeSlider?.addEventListener('input', (e) => this.setVoiceVolume(e.target.value));
        this.elements.ambientVolumeSlider?.addEventListener('input', (e) => this.setAmbientVolume(e.target.value));

        // Ambient track selection
        document.querySelectorAll('.ambient-track').forEach(btn => {
            btn.addEventListener('click', () => this.setAmbientTrack(btn.dataset.track));
        });

        // Legacy header buttons (keep for compatibility)
        this.elements.soundToggle?.addEventListener('click', () => this.toggleVoiceGuide());
        this.elements.musicToggle?.addEventListener('click', () => this.toggleAmbient());
    }

    // ========== CALIBRATION PHASE ==========

    showCalibration() {
        this.state = 'calibrating';
        this.elements.calibrationOverlay.style.display = 'flex';
        this.calibrationFrames = 0;
        this.broadcastState();
        this.runCalibrationLoop();
    }

    runCalibrationLoop() {
        if (this.state !== 'calibrating') return;

        const video = this.elements.video;
        const canvas = this.elements.canvas;
        const ctx = canvas.getContext('2d');

        if (video.currentTime !== this.lastVideoTime && video.readyState >= 2) {
            this.lastVideoTime = video.currentTime;

            const results = this.poseLandmarker.detectForVideo(video, performance.now());

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (results.landmarks && results.landmarks.length > 0) {
                // During calibration, use raw landmarks directly (no smoothing)
                // This prevents the skeleton from getting "stuck"
                const landmarks = results.landmarks[0];

                // Reset smoothing state for fresh start after calibration
                this.smoothedLandmarks = null;
                this.smoothedTargetPosition = null;

                this.drawLandmarks(ctx, landmarks);

                // Check if full body is in frame
                const bodyCheck = this.checkFullBodyInFrame(landmarks);

                if (bodyCheck.inFrame) {
                    this.calibrationFrames++;
                    this.elements.calibrationStatus.textContent = 'Hold still... ' + Math.min(100, Math.round(this.calibrationFrames / 30 * 100)) + '%';
                    this.elements.calibrationStatus.style.color = '#7c9a92';

                    // Need 30 frames (~1 sec) of stable full body
                    if (this.calibrationFrames >= 30) {
                        this.elements.calibrationStatus.textContent = 'Calibrated! Press Start when ready.';
                        this.elements.startBtn.disabled = false;
                        this.elements.startBtn.style.display = 'block';
                    }
                } else {
                    this.calibrationFrames = Math.max(0, this.calibrationFrames - 2);
                    this.elements.calibrationStatus.textContent = bodyCheck.message;
                    this.elements.calibrationStatus.style.color = '#d4a574';
                    this.elements.startBtn.disabled = true;
                }
            } else {
                this.calibrationFrames = 0;
                this.elements.calibrationStatus.textContent = 'No person detected. Step into frame.';
                this.elements.calibrationStatus.style.color = '#c97b7b';
                this.elements.startBtn.disabled = true;
            }
        }

        requestAnimationFrame(() => this.runCalibrationLoop());
    }

    checkFullBodyInFrame(landmarks) {
        // Key landmarks for full body: nose, shoulders, hips, knees, ankles
        const nose = landmarks[0];
        const leftShoulder = landmarks[11];
        const rightShoulder = landmarks[12];
        const leftHip = landmarks[23];
        const rightHip = landmarks[24];
        const leftAnkle = landmarks[27];
        const rightAnkle = landmarks[28];

        const margin = 0.05; // 5% margin from edges

        // Check visibility
        const minVisibility = 0.5;
        if (nose.visibility < minVisibility) return { inFrame: false, message: 'Face not visible' };
        if (leftShoulder.visibility < minVisibility || rightShoulder.visibility < minVisibility)
            return { inFrame: false, message: 'Shoulders not visible' };
        if (leftHip.visibility < minVisibility || rightHip.visibility < minVisibility)
            return { inFrame: false, message: 'Hips not visible - step back' };
        if (leftAnkle.visibility < minVisibility || rightAnkle.visibility < minVisibility)
            return { inFrame: false, message: 'Feet not visible - step back or adjust camera' };

        // Check if landmarks are within frame bounds
        const allPoints = [nose, leftShoulder, rightShoulder, leftHip, rightHip, leftAnkle, rightAnkle];
        for (const point of allPoints) {
            if (point.x < margin || point.x > 1 - margin) {
                return { inFrame: false, message: 'Move to center of frame' };
            }
            if (point.y < margin || point.y > 1 - margin) {
                return { inFrame: false, message: 'Adjust position - body cut off' };
            }
        }

        return { inFrame: true, message: 'Full body detected' };
    }

    // ========== COUNTDOWN PHASE ==========

    startCountdown() {
        this.state = 'countdown';
        this.elements.calibrationOverlay.style.display = 'none';
        this.elements.countdownOverlay.style.display = 'flex';

        // CRITICAL: Unlock audio on user gesture (browser autoplay policy)
        // This must happen during the click handler, not later in setTimeout/setInterval
        this.unlockAudio();

        // Quick 3-second countdown
        let count = 3;
        this.elements.countdownNumber.textContent = count;
        this.broadcastCountdown(count);

        const countdownInterval = setInterval(() => {
            count--;
            if (count > 0) {
                this.elements.countdownNumber.textContent = count;
                this.broadcastCountdown(count);
            } else {
                clearInterval(countdownInterval);
                this.elements.countdownOverlay.style.display = 'none';
                this.startSession();
            }
        }, 1000);
    }

    // ========== ACTIVE SESSION ==========

    async startSession() {
        this.state = 'intro';  // New state for intro phase
        this.currentPoseIndex = 0;
        this.introPlayed = false;

        // Reset form tracking for new session
        this.formTimeTracking = {
            perfect: 0,
            good: 0,
            okay: 0,
            needsWork: 0
        };
        this.currentFormLevel = 'needsWork';

        // Reset per-pose performance tracking
        this.posePerformance = [];
        this.currentPoseFormTime = {
            perfect: 0,
            good: 0,
            okay: 0,
            needsWork: 0
        };

        // Set neutral UI state during intro
        if (this.elements.formStatus) {
            this.elements.formStatus.textContent = 'Get ready...';
            this.elements.formStatus.style.color = '#a8c5be';
        }
        if (this.elements.matchScore) {
            this.elements.matchScore.textContent = '--';
            this.elements.matchScore.style.color = '#a8c5be';
        }

        // Start ambient audio if enabled
        if (this.ambientEnabled) {
            this.startAmbientAudio();
        }

        // Update queue display but don't load pose yet
        this.updateQueueDisplay();

        // Start detection loop (but no target pose shown during intro)
        this.runDetectionLoop();
        this.broadcastState();

        // Play session intro FIRST (each audio item has its own 30s timeout as safety)
        console.log('Starting session intro voice...');
        try {
            await this.playSessionStart();
        } catch (err) {
            console.warn('Voice error:', err);
        }
        console.log('Session intro complete, loading first pose...');

        // Now intro is done - load first pose/segment
        this.introPlayed = true;
        console.log('Intro complete, introPlayed:', this.introPlayed);

        // Start the timer loop first (it will handle positioning state)
        this.runTimerLoop();

        // Load first pose/segment based on mode
        if (this.useManifest && this.manifest?.segments?.length > 0) {
            console.log('[SESSION] Starting manifest-based flow');
            this.loadSegment(0);
        } else {
            console.log('[SESSION] Starting legacy flow');
            this.loadPose(0);
        }
    }

    async loadPose(index) {
        console.log(`\n========== LOADING POSE ${index}/${this.sessionQueue.length} ==========`);

        if (index >= this.sessionQueue.length) {
            console.log('All poses complete, ending session');
            this.completeSession();
            return;
        }

        this.currentPose = this.sessionQueue[index];
        this.currentPoseIndex = index;
        console.log(`Pose: ${this.currentPose.name}, duration: ${this.currentPose.duration_seconds[0]}s`);
        if (this.currentPose.variations && this.currentPose.variations.length > 0) {
            console.log(`Variations: ${this.currentPose.variations.length} (${this.currentPose.variations.map(v => v.name).join(', ')})`);
        } else {
            console.log(`Reference landmarks: ${this.currentPose.reference_landmarks?.length || 'none'}`);
            console.log(`Reference angles:`, this.currentPose.reference_angles);
        }

        this.poseTimeTotal = this.currentPose.duration_seconds[0];
        this.poseTimeRemaining = this.poseTimeTotal;
        this.goodFormTime = 0;
        this.poseMidpointPlayed = false;
        this.poseTimerStarted = false;
        this.smoothedLandmarks = null;  // Reset smoothing for fresh pose
        this.smoothedTargetPosition = null;  // Reset target pose smoothing
        this.targetPoseWarmupFrames = 0;  // Require warmup before showing skeleton

        // Reset form tracking for new pose
        this.currentFormLevel = 'needsWork';
        this.isFormGood = false;

        // Reset variation tracking for new pose
        this.currentMatchedVariation = null;
        this.variationMatchCounts = {};

        // Log if pose has variations
        if (this.currentPose.variations && this.currentPose.variations.length > 0) {
            console.log(`Pose has ${this.currentPose.variations.length} variations:`,
                this.currentPose.variations.map(v => v.name).join(', '));
        }

        // Update UI with pose info
        this.elements.poseName.textContent = this.currentPose.name;
        this.elements.poseSanskrit.textContent = this.currentPose.sanskrit;
        this.elements.poseInstructions.innerHTML = this.currentPose.instructions
            .map(inst => `<li>${inst}</li>`)
            .join('');

        // Show pose image if element exists
        const poseImage = document.getElementById('pose-reference-image');
        if (poseImage && this.currentPose.image) {
            poseImage.src = this.currentPose.image;
            poseImage.style.display = 'block';
        }

        this.updateQueueDisplay();

        // Enter INSTRUCTIONS state - form detection is OFF during this phase
        // User just listens to the voice guide explain the pose
        this.state = 'instructions';
        this.broadcastState();
        console.log(`[STATE] Entering INSTRUCTIONS state - form detection OFF`);

        // Play pose introduction - explains how to do the pose
        try {
            await this.playPoseStart(index);
        } catch (err) {
            console.warn('Voice error:', err);
        }

        // Instructions complete - now enter POSITIONING state
        // Form detection is ON, but timer doesn't start until user matches pose
        this.state = 'positioning';
        this.broadcastState();
        console.log(`[STATE] Entering POSITIONING state - waiting for user to get into pose`);

        // Brief delay before going active
        await new Promise(r => setTimeout(r, 200));

        // Now enter ACTIVE state - timer can start when form is good
        this.state = 'active';
        this.broadcastState();
        console.log(`[STATE] Entering ACTIVE state - pose ${this.currentPose.name} ready`);
    }

    updateQueueDisplay() {
        if (!this.elements.poseQueue) return;

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
        // Allow loop to run during various states, but skip form detection for some
        // IMPORTANT: Include all states to prevent freezing between poses
        const validStates = ['active', 'paused', 'intro', 'positioning', 'instructions', 'transition',
                            'transitioning', 'establishing'];
        if (!validStates.includes(this.state)) return;

        const video = this.elements.video;
        const canvas = this.elements.canvas;
        const ctx = canvas.getContext('2d');

        if (video.currentTime !== this.lastVideoTime && video.readyState >= 2) {
            this.lastVideoTime = video.currentTime;

            const results = this.poseLandmarker.detectForVideo(video, performance.now());

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (results.landmarks && results.landmarks.length > 0) {
                const rawLandmarks = results.landmarks[0];

                // Apply smoothing to reduce jitter
                this.currentLandmarks = this.smoothLandmarks(rawLandmarks);

                // During instructions, show user skeleton and target pose but don't evaluate form
                if (this.state === 'instructions') {
                    this.drawLandmarks(ctx, this.currentLandmarks);
                    // Show target pose during instructions so user knows what to aim for
                    if (this.hasReferenceLandmarks()) {
                        this.drawTargetPose(ctx);
                    }
                    this.elements.matchScore.textContent = '--';
                    this.broadcastState();
                    requestAnimationFrame(() => this.runDetectionLoop());
                    return;
                }

                // During transitioning, show interpolating ghost skeleton
                if (this.state === 'transitioning') {
                    this.drawLandmarks(ctx, this.currentLandmarks);
                    // Draw interpolating target if available
                    if (this.interpolator && this.ghostRenderer) {
                        const interpLandmarks = this.interpolator.getCurrentLandmarks();
                        this.ghostRenderer.updateFade(performance.now());
                        this.ghostRenderer.show();
                        this.ghostRenderer.render(interpLandmarks);
                    } else if (this.hasReferenceLandmarks()) {
                        this.drawTargetPose(ctx);
                    }
                    this.elements.matchScore.textContent = '--';
                    this.broadcastState();
                    requestAnimationFrame(() => this.runDetectionLoop());
                    return;
                }

                // During establishing, evaluate form but timer doesn't run yet
                if (this.state === 'establishing') {
                    this.matchScore = this.calculatePoseMatch(this.currentLandmarks);
                    this.elements.matchScore.textContent = `${Math.round(this.matchScore)}%`;
                    this.updateFormStatus(this.matchScore);

                    const wasFormGood = this.isFormGood;
                    this.isFormGood = this.currentFormLevel === 'perfect' || this.currentFormLevel === 'good';

                    if (!wasFormGood && this.isFormGood) {
                        console.log(`>>> Form established! Score: ${Math.round(this.matchScore)}%`);
                    }

                    this.drawLandmarks(ctx, this.currentLandmarks);
                    if (this.hasReferenceLandmarks()) {
                        this.drawTargetPose(ctx);
                    }
                    this.broadcastState();
                    requestAnimationFrame(() => this.runDetectionLoop());
                    return;
                }

                // Calculate match and update form during active session or positioning (not intro or transition)
                const isActiveSession = (this.state === 'active' || this.state === 'positioning') && this.introPlayed;
                const isTransition = this.state === 'transition' || this.state === 'intro';

                if (isActiveSession && !isTransition) {
                    // Calculate pose match FIRST (before drawing)
                    this.matchScore = this.calculatePoseMatch(this.currentLandmarks);
                    this.elements.matchScore.textContent = `${Math.round(this.matchScore)}%`;

                    // Update form status based on 4-tier system (sets currentFormLevel)
                    this.updateFormStatus(this.matchScore);

                    // Timer only runs for Perfect/Good (green states), stops for Okay/NeedsWork
                    const wasFormGood = this.isFormGood;
                    this.isFormGood = this.currentFormLevel === 'perfect' || this.currentFormLevel === 'good';

                    // Log state transitions for debugging
                    if (!wasFormGood && this.isFormGood) {
                        console.log(`\n>>> FORM NOW GOOD! Score: ${Math.round(this.matchScore)}%, Level: ${this.currentFormLevel}`);
                        console.log(`    State: ${this.state}, Timer Started: ${this.poseTimerStarted}`);
                    }
                    if (wasFormGood && !this.isFormGood) {
                        console.log(`<<< Form dropped below threshold. Score: ${Math.round(this.matchScore)}%`);
                        // Trigger voice correction after form drops for a few frames
                        this.triggerCorrectionFeedback();
                    }

                    // Now draw user's skeleton WITH correct colors
                    this.drawLandmarks(ctx, this.currentLandmarks);

                    // Draw target pose skeleton overlay
                    if (this.hasReferenceLandmarks()) {
                        this.drawTargetPose(ctx);
                    }
                } else {
                    // During intro/calibration, show neutral state
                    this.drawLandmarks(ctx, this.currentLandmarks);
                    this.elements.matchScore.textContent = '--';
                    this.isFormGood = false;
                }

                // Broadcast to remote
                this.broadcastState();
            } else {
                this.isFormGood = false;
                this.matchScore = 0;
                this.currentFormLevel = 'needsWork';
                this.updateFormStatus(0);
                this.broadcastState();
            }
        }

        requestAnimationFrame(() => this.runDetectionLoop());
    }

    // Voice correction feedback when form drops
    triggerCorrectionFeedback() {
        // Only give corrections after the timer has started (user was in good form first)
        if (!this.poseTimerStarted) {
            return;
        }

        // Debounce: only trigger once every 8 seconds
        const now = Date.now();
        if (this.lastCorrectionTime && (now - this.lastCorrectionTime) < 8000) {
            return;
        }

        // Don't interrupt other voice audio
        if (this.isVoicePlaying) {
            return;
        }

        // Find correction items for current pose
        const correctionItems = this.voiceScript.filter(item =>
            item.timing === 'pose_correction' && item.pose_index === this.currentPoseIndex
        );

        if (correctionItems.length > 0) {
            this.lastCorrectionTime = now;
            // Play a random correction hint
            const item = correctionItems[Math.floor(Math.random() * correctionItems.length)];
            console.log(`[VOICE] Playing correction: "${item.text?.substring(0, 50)}..."`);
            this.playVoiceItem(item).catch(err => console.warn('Correction voice error:', err));
        }
    }

    smoothLandmarks(rawLandmarks) {
        // Apply exponential moving average smoothing to reduce jitter
        // Uses same approach as the posture checking system for consistency
        if (!this.smoothedLandmarks) {
            // Initialize with deep copy of first frame (prevents reference issues)
            this.smoothedLandmarks = JSON.parse(JSON.stringify(rawLandmarks));
            return this.smoothedLandmarks;
        }

        // Smooth each landmark using EMA formula
        for (let i = 0; i < rawLandmarks.length; i++) {
            if (rawLandmarks[i] && this.smoothedLandmarks[i]) {
                this.smoothedLandmarks[i] = {
                    x: this.smoothedLandmarks[i].x * (1 - this.smoothingFactor) + rawLandmarks[i].x * this.smoothingFactor,
                    y: this.smoothedLandmarks[i].y * (1 - this.smoothingFactor) + rawLandmarks[i].y * this.smoothingFactor,
                    z: (this.smoothedLandmarks[i].z || 0) * (1 - this.smoothingFactor) + (rawLandmarks[i].z || 0) * this.smoothingFactor,
                    visibility: rawLandmarks[i].visibility
                };
            }
        }

        return this.smoothedLandmarks;
    }

    drawLandmarks(ctx, landmarks) {
        const { DrawingUtils, PoseLandmarker } = window.tasksVision;
        const drawingUtils = new DrawingUtils(ctx);

        // Determine glow color based on form level
        let glowColor;
        if (!this.introPlayed || this.state === 'intro' || this.state === 'calibrating' || this.state === 'transition') {
            glowColor = '#a8c5be';  // Neutral during transitions
        } else if (this.currentFormLevel === 'perfect' || this.currentFormLevel === 'good') {
            glowColor = '#4ade80';  // Bright green for good/perfect
        } else if (this.currentFormLevel === 'okay') {
            glowColor = '#fb923c';  // Orange for okay
        } else {
            glowColor = '#f87171';  // Red for needs work
        }

        // Update video container border glow
        this.updateVideoBorderGlow(glowColor);

        // Draw user skeleton in WHITE with colored GLOW
        ctx.save();

        // Create glow effect
        ctx.shadowColor = glowColor;
        ctx.shadowBlur = 15;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;

        // Draw connectors in white with glow
        drawingUtils.drawConnectors(
            landmarks,
            PoseLandmarker.POSE_CONNECTIONS,
            { color: '#ffffff', lineWidth: 4 }
        );

        // Draw landmarks in white with glow
        drawingUtils.drawLandmarks(landmarks, {
            color: '#ffffff',
            lineWidth: 1,
            radius: 6
        });

        ctx.restore();
    }

    updateVideoBorderGlow(glowColor) {
        const videoWrapper = document.querySelector('.video-wrapper');
        if (videoWrapper) {
            videoWrapper.style.boxShadow = `0 0 30px ${glowColor}, 0 0 60px ${glowColor}40, inset 0 0 20px ${glowColor}20`;
            videoWrapper.style.border = `3px solid ${glowColor}`;
        }
    }

    drawTargetPose(ctx) {
        // Get reference landmarks from manifest segment or pose
        let refLandmarks = null;

        // First try to get landmarks from manifest segment (preferred)
        if (this.useManifest && this.currentSegment?.landmarks?.active) {
            refLandmarks = this.currentSegment.landmarks.active;
        }
        // Then try variations
        else if (this.currentPose?.variations && this.currentPose.variations.length > 0) {
            if (this.currentMatchedVariation) {
                const matchedVar = this.currentPose.variations.find(v => v.id === this.currentMatchedVariation.id);
                refLandmarks = matchedVar?.reference_landmarks;
            }
            if (!refLandmarks) {
                refLandmarks = this.currentPose.variations[0]?.reference_landmarks;
            }
        }
        // Finally try legacy pose-level landmarks
        else {
            refLandmarks = this.currentPose?.reference_landmarks;
        }

        // CRITICAL: Don't draw if we don't have BOTH reference AND user landmarks
        if (!refLandmarks || refLandmarks.length === 0) {
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }
        if (!this.currentLandmarks || this.currentLandmarks.length === 0) {
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }

        // Validate user landmarks have required points
        const userLandmarks = this.currentLandmarks;
        const userLeftShoulder = userLandmarks[11];
        const userRightShoulder = userLandmarks[12];
        const userLeftHip = userLandmarks[23];
        const userRightHip = userLandmarks[24];
        const userLeftAnkle = userLandmarks[27];
        const userRightAnkle = userLandmarks[28];

        // Check all required landmarks exist and have valid coordinates
        if (!userLeftShoulder || !userRightShoulder || !userLeftHip ||
            !userRightHip || !userLeftAnkle || !userRightAnkle) {
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }

        // Helper to validate a coordinate is a valid number in range
        const isValidCoord = (val) => typeof val === 'number' && !isNaN(val) && isFinite(val);

        // Validate all coordinates are valid numbers (not NaN/undefined)
        if (!isValidCoord(userLeftHip.x) || !isValidCoord(userLeftHip.y) ||
            !isValidCoord(userRightHip.x) || !isValidCoord(userRightHip.y) ||
            !isValidCoord(userLeftShoulder.x) || !isValidCoord(userLeftShoulder.y) ||
            !isValidCoord(userRightShoulder.x) || !isValidCoord(userRightShoulder.y) ||
            !isValidCoord(userLeftAnkle.x) || !isValidCoord(userLeftAnkle.y) ||
            !isValidCoord(userRightAnkle.x) || !isValidCoord(userRightAnkle.y)) {
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }

        // Check visibility - only draw if user body is reasonably visible
        const avgVisibility = (
            (userLeftShoulder.visibility || 0) +
            (userRightShoulder.visibility || 0) +
            (userLeftHip.visibility || 0) +
            (userRightHip.visibility || 0)
        ) / 4;

        if (avgVisibility < 0.5) {
            // User not clearly visible, don't show confusing skeleton
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }

        const width = ctx.canvas.width;
        const height = ctx.canvas.height;

        // User center (midpoint of hips)
        const rawCenterX = (userLeftHip.x + userRightHip.x) / 2;
        const rawCenterY = (userLeftHip.y + userRightHip.y) / 2;

        // Validate center coordinates are within reasonable bounds (user is actually in frame)
        // Using explicit checks to handle NaN (NaN comparisons return false)
        if (!(rawCenterX >= 0.1 && rawCenterX <= 0.9 && rawCenterY >= 0.1 && rawCenterY <= 0.9)) {
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }

        // User body height (shoulders to ankles)
        const userShoulderY = (userLeftShoulder.y + userRightShoulder.y) / 2;
        const userAnkleY = (userLeftAnkle.y + userRightAnkle.y) / 2;
        const rawBodyHeight = Math.abs(userAnkleY - userShoulderY);

        // Validate body height is reasonable (10-80% of frame - not too small or too big)
        // Using >= and <= to properly handle NaN (NaN comparisons return false)
        if (!(rawBodyHeight >= 0.1 && rawBodyHeight <= 0.8)) {
            this.targetPoseWarmupFrames = 0;  // Reset warmup
            return;
        }

        // Warmup period: require several consecutive valid frames before showing skeleton
        // This prevents jittery skeleton appearance when user is still positioning
        this.targetPoseWarmupFrames = (this.targetPoseWarmupFrames || 0) + 1;

        // Wait for at least 10 good frames (~333ms at 30fps) before showing
        if (this.targetPoseWarmupFrames < 10) {
            return;
        }

        // Reference pose landmarks - handle both array and object formats
        let refLeftHip, refRightHip, refLeftShoulder, refRightShoulder, refLeftAnkle, refRightAnkle;

        if (Array.isArray(refLandmarks)) {
            refLeftHip = refLandmarks[23];
            refRightHip = refLandmarks[24];
            refLeftShoulder = refLandmarks[11];
            refRightShoulder = refLandmarks[12];
            refLeftAnkle = refLandmarks[27];
            refRightAnkle = refLandmarks[28];
        } else {
            // Named landmarks format
            refLeftHip = refLandmarks.find?.(l => l.name === 'LEFT_HIP') || refLandmarks[23];
            refRightHip = refLandmarks.find?.(l => l.name === 'RIGHT_HIP') || refLandmarks[24];
            refLeftShoulder = refLandmarks.find?.(l => l.name === 'LEFT_SHOULDER') || refLandmarks[11];
            refRightShoulder = refLandmarks.find?.(l => l.name === 'RIGHT_SHOULDER') || refLandmarks[12];
            refLeftAnkle = refLandmarks.find?.(l => l.name === 'LEFT_ANKLE') || refLandmarks[27];
            refRightAnkle = refLandmarks.find?.(l => l.name === 'RIGHT_ANKLE') || refLandmarks[28];
        }

        // Validate reference landmarks exist and have valid coordinates
        if (!refLeftHip || !refRightHip || !refLeftShoulder || !refRightShoulder) {
            return;
        }

        // Check reference landmark coordinates are valid numbers
        if (!isValidCoord(refLeftHip.x) || !isValidCoord(refLeftHip.y) ||
            !isValidCoord(refRightHip.x) || !isValidCoord(refRightHip.y) ||
            !isValidCoord(refLeftShoulder.x) || !isValidCoord(refLeftShoulder.y) ||
            !isValidCoord(refRightShoulder.x) || !isValidCoord(refRightShoulder.y)) {
            console.warn('[SKELETON] Invalid reference landmark coordinates');
            return;
        }

        const refCenterX = (refLeftHip.x + refRightHip.x) / 2;
        const refCenterY = (refLeftHip.y + refRightHip.y) / 2;
        const refShoulderY = (refLeftShoulder.y + refRightShoulder.y) / 2;

        // Safely calculate ankle Y with fallback
        let refAnkleY = refCenterY + 0.3;  // Default fallback
        if (refLeftAnkle && refRightAnkle &&
            isValidCoord(refLeftAnkle.y) && isValidCoord(refRightAnkle.y)) {
            refAnkleY = (refLeftAnkle.y + refRightAnkle.y) / 2;
        }

        const refBodyHeight = Math.abs(refAnkleY - refShoulderY);
        // Prevent division by zero or extremely small values
        if (!isValidCoord(refBodyHeight) || refBodyHeight < 0.05) {
            console.warn('[SKELETON] Invalid reference body height:', refBodyHeight);
            return;
        }

        // Apply smoothing to target position to prevent jitter
        if (!this.smoothedTargetPosition) {
            this.smoothedTargetPosition = {
                centerX: rawCenterX,
                centerY: rawCenterY,
                bodyHeight: rawBodyHeight
            };
        } else {
            const alpha = this.targetSmoothingFactor;
            this.smoothedTargetPosition.centerX = this.smoothedTargetPosition.centerX * (1 - alpha) + rawCenterX * alpha;
            this.smoothedTargetPosition.centerY = this.smoothedTargetPosition.centerY * (1 - alpha) + rawCenterY * alpha;
            this.smoothedTargetPosition.bodyHeight = this.smoothedTargetPosition.bodyHeight * (1 - alpha) + rawBodyHeight * alpha;
        }

        const userCenterX = this.smoothedTargetPosition.centerX;
        const userCenterY = this.smoothedTargetPosition.centerY;
        const userBodyHeight = this.smoothedTargetPosition.bodyHeight;

        // Scale factor to match user's body size
        const scale = userBodyHeight / refBodyHeight;

        // Validate scale is reasonable (0.2x to 5x range)
        if (!isValidCoord(scale) || scale < 0.2 || scale > 5) {
            console.warn('[SKELETON] Invalid scale factor:', scale);
            return;
        }

        // Transform reference landmark to user's coordinate space
        const transformLandmark = (ref) => {
            if (!ref) return null;
            if (!isValidCoord(ref.x) || !isValidCoord(ref.y)) return null;
            const x = (ref.x - refCenterX) * scale + userCenterX;
            const y = (ref.y - refCenterY) * scale + userCenterY;
            // Clamp to valid screen range with some margin for limbs extending off-screen
            return {
                x: Math.max(-0.5, Math.min(1.5, x)),
                y: Math.max(-0.5, Math.min(1.5, y))
            };
        };

        // Draw target pose as bright CYAN outline (distinct from white user skeleton)
        ctx.save();
        ctx.globalAlpha = 0.85;
        ctx.strokeStyle = '#00FFFF';  // Bright cyan - high contrast with user's white skeleton
        ctx.lineWidth = 5;
        ctx.shadowColor = '#00FFFF';
        ctx.shadowBlur = 12;
        ctx.setLineDash([]);  // Solid line for clarity

        // Define pose connections
        const connections = [
            [11, 12], // shoulders
            [11, 13], [13, 15], // left arm
            [12, 14], [14, 16], // right arm
            [11, 23], [12, 24], // torso sides
            [23, 24], // hips
            [23, 25], [25, 27], // left leg
            [24, 26], [26, 28], // right leg
        ];

        for (const [i, j] of connections) {
            const p1 = refLandmarks[i];
            const p2 = refLandmarks[j];
            if (p1 && p2) {
                const t1 = transformLandmark(p1);
                const t2 = transformLandmark(p2);
                ctx.beginPath();
                // Don't mirror here - CSS transform handles mirroring for both video and canvas
                ctx.moveTo(t1.x * width, t1.y * height);
                ctx.lineTo(t2.x * width, t2.y * height);
                ctx.stroke();
            }
        }

        // Draw joints as circles (yellow to match target lines)
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(251, 191, 36, 0.4)';  // Yellow/gold for target joints
        const jointIndices = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];
        for (const i of jointIndices) {
            const p = refLandmarks[i];
            if (p) {
                const t = transformLandmark(p);
                ctx.beginPath();
                // Don't mirror here - CSS transform handles it
                ctx.arc(t.x * width, t.y * height, 8, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        ctx.restore();
    }

    updateFormStatus(matchScore) {
        if (!this.elements.formStatus) return;

        // 4-tier form quality system - timer only runs for green states (perfect/good)
        if (matchScore >= 65) {
            // Perfect - timer runs, best grade
            this.elements.formStatus.innerHTML = '<i data-lucide="sparkles"></i> Perfect!';
            this.elements.formStatus.style.color = '#4ade80';  // Bright green
            this.elements.matchScore.style.color = '#4ade80';
            this.currentFormLevel = 'perfect';
        } else if (matchScore >= 45) {
            // Good - timer runs
            this.elements.formStatus.innerHTML = '<i data-lucide="thumbs-up"></i> Good form';
            this.elements.formStatus.style.color = '#4ade80';  // Bright green
            this.elements.matchScore.style.color = '#4ade80';
            this.currentFormLevel = 'good';
        } else if (matchScore >= 25) {
            // Okay - timer PAUSED, adjust to improve
            this.elements.formStatus.innerHTML = '<i data-lucide="pause-circle"></i> Adjust - Timer paused';
            this.elements.formStatus.style.color = '#fb923c';  // Orange
            this.elements.matchScore.style.color = '#fb923c';
            this.currentFormLevel = 'okay';
        } else {
            // Needs Work - timer PAUSED
            this.elements.formStatus.innerHTML = '<i data-lucide="alert-circle"></i> Adjust position';
            this.elements.formStatus.style.color = '#f87171';  // Red
            this.elements.matchScore.style.color = '#f87171';
            this.currentFormLevel = 'needsWork';
        }
        // Refresh Lucide icons after DOM change
        this.refreshIcons();
    }

    refreshIcons() {
        // Re-render Lucide icons after dynamic DOM changes
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    showToast(message, type = 'info') {
        // Create toast element if it doesn't exist
        let toast = document.getElementById('yoga-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'yoga-toast';
            toast.style.cssText = `
                position: fixed;
                bottom: 100px;
                left: 50%;
                transform: translateX(-50%);
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 0.9rem;
                z-index: 10000;
                opacity: 0;
                transition: opacity 0.3s;
                max-width: 80%;
                text-align: center;
            `;
            document.body.appendChild(toast);
        }

        // Set colors based on type
        if (type === 'warning') {
            toast.style.background = 'rgba(212, 165, 116, 0.95)';
            toast.style.color = '#2c3333';
        } else if (type === 'error') {
            toast.style.background = 'rgba(201, 123, 123, 0.95)';
            toast.style.color = 'white';
        } else {
            toast.style.background = 'rgba(124, 154, 146, 0.95)';
            toast.style.color = 'white';
        }

        toast.textContent = message;
        toast.style.opacity = '1';

        // Auto-hide after 4 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
        }, 4000);
    }

    showErrorOverlay(title, message) {
        // Create error overlay if it doesn't exist
        let overlay = document.getElementById('yoga-error-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'yoga-error-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0; left: 0;
                width: 100vw; height: 100vh;
                background: rgba(252, 250, 247, 0.98);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 99999;
                padding: 20px;
            `;
            document.body.appendChild(overlay);
        }

        overlay.innerHTML = `
            <div style="max-width: 400px; text-align: center; background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="font-size: 3rem; margin-bottom: 16px; color: #d4a574;">⚠️</div>
                <h2 style="color: #2c3333; margin-bottom: 12px; font-weight: 400;">${title}</h2>
                <p style="color: #6b7575; margin-bottom: 24px; line-height: 1.6;">${message}</p>
                <button onclick="location.reload()" style="background: linear-gradient(135deg, #7c9a92 0%, #a8c5be 100%); color: white; border: none; padding: 14px 28px; border-radius: 12px; font-size: 1rem; cursor: pointer;">
                    Refresh Page
                </button>
            </div>
        `;
        overlay.style.display = 'flex';
    }

    calculatePoseMatch(userLandmarks) {
        // Handle poses with multiple variations
        if (this.currentPose?.variations && this.currentPose.variations.length > 0) {
            return this.calculateBestVariationMatch(userLandmarks);
        }

        // Legacy: single reference angles at pose level
        if (!this.currentPose?.reference_angles) return 0;

        const refAngles = this.currentPose.reference_angles;
        const userAngles = this.calculateAngles(userLandmarks);

        return this.calculateAngleMatch(refAngles, userAngles);
    }

    /**
     * Calculate match against all variations and return the best score.
     * Tracks which variation the user is matching most frequently.
     */
    calculateBestVariationMatch(userLandmarks) {
        const userAngles = this.calculateAngles(userLandmarks);
        let bestScore = 0;
        let bestVariation = null;

        for (const variation of this.currentPose.variations) {
            if (!variation.reference_angles) continue;

            const score = this.calculateAngleMatch(variation.reference_angles, userAngles);
            if (score > bestScore) {
                bestScore = score;
                bestVariation = variation;
            }
        }

        // Track which variation is being matched (for reporting)
        if (bestVariation && bestScore >= 45) {  // Only count if form is "good" or better
            const varId = bestVariation.id;
            this.variationMatchCounts[varId] = (this.variationMatchCounts[varId] || 0) + 1;

            // Update current matched variation if this one has most matches
            const maxCount = Math.max(...Object.values(this.variationMatchCounts));
            if (this.variationMatchCounts[varId] === maxCount) {
                this.currentMatchedVariation = {
                    id: bestVariation.id,
                    name: bestVariation.name
                };
            }
        }

        return bestScore;
    }

    /**
     * Check if the current pose has reference landmarks available
     * (either from variations or legacy pose-level).
     */
    hasReferenceLandmarks() {
        if (!this.currentPose) return false;
        if (this.currentPose.reference_landmarks) return true;
        if (this.currentPose.variations && this.currentPose.variations.length > 0) {
            return this.currentPose.variations.some(v => v.reference_landmarks);
        }
        return false;
    }

    /**
     * Calculate match score between reference angles and user angles.
     */
    calculateAngleMatch(refAngles, userAngles) {
        let totalDiff = 0;
        let angleCount = 0;

        for (const [key, refAngle] of Object.entries(refAngles)) {
            if (refAngle !== null && userAngles[key] !== undefined) {
                let diff = Math.abs(refAngle - userAngles[key]);
                if (diff > 180) diff = 360 - diff;
                totalDiff += diff;
                angleCount++;
            }
        }

        if (angleCount === 0) return 0;

        const avgDiff = totalDiff / angleCount;
        // Very lenient formula for accessibility:
        // 20 degree avg diff = 87% (perfect)
        // 35 degree avg diff = 77% (good)
        // 50 degree avg diff = 67% (okay)
        // 70 degree avg diff = 53% (okay)
        // This allows users of all flexibility levels to participate
        return Math.max(0, 100 - (avgDiff / 150 * 100));
    }

    calculateAngles(landmarks) {
        const getAngle = (a, b, c) => {
            const radians = Math.atan2(c.y - b.y, c.x - b.x) - Math.atan2(a.y - b.y, a.x - b.x);
            let angle = Math.abs(radians * 180 / Math.PI);
            if (angle > 180) angle = 360 - angle;
            return angle;
        };

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


    runTimerLoop() {
        // Clear any existing timer
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
        }

        this.timerInterval = setInterval(async () => {
            // Handle non-active states
            if (this.state === 'paused') return;
            if (this.state === 'complete' || this.state === 'loading' || this.state === 'calibrating' || this.state === 'countdown') return;

            if (this.state === 'intro') {
                // During intro, show waiting message
                this.elements.poseTimer.textContent = 'Listen...';
                this.elements.poseTimer.style.color = '#a8c5be';
                return;
            }

            if (this.state === 'instructions') {
                // During instructions, voice plays while user gets into position
                // Form detection is ACTIVE - check if user has matched the pose
                if (this.isFormGood && !this.formCalibrated) {
                    this.formCalibrated = true;
                    console.log('[FORM] User matched pose threshold during instructions');
                    this.checkReadyForHold();
                }

                // Check for timeout if user can't get into position
                const elapsed = Date.now() - (this.establishingStartTime || Date.now());
                if (elapsed > this.establishingTimeoutMs && !this.formCalibrated) {
                    console.log('[FORM] Timeout - starting timer anyway');
                    this.formCalibrated = true;
                    this.checkReadyForHold();
                }

                // Show form feedback
                if (this.isFormGood) {
                    this.elements.poseTimer.textContent = 'Great!';
                    this.elements.poseTimer.style.color = '#4ade80';
                    if (this.elements.formStatus) {
                        this.elements.formStatus.innerHTML = '<i data-lucide="check"></i> Hold that form';
                        this.elements.formStatus.style.color = '#4ade80';
                        this.refreshIcons();
                    }
                } else {
                    this.elements.poseTimer.textContent = 'Get into pose';
                    this.elements.poseTimer.style.color = '#a8c5be';
                    if (this.elements.formStatus) {
                        this.elements.formStatus.innerHTML = '<i data-lucide="target"></i> Match the guide';
                        this.elements.formStatus.style.color = '#a8c5be';
                        this.refreshIcons();
                    }
                }
                return;
            }

            if (this.state === 'transitioning') {
                // During interpolation/transition animation
                this.elements.poseTimer.textContent = 'Flow...';
                this.elements.poseTimer.style.color = '#a8c5be';
                if (this.elements.formStatus) {
                    this.elements.formStatus.innerHTML = '<i data-lucide="wind"></i> Smooth transition';
                    this.elements.formStatus.style.color = '#a8c5be';
                    this.refreshIcons();
                }
                return;
            }

            if (this.state === 'establishing') {
                // User is getting into position, form detection is ON but timer paused
                const elapsed = Date.now() - (this.establishingStartTime || Date.now());
                const remaining = Math.max(0, Math.ceil((this.establishingTimeoutMs - elapsed) / 1000));

                if (this.isFormGood) {
                    this.elements.poseTimer.textContent = 'Great!';
                    this.elements.poseTimer.style.color = '#4ade80';
                } else if (remaining <= 5) {
                    this.elements.poseTimer.textContent = `Starting in ${remaining}...`;
                    this.elements.poseTimer.style.color = '#d4a574';
                } else {
                    this.elements.poseTimer.textContent = 'Get Into Pose';
                    this.elements.poseTimer.style.color = '#d4a574';
                }

                // Check if we should transition to ACTIVE_HOLD
                this.checkEstablishingTransition();
                this.broadcastState();
                return;
            }

            if (this.state === 'transition') {
                // During transition, show relax message (legacy)
                this.elements.poseTimer.textContent = 'Relax...';
                this.elements.poseTimer.style.color = '#a8c5be';
                if (this.elements.formStatus) {
                    this.elements.formStatus.innerHTML = '<i data-lucide="wind"></i> Take a breath';
                    this.elements.formStatus.style.color = '#a8c5be';
                    this.refreshIcons();
                }
                return;
            }

            if (this.state === 'positioning') {
                // During positioning, show waiting message (legacy)
                this.elements.poseTimer.textContent = 'Get Ready';
                this.elements.poseTimer.style.color = '#d4a574';
                return;
            }

            // Now we're in 'active' state - check if user has gotten into position
            if (!this.poseTimerStarted) {
                // Track how long user has been trying to get into position
                this.positioningTime = (this.positioningTime || 0) + 1;

                if (this.isFormGood) {
                    // User reached the pose! Start the timer
                    this.poseTimerStarted = true;
                    this.positioningTime = 0;
                    console.log('\n=== POSE TIMER STARTED! ===');
                    console.log(`Pose: ${this.currentPose?.name}, Time: ${this.poseTimeRemaining}s`);
                } else if (this.positioningTime >= 10) {
                    // After 10 seconds of trying, auto-start with gentle encouragement
                    // This prevents users from getting stuck on difficult poses
                    this.poseTimerStarted = true;
                    this.positioningTime = 0;
                    console.log('=== AUTO-STARTING (accessibility mode) ===');
                } else {
                    // Still waiting for user to get into position
                    const remaining = 10 - this.positioningTime;
                    if (remaining <= 5) {
                        this.elements.poseTimer.textContent = `Starting in ${remaining}...`;
                    } else {
                        this.elements.poseTimer.textContent = 'Get Into Pose';
                    }
                    this.elements.poseTimer.style.color = '#d4a574';
                    this.broadcastState();
                    return;
                }
            }

            // Session timer always runs once pose timer starts
            this.sessionElapsed++;
            this.elements.sessionTimer.textContent = this.formatTime(this.sessionElapsed);

            // Progress bar
            const progress = (this.sessionElapsed / this.sessionDuration) * 100;
            this.elements.sessionProgress.style.width = `${Math.min(100, progress)}%`;

            // Track time in each form quality tier (session-wide and per-pose)
            if (this.currentFormLevel === 'perfect') {
                this.formTimeTracking.perfect++;
                this.currentPoseFormTime.perfect++;
            } else if (this.currentFormLevel === 'good') {
                this.formTimeTracking.good++;
                this.currentPoseFormTime.good++;
            } else if (this.currentFormLevel === 'okay') {
                this.formTimeTracking.okay++;
                this.currentPoseFormTime.okay++;
            } else {
                this.formTimeTracking.needsWork++;
                this.currentPoseFormTime.needsWork++;
            }

            // Pose timer counts down ONLY for Perfect/Good (green states)
            if (this.isFormGood) {
                this.poseTimeRemaining--;
                this.goodFormTime++;
                // Timer running - green
                this.elements.poseTimer.style.color = '#4ade80';
            } else {
                // Timer paused - show appropriate color
                if (this.currentFormLevel === 'okay') {
                    this.elements.poseTimer.style.color = '#fb923c';  // Orange
                } else {
                    this.elements.poseTimer.style.color = '#f87171';  // Red
                }
            }

            this.elements.poseTimer.textContent = this.formatPoseTime(this.poseTimeRemaining);

            // Play midpoint encouragement (around halfway through the pose)
            const midpoint = Math.floor(this.poseTimeTotal / 2);
            if (!this.poseMidpointPlayed && this.goodFormTime >= midpoint) {
                this.poseMidpointPlayed = true;
                this.playPoseMidpoint(this.currentPoseIndex);
            }

            // Move to next pose/segment when time runs out - CONTINUOUS FLOW
            if (this.poseTimeRemaining <= 0) {
                console.log(`Pose ${this.currentPoseIndex} complete! Flowing to next...`);

                // Capture pose performance before moving on
                this.capturePosePerformance();

                // Reset tracking for new pose
                this.poseTimerStarted = false;
                this.isFormGood = false;
                this.matchScore = 0;
                this.audioComplete = false;
                this.formCalibrated = false;

                // Play pose end voice (non-blocking - flows into next)
                this.playPoseEnd(this.currentPoseIndex).catch(err => {
                    console.warn('Voice error:', err);
                });

                // Immediately flow into next pose/segment (no break)
                if (this.useManifest) {
                    this.currentSegmentIndex++;
                    this.loadSegment(this.currentSegmentIndex);
                } else {
                    this.currentPoseIndex++;
                    this.loadPose(this.currentPoseIndex);
                }
            }
        }, 1000);
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    formatPoseTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        if (mins > 0) {
            return `${mins}:${String(secs).padStart(2, '0')}`;
        }
        return `0:${String(Math.max(0, secs)).padStart(2, '0')}`;
    }

    togglePause() {
        if (this.state === 'active') {
            this.state = 'paused';
            this.elements.pauseBtn.innerHTML = '<i data-lucide="play" style="margin-right: 6px;"></i>Resume';
        } else if (this.state === 'paused') {
            this.state = 'active';
            this.elements.pauseBtn.innerHTML = '<i data-lucide="pause" style="margin-right: 6px;"></i>Pause';
            this.runDetectionLoop();
        }
        this.refreshIcons();
        this.broadcastState();
    }

    /**
     * Capture current pose performance for session report
     */
    capturePosePerformance() {
        const pose = this.currentPose;
        if (!pose) return;

        const { perfect, good, okay, needsWork } = this.currentPoseFormTime;
        const total = perfect + good + okay + needsWork;

        // Calculate weighted score (same formula as final grade)
        let avgScore = 0;
        if (total > 0) {
            avgScore = Math.round(((perfect * 100) + (good * 85) + (okay * 70) + (needsWork * 40)) / total);
        }

        // Determine which variation was used (if pose has variations)
        let variationUsed = null;
        if (pose.variations && pose.variations.length > 0 && this.currentMatchedVariation) {
            variationUsed = {
                id: this.currentMatchedVariation.id,
                name: this.currentMatchedVariation.name
            };
        }

        // Store pose performance
        this.posePerformance.push({
            id: pose.id,
            name: pose.name,
            sanskrit: pose.sanskrit || '',
            image: pose.image || `/static/images/poses/${pose.id}.png`,
            avgScore: avgScore,
            formTime: { ...this.currentPoseFormTime },
            side: this.currentSegment?.side || null,
            variation: variationUsed
        });

        // Reset for next pose
        this.currentPoseFormTime = {
            perfect: 0,
            good: 0,
            okay: 0,
            needsWork: 0
        };

        // Reset variation tracking for next pose
        this.currentMatchedVariation = null;
        this.variationMatchCounts = {};
    }

    /**
     * Save session data to localStorage for the report page
     */
    saveSessionData() {
        const { perfect, good, okay, needsWork } = this.formTimeTracking;
        const total = perfect + good + okay + needsWork;

        // Calculate overall score
        let avgScore = 0;
        if (total > 0) {
            avgScore = Math.round(((perfect * 100) + (good * 85) + (okay * 70) + (needsWork * 40)) / total);
        }

        // Get session duration from URL params or manifest
        const params = new URLSearchParams(window.location.search);
        const duration = parseInt(params.get('duration')) || Math.round(this.sessionElapsed / 60);

        const sessionData = {
            duration: duration,
            poses: this.posePerformance,
            avgScore: avgScore,
            formTracking: { ...this.formTimeTracking },
            totalTime: this.sessionElapsed,
            completedAt: new Date().toISOString()
        };

        localStorage.setItem('lastYogaSession', JSON.stringify(sessionData));
        console.log('[SESSION] Saved session data:', sessionData);
    }

    endSession() {
        if (confirm('End this session early?')) {
            // Capture current pose before ending
            this.capturePosePerformance();
            this.saveSessionData();

            this.state = 'complete';
            if (this.timerInterval) clearInterval(this.timerInterval);
            window.location.href = '/yoga/report';
        }
    }

    completeSession() {
        this.state = 'complete';
        if (this.timerInterval) clearInterval(this.timerInterval);

        // Stop ambient audio
        this.stopAmbientAudio();

        // Broadcast completion to remote
        this.broadcastState();

        // Capture any remaining pose performance data
        if (this.currentPose && this.currentPoseFormTime.perfect + this.currentPoseFormTime.good +
            this.currentPoseFormTime.okay + this.currentPoseFormTime.needsWork > 0) {
            this.capturePosePerformance();
        }

        // Save session data for report page
        this.saveSessionData();

        // Play session end voice in background
        this.playSessionEnd().catch(err => console.warn('Voice error:', err));

        // Redirect to wellness report after a brief pause for the voice to start
        setTimeout(() => {
            window.location.href = '/yoga/report';
        }, 3000);
    }

    calculateFinalGrade() {
        const { perfect, good, okay, needsWork } = this.formTimeTracking;
        const total = perfect + good + okay + needsWork;

        if (total === 0) {
            return { letter: 'N/A', label: 'No Data', icon: 'question-circle' };
        }

        // Weight each tier: perfect=100, good=85, okay=70, needsWork=40
        const score = ((perfect * 100) + (good * 85) + (okay * 70) + (needsWork * 40)) / total;

        if (score >= 95) return { letter: 'A+', label: 'Outstanding', icon: 'star-fill' };
        if (score >= 90) return { letter: 'A', label: 'Excellent', icon: 'star' };
        if (score >= 85) return { letter: 'B+', label: 'Great', icon: 'trophy' };
        if (score >= 80) return { letter: 'B', label: 'Good', icon: 'hand-thumbs-up' };
        if (score >= 75) return { letter: 'C+', label: 'Nice Effort', icon: 'lightning-charge' };
        if (score >= 70) return { letter: 'C', label: 'Keep Practicing', icon: 'person-arms-up' };
        if (score >= 60) return { letter: 'D', label: 'Getting There', icon: 'flower1' };
        return { letter: 'F', label: 'Keep Trying', icon: 'arrow-up-circle' };
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    new YogaSession();
});
