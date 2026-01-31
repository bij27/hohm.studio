/**
 * Skeleton Interpolation Module
 * Provides smooth keyframe blending for fluid pose transitions with easing functions.
 */

/**
 * Easing functions for smooth transitions.
 * All functions take t in [0, 1] and return a value in [0, 1].
 */
const Easings = {
    /**
     * Linear interpolation (no easing).
     */
    linear: (t) => t,

    /**
     * Ease in with quadratic curve (slow start).
     */
    easeIn: (t) => t * t,

    /**
     * Ease out with quadratic curve (slow end).
     */
    easeOut: (t) => t * (2 - t),

    /**
     * Ease in-out with quadratic curve (slow start and end).
     * This is the default for yoga transitions.
     */
    easeInOut: (t) => {
        return t < 0.5
            ? 2 * t * t
            : 1 - Math.pow(-2 * t + 2, 2) / 2;
    },

    /**
     * Ease in with cubic curve (slower start).
     */
    easeInCubic: (t) => t * t * t,

    /**
     * Ease out with cubic curve (slower end).
     */
    easeOutCubic: (t) => 1 - Math.pow(1 - t, 3),

    /**
     * Ease in-out with cubic curve (smoother).
     */
    easeInOutCubic: (t) => {
        return t < 0.5
            ? 4 * t * t * t
            : 1 - Math.pow(-2 * t + 2, 3) / 2;
    },

    /**
     * Smooth step - S-curve with zero derivatives at endpoints.
     */
    smoothStep: (t) => t * t * (3 - 2 * t),

    /**
     * Smoother step - even smoother S-curve.
     */
    smootherStep: (t) => t * t * t * (t * (t * 6 - 15) + 10)
};

/**
 * Linear interpolation between two values.
 * @param {number} start - Start value
 * @param {number} end - End value
 * @param {number} t - Interpolation factor [0, 1]
 * @returns {number} Interpolated value
 */
function lerp(start, end, t) {
    return start + (end - start) * t;
}

/**
 * Interpolate between two landmark positions.
 * @param {Object} start - Start landmark {x, y, z, visibility}
 * @param {Object} end - End landmark {x, y, z, visibility}
 * @param {number} t - Interpolation factor [0, 1]
 * @returns {Object} Interpolated landmark
 */
function lerpLandmark(start, end, t) {
    return {
        x: lerp(start.x || 0, end.x || 0, t),
        y: lerp(start.y || 0, end.y || 0, t),
        z: lerp(start.z || 0, end.z || 0, t),
        visibility: lerp(start.visibility || 1, end.visibility || 1, t),
        name: start.name || end.name
    };
}

/**
 * Interpolate between two complete landmark arrays.
 * @param {Array} startLandmarks - Array of 33 start landmarks
 * @param {Array} endLandmarks - Array of 33 end landmarks
 * @param {number} t - Interpolation factor [0, 1]
 * @returns {Array} Array of 33 interpolated landmarks
 */
function lerpLandmarks(startLandmarks, endLandmarks, t) {
    if (!startLandmarks || !endLandmarks) {
        return endLandmarks || startLandmarks || [];
    }

    const result = [];
    const length = Math.max(startLandmarks.length, endLandmarks.length);

    for (let i = 0; i < length; i++) {
        const start = startLandmarks[i] || { x: 0, y: 0, z: 0, visibility: 0 };
        const end = endLandmarks[i] || { x: 0, y: 0, z: 0, visibility: 0 };
        result.push(lerpLandmark(start, end, t));
    }

    return result;
}

/**
 * SkeletonInterpolator class for smooth keyframe blending.
 * Manages interpolation state and provides frame-by-frame updates.
 */
class SkeletonInterpolator {
    /**
     * Create a new interpolator.
     * @param {Array} startLandmarks - Starting landmark positions
     * @param {Array} endLandmarks - Target landmark positions
     * @param {number} durationMs - Duration of interpolation in milliseconds
     * @param {string} easingName - Name of easing function (default: "easeInOut")
     */
    constructor(startLandmarks, endLandmarks, durationMs, easingName = "easeInOut") {
        this.startLandmarks = startLandmarks;
        this.endLandmarks = endLandmarks;
        this.durationMs = durationMs;
        this.easingName = easingName;
        this.easing = Easings[easingName] || Easings.easeInOut;

        this.elapsedMs = 0;
        this.currentLandmarks = startLandmarks ? [...startLandmarks] : [];
        this.isComplete = false;

        // Callbacks
        this.onProgress = null;
        this.onComplete = null;
    }

    /**
     * Update the interpolation state.
     * @param {number} deltaMs - Time elapsed since last update in milliseconds
     * @returns {Array} Current interpolated landmarks
     */
    update(deltaMs) {
        if (this.isComplete) {
            return this.endLandmarks;
        }

        this.elapsedMs += deltaMs;

        // Calculate raw progress [0, 1]
        const rawT = Math.min(1, this.elapsedMs / this.durationMs);

        // Apply easing
        const easedT = this.easing(rawT);

        // Interpolate landmarks
        this.currentLandmarks = lerpLandmarks(this.startLandmarks, this.endLandmarks, easedT);

        // Call progress callback
        if (this.onProgress) {
            this.onProgress(rawT, easedT, this.currentLandmarks);
        }

        // Check for completion
        if (rawT >= 1) {
            this.isComplete = true;
            this.currentLandmarks = this.endLandmarks;

            if (this.onComplete) {
                this.onComplete();
            }
        }

        return this.currentLandmarks;
    }

    /**
     * Get current progress as a percentage.
     * @returns {number} Progress percentage [0, 100]
     */
    getProgress() {
        return Math.min(100, (this.elapsedMs / this.durationMs) * 100);
    }

    /**
     * Get the current interpolated landmarks.
     * @returns {Array} Current landmarks
     */
    getCurrentLandmarks() {
        return this.currentLandmarks;
    }

    /**
     * Check if interpolation is complete.
     * @returns {boolean} True if complete
     */
    isFinished() {
        return this.isComplete;
    }

    /**
     * Reset the interpolator to start again.
     */
    reset() {
        this.elapsedMs = 0;
        this.isComplete = false;
        this.currentLandmarks = this.startLandmarks ? [...this.startLandmarks] : [];
    }

    /**
     * Set new target landmarks (for dynamic retargeting).
     * @param {Array} newEndLandmarks - New target landmarks
     * @param {boolean} resetProgress - Whether to reset progress (default: false)
     */
    setTarget(newEndLandmarks, resetProgress = false) {
        if (resetProgress) {
            this.startLandmarks = this.currentLandmarks;
            this.elapsedMs = 0;
            this.isComplete = false;
        }
        this.endLandmarks = newEndLandmarks;
    }
}

/**
 * InterpolationManager for managing multiple concurrent interpolations.
 * Useful for complex transitions involving multiple skeleton overlays.
 */
class InterpolationManager {
    constructor() {
        this.interpolators = new Map();
        this.lastUpdateTime = performance.now();
    }

    /**
     * Create a new interpolation.
     * @param {string} id - Unique identifier for this interpolation
     * @param {Array} startLandmarks - Starting landmarks
     * @param {Array} endLandmarks - Target landmarks
     * @param {number} durationMs - Duration in milliseconds
     * @param {string} easing - Easing function name
     * @returns {SkeletonInterpolator} The created interpolator
     */
    create(id, startLandmarks, endLandmarks, durationMs, easing = "easeInOut") {
        const interpolator = new SkeletonInterpolator(startLandmarks, endLandmarks, durationMs, easing);
        this.interpolators.set(id, interpolator);
        return interpolator;
    }

    /**
     * Get an interpolator by ID.
     * @param {string} id - Interpolator ID
     * @returns {SkeletonInterpolator|undefined}
     */
    get(id) {
        return this.interpolators.get(id);
    }

    /**
     * Remove an interpolator.
     * @param {string} id - Interpolator ID
     */
    remove(id) {
        this.interpolators.delete(id);
    }

    /**
     * Update all active interpolators.
     * @param {number} [currentTime] - Current timestamp (default: performance.now())
     * @returns {Map} Map of ID to current landmarks
     */
    updateAll(currentTime = performance.now()) {
        const deltaMs = currentTime - this.lastUpdateTime;
        this.lastUpdateTime = currentTime;

        const results = new Map();
        const completed = [];

        for (const [id, interpolator] of this.interpolators) {
            const landmarks = interpolator.update(deltaMs);
            results.set(id, landmarks);

            if (interpolator.isFinished()) {
                completed.push(id);
            }
        }

        // Optionally clean up completed interpolators
        // (commented out to allow manual cleanup for better control)
        // completed.forEach(id => this.interpolators.delete(id));

        return results;
    }

    /**
     * Check if any interpolations are active.
     * @returns {boolean}
     */
    hasActive() {
        for (const interpolator of this.interpolators.values()) {
            if (!interpolator.isFinished()) {
                return true;
            }
        }
        return false;
    }

    /**
     * Clear all interpolators.
     */
    clear() {
        this.interpolators.clear();
    }
}

/**
 * Ghost skeleton renderer for showing interpolated target during transitions.
 * Renders a semi-transparent "ghost" of where the user should move to.
 */
class GhostSkeletonRenderer {
    /**
     * Create a ghost skeleton renderer.
     * @param {CanvasRenderingContext2D} ctx - Canvas context
     * @param {Object} options - Rendering options
     */
    constructor(ctx, options = {}) {
        this.ctx = ctx;
        this.options = {
            color: options.color || 'rgba(251, 191, 36, 0.6)',  // Yellow/gold
            lineWidth: options.lineWidth || 4,
            dashPattern: options.dashPattern || [8, 8],
            jointRadius: options.jointRadius || 8,
            jointColor: options.jointColor || 'rgba(251, 191, 36, 0.4)',
            fadeInDuration: options.fadeInDuration || 500,  // ms
            fadeOutDuration: options.fadeOutDuration || 300  // ms
        };

        this.opacity = 0;
        this.targetOpacity = 0;
        this.fadeStartTime = null;
    }

    /**
     * Show the ghost skeleton (fade in).
     */
    show() {
        this.targetOpacity = 1;
        this.fadeStartTime = performance.now();
    }

    /**
     * Hide the ghost skeleton (fade out).
     */
    hide() {
        this.targetOpacity = 0;
        this.fadeStartTime = performance.now();
    }

    /**
     * Update opacity for fading.
     * @param {number} currentTime - Current timestamp
     */
    updateFade(currentTime) {
        if (this.fadeStartTime === null) return;

        const elapsed = currentTime - this.fadeStartTime;
        const duration = this.targetOpacity === 1
            ? this.options.fadeInDuration
            : this.options.fadeOutDuration;

        const progress = Math.min(1, elapsed / duration);

        if (this.targetOpacity === 1) {
            this.opacity = progress;
        } else {
            this.opacity = 1 - progress;
        }

        if (progress >= 1) {
            this.fadeStartTime = null;
        }
    }

    /**
     * Render the ghost skeleton.
     * @param {Array} landmarks - Landmarks to render
     * @param {Object} transform - Transform info for scaling/positioning
     */
    render(landmarks, transform = null) {
        if (this.opacity <= 0 || !landmarks || landmarks.length === 0) return;

        const ctx = this.ctx;
        const width = ctx.canvas.width;
        const height = ctx.canvas.height;

        ctx.save();
        ctx.globalAlpha = this.opacity * 0.6;
        ctx.strokeStyle = this.options.color;
        ctx.lineWidth = this.options.lineWidth;
        ctx.setLineDash(this.options.dashPattern);

        // Transform function (can apply user-body-relative scaling)
        const transformPoint = (lm) => {
            if (transform) {
                const x = (lm.x - transform.refCenterX) * transform.scale + transform.userCenterX;
                const y = (lm.y - transform.refCenterY) * transform.scale + transform.userCenterY;
                return { x: x * width, y: y * height };
            }
            return { x: lm.x * width, y: lm.y * height };
        };

        // Define pose connections (same as MediaPipe)
        const connections = [
            [11, 12], // shoulders
            [11, 13], [13, 15], // left arm
            [12, 14], [14, 16], // right arm
            [11, 23], [12, 24], // torso sides
            [23, 24], // hips
            [23, 25], [25, 27], // left leg
            [24, 26], [26, 28], // right leg
        ];

        // Draw connections
        for (const [i, j] of connections) {
            const p1 = landmarks[i];
            const p2 = landmarks[j];
            if (p1 && p2) {
                const t1 = transformPoint(p1);
                const t2 = transformPoint(p2);
                ctx.beginPath();
                ctx.moveTo(t1.x, t1.y);
                ctx.lineTo(t2.x, t2.y);
                ctx.stroke();
            }
        }

        // Draw joints
        ctx.setLineDash([]);
        ctx.fillStyle = this.options.jointColor;
        const jointIndices = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];
        for (const i of jointIndices) {
            const p = landmarks[i];
            if (p) {
                const t = transformPoint(p);
                ctx.beginPath();
                ctx.arc(t.x, t.y, this.options.jointRadius, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        ctx.restore();
    }
}

// Export for use in yoga-session.js
if (typeof window !== 'undefined') {
    window.YogaInterpolation = {
        Easings,
        lerp,
        lerpLandmark,
        lerpLandmarks,
        SkeletonInterpolator,
        InterpolationManager,
        GhostSkeletonRenderer
    };
}

// Also export as ES module if supported
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        Easings,
        lerp,
        lerpLandmark,
        lerpLandmarks,
        SkeletonInterpolator,
        InterpolationManager,
        GhostSkeletonRenderer
    };
}
