// --- PosturePro Bulletproof Video Renderer (UI & Logic Sync) ---

(function() {
    // --- Application State ---
    const APP_STATE = { IDLE: 'idle', CALIBRATING: 'calibrating', MONITORING: 'monitoring' };
    let currentState = APP_STATE.IDLE;
    let lastVideoTime = -1;
    let poseLandmarker = null;
    let FilesetResolver = null;
    
    // Baseline Capture
    let baselineLandmarks = null;
    let lastKnownLandmarks = null;
    let calibratedLandmarks = null;  // Store the "ideal" pose from calibration
    let isDeviating = false;         // Immediate deviation flag
    let deviationAmount = 0;         // How far off from ideal

    // === SMOOTHED LANDMARKS - Average over multiple frames ===
    let smoothedLandmarks = null;
    const LANDMARK_SMOOTH_FACTOR = 0.25;  // 25% new data, 75% old (smooth but responsive)

    // Balance scale state
    let balancePosition = 80;        // Start optimistic
    let smoothedBalance = 80;
    let smoothedDeviation = 0;       // Smooth the deviation too
    let badPostureStartTime = null;
    let goodPostureStartTime = null;
    const BAD_POSTURE_NOTIFY_DELAY = 6000;  // 6 seconds before notification
    const ADAPTIVE_BASELINE_DELAY = 10000;  // 10 seconds of good posture
    const BASELINE_BLEND_RATE = 0.15;       // 15% blend rate

    // Audio alert state - beep once when conditions met, don't repeat
    let audioAlertTriggered = false;
    let lastGoodTimeMinutes = 0;
    let lastBadTimeMinutes = 0;

    // === PiP (Picture-in-Picture) State ===
    let pipWindow = null;
    let pipCanvas = null;
    let pipCtx = null;
    let pipStream = null;
    let pipVideo = null;
    let isPipActive = false;
    let currentZone = 'good';  // Track current posture zone for border color

    // === Notification State ===
    let notificationPermission = 'default';
    let notificationsEnabled = true;  // User toggle
    let lastNotificationTime = 0;
    let notificationFrequencyMs = 60000;  // Default: 1 per minute (user configurable)
    const POSTURE_TIPS = [
        { issue: 'fwdHead', tip: 'Pull your head back - try a chin tuck' },
        { issue: 'depth', tip: 'Sit back in your chair' },
        { issue: 'twist', tip: 'Face your screen squarely' },
        { issue: 'shoulderDrop', tip: 'Roll your shoulders back and sit tall' },
        { issue: 'headDrop', tip: 'Lift your chin up slightly' },
        { issue: 'tilt', tip: 'Level your shoulders' },
        { issue: 'lateral', tip: 'Center yourself in front of your screen' },
    ];

    // === Beep/Alert State ===
    let previousPostureZone = 'good';  // Track previous zone for transition detection
    let beepCooldownMs = 30000;  // Default: moderate (30s cooldown)
    let lastBeepTime = 0;


    // --- Person Detection Tracking ---
    let lastLandmarkTime = 0;
    const NO_PERSON_TIMEOUT_MS = 2000;  // 2 seconds without landmarks = show overlay
    let noPersonOverlayVisible = false;

    // --- DOM Reference Map with Strict Guarding ---
    const getSafeEl = (id) => {
        const el = document.getElementById(id);
        if (!el) {
            console.warn(`[MISSING ELEMENT: ${id}]`);
        }
        return el;
    };

    let els = {};
    const initElements = () => {
        els = {
            webcam: getSafeEl('webcam'),
            canvas: getSafeEl('landmark-overlay'),
            calGuide: getSafeEl('cal-guide'),
            progressBar: getSafeEl('progress-bar'),
            progressContainer: getSafeEl('progress-container'),
            countdownEl: getSafeEl('countdown'),
            calibrationLabel: getSafeEl('calibration-label'),
            sessionBtn: getSafeEl('session-btn'),
            statsPanel: getSafeEl('session-stats'),
            settingsPanel: getSafeEl('settings-panel'),
            metricsContainer: getSafeEl('active-issues'),
            goodTimerEl: getSafeEl('good-timer'),
            badTimerEl: getSafeEl('bad-timer'),
            globalTimerEl: getSafeEl('global-session-timer'),
            alertBox: getSafeEl('alert-box'),
            errorOverlay: getSafeEl('error-overlay'),
            errorTitle: getSafeEl('error-title'),
            errorMessage: getSafeEl('error-message'),
            errorRetryBtn: getSafeEl('error-retry-btn'),
            noPersonOverlay: getSafeEl('no-person-overlay')
        };
    };

    // --- Error Display Functions ---
    function showError(title, message, canRetry = true) {
        if (els.errorOverlay) {
            els.errorOverlay.style.display = 'flex';
        }
        if (els.errorTitle) {
            els.errorTitle.textContent = title;
        }
        if (els.errorMessage) {
            els.errorMessage.textContent = message;
        }
        if (els.errorRetryBtn) {
            els.errorRetryBtn.style.display = canRetry ? 'block' : 'none';
        }
        if (els.sessionBtn) {
            els.sessionBtn.classList.remove('btn-loading');
            els.sessionBtn.disabled = true;
        }
    }

    function hideError() {
        if (els.errorOverlay) {
            els.errorOverlay.style.display = 'none';
        }
    }

    function showNoPersonOverlay() {
        if (!noPersonOverlayVisible && els.noPersonOverlay) {
            els.noPersonOverlay.style.display = 'flex';
            noPersonOverlayVisible = true;
        }
    }

    function hideNoPersonOverlay() {
        if (noPersonOverlayVisible && els.noPersonOverlay) {
            els.noPersonOverlay.style.display = 'none';
            noPersonOverlayVisible = false;
        }
    }

    // --- Connection Status UI ---
    function updateConnectionStatus(connected, wasConnectedBefore) {
        const statusEl = document.getElementById('connection-status');
        const dotEl = document.getElementById('connection-dot');
        const textEl = document.getElementById('connection-text');

        if (!statusEl || !dotEl || !textEl) return;

        if (connected) {
            if (wasConnectedBefore) {
                // Reconnected - show briefly then hide
                statusEl.style.display = 'inline-flex';
                statusEl.style.background = 'rgba(76, 175, 80, 0.2)';
                dotEl.style.background = '#4CAF50';
                textEl.textContent = 'Reconnected';
                textEl.style.color = '#4CAF50';

                // Hide after 3 seconds
                setTimeout(() => {
                    statusEl.style.display = 'none';
                }, 3000);
            } else {
                // First connection - don't show anything
                statusEl.style.display = 'none';
            }
        } else {
            // Disconnected - show warning
            statusEl.style.display = 'inline-flex';
            statusEl.style.background = 'rgba(255, 152, 0, 0.2)';
            dotEl.style.background = '#FF9800';
            dotEl.style.animation = 'pulse 1s infinite';
            textEl.textContent = 'Reconnecting...';
            textEl.style.color = '#FF9800';
        }
    }

    // --- Dashboard UI Flip ---
    function showDashboard() {
        if (els.statsPanel) els.statsPanel.classList.add('active');
        if (els.settingsPanel) els.settingsPanel.classList.add('active');
        if (els.calGuide) els.calGuide.style.display = 'none';
        if (els.progressContainer) els.progressContainer.style.display = 'none';
        if (els.calibrationLabel) els.calibrationLabel.style.display = 'none';
        const guide = document.getElementById('guide-steps');
        if (guide) guide.style.display = 'none';
        
        if (els.sessionBtn) {
            els.sessionBtn.disabled = false;
            els.sessionBtn.innerHTML = '<i data-lucide="square" style="margin-right: 8px;"></i>Stop Session';
            els.sessionBtn.style.backgroundColor = "#c97b7b";
            if (window.lucide) window.lucide.createIcons();
        }
        console.log("[UI] Dashboard Activated.");
    }

    // --- Audio Feedback Engine ---
    function playAlertSound() {
        if (getSafeEl('audio-toggle')?.checked === false) return;
        
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(880, audioCtx.currentTime); 
            gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);

            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            oscillator.start();
            oscillator.stop(audioCtx.currentTime + 0.5);
            console.log("[AUDIO] Posture Alert Triggered.");
        } catch (e) {
            console.error("[AUDIO ERROR] Failed to play beep:", e);
        }
    }

    // === NOTIFICATION SYSTEM ===

    async function requestNotificationPermission() {
        if (!('Notification' in window)) {
            console.log('[NOTIFY] Notifications not supported');
            return false;
        }

        if (Notification.permission === 'granted') {
            notificationPermission = 'granted';
            return true;
        }

        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            notificationPermission = permission;
            return permission === 'granted';
        }

        return false;
    }

    function sendPostureNotification(tip) {
        const now = Date.now();

        // Check if notifications are enabled
        if (!notificationsEnabled) {
            return;
        }

        // Throttle notifications based on user setting
        if (now - lastNotificationTime < notificationFrequencyMs) {
            return;
        }

        if (notificationPermission !== 'granted') {
            return;
        }

        try {
            const notification = new Notification('Posture Check', {
                body: tip || 'Time to adjust your posture',
                icon: '/static/images/logo.png',
                badge: '/static/images/logo.png',
                tag: 'posture-alert',  // Replace previous notification
                requireInteraction: false,
                silent: false
            });

            lastNotificationTime = now;

            // Auto-close after 5 seconds
            setTimeout(() => notification.close(), 5000);

            // Focus window when clicked
            notification.onclick = () => {
                window.focus();
                notification.close();
            };

            console.log('[NOTIFY] Sent notification:', tip);
        } catch (e) {
            console.error('[NOTIFY] Failed to send notification:', e);
        }
    }

    function getPostureTipForNotification() {
        const d = lastDeviations;
        if (!d) return 'Check your posture';

        // Find worst issue
        const issues = [
            { val: d.fwdHead || 0, tip: 'Pull your head back - try a chin tuck' },
            { val: d.depth || 0, tip: 'Sit back in your chair' },
            { val: d.twist || 0, tip: 'Face your screen squarely' },
            { val: d.shoulderDrop || 0, tip: 'Roll your shoulders back and sit tall' },
            { val: d.headDrop || 0, tip: 'Lift your chin up slightly' },
            { val: d.tilt || 0, tip: 'Level your shoulders' },
            { val: d.lateral || 0, tip: 'Center yourself' },
        ];

        issues.sort((a, b) => b.val - a.val);
        return issues[0].tip;
    }

    // Trigger alert when entering bad posture
    function triggerPostureAlert() {
        const now = Date.now();

        // Check cooldown (if user set one)
        if (beepCooldownMs > 0 && (now - lastBeepTime) < beepCooldownMs) {
            return;
        }

        // Play beep sound
        playAlertSound();
        lastBeepTime = now;

        // Also send notification
        const tip = getPostureTipForNotification();
        sendPostureNotification(tip);

        console.log('[ALERT] Bad posture detected - beep triggered');
    }

    // === PICTURE-IN-PICTURE SYSTEM ===

    let pipStarting = false;  // Guard against multiple simultaneous start attempts
    let pipInitialized = false;

    function initPipCanvas() {
        if (pipInitialized) return;

        pipCanvas = document.createElement('canvas');
        pipCanvas.width = 480;  // Higher resolution PiP
        pipCanvas.height = 360;
        pipCtx = pipCanvas.getContext('2d');

        // Create video element to hold the canvas stream
        pipVideo = document.createElement('video');
        pipVideo.muted = true;
        pipVideo.playsInline = true;
        pipVideo.autoplay = true;

        // Handle PiP close event
        pipVideo.addEventListener('leavepictureinpicture', () => {
            isPipActive = false;
            pipWindow = null;
            console.log('[PIP] Closed by user');
        });

        pipInitialized = true;
        console.log('[PIP] Canvas initialized');
    }

    function getZoneColor(zone) {
        switch (zone) {
            case 'good': return '#4CAF50';    // Green
            case 'warning': return '#FF9800'; // Orange
            case 'bad': return '#F44336';     // Red
            default: return '#4CAF50';
        }
    }

    function drawPipFrame() {
        if (!pipCtx || !els.webcam || !els.canvas) return;
        if (els.webcam.videoWidth === 0) return;  // Video not ready

        const w = pipCanvas.width;
        const h = pipCanvas.height;
        const borderWidth = 8;
        const borderColor = getZoneColor(currentZone);

        // Clear canvas
        pipCtx.clearRect(0, 0, w, h);

        // Draw border glow
        pipCtx.save();
        pipCtx.shadowBlur = 15;
        pipCtx.shadowColor = borderColor;
        pipCtx.strokeStyle = borderColor;
        pipCtx.lineWidth = borderWidth;
        pipCtx.strokeRect(borderWidth/2, borderWidth/2, w - borderWidth, h - borderWidth);
        pipCtx.restore();

        // Draw webcam feed (scaled down, mirrored) inside border
        const innerX = borderWidth;
        const innerY = borderWidth;
        const innerW = w - (borderWidth * 2);
        const innerH = h - (borderWidth * 2);

        // Mirror both webcam and skeleton together
        pipCtx.save();
        pipCtx.translate(innerX + innerW, innerY);
        pipCtx.scale(-1, 1);

        // Draw webcam
        pipCtx.drawImage(els.webcam, 0, 0, innerW, innerH);

        // Draw skeleton overlay (also mirrored)
        if (els.canvas && els.canvas.width > 0) {
            pipCtx.drawImage(els.canvas, 0, 0, innerW, innerH);
        }

        pipCtx.restore();
    }

    // PiP drawing loop - runs continuously when PiP is active
    function pipLoop() {
        if (!isPipActive) return;
        drawPipFrame();
        requestAnimationFrame(pipLoop);
    }

    async function startPip() {
        // Guards
        if (isPipActive || pipStarting) return;
        if (!els.webcam || els.webcam.videoWidth === 0) {
            console.log('[PIP] Video not ready yet');
            return;
        }
        if (!document.pictureInPictureEnabled) {
            console.log('[PIP] Not supported in this browser');
            return;
        }
        if (document.pictureInPictureElement) {
            console.log('[PIP] Already have a PiP element');
            return;
        }

        pipStarting = true;

        try {
            initPipCanvas();

            // Draw first frame before starting stream
            drawPipFrame();

            // Create stream from canvas (15fps is enough for monitoring)
            if (!pipStream) {
                pipStream = pipCanvas.captureStream(15);
            }

            // Set up video with stream
            if (pipVideo.srcObject !== pipStream) {
                pipVideo.srcObject = pipStream;
            }

            // Wait for video to be ready
            await new Promise((resolve, reject) => {
                if (pipVideo.readyState >= 2) {
                    resolve();
                    return;
                }

                const onCanPlay = () => {
                    pipVideo.removeEventListener('canplay', onCanPlay);
                    pipVideo.removeEventListener('error', onError);
                    resolve();
                };
                const onError = (e) => {
                    pipVideo.removeEventListener('canplay', onCanPlay);
                    pipVideo.removeEventListener('error', onError);
                    reject(e);
                };

                pipVideo.addEventListener('canplay', onCanPlay);
                pipVideo.addEventListener('error', onError);

                // Timeout after 3 seconds
                setTimeout(() => {
                    pipVideo.removeEventListener('canplay', onCanPlay);
                    pipVideo.removeEventListener('error', onError);
                    resolve();  // Try anyway
                }, 3000);
            });

            // Play video
            try {
                await pipVideo.play();
            } catch (playError) {
                // Ignore AbortError - it's usually harmless
                if (playError.name !== 'AbortError') {
                    throw playError;
                }
            }

            // Small delay to ensure video is playing
            await new Promise(r => setTimeout(r, 100));

            // Request PiP
            pipWindow = await pipVideo.requestPictureInPicture();
            isPipActive = true;
            pipStarting = false;

            console.log('[PIP] Started successfully');
            pipLoop();

        } catch (e) {
            console.error('[PIP] Failed to start:', e.message);
            isPipActive = false;
            pipStarting = false;
        }
    }

    async function stopPip() {
        if (!isPipActive && !document.pictureInPictureElement) return;

        try {
            if (document.pictureInPictureElement) {
                await document.exitPictureInPicture();
            }
        } catch (e) {
            console.error('[PIP] Failed to stop:', e);
        }

        isPipActive = false;
        pipWindow = null;
        console.log('[PIP] Stopped');
    }

    function togglePip() {
        if (isPipActive) {
            stopPip();
        } else {
            startPip();
        }
    }

    // Handle page visibility changes
    let hasShownPipPrompt = false;
    let tabHiddenTime = null;
    function handleVisibilityChange() {
        if (currentState !== APP_STATE.MONITORING) return;

        if (document.hidden) {
            // Tab is now hidden
            tabHiddenTime = Date.now();

            if (!isPipActive) {
                // Can't auto-start PiP (requires user gesture)
                // Send a notification reminding user about PiP instead
                if (!hasShownPipPrompt && notificationPermission === 'granted') {
                    try {
                        new Notification('hohm.studio is still watching', {
                            body: 'Click the PiP button to float the video while you work',
                            icon: '/static/images/logo.png',
                            tag: 'pip-reminder',
                            requireInteraction: false,
                            silent: true
                        });
                        hasShownPipPrompt = true;  // Only show once per session
                    } catch (e) {
                        // Ignore notification errors
                    }
                }
            }
        } else {
            // Tab is now visible again
            if (tabHiddenTime) {
                const hiddenDuration = Date.now() - tabHiddenTime;
                // If tab was hidden for more than 30 seconds without PiP,
                // the timer might be inaccurate (detection paused)
                if (hiddenDuration > 30000 && !isPipActive) {
                    console.log(`[VISIBILITY] Tab was hidden for ${Math.round(hiddenDuration/1000)}s without PiP`);
                    // Timer continued but detection may have been paused
                    // This is informational - we don't reset the timer
                }
                tabHiddenTime = null;
            }
        }
    }

    // === Smooth incoming landmarks to remove jitter ---
    function smoothLandmarks(current) {
        if (!smoothedLandmarks) {
            // Initialize with current landmarks
            smoothedLandmarks = JSON.parse(JSON.stringify(current));
            return smoothedLandmarks;
        }

        // Blend new landmarks with smoothed history
        for (let i = 0; i < current.length; i++) {
            if (current[i] && smoothedLandmarks[i]) {
                smoothedLandmarks[i] = {
                    x: smoothedLandmarks[i].x * (1 - LANDMARK_SMOOTH_FACTOR) + current[i].x * LANDMARK_SMOOTH_FACTOR,
                    y: smoothedLandmarks[i].y * (1 - LANDMARK_SMOOTH_FACTOR) + current[i].y * LANDMARK_SMOOTH_FACTOR,
                    z: (smoothedLandmarks[i].z || 0) * (1 - LANDMARK_SMOOTH_FACTOR) + (current[i].z || 0) * LANDMARK_SMOOTH_FACTOR,
                };
            }
        }
        return smoothedLandmarks;
    }

    // --- Balance-Based Posture Check (smooth, non-intrusive) ---
    function checkPostureImmediate(rawCurrent) {
        if (!calibratedLandmarks || !rawCurrent) {
            isDeviating = false;
            deviationAmount = 0;
            return;
        }

        // === SMOOTH THE LANDMARKS FIRST ===
        const current = smoothLandmarks(rawCurrent);

        // Safety check - ensure required landmarks exist
        if (!current[0] || !current[11] || !current[12] ||
            !calibratedLandmarks[0] || !calibratedLandmarks[11] || !calibratedLandmarks[12]) {
            isDeviating = false;
            deviationAmount = 0;
            return;
        }

        // === Y-AXIS (vertical) measurements ===
        const currentShoulderY = (current[11].y + current[12].y) / 2;
        const idealShoulderY = (calibratedLandmarks[11].y + calibratedLandmarks[12].y) / 2;
        const currentNoseY = current[0].y;
        const idealNoseY = calibratedLandmarks[0].y;

        // Shoulder tilt (one shoulder higher than other)
        const currentShoulderAsym = Math.abs(current[11].y - current[12].y);
        const idealShoulderAsym = Math.abs(calibratedLandmarks[11].y - calibratedLandmarks[12].y);

        // === Z-AXIS (depth) measurements - CRITICAL for forward head ===
        const currentNoseZ = current[0].z || 0;
        const idealNoseZ = calibratedLandmarks[0].z || 0;
        const currentShoulderZ = ((current[11].z || 0) + (current[12].z || 0)) / 2;
        const idealShoulderZ = ((calibratedLandmarks[11].z || 0) + (calibratedLandmarks[12].z || 0)) / 2;

        // Forward head: nose moves forward relative to shoulders
        // In MediaPipe, more negative Z = closer to camera
        const currentHeadForward = currentShoulderZ - currentNoseZ;  // How far nose is in front of shoulders
        const idealHeadForward = idealShoulderZ - idealNoseZ;
        const forwardHeadDelta = currentHeadForward - idealHeadForward;  // Positive = head moved forward

        // Overall depth change (leaning toward/away from screen)
        const depthChange = Math.abs(currentShoulderZ - idealShoulderZ);

        // Body lean angle (using Z difference between shoulders)
        const currentShoulderZDiff = Math.abs((current[11].z || 0) - (current[12].z || 0));
        const idealShoulderZDiff = Math.abs((calibratedLandmarks[11].z || 0) - (calibratedLandmarks[12].z || 0));
        const bodyTwist = Math.abs(currentShoulderZDiff - idealShoulderZDiff);

        // === X-AXIS (horizontal) measurements ===
        const currentCenterX = (current[11].x + current[12].x) / 2;
        const idealCenterX = (calibratedLandmarks[11].x + calibratedLandmarks[12].x) / 2;
        const lateralShift = Math.abs(currentCenterX - idealCenterX);

        // Head tilt left/right
        const currentNoseX = current[0].x;
        const idealNoseX = calibratedLandmarks[0].x;
        const headLateralShift = Math.abs(currentNoseX - idealNoseX);

        // === Calculate deviations ===
        const shoulderDrop = Math.max(0, currentShoulderY - idealShoulderY);
        const headDrop = Math.max(0, currentNoseY - idealNoseY);
        const shoulderTilt = Math.abs(currentShoulderAsym - idealShoulderAsym);

        // === VERY WIDE TOLERANCES - Only catch significant deviations ===
        const TOL_SHOULDER_DROP = 0.06;    // 6% - very forgiving
        const TOL_HEAD_DROP = 0.07;        // 7%
        const TOL_TILT = 0.05;             // 5%
        const TOL_LATERAL = 0.08;          // 8%
        const TOL_FORWARD_HEAD = 0.07;     // 7% Z-axis
        const TOL_DEPTH = 0.10;            // 10%
        const TOL_TWIST = 0.06;            // 6%

        // Calculate severity for each metric (0 = in zone, 1+ = outside zone)
        // Using gentler divisors for slower severity ramp-up
        const severities = {
            forwardHead: Math.max(0, Math.abs(forwardHeadDelta) - TOL_FORWARD_HEAD) / 0.08,
            depth: Math.max(0, depthChange - TOL_DEPTH) / 0.10,
            twist: Math.max(0, bodyTwist - TOL_TWIST) / 0.08,
            shoulderDrop: Math.max(0, shoulderDrop - TOL_SHOULDER_DROP) / 0.07,
            headDrop: Math.max(0, headDrop - TOL_HEAD_DROP) / 0.08,
            tilt: Math.max(0, shoulderTilt - TOL_TILT) / 0.06,
            lateral: Math.max(0, Math.max(lateralShift, headLateralShift) - TOL_LATERAL) / 0.08
        };

        // === MAX-BASED SCORING (C) - Only worst metric matters ===
        const worstMetric = Object.entries(severities).reduce((worst, [key, val]) =>
            val > worst.val ? {key, val} : worst, {key: 'none', val: 0});

        const rawDeviation = worstMetric.val;

        // === SMOOTH THE DEVIATION - prevents jittery scale ===
        // Only update if change is significant
        const deviationDelta = Math.abs(rawDeviation - smoothedDeviation);
        if (deviationDelta > 0.03) {  // Only update if change > 3%
            smoothedDeviation = smoothedDeviation * 0.75 + rawDeviation * 0.25;
        }
        deviationAmount = smoothedDeviation;

        // Store for tips
        updateDeviationsForTip(
            severities.forwardHead, severities.depth, severities.twist,
            severities.shoulderDrop, severities.headDrop, severities.tilt, severities.lateral
        );

        // Debug log (less frequent)
        if (Math.random() < 0.01) {
            console.log(`[POSTURE] worst=${worstMetric.key}(${rawDeviation.toFixed(2)}), smoothed=${smoothedDeviation.toFixed(2)}`);
        }

        // === WIDE ZONE-BASED STATUS - Only flag extreme issues ===
        // Good: deviation < 0.8 (very wide tolerance)
        // Warning: deviation 0.8-1.5 (moderately outside)
        // Bad: deviation > 1.5 (clearly extreme)
        let zone;
        if (deviationAmount < 0.8) {
            zone = 'good';
            isDeviating = false;
        } else if (deviationAmount < 1.5) {
            zone = 'warning';
            isDeviating = true;
        } else {
            zone = 'bad';
            isDeviating = true;
        }

        // Detect transition to bad posture and trigger immediate beep
        if (zone === 'bad' && previousPostureZone !== 'bad') {
            // Just entered bad posture - beep immediately
            triggerPostureAlert();
        }
        previousPostureZone = zone;

        // Update current zone for PiP border color
        currentZone = zone;

        // Calculate balance position based on zones
        if (zone === 'good') {
            balancePosition = 95 - (deviationAmount * 40);  // 0->95, 0.8->63
        } else if (zone === 'warning') {
            balancePosition = 63 - ((deviationAmount - 0.8) * 35);  // 0.8->63, 1.5->38
        } else {
            balancePosition = Math.max(10, 38 - ((deviationAmount - 1.5) * 15));
        }

        // === SMOOTHING on balance - prevents swinging ===
        // Only update if change is significant (prevents micro-jitter)
        const balanceDelta = Math.abs(balancePosition - smoothedBalance);
        if (balanceDelta > 0.5) {  // Only move if change > 0.5%
            smoothedBalance = smoothedBalance * 0.80 + balancePosition * 0.20;
        }

        // Update the visual balance indicator
        updateBalanceUI(smoothedBalance, zone);

        // === ADAPTIVE BASELINE (D) - Adjust baseline when doing well ===
        if (zone === 'good') {
            if (!goodPostureStartTime) {
                goodPostureStartTime = Date.now();
            } else if (Date.now() - goodPostureStartTime > ADAPTIVE_BASELINE_DELAY) {
                // Blend calibrated landmarks toward current position
                adaptBaseline(current);
                goodPostureStartTime = Date.now();  // Reset timer
            }
            // Clear bad posture timer
            badPostureStartTime = null;
            if (els.metricsContainer) {
                els.metricsContainer.style.display = 'none';
            }
        } else {
            // Reset good posture timer
            goodPostureStartTime = null;

            // Handle bad posture notifications
            if (zone === 'bad') {
                if (!badPostureStartTime) {
                    badPostureStartTime = Date.now();
                } else if (Date.now() - badPostureStartTime > BAD_POSTURE_NOTIFY_DELAY) {
                    showPostureTip();
                }
            } else {
                // Warning zone - don't notify yet, just reset timer
                badPostureStartTime = null;
                if (els.metricsContainer) {
                    els.metricsContainer.style.display = 'none';
                }
            }
        }
    }

    // === ADAPTIVE BASELINE (D) - Gradually adjust the "ideal" position ===
    function adaptBaseline(current) {
        if (!calibratedLandmarks || !current) return;

        // Blend each landmark toward current position
        for (let i = 0; i < calibratedLandmarks.length; i++) {
            if (calibratedLandmarks[i] && current[i]) {
                calibratedLandmarks[i] = {
                    x: calibratedLandmarks[i].x * (1 - BASELINE_BLEND_RATE) + current[i].x * BASELINE_BLEND_RATE,
                    y: calibratedLandmarks[i].y * (1 - BASELINE_BLEND_RATE) + current[i].y * BASELINE_BLEND_RATE,
                    z: calibratedLandmarks[i].z * (1 - BASELINE_BLEND_RATE) + current[i].z * BASELINE_BLEND_RATE,
                };
            }
        }
        console.log('[ADAPTIVE] Baseline adjusted toward current good posture');
    }

    // --- Update Balance Scale UI ---
    function updateBalanceUI(balance, zone) {
        const indicator = document.getElementById('balance-indicator');
        const statusText = document.getElementById('balance-status');

        if (indicator) {
            indicator.style.left = `${balance}%`;
        }

        if (statusText) {
            // Simple zone-based messages
            if (zone === 'good') {
                if (balance >= 80) {
                    statusText.textContent = 'Great posture!';
                } else {
                    statusText.textContent = 'Good';
                }
                statusText.style.color = '#4CAF50';
            } else if (zone === 'warning') {
                statusText.textContent = 'Adjust slightly';
                statusText.style.color = '#FF9800';
            } else {
                statusText.textContent = 'Sit up straight';
                statusText.style.color = '#F44336';
            }
        }
    }

    // --- Show Posture Tip (only after prolonged bad posture) ---
    // Store the worst deviations for tip display
    let lastDeviations = {};

    function updateDeviationsForTip(fwdHead, depth, twist, shoulderDrop, headDrop, tilt, lateral) {
        lastDeviations = { fwdHead, depth, twist, shoulderDrop, headDrop, tilt, lateral };
    }

    function showPostureTip() {
        if (!els.metricsContainer) return;

        const d = lastDeviations;
        let tip = '';

        // Find the worst issue and give specific advice
        const issues = [
            { val: d.fwdHead || 0, tip: 'Pull your head back - chin tuck' },
            { val: d.depth || 0, tip: 'Sit back in your chair' },
            { val: d.twist || 0, tip: 'Face the screen squarely' },
            { val: d.shoulderDrop || 0, tip: 'Roll shoulders back, sit tall' },
            { val: d.headDrop || 0, tip: 'Lift your chin up' },
            { val: d.tilt || 0, tip: 'Level your shoulders' },
            { val: d.lateral || 0, tip: 'Center yourself' },
        ];

        // Sort by severity and pick the worst
        issues.sort((a, b) => b.val - a.val);
        tip = issues[0].tip;

        els.metricsContainer.style.display = 'block';
        els.metricsContainer.innerHTML = `<strong>Tip:</strong> ${tip}`;
        els.metricsContainer.style.color = '#FF9800';
        els.metricsContainer.style.fontWeight = 'normal';
    }

    // --- Transition Logic ---
    function forceStartActive() {
        if (currentState === APP_STATE.MONITORING) return;
        
        if (lastKnownLandmarks) {
            baselineLandmarks = JSON.parse(JSON.stringify(lastKnownLandmarks));
            console.log("[BASELINE] Captured posture for comparison.");
        }

        console.log("[DEADBOLT] Forcing state to ACTIVE.");
        currentState = APP_STATE.MONITORING;
        showDashboard();
        
        if (window.wsClient && window.wsClient.socket && window.wsClient.socket.readyState === WebSocket.OPEN) {
            window.wsClient.socket.send(JSON.stringify({ action: 'start_session' }));
        }
        startTimer();
    }

    // --- MediaPipe Initialization ---
    async function initAI() {
        const AI_LOAD_TIMEOUT_MS = 15000;  // 15 second timeout

        try {
            console.log("[AI] Initializing Library via Global tasksVision...", window.tasksVision);

            // Check if MediaPipe module loaded
            if (typeof tasksVision === 'undefined') {
                console.error("[AI OFFLINE] window.tasksVision not found.");
                showError(
                    "AI Model Failed to Load",
                    "Could not load pose detection from CDN. Check your internet connection and refresh the page.",
                    true
                );
                return false;
            }

            // Wrap initialization in a timeout promise
            const loadPromise = (async () => {
                FilesetResolver = await tasksVision.FilesetResolver.forVisionTasks(
                    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm"
                );

                poseLandmarker = await tasksVision.PoseLandmarker.createFromOptions(FilesetResolver, {
                    baseOptions: {
                        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
                    },
                    runningMode: "VIDEO"
                });
                return true;
            })();

            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('AI load timeout')), AI_LOAD_TIMEOUT_MS);
            });

            await Promise.race([loadPromise, timeoutPromise]);
            console.log("[AI] Online: PoseLandmarker Loaded.");
            return true;

        } catch (e) {
            console.error("[AI OFFLINE] Initialization Failed:", e);
            poseLandmarker = null;
            showError(
                "AI Model Failed to Load",
                "Pose detection timed out. This may be due to slow internet. Please refresh and try again.",
                true
            );
            return false;
        }
    }

    // --- Check localStorage availability ---
    function isLocalStorageAvailable() {
        try {
            const test = '__storage_test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
            return true;
        } catch (e) {
            return false;
        }
    }

    // --- Check PiP browser support ---
    function isPipSupported() {
        return document.pictureInPictureEnabled &&
               typeof HTMLVideoElement.prototype.requestPictureInPicture === 'function';
    }

    // --- Webcam disconnect detection ---
    let webcamCheckInterval = null;
    function startWebcamMonitoring() {
        if (webcamCheckInterval) return;

        webcamCheckInterval = setInterval(() => {
            if (currentState !== APP_STATE.MONITORING && currentState !== APP_STATE.CALIBRATING) return;

            if (els.webcam) {
                const stream = els.webcam.srcObject;
                if (stream) {
                    const videoTrack = stream.getVideoTracks()[0];
                    if (videoTrack && videoTrack.readyState === 'ended') {
                        console.error('[WEBCAM] Video track ended - camera disconnected');
                        showError(
                            "Camera Disconnected",
                            "Your camera was disconnected. Please reconnect it and refresh the page.",
                            true
                        );
                        stopWebcamMonitoring();
                    }
                }
            }
        }, 2000);  // Check every 2 seconds
    }

    function stopWebcamMonitoring() {
        if (webcamCheckInterval) {
            clearInterval(webcamCheckInterval);
            webcamCheckInterval = null;
        }
    }

    // --- Poor lighting / low visibility detection ---
    let lowVisibilityWarningShown = false;
    let consecutiveLowVisibilityFrames = 0;
    const LOW_VISIBILITY_THRESHOLD = 0.5;  // Visibility below 50%
    const LOW_VISIBILITY_FRAME_THRESHOLD = 30;  // ~1 second of low visibility

    function checkLandmarkVisibility(worldLandmarks) {
        if (!worldLandmarks || lowVisibilityWarningShown) return;

        // Check visibility of key landmarks (shoulders, head)
        const keyLandmarkIndices = [0, 11, 12];  // nose, left shoulder, right shoulder
        let avgVisibility = 0;
        let count = 0;

        for (const idx of keyLandmarkIndices) {
            if (worldLandmarks[idx]?.visibility !== undefined) {
                avgVisibility += worldLandmarks[idx].visibility;
                count++;
            }
        }

        if (count > 0) {
            avgVisibility /= count;

            if (avgVisibility < LOW_VISIBILITY_THRESHOLD) {
                consecutiveLowVisibilityFrames++;

                if (consecutiveLowVisibilityFrames > LOW_VISIBILITY_FRAME_THRESHOLD) {
                    console.warn('[VISIBILITY] Low landmark visibility detected:', avgVisibility.toFixed(2));
                    // Show warning in the active issues container
                    if (els.metricsContainer && currentState === APP_STATE.MONITORING) {
                        els.metricsContainer.style.display = 'block';
                        els.metricsContainer.innerHTML = '<strong>Tip:</strong> Try improving your lighting for better tracking';
                        els.metricsContainer.style.color = '#FF9800';
                    }
                    lowVisibilityWarningShown = true;  // Only show once per session
                }
            } else {
                consecutiveLowVisibilityFrames = 0;  // Reset counter
            }
        }
    }

    // --- Processing Loop ---
    let frameCount = 0;
    function loop() {
        if (currentState === APP_STATE.IDLE) {
            requestAnimationFrame(loop);
            return;
        }

        frameCount++;

        try {
            if (els.webcam && els.webcam.videoWidth > 0) {
                // Remove the lastVideoTime check briefly to see if it helps with reporting lag
                // but keep the sync logic
                if (els.webcam.currentTime === lastVideoTime) {
                   // No new frame, but we still loop
                }
                lastVideoTime = els.webcam.currentTime;
                
                if (els.canvas) {
                    if (els.canvas.width !== els.webcam.videoWidth) {
                        console.log(`[CANVAS SYNC] ${els.webcam.videoWidth}x${els.webcam.videoHeight}`);
                        els.canvas.width = els.webcam.videoWidth;
                        els.canvas.height = els.webcam.videoHeight;
                    }
                    
                    const ctx = els.canvas.getContext('2d');
                    if (ctx) {
                        ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);

                        if (poseLandmarker) {
                            const results = poseLandmarker.detectForVideo(els.webcam, performance.now());
                            if (results && results.landmarks && results.landmarks.length > 0) {
                                // Person detected - update tracking
                                lastLandmarkTime = Date.now();
                                hideNoPersonOverlay();

                                // Use normalized landmarks for drawing, worldLandmarks for analysis (has visibility)
                                const normalizedLandmarks = results.landmarks[0];
                                const worldLandmarks = results.worldLandmarks?.[0] || normalizedLandmarks;

                                // Check for poor lighting conditions
                                checkLandmarkVisibility(worldLandmarks);

                                lastKnownLandmarks = normalizedLandmarks;

                                if (currentState === APP_STATE.MONITORING) {
                                    // During monitoring: analyze posture (this also smooths landmarks)
                                    checkPostureImmediate(normalizedLandmarks);

                                    // Draw ONLY the smoothed skeleton (prevents jitter)
                                    if (smoothedLandmarks) {
                                        drawSkeleton(ctx, smoothedLandmarks);
                                    } else {
                                        drawSkeleton(ctx, normalizedLandmarks);
                                    }
                                } else {
                                    // During calibration: draw raw skeleton
                                    drawSkeleton(ctx, normalizedLandmarks);
                                }

                                // Send normalized landmarks with visibility from world landmarks
                                sendToBackend(normalizedLandmarks, worldLandmarks);
                            } else {
                                // No person detected - check if timeout exceeded
                                if (currentState !== APP_STATE.IDLE && Date.now() - lastLandmarkTime > NO_PERSON_TIMEOUT_MS) {
                                    showNoPersonOverlay();
                                }
                            }
                        } else {
                            if (frameCount % 200 === 0) console.warn("[AI] poseLandmarker not initialized yet.");
                        }
                    }
                }
            }
        } catch (e) {
            console.error("[LOOP ERROR]", e);
        }
        requestAnimationFrame(loop);
    }


    // --- Target Zone Skeleton (subtle, always visible during monitoring) ---
    function drawTargetZone(ctx, points) {
        if (!points || !els.canvas || !Array.isArray(points)) return;
        const w = els.canvas.width;
        const h = els.canvas.height;

        ctx.save();
        ctx.globalAlpha = 0.25;  // Subtle, not distracting
        ctx.strokeStyle = '#FFFFFF';
        ctx.fillStyle = '#FFFFFF';
        ctx.lineWidth = 8;
        ctx.setLineDash([]);

        // Only draw the key posture lines (shoulders, head)
        const connections = [
            [11, 12], // Shoulder line
            [0, 11], [0, 12], // Neck to shoulders
        ];

        connections.forEach(([i1, i2]) => {
            const p1 = points[i1];
            const p2 = points[i2];
            if (p1 && p2) {
                ctx.beginPath();
                ctx.moveTo(p1.x * w, p1.y * h);
                ctx.lineTo(p2.x * w, p2.y * h);
                ctx.stroke();
            }
        });

        // Draw target circles for key joints
        const keyJoints = [0, 11, 12];
        keyJoints.forEach(idx => {
            const p = points[idx];
            if (p) {
                ctx.beginPath();
                ctx.arc(p.x * w, p.y * h, 15, 0, 2 * Math.PI);
                ctx.stroke();
            }
        });

        ctx.restore();
    }

    // --- Main Skeleton Drawing ---
    function drawSkeleton(ctx, points) {
        if (!points || !els.canvas) return;
        const w = els.canvas.width;
        const h = els.canvas.height;

        // Draw target zone FIRST (underneath) - always visible during monitoring
        if (calibratedLandmarks && currentState === APP_STATE.MONITORING) {
            drawTargetZone(ctx, calibratedLandmarks);
        }

        // Determine color based on zone (simple, clear feedback)
        let color;
        if (currentState === APP_STATE.CALIBRATING) {
            color = '#2196F3'; // Blue for calibration
        } else if (!isDeviating) {
            color = '#00FF40';  // Green - in the zone
        } else if (smoothedBalance >= 35) {
            color = '#FFAA00';  // Orange - warning zone
        } else {
            color = '#FF4444';  // Red - bad zone
        }

        ctx.shadowBlur = 8;
        ctx.shadowColor = color;
        ctx.fillStyle = color;
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.setLineDash([]);

        // Draw Skeleton Connections
        const connections = [
            [11, 12], [11, 23], [12, 24], [23, 24], // Torso
            [11, 13], [13, 15], [12, 14], [14, 16], // Arms
            [0, 11], [0, 12], // Neck lines
            [7, 8], // Ear to Ear
            [7, 11], [8, 12] // Ear to Shoulder
        ];

        connections.forEach(([i1, i2]) => {
            const p1 = points[i1];
            const p2 = points[i2];
            if (p1 && p2) {
                ctx.beginPath();
                ctx.moveTo(p1.x * w, p1.y * h);
                ctx.lineTo(p2.x * w, p2.y * h);
                ctx.stroke();
            }
        });

        // Draw Joints
        points.forEach((p, idx) => {
            const importantJoints = [0, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24];
            if (importantJoints.includes(idx)) {
                const size = (idx === 11 || idx === 12 || idx === 0) ? 6 : 3;
                ctx.beginPath();
                ctx.arc(p.x * w, p.y * h, size, 0, 2 * Math.PI);
                ctx.fill();
            }
        });

        ctx.shadowBlur = 0;
    }

    function sendToBackend(normalizedPoints, worldPoints) {
        if (!window.wsClient) {
            console.warn("[SEND] No wsClient");
            return;
        }
        if (!window.wsClient.socket) {
            console.warn("[SEND] No socket");
            return;
        }
        if (window.wsClient.socket.readyState !== WebSocket.OPEN) {
            console.warn("[SEND] Socket not open, state:", window.wsClient.socket.readyState);
            return;
        }
        const now = Date.now();
        if (now - (window.lastSend || 0) < 200) return; // Faster updates (5fps)
        window.lastSend = now;

        const action = currentState === APP_STATE.CALIBRATING ? 'calibrate_landmarks' : 'process_landmarks';

        // Merge normalized (x,y for screen coords) with world (visibility)
        const landmarkObj = {};
        normalizedPoints.forEach((p, i) => {
            const worldP = worldPoints?.[i] || {};
            landmarkObj[i] = {
                x: p.x,
                y: p.y,
                z: p.z,
                // Use visibility from world landmarks, default to 1.0 if not available
                visibility: worldP.visibility ?? 1.0
            };
        });

        window.wsClient.socket.send(JSON.stringify({
            action: action,
            landmarks: landmarkObj
        }));
    }

    // --- Timer System (all tracked on frontend for accuracy) ---
    let timerId = null;
    let sessionStartTime = null;
    let goodTimeSec = 0;
    let badTimeSec = 0;
    let lastTimerUpdate = null;
    let currentPostureStatus = 'good';  // Track current status for timer allocation

    function formatTime(totalSec) {
        const h = Math.floor(totalSec / 3600).toString().padStart(2, '0');
        const m = Math.floor((totalSec % 3600) / 60).toString().padStart(2, '0');
        const s = (totalSec % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }

    function formatTimeShort(totalSec) {
        const m = Math.floor(totalSec / 60);
        const s = (totalSec % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    }

    function startTimer() {
        if (timerId) clearInterval(timerId);

        sessionStartTime = Date.now();
        lastTimerUpdate = sessionStartTime;
        goodTimeSec = 0;
        badTimeSec = 0;
        currentPostureStatus = 'good';

        timerId = setInterval(() => {
            const now = Date.now();
            const deltaSec = (now - lastTimerUpdate) / 1000;
            lastTimerUpdate = now;

            // Accumulate time based on current posture status
            if (currentPostureStatus === 'bad') {
                badTimeSec += deltaSec;
            } else {
                goodTimeSec += deltaSec;
            }

            // Update session timer
            const totalSec = Math.floor((now - sessionStartTime) / 1000);
            if (els.globalTimerEl) {
                els.globalTimerEl.innerText = formatTime(totalSec);
            }

            // Update good/bad timers
            if (els.goodTimerEl) {
                els.goodTimerEl.innerText = formatTimeShort(Math.floor(goodTimeSec));
            }
            if (els.badTimerEl) {
                els.badTimerEl.innerText = formatTimeShort(Math.floor(badTimeSec));
            }
        }, 100);  // Update every 100ms for smooth display
    }

    function updatePostureStatus(status) {
        // Called when we receive status from backend
        // 'good' or 'warning' = good posture, 'bad' = bad posture
        currentPostureStatus = (status === 'bad') ? 'bad' : 'good';
    }

    function getSessionStats() {
        // Return current stats for saving
        return {
            goodTimeSec: goodTimeSec,
            badTimeSec: badTimeSec,
            totalSec: (Date.now() - sessionStartTime) / 1000
        };
    }

    // --- Interaction ---
    async function startSession() {
        initElements();
        hideError();
        console.log("[SESSION] Starting...");

        // Show loading state
        if (els.sessionBtn) {
            els.sessionBtn.classList.add('btn-loading');
            els.sessionBtn.disabled = true;
        }

        // Step 1: Get camera access
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
            if (els.webcam) els.webcam.srcObject = stream;
            // Start monitoring for camera disconnection
            startWebcamMonitoring();
        } catch (e) {
            console.error("[CAMERA ERROR]", e);

            // Determine specific error message
            let errorTitle = "Camera Error";
            let errorMsg = "Unable to access your camera.";

            if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
                errorTitle = "Camera Access Denied";
                errorMsg = "Please allow camera access in your browser settings and try again.";
            } else if (e.name === 'NotFoundError' || e.name === 'DevicesNotFoundError') {
                errorTitle = "No Camera Found";
                errorMsg = "No camera detected. Please connect a camera and try again.";
            } else if (e.name === 'NotReadableError' || e.name === 'TrackStartError') {
                errorTitle = "Camera In Use";
                errorMsg = "Your camera may be in use by another application. Please close other apps and try again.";
            }

            showError(errorTitle, errorMsg);
            return;
        }

        // Step 2: Initialize AI (MediaPipe)
        if (!poseLandmarker) {
            const aiLoaded = await initAI();
            if (!aiLoaded) {
                showError("AI Failed to Load", "Could not load pose detection. Please refresh the page and try again.");
                return;
            }
        }

        currentState = APP_STATE.CALIBRATING;
        lastLandmarkTime = Date.now();  // Initialize tracking

        if (els.sessionBtn) {
            els.sessionBtn.classList.remove('btn-loading');
            els.sessionBtn.disabled = true;
            els.sessionBtn.innerHTML = '<i data-lucide="target" style="margin-right: 8px;"></i>Aligning...';
            if (window.lucide) window.lucide.createIcons();
        }
        if (els.calibrationLabel) {
            els.calibrationLabel.style.display = 'block';
            els.calibrationLabel.innerText = 'ALIGNING...';
            els.calibrationLabel.style.background = 'rgba(33, 150, 243, 0.8)';
        }
        if (els.progressContainer) {
            els.progressContainer.style.display = 'block';
            if (els.progressBar) els.progressBar.style.width = '0%';
        }

        loop();
    }

    // --- Send final stats before session ends ---
    function sendFinalStats() {
        if (!window.wsClient || !window.wsClient.socket ||
            window.wsClient.socket.readyState !== WebSocket.OPEN) {
            return;
        }

        const stats = {
            action: 'update_session_stats',
            good_time_sec: goodTimeSec,
            bad_time_sec: badTimeSec,
            total_time_sec: sessionStartTime ? (Date.now() - sessionStartTime) / 1000 : 0
        };

        window.wsClient.socket.send(JSON.stringify(stats));
        console.log("[SESSION] Sent final stats:", stats);
    }

    // --- Entry Point ---
    window.addEventListener('load', () => {
        initElements();

        // Check localStorage availability for consent
        if (!isLocalStorageAvailable()) {
            console.warn('[STORAGE] localStorage not available - consent may not persist');
            // Show warning but don't block - user can still use the app
        }

        // Request notification permission early
        requestNotificationPermission();

        // Add visibility change listener for auto-PiP
        document.addEventListener('visibilitychange', handleVisibilityChange);

        // Set up PiP button if it exists - check browser support first
        const pipBtn = document.getElementById('pip-btn');
        if (pipBtn) {
            if (isPipSupported()) {
                pipBtn.onclick = togglePip;
            } else {
                pipBtn.disabled = true;
                pipBtn.title = 'Picture-in-Picture not supported in this browser';
                pipBtn.style.opacity = '0.5';
                pipBtn.style.cursor = 'not-allowed';
                console.log('[PIP] Not supported in this browser');
            }
        }

        // Set up notification toggle
        const notifyToggle = document.getElementById('notify-toggle');
        if (notifyToggle) {
            notifyToggle.onchange = (e) => {
                notificationsEnabled = e.target.checked;
                console.log('[SETTINGS] Notifications:', notificationsEnabled ? 'ON' : 'OFF');
            };
        }

        // Set up alert frequency selector
        const alertFrequency = document.getElementById('alert-frequency');
        if (alertFrequency) {
            alertFrequency.onchange = (e) => {
                const value = e.target.value;
                if (value === 'always') {
                    beepCooldownMs = 0;
                    notificationFrequencyMs = 10000;  // 10s min for notifications
                } else if (value === 'moderate') {
                    beepCooldownMs = 30000;  // 30s cooldown
                    notificationFrequencyMs = 60000;
                } else if (value === 'relaxed') {
                    beepCooldownMs = 60000;  // 1 min cooldown
                    notificationFrequencyMs = 120000;
                }
                console.log('[SETTINGS] Alert frequency:', value, 'cooldown:', beepCooldownMs);
            };
        }

        if (els.sessionBtn) {
            els.sessionBtn.onclick = () => {
                if (currentState === APP_STATE.IDLE) {
                    startSession();
                } else {
                    // Stop PiP before ending session
                    stopPip();
                    // Send final stats before ending
                    sendFinalStats();
                    // Small delay to ensure message is sent
                    setTimeout(() => location.reload(), 100);
                }
            };
        }

        // Also send stats when page is about to unload
        window.addEventListener('beforeunload', () => {
            if (currentState === APP_STATE.MONITORING) {
                sendFinalStats();
            }
        });

        // Error retry button - reload the page
        if (els.errorRetryBtn) {
            els.errorRetryBtn.onclick = () => location.reload();
        }

        if (window.wsClient) {
            // Set up connection state change handler
            window.wsClient.onConnectionChange = (connected, wasConnectedBefore) => {
                updateConnectionStatus(connected, wasConnectedBefore);

                // If reconnected during an active session, restart the session on backend
                if (connected && wasConnectedBefore && currentState === APP_STATE.MONITORING) {
                    console.log("[SESSION] Reconnected during active session - restarting backend session");
                    window.wsClient.startSession();
                }
            };

            // Set up message handler BEFORE connecting
            window.wsClient.onMessage = (msg) => {
                try {
                    if (msg.type === 'calibration_progress') {
                        if (els.calibrationLabel) {
                            els.calibrationLabel.innerText = msg.data.instruction.toUpperCase();
                            els.calibrationLabel.style.background = msg.data.is_collecting ? 'rgba(76, 175, 80, 0.9)' : 'rgba(33, 150, 243, 0.8)';
                        }
                        if (els.progressBar) {
                            els.progressBar.style.width = `${(msg.data.count / msg.data.total) * 100}%`;
                            els.progressBar.style.background = msg.data.is_collecting ? '#4CAF50' : '#2196F3';
                        }
                    } else if (msg.type === 'calibration_warning') {
                        // Handle no-detection warning during calibration
                        if (els.calibrationLabel) {
                            els.calibrationLabel.innerText = msg.data.message.toUpperCase();
                            els.calibrationLabel.style.background = 'rgba(255, 152, 0, 0.9)'; // Orange warning
                        }
                    } else if (msg.type === 'calibration_complete') {
                        console.log("[CALIBRATION] Complete! Transitioning to monitoring...");
                        // Store calibrated pose as the "ideal" reference
                        if (lastKnownLandmarks) {
                            calibratedLandmarks = JSON.parse(JSON.stringify(lastKnownLandmarks));
                            console.log("[CALIBRATION] Stored ideal pose reference");
                        }
                        forceStartActive();
                    } else if (msg.type === 'metrics' && currentState === APP_STATE.MONITORING) {
                        const score = msg.data.score;
                        const status = msg.data.status;
                        const issues = msg.data.current_issues;

                        // Update posture status for timer tracking
                        // Only "good" counts as good time, "warning" and "bad" count as bad time
                        const isGoodPosture = (status === 'good');
                        updatePostureStatus(isGoodPosture ? 'good' : 'bad');

                        // Debug log
                        if (Math.random() < 0.05) {  // Log 5% of updates
                            console.log(`[POSTURE] Score: ${score}, Status: ${status}, Timer: ${isGoodPosture ? 'GOOD' : 'BAD'}`);
                        }

                        // Beep logic is now handled in checkPostureImmediate()
                        // via zone transition detection (triggerPostureAlert)

                        // Hide the intrusive alert box - we use the balance scale now
                        if (els.alertBox) els.alertBox.style.display = 'none';
                    } else if (msg.type === 'alert') {
                        // Backend alerts are now disabled in favor of frontend timer-based logic
                        console.log("[ALERT]", msg.data.message);
                        // Don't play sound here - we handle it above based on timer comparison
                    } else if (msg.type === 'session_started') {
                        console.log("[SESSION] Started with ID:", msg.data.session_id);
                    } else if (msg.type === 'session_stopped') {
                        console.log("[SESSION] Stopped:", msg.data);
                    }
                } catch (err) {
                    console.error("[WS MSG ERROR]", err);
                }
            };

            // Connect AFTER setting up handlers
            window.wsClient.connect();
        }
    });
})();
