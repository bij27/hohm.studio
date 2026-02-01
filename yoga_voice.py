"""
Yoga Voice Guide System
Uses Edge TTS to generate nurturing, calm voice guidance for yoga sessions.
"""

import edge_tts
import asyncio
import hashlib
import os
import random
from pathlib import Path
from typing import List, Dict, Optional
from utils.debug import debug_log as _debug_log


# Voice configuration - Indian-British female voice
VOICE = "en-IN-NeerjaNeural"  # Warm, clear Indian English female
VOICE_RATE = "-10%"  # Slightly slower for calm delivery
VOICE_PITCH = "-5Hz"  # Slightly lower for soothing tone

# Audio cache directory
AUDIO_CACHE_DIR = Path("static/audio/voice")


class YogaScriptGenerator:
    """Generates nurturing, linear yoga session scripts."""

    # Session opening phrases
    WELCOMES = [
        "Welcome to your {duration} minute yoga session.",
        "Hello, and welcome to your {duration} minute practice.",
        "Namaste. Welcome to your {duration} minute yoga journey.",
    ]

    # Side-aware phrases for bilateral poses
    LEFT_SIDE_INTROS = [
        "Let's start on your left side.",
        "We'll begin with your left side.",
        "Starting on the left.",
        "First, on your left side.",
    ]

    RIGHT_SIDE_INTROS = [
        "Now, let's mirror that on your right side.",
        "Switching to your right side.",
        "Now the same on your right.",
        "Let's balance with the right side.",
        "And now, your right side.",
    ]

    SET_TRANSITIONS = [
        "Beautiful. Now let's transition to the other side.",
        "Wonderful work. Time to switch sides.",
        "Lovely. Let's balance that out on the other side.",
        "Great form. Now mirror that pose.",
        "Well done. Same pose, opposite side.",
    ]

    SIDE_SPECIFIC_CUES = {
        "left": {
            "leg": "your left leg",
            "arm": "your left arm",
            "foot": "your left foot",
            "hand": "your left hand",
            "hip": "your left hip",
            "knee": "your left knee",
        },
        "right": {
            "leg": "your right leg",
            "arm": "your right arm",
            "foot": "your right foot",
            "hand": "your right hand",
            "hip": "your right hip",
            "knee": "your right knee",
        }
    }

    SESSION_INTROS = [
        "Today, we'll be flowing through {pose_count} poses, focusing on {focus_area}.",
        "In this session, we'll practice {pose_count} poses to help you {focus_benefit}.",
        "We have {pose_count} beautiful poses planned for you today.",
    ]

    OPENING_INSTRUCTIONS = [
        "Find a comfortable space, take a deep breath, and let's begin.",
        "Take a moment to center yourself. When you're ready, we'll start together.",
        "Ground yourself, breathe deeply, and prepare your body for movement.",
    ]

    # Pose introduction phrases
    POSE_INTROS = [
        "Let's move into {pose_name}.",
        "Now, we'll practice {pose_name}.",
        "Our next pose is {pose_name}.",
        "Gently transition into {pose_name}.",
    ]

    FIRST_POSE_INTROS = [
        "We'll begin with {pose_name}.",
        "Let's start our practice with {pose_name}.",
        "Our opening pose is {pose_name}.",
    ]

    # Pose instruction templates (customized per pose)
    POSE_INSTRUCTIONS = {
        "mountain_pose": "Stand tall with your feet together, arms relaxed at your sides. Feel the ground beneath you.",
        "warrior_i": "Step one foot back, bend your front knee, and raise your arms overhead. Feel your strength.",
        "warrior_ii": "Open your hips to the side, extend your arms parallel to the ground, and gaze over your front hand.",
        "tree_pose": "Shift your weight to one leg, place the other foot on your inner thigh or calf, and find your balance.",
        "downward_dog": "Form an inverted V shape, pressing your hands and feet into the ground. Let your head hang freely.",
        "cobra_pose": "Lie on your belly, place your hands under your shoulders, and gently lift your chest.",
        "child_pose": "Kneel down, sit back on your heels, and fold forward with your arms extended or by your sides.",
        "seated_forward_bend": "Sit with your legs extended, inhale to lengthen your spine, and fold forward over your legs.",
    }

    DEFAULT_INSTRUCTION = "Follow the visual guide on screen and align your body with the target pose."

    # Hold encouragements
    HOLD_PHRASES = [
        "Hold this pose and breathe deeply.",
        "Maintain the position. You're doing wonderfully.",
        "Stay present in this pose. Feel your breath.",
        "Keep holding. Notice the sensations in your body.",
    ]

    # Breath cues for vinyasa style
    INHALE_CUES = [
        "Inhale deeply.",
        "Take a slow breath in.",
        "Breathe in.",
        "Inhale, expanding your chest.",
    ]

    EXHALE_CUES = [
        "Exhale slowly.",
        "Breathe out.",
        "Release the breath.",
        "Exhale, letting go of tension.",
    ]

    BREATH_HOLDS = [
        "Continue breathing steadily.",
        "Match each movement to your breath.",
        "Let your breath guide you.",
        "Inhale to lengthen, exhale to deepen.",
        "Breathe naturally and stay present.",
    ]

    # Form feedback
    GOOD_FORM = [
        "Beautiful form. Keep it up.",
        "You're aligned perfectly. Well done.",
        "Excellent posture. Stay with it.",
    ]

    ADJUST_FORM = [
        "Gently adjust your position to match the guide.",
        "Take a moment to realign with the target pose.",
        "Softly correct your form when you're ready.",
        "Notice where you can adjust to get closer to the target.",
        "Follow the yellow guide on screen for alignment.",
        "Small adjustments make a big difference.",
        "Check your alignment with the target pose.",
        "Keep breathing as you adjust your position.",
    ]

    # Pose completion (for flowing transitions - no stopping)
    POSE_COMPLETE = [
        "Beautiful. Now flow with me.",
        "Lovely. Let's continue moving.",
        "Wonderful. Keep flowing.",
        "Well done. Stay with the movement.",
    ]

    # Flowing transitions (continuous movement, no breaks)
    FLOW_TRANSITIONS = [
        "Smoothly transition now.",
        "Flow into the next position.",
        "Let the movement guide you.",
        "Seamlessly move forward.",
        "Continue the flow.",
        "Keep moving with your breath.",
    ]

    # Rotation switch (right side to left side)
    ROTATION_SWITCH = [
        "Excellent work on the right side. Now, let's mirror everything on your left.",
        "Beautiful flow. Time to balance with your left side.",
        "Right side complete. Let's bring that same energy to your left.",
        "Wonderful. Now we'll repeat the sequence on your left side.",
    ]

    # Legacy transitions (kept for compatibility)
    TRANSITIONS = [
        "Take a breath, and let's move on.",
        "When you're ready, we'll continue to the next pose.",
        "Wonderful work. Let's flow into our next position.",
        "Rest for a moment, then we'll continue.",
    ]

    # Encouragements (used periodically)
    ENCOURAGEMENTS = [
        "You're doing wonderfully.",
        "Stay present and breathe.",
        "Trust your body.",
        "Each breath brings you deeper into the practice.",
        "You're making beautiful progress.",
        "Honor where you are today.",
        "Listen to your body and move with intention.",
    ]

    # Session closing
    COOLDOWN_INTROS = [
        "We're now entering our cool-down phase.",
        "Let's begin to slow down and relax.",
        "Time to gently wind down our practice.",
    ]

    SESSION_ENDINGS = [
        "You've completed your yoga session. Take a moment to appreciate your practice today.",
        "Wonderful work. Your practice is complete. Carry this peace with you.",
        "Namaste. Thank you for practicing today. You've done beautifully.",
    ]

    FINAL_WORDS = [
        "When you're ready, gently open your eyes and return to your day.",
        "Take your time coming back. You've given yourself a beautiful gift today.",
        "Rest here as long as you need. Thank you for your practice.",
    ]

    @classmethod
    def generate_session_script(cls, session_data: Dict) -> List[Dict]:
        """
        Generate a complete session script with cue points.

        Returns list of script items:
        [
            {"type": "welcome", "text": "...", "timing": "session_start"},
            {"type": "pose_intro", "text": "...", "timing": "pose_start", "pose_index": 0},
            ...
        ]

        Supports bilateral poses with side-aware phrases when pose has "side" field.
        Supports breath cues for vinyasa style when breathCues is true.
        """
        script = []
        duration = session_data.get("duration", 15)
        poses = session_data.get("poses", [])
        focus = session_data.get("focus", "flexibility and balance")
        breath_cues = session_data.get("breathCues", True)
        session_style = session_data.get("style", "vinyasa")

        _debug_log(f"[SCRIPT] Style: {session_style}, breathCues: {breath_cues}")

        # === SESSION START ===
        script.append({
            "type": "welcome",
            "text": random.choice(cls.WELCOMES).format(duration=duration),
            "timing": "session_start"
        })

        focus_benefits = {
            "all": "flexibility and balance",
            "balance": "steadiness and focus",
            "flexibility": "openness and flow",
            "strength": "power and stability",
            "relaxation": "calm and peace"
        }
        focus_benefit = focus_benefits.get(focus, "mindfulness and wellbeing")

        script.append({
            "type": "intro",
            "text": random.choice(cls.SESSION_INTROS).format(
                pose_count=len(poses),
                focus_area=focus_benefit,
                focus_benefit=focus_benefit
            ),
            "timing": "session_start"
        })

        script.append({
            "type": "opening",
            "text": random.choice(cls.OPENING_INSTRUCTIONS),
            "timing": "session_start"
        })

        # === POSE GUIDANCE ===
        for i, pose in enumerate(poses):
            pose_id = pose.get("id", "")
            pose_name = pose.get("name", "this pose")
            duration_secs = pose.get("duration_seconds", [30])[0]
            instructions = pose.get("instructions", [])
            phase = pose.get("phase", "main")
            side = pose.get("side")  # "left", "right", or None for symmetric poses
            is_bilateral = side is not None

            _debug_log(f"[SCRIPT] Pose {i}: {pose_name} (side={side}, {len(instructions) if isinstance(instructions, list) else 0} instructions)")

            # Cooldown transition
            if phase == "cooldown" and i > 0:
                prev_phase = poses[i-1].get("phase", "main")
                if prev_phase != "cooldown":
                    script.append({
                        "type": "cooldown_intro",
                        "text": random.choice(cls.COOLDOWN_INTROS),
                        "timing": "pose_start",
                        "pose_index": i
                    })

            # Pose introduction with side awareness
            if i == 0:
                intro_text = random.choice(cls.FIRST_POSE_INTROS).format(pose_name=pose_name)
            else:
                intro_text = random.choice(cls.POSE_INTROS).format(pose_name=pose_name)

            script.append({
                "type": "pose_intro",
                "text": intro_text,
                "timing": "pose_start",
                "pose_index": i,
                "side": side
            })

            # Add side-specific intro for bilateral poses
            if is_bilateral:
                if side == "left":
                    side_intro = random.choice(cls.LEFT_SIDE_INTROS)
                elif side == "right":
                    # Check if previous pose was same pose on left side (set transition)
                    prev_pose = poses[i - 1] if i > 0 else None
                    if prev_pose and prev_pose.get("id") == pose_id and prev_pose.get("side") == "left":
                        side_intro = random.choice(cls.SET_TRANSITIONS)
                    else:
                        side_intro = random.choice(cls.RIGHT_SIDE_INTROS)
                else:
                    side_intro = None

                if side_intro:
                    script.append({
                        "type": "side_intro",
                        "text": side_intro,
                        "timing": "pose_start",
                        "pose_index": i,
                        "side": side
                    })

            # Breath cue before pose instructions (vinyasa style)
            if breath_cues:
                script.append({
                    "type": "breath_cue",
                    "text": random.choice(cls.INHALE_CUES),
                    "timing": "pose_start",
                    "pose_index": i
                })

            # Pose instructions - include ALL step-by-step instructions
            if instructions and len(instructions) > 0:
                # Add each instruction as a separate script item
                for step_num, instruction in enumerate(instructions):
                    script.append({
                        "type": "pose_instruction",
                        "text": instruction,
                        "timing": "pose_start",
                        "pose_index": i,
                        "step": step_num
                    })
            elif pose_id in cls.POSE_INSTRUCTIONS:
                script.append({
                    "type": "pose_instruction",
                    "text": cls.POSE_INSTRUCTIONS[pose_id],
                    "timing": "pose_start",
                    "pose_index": i,
                    "step": 0
                })
            else:
                script.append({
                    "type": "pose_instruction",
                    "text": cls.DEFAULT_INSTRUCTION,
                    "timing": "pose_start",
                    "pose_index": i,
                    "step": 0
                })

            # Hold duration callout
            script.append({
                "type": "hold",
                "text": f"We'll hold this for {duration_secs} seconds. " + random.choice(cls.HOLD_PHRASES),
                "timing": "pose_holding",
                "pose_index": i
            })

            # Breath guidance during hold (vinyasa style)
            if breath_cues:
                script.append({
                    "type": "breath_cue",
                    "text": random.choice(cls.BREATH_HOLDS),
                    "timing": "pose_holding",
                    "pose_index": i
                })

            # Mid-pose encouragement (for longer holds)
            if duration_secs >= 30:
                script.append({
                    "type": "encouragement",
                    "text": random.choice(cls.ENCOURAGEMENTS),
                    "timing": "pose_midpoint",
                    "pose_index": i
                })
                # Extra breath cue at midpoint for long holds (vinyasa style)
                if breath_cues:
                    script.append({
                        "type": "breath_cue",
                        "text": random.choice(cls.BREATH_HOLDS),
                        "timing": "pose_midpoint",
                        "pose_index": i
                    })

            # Pose corrections (played when form drops)
            # Add multiple correction phrases so they don't repeat
            for correction in cls.ADJUST_FORM:
                script.append({
                    "type": "pose_correction",
                    "text": correction,
                    "timing": "pose_correction",
                    "pose_index": i
                })

            # Exhale cue before releasing pose (vinyasa style)
            if breath_cues:
                script.append({
                    "type": "breath_cue",
                    "text": random.choice(cls.EXHALE_CUES),
                    "timing": "pose_end",
                    "pose_index": i
                })

            # Check if next pose is a rotation switch (right side to left side)
            next_pose = poses[i + 1] if i < len(poses) - 1 else None
            is_rotation_switch = (
                next_pose and
                next_pose.get("isRotationStart") and
                next_pose.get("rotationSide") == "left"
            )

            # Pose completion with flowing transition
            if i < len(poses) - 1:
                # Not the last pose - flow into next
                if is_rotation_switch:
                    # Switching from right side to left side
                    script.append({
                        "type": "rotation_switch",
                        "text": random.choice(cls.ROTATION_SWITCH),
                        "timing": "pose_end",
                        "pose_index": i
                    })
                else:
                    # Normal flowing transition
                    script.append({
                        "type": "pose_complete",
                        "text": random.choice(cls.POSE_COMPLETE),
                        "timing": "pose_end",
                        "pose_index": i
                    })
                    script.append({
                        "type": "flow_transition",
                        "text": random.choice(cls.FLOW_TRANSITIONS),
                        "timing": "pose_end",
                        "pose_index": i
                    })
            else:
                # Last pose - actual completion
                script.append({
                    "type": "pose_complete",
                    "text": "And release. You did beautifully.",
                    "timing": "pose_end",
                    "pose_index": i
                })

        # === SESSION END ===
        script.append({
            "type": "session_end",
            "text": random.choice(cls.SESSION_ENDINGS),
            "timing": "session_end"
        })

        script.append({
            "type": "closing",
            "text": random.choice(cls.FINAL_WORDS),
            "timing": "session_end"
        })

        return script


class YogaVoiceGenerator:
    """Generates audio files using Edge TTS."""

    def __init__(self, cache_dir: Path = AUDIO_CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, text: str) -> str:
        """Generate a cache key for the text."""
        return hashlib.md5(text.encode()).hexdigest()

    def _get_cache_path(self, text: str) -> Path:
        """Get the cache file path for the text."""
        key = self._get_cache_key(text)
        return self.cache_dir / f"{key}.mp3"

    async def generate_audio(self, text: str) -> Optional[str]:
        """
        Generate audio for the given text.
        Returns the relative URL path to the audio file, or None if generation fails.
        """
        try:
            cache_path = self._get_cache_path(text)

            # Return cached if exists
            if cache_path.exists():
                return f"/static/audio/voice/{cache_path.name}"

            # Ensure cache directory exists
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            # Generate with Edge TTS
            communicate = edge_tts.Communicate(
                text,
                voice=VOICE,
                rate=VOICE_RATE,
                pitch=VOICE_PITCH
            )
            await communicate.save(str(cache_path))

            return f"/static/audio/voice/{cache_path.name}"
        except Exception as e:
            _debug_log(f"[VOICE] Audio generation failed for '{text[:50]}...': {e}")
            return None

    async def generate_session_audio(self, script: List[Dict]) -> List[Dict]:
        """
        Generate audio for all script items.
        Returns the script with audio URLs added (None if generation failed).
        """
        for item in script:
            audio_url = await self.generate_audio(item["text"])
            item["audio_url"] = audio_url  # May be None if generation failed
        return script

    async def pregenerate_common_phrases(self):
        """Pre-generate commonly used phrases for faster playback."""
        common_phrases = [
            "Take a deep breath.",
            "And exhale.",
            "Beautiful form. Keep it up.",
            "Gently adjust your position.",
            "You're doing wonderfully.",
            "Hold the pose.",
            "And release.",
            "Rest for a moment.",
            "When you're ready, we'll continue.",
            "Namaste.",
        ]
        for phrase in common_phrases:
            await self.generate_audio(phrase)


# Singleton instance
voice_generator = YogaVoiceGenerator()


async def generate_session_voice_script(session_data: Dict) -> List[Dict]:
    """
    Main entry point: Generate complete voice script with audio URLs.
    """
    script = YogaScriptGenerator.generate_session_script(session_data)
    script_with_audio = await voice_generator.generate_session_audio(script)
    return script_with_audio
