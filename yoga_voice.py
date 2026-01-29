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

    # Pose completion
    POSE_COMPLETE = [
        "And release. Well done.",
        "Gently come out of the pose. That was wonderful.",
        "And relax. You did beautifully.",
        "Release the pose. Take a breath.",
    ]

    # Transitions
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
        """
        script = []
        duration = session_data.get("duration", 15)
        poses = session_data.get("poses", [])
        focus = session_data.get("focus", "flexibility and balance")

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

            # Debug: Log what we're processing
            print(f"[SCRIPT] Processing pose {i}: {pose_name}")
            print(f"[SCRIPT]   instructions type: {type(instructions)}, len: {len(instructions) if isinstance(instructions, list) else 'N/A'}")
            if isinstance(instructions, list):
                for j, inst in enumerate(instructions):
                    print(f"[SCRIPT]   [{j}]: {inst[:40] if inst else 'empty'}...")

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

            # Pose introduction
            if i == 0:
                intro_text = random.choice(cls.FIRST_POSE_INTROS).format(pose_name=pose_name)
            else:
                intro_text = random.choice(cls.POSE_INTROS).format(pose_name=pose_name)

            script.append({
                "type": "pose_intro",
                "text": intro_text,
                "timing": "pose_start",
                "pose_index": i
            })

            # Pose instructions - include ALL step-by-step instructions
            if instructions and len(instructions) > 0:
                print(f"[SCRIPT]   Adding {len(instructions)} instructions to script")
                # Add each instruction as a separate script item
                for step_num, instruction in enumerate(instructions):
                    script.append({
                        "type": "pose_instruction",
                        "text": instruction,
                        "timing": "pose_start",
                        "pose_index": i,
                        "step": step_num
                    })
                    print(f"[SCRIPT]   Added instruction {step_num}: {instruction[:40]}...")
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

            # Mid-pose encouragement (for longer holds)
            if duration_secs >= 30:
                script.append({
                    "type": "encouragement",
                    "text": random.choice(cls.ENCOURAGEMENTS),
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

            # Pose completion
            script.append({
                "type": "pose_complete",
                "text": random.choice(cls.POSE_COMPLETE),
                "timing": "pose_end",
                "pose_index": i
            })

            # Transition (except for last pose)
            if i < len(poses) - 1:
                script.append({
                    "type": "transition",
                    "text": random.choice(cls.TRANSITIONS),
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

    async def generate_audio(self, text: str) -> str:
        """
        Generate audio for the given text.
        Returns the relative URL path to the audio file.
        """
        cache_path = self._get_cache_path(text)

        # Return cached if exists
        if cache_path.exists():
            return f"/static/audio/voice/{cache_path.name}"

        # Generate with Edge TTS
        communicate = edge_tts.Communicate(
            text,
            voice=VOICE,
            rate=VOICE_RATE,
            pitch=VOICE_PITCH
        )
        await communicate.save(str(cache_path))

        return f"/static/audio/voice/{cache_path.name}"

    async def generate_session_audio(self, script: List[Dict]) -> List[Dict]:
        """
        Generate audio for all script items.
        Returns the script with audio URLs added.
        """
        for item in script:
            audio_url = await self.generate_audio(item["text"])
            item["audio_url"] = audio_url
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
