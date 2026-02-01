#!/usr/bin/env python3
"""
Pre-generate all yoga voice audio files using Edge TTS.

Run this locally to generate all audio files, then deploy them with the app.
This avoids runtime TTS generation which may be blocked in cloud environments.

Usage:
    python scripts/pregenerate_voice_audio.py
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    print("edge-tts not installed. Run: pip install edge-tts")
    sys.exit(1)

# Voice configuration (same as yoga_voice.py)
VOICE = "en-IN-NeerjaNeural"
VOICE_RATE = "-10%"
VOICE_PITCH = "-5Hz"

# Output directory
AUDIO_DIR = Path(__file__).parent.parent / "static" / "audio" / "voice"

# Template values for phrase generation
DURATIONS = [5, 10, 15, 20, 25, 30]
POSE_COUNTS = [2, 3, 4, 5, 6, 7, 8, 9, 10]
HOLD_SECONDS = [30, 45, 48, 60]

FOCUS_AREAS = {
    "all": "flexibility and balance",
    "balance": "steadiness and focus",
    "flexibility": "openness and flow",
    "strength": "power and stability",
    "relaxation": "calm and peace",
}

# Pose data
POSES = {
    "ardhachandrasana": {
        "name": "Half Moon",
        "instructions": [
            "Stand on one leg with the other extended behind you",
            "Reach one arm to the ground and the other toward the sky",
            "Keep your hips stacked and open your chest",
            "Gaze upward toward your raised hand",
        ]
    },
    "baddhakonasana": {
        "name": "Butterfly",
        "instructions": [
            "Sit with the soles of your feet together",
            "Let your knees drop toward the floor",
            "Hold your feet with your hands",
            "Lengthen your spine and relax your shoulders",
        ]
    },
    "downward-dog": {
        "name": "Downward Dog",
        "instructions": [
            "Start on hands and knees",
            "Lift your hips up and back",
            "Press your heels toward the floor",
            "Keep your arms straight and head between your biceps",
        ]
    },
    "natarajasana": {
        "name": "Dancer",
        "instructions": [
            "Stand on one leg",
            "Grab your back foot with your hand",
            "Kick your foot into your hand while leaning forward",
            "Extend your free arm forward for balance",
        ]
    },
    "triangle": {
        "name": "Triangle",
        "instructions": [
            "Stand with feet wide apart",
            "Turn one foot out 90 degrees",
            "Reach toward that foot while keeping both legs straight",
            "Extend your other arm toward the sky",
        ]
    },
    "utkatakonasana": {
        "name": "Goddess",
        "instructions": [
            "Stand with feet wide, toes pointed outward",
            "Bend your knees deeply over your toes",
            "Keep your spine straight and core engaged",
            "Bring arms to goal post position or prayer",
        ]
    },
    "veerabhadrasana": {
        "name": "Warrior",
        "instructions": [
            "Step one foot back into a lunge",
            "Bend your front knee over your ankle",
            "Keep your back leg straight",
            "Raise your arms overhead or to the sides",
        ]
    },
    "vrukshasana": {
        "name": "Tree",
        "instructions": [
            "Stand on one leg",
            "Place your other foot on your inner thigh or calf",
            "Never place your foot on your knee",
            "Bring hands to prayer or raise overhead",
        ]
    },
}

# All phrase templates
PHRASES = {
    # === SESSION START ===
    "welcomes": [
        "Welcome to your {duration} minute yoga session.",
        "Hello, and welcome to your {duration} minute practice.",
        "Namaste. Welcome to your {duration} minute yoga journey.",
    ],
    "session_intros": [
        "Today, we'll be flowing through {pose_count} poses, focusing on {focus_area}.",
        "In this session, we'll practice {pose_count} poses to help you {focus_benefit}.",
        "We have {pose_count} beautiful poses planned for you today.",
    ],
    "opening_instructions": [
        "Find a comfortable space, take a deep breath, and let's begin.",
        "Take a moment to center yourself. When you're ready, we'll start together.",
        "Ground yourself, breathe deeply, and prepare your body for movement.",
    ],

    # === POSE INTROS ===
    "first_pose_intros": [
        "We'll begin with {pose_name}.",
        "Let's start our practice with {pose_name}.",
        "Our opening pose is {pose_name}.",
    ],
    "pose_intros": [
        "Let's move into {pose_name}.",
        "Now, we'll practice {pose_name}.",
        "Our next pose is {pose_name}.",
        "Gently transition into {pose_name}.",
    ],

    # === SIDE INTROS ===
    "left_side_intros": [
        "Let's start on your left side.",
        "We'll begin with your left side.",
        "Starting on the left.",
        "First, on your left side.",
    ],
    "right_side_intros": [
        "Now, let's mirror that on your right side.",
        "Switching to your right side.",
        "Now the same on your right.",
        "Let's balance with the right side.",
        "And now, your right side.",
    ],
    "set_transitions": [
        "Beautiful. Now let's transition to the other side.",
        "Wonderful work. Time to switch sides.",
        "Lovely. Let's balance that out on the other side.",
        "Great form. Now mirror that pose.",
        "Well done. Same pose, opposite side.",
    ],

    # === BREATH CUES ===
    "inhale_cues": [
        "Inhale deeply.",
        "Take a slow breath in.",
        "Breathe in.",
        "Inhale, expanding your chest.",
        "Draw a deep breath in.",
        "Fill your lungs completely.",
        "Inhale through your nose.",
        "Breathe in fully.",
        "Take in a nourishing breath.",
        "Inhale and create space.",
    ],
    "exhale_cues": [
        "Exhale slowly.",
        "Breathe out.",
        "Release the breath.",
        "Exhale, letting go of tension.",
        "Let the breath go completely.",
        "Breathe out any stress.",
        "Exhale through your mouth.",
        "Release and let go.",
        "Soften as you breathe out.",
        "Exhale and surrender.",
    ],
    "breath_holds": [
        "Continue breathing steadily.",
        "Match each movement to your breath.",
        "Let your breath guide you.",
        "Inhale to lengthen, exhale to deepen.",
        "Breathe naturally and stay present.",
        "Your breath is your anchor. Keep it flowing.",
        "Slow, steady breaths. You've got this.",
        "With each exhale, release a little more.",
        "Breathe deeply into your belly.",
        "Let your breath soften any tension.",
        "Find your rhythm. Inhale calm, exhale stress.",
        "Your breath connects mind and body.",
        "Stay connected to your breath.",
        "Each breath deepens your practice.",
    ],

    # === HOLD PHRASES ===
    "hold_phrases": [
        "We'll hold this for {seconds} seconds. Hold this pose and breathe deeply.",
        "We'll hold this for {seconds} seconds. Maintain the position. You're doing wonderfully.",
        "We'll hold this for {seconds} seconds. Stay present in this pose. Feel your breath.",
        "We'll hold this for {seconds} seconds. Keep holding. Notice the sensations in your body.",
        "We'll hold this for {seconds} seconds. Breathe into the stretch and hold steady.",
        "We'll hold this for {seconds} seconds. Find stillness here. Let your breath anchor you.",
        "We'll hold this for {seconds} seconds. Stay with it. Your body is getting stronger.",
        "We'll hold this for {seconds} seconds. Embrace this moment. You're exactly where you need to be.",
        "We'll hold this for {seconds} seconds. Feel the energy flowing through your body.",
        "We'll hold this for {seconds} seconds. Ground yourself and breathe through any tension.",
        "We'll hold this for {seconds} seconds. You're building strength with every breath.",
        "We'll hold this for {seconds} seconds. Notice how your body responds to stillness.",
    ],

    # === FORM FEEDBACK ===
    "good_form": [
        "Beautiful form. Keep it up.",
        "You're aligned perfectly. Well done.",
        "Excellent posture. Stay with it.",
        "That's it. You've found the pose.",
        "Your alignment looks wonderful.",
        "Perfect. Hold it right there.",
        "You're nailing this pose.",
        "Great work. Your form is on point.",
        "Yes, that's exactly right.",
        "Beautiful. Stay right where you are.",
    ],
    "adjust_form": [
        "Gently adjust your position to match the guide.",
        "Take a moment to realign with the target pose.",
        "Softly correct your form when you're ready.",
        "Notice where you can adjust to get closer to the target.",
        "Follow the yellow guide on screen for alignment.",
        "Small adjustments make a big difference.",
        "Check your alignment with the target pose.",
        "Keep breathing as you adjust your position.",
    ],

    # === ENCOURAGEMENTS ===
    "encouragements": [
        "You're doing wonderfully.",
        "Stay present and breathe.",
        "Trust your body.",
        "Each breath brings you deeper into the practice.",
        "You're making beautiful progress.",
        "Listen to your body and move with intention.",
        "You're stronger than you think.",
        "Every pose is a chance to grow.",
        "Your dedication is inspiring.",
        "Feel the calm settling in.",
        "You're creating space in your body and mind.",
        "This is your time. Embrace it.",
        "Notice how far you've come.",
        "Your practice is unique and beautiful.",
        "Be patient and kind with yourself.",
        "You're doing exactly what your body needs.",
        "Let go of perfection. You're already enough.",
        "Your effort today matters.",
    ],

    # === POSE COMPLETION ===
    "pose_complete": [
        "Beautiful. Now flow with me.",
        "Lovely. Let's continue moving.",
        "Wonderful. Keep flowing.",
        "Well done. Stay with the movement.",
        "Perfect. Let's move together.",
        "Graceful. Continue the flow.",
        "Excellent. Keep the energy moving.",
        "That was beautiful. Onward we go.",
        "Nicely done. Let's transition.",
        "Breathe and flow into the next pose.",
        "Great work. Keep moving with intention.",
        "Wonderful expression. Let's continue.",
    ],
    "final_release": [
        "And release. You did beautifully.",
    ],

    # === GENERIC FLOW TRANSITIONS (fallback) ===
    "flow_transitions": [
        "Mindfully transition to the next pose.",
        "Flow with intention into the next position.",
        "Let your breath guide you as you move.",
        "Transition smoothly when you're ready.",
        "Move gracefully into the next shape.",
        "Let the movement come naturally.",
        "Breathe as you flow to the next pose.",
        "Gently shift your body into position.",
        "Follow your body's natural rhythm.",
        "Ease into the transition with awareness.",
        "Move with the same calm you've cultivated.",
        "Let each movement be deliberate and soft.",
    ],

    # === ROTATION SWITCH ===
    "rotation_switch": [
        "Excellent work on the right side. Now, let's mirror everything on your left.",
        "Beautiful flow. Time to balance with your left side.",
        "Right side complete. Let's bring that same energy to your left.",
        "Wonderful. Now we'll repeat the sequence on your left side.",
        "That was lovely. Let's balance it out on the left side.",
        "Great work. Time to switch and flow through the left.",
        "Right side done. Let's create symmetry on your left.",
        "Perfect. Now let's give the same attention to your left side.",
        "You've earned this transition. Left side awaits.",
        "Beautiful. Let's mirror that energy on the opposite side.",
    ],

    # === COOLDOWN ===
    "cooldown_intros": [
        "We're now entering our cool-down phase.",
        "Let's begin to slow down and relax.",
        "Time to gently wind down our practice.",
        "Let's ease into our closing sequence.",
        "We're approaching the end. Let's slow our breath.",
        "Time to honor your body with some rest.",
        "Let's transition into our final moments together.",
        "Begin to soften and release any remaining tension.",
    ],

    # === SESSION END ===
    "session_endings": [
        "You've completed your yoga session. Take a moment to appreciate your practice today.",
        "Wonderful work. Your practice is complete. Carry this peace with you.",
        "Namaste. Thank you for practicing today. You've done beautifully.",
        "Your session is complete. You showed up for yourself today, and that matters.",
        "Well done. Your body and mind thank you for this time.",
        "And release. You did beautifully.",
        "Your practice today has planted seeds of wellness. Nurture them.",
        "Thank you for moving with me. You've honored your body well.",
        "You've completed your practice. Carry this calm into the rest of your day.",
        "Beautiful work. Remember this feeling of peace.",
    ],
    "final_words": [
        "When you're ready, gently open your eyes and return to your day.",
        "Take your time coming back. You've given yourself a beautiful gift today.",
        "Rest here as long as you need. Thank you for your practice.",
        "Slowly begin to deepen your breath and wiggle your fingers and toes.",
        "Take one more deep breath. You're ready to continue your day.",
        "Open your eyes when you're ready. Move gently back into the world.",
        "Seal your practice with gratitude. Namaste.",
        "Let the benefits of this practice stay with you throughout your day.",
        "Remember, you can return to this calm whenever you need it.",
    ],
}

# Pose-to-pose transitions
POSE_TRANSITIONS = {
    # From Warrior
    ("veerabhadrasana", "vrukshasana"): "Step your back foot forward to meet your front foot. Ground through your standing leg, then slowly lift your other foot to rest on your inner thigh.",
    ("veerabhadrasana", "triangle"): "Straighten your front leg and open your hips to the side. Extend your arms wide, then reach toward your front foot as you come into Triangle.",
    ("veerabhadrasana", "utkatakonasana"): "Turn your back foot out and pivot to face forward. Widen your stance, bend both knees deeply, and sink into Goddess pose.",
    ("veerabhadrasana", "downward-dog"): "Place your hands on the mat framing your front foot. Step your front foot back to meet the other, lifting your hips high into Downward Dog.",
    ("veerabhadrasana", "ardhachandrasana"): "Shift your weight onto your front foot and place your front hand on the mat. Lift your back leg parallel to the ground and open your chest to the side.",
    ("veerabhadrasana", "natarajasana"): "Step your back foot forward and find your balance on your front leg. Reach back with one hand to grab your opposite ankle, then hinge forward.",

    # From Tree
    ("vrukshasana", "veerabhadrasana"): "Lower your raised foot to the ground behind you, stepping back into a lunge. Bend your front knee and sink your hips into Warrior.",
    ("vrukshasana", "ardhachandrasana"): "Keep your standing leg strong and hinge forward at your hips. Extend your raised leg behind you as you reach one hand toward the ground.",
    ("vrukshasana", "natarajasana"): "Lower your raised foot slightly and catch your ankle with your hand. Press your foot into your palm as you hinge forward into Dancer.",
    ("vrukshasana", "utkatakonasana"): "Lower your raised foot wide to the side, turning your toes outward. Bend both knees deeply and sink your hips into Goddess pose.",
    ("vrukshasana", "triangle"): "Lower your raised foot wide to the side. Straighten both legs, extend your arms, and reach toward one foot as you fold into Triangle.",

    # From Downward Dog
    ("downward-dog", "veerabhadrasana"): "Step your right foot forward between your hands. Ground your back heel and rise up, bending your front knee into Warrior.",
    ("downward-dog", "triangle"): "Step your foot forward and rise to standing with feet wide. Turn your front foot out, extend your arms, and fold sideways into Triangle.",
    ("downward-dog", "utkatakonasana"): "Walk your feet toward your hands and rise to standing. Step your feet wide, turn your toes out, and sink into Goddess pose.",
    ("downward-dog", "vrukshasana"): "Walk your feet toward your hands and slowly roll up to standing. Shift your weight to one leg and lift the other foot to your inner thigh.",

    # From Triangle
    ("triangle", "veerabhadrasana"): "Bend your front knee and square your hips forward. Sink deeper as you transition into Warrior pose.",
    ("triangle", "utkatakonasana"): "Bend both knees and turn your feet to point outward. Lower your hips and bring your torso upright into Goddess.",
    ("triangle", "ardhachandrasana"): "Bend your front knee slightly and shift your weight forward. Lift your back leg as you bring your bottom hand to the mat for Half Moon.",
    ("triangle", "downward-dog"): "Bring both hands to the mat inside your front foot. Step back to meet your feet and lift your hips high into Downward Dog.",

    # From Goddess
    ("utkatakonasana", "veerabhadrasana"): "Pivot on your feet, turning to face one direction. Extend your back leg straight as you sink into a Warrior lunge.",
    ("utkatakonasana", "triangle"): "Straighten one leg while keeping the other bent. Extend your arms wide and reach toward your straight leg into Triangle.",
    ("utkatakonasana", "vrukshasana"): "Shift your weight to one leg and bring your feet together. Lift your other foot to your inner thigh as you rise into Tree.",
    ("utkatakonasana", "downward-dog"): "Bring your hands to the mat and step your feet back. Lift your hips high, coming into Downward Dog.",

    # From Half Moon
    ("ardhachandrasana", "veerabhadrasana"): "Slowly lower your lifted leg behind you into a lunge. Lift your torso upright and settle into Warrior pose.",
    ("ardhachandrasana", "vrukshasana"): "Bring your extended leg down and draw your foot to your inner thigh. Lift your torso upright into Tree pose.",
    ("ardhachandrasana", "triangle"): "Lower your lifted leg to the ground behind you. Keep both legs straight as you open into Triangle.",
    ("ardhachandrasana", "downward-dog"): "Lower your lifted leg and bring both hands to the mat. Step back and lift your hips into Downward Dog.",

    # From Dancer
    ("natarajasana", "vrukshasana"): "Gently release your back foot and draw it to your inner thigh. Stand tall in Tree pose.",
    ("natarajasana", "veerabhadrasana"): "Release your foot and step it back behind you into a lunge. Sink your hips into Warrior.",
    ("natarajasana", "ardhachandrasana"): "Release your foot and extend your leg straight behind you. Lower your torso and reach toward the ground for Half Moon.",
    ("natarajasana", "downward-dog"): "Release your back foot and fold forward, bringing your hands to the mat. Step back into Downward Dog.",

    # From Butterfly
    ("baddhakonasana", "downward-dog"): "Release your feet and come onto your hands and knees. Tuck your toes and lift your hips into Downward Dog.",
    ("baddhakonasana", "vrukshasana"): "Uncross your legs and rise to standing. Ground through one foot and lift the other to your inner thigh.",
    ("baddhakonasana", "utkatakonasana"): "Rise to standing, keeping your feet wide and toes turned out. Bend your knees and sink into Goddess.",
}

# Same-pose side switches
SIDE_SWITCH_TRANSITIONS = {
    "vrukshasana": "Slowly lower your foot to the ground. Shift your weight to your other leg and lift your opposite foot to your inner thigh.",
    "veerabhadrasana": "Step your feet together and pause. Now step your other foot forward, bending into Warrior on the opposite side.",
    "ardhachandrasana": "Lower your lifted leg and pivot to face the opposite direction. Shift your weight and lift your other leg into Half Moon.",
    "natarajasana": "Release your foot and stand tall. Shift your weight to your other leg, reach back for your opposite ankle, and flow into Dancer.",
    "triangle": "Rise up and pivot your feet to face the opposite direction. Extend your arms and fold toward your other leg.",
    "utkatakonasana": "Stay low in your squat as you shift your weight. Goddess is symmetric, so simply re-center your stance.",
}


def get_cache_key(text: str) -> str:
    """Generate a cache key for the text (same as yoga_voice.py)."""
    return hashlib.md5(text.encode()).hexdigest()


def collect_all_phrases() -> list[str]:
    """Collect all unique phrases that need audio generation."""
    phrases = set()

    # === WELCOMES (with duration) ===
    for template in PHRASES["welcomes"]:
        for duration in DURATIONS:
            phrases.add(template.format(duration=duration))

    # === SESSION INTROS (with pose_count and focus) ===
    for template in PHRASES["session_intros"]:
        for pose_count in POSE_COUNTS:
            for focus_key, focus_text in FOCUS_AREAS.items():
                try:
                    phrases.add(template.format(
                        pose_count=pose_count,
                        focus_area=focus_text,
                        focus_benefit=focus_text
                    ))
                except KeyError:
                    # Template might not use all placeholders
                    pass

    # === STATIC PHRASES ===
    for key in ["opening_instructions", "left_side_intros", "right_side_intros",
                "set_transitions", "inhale_cues", "exhale_cues", "breath_holds",
                "good_form", "adjust_form", "encouragements", "pose_complete",
                "final_release", "flow_transitions", "rotation_switch",
                "cooldown_intros", "session_endings", "final_words"]:
        for phrase in PHRASES[key]:
            phrases.add(phrase)

    # === POSE INTROS (with pose names) ===
    for template in PHRASES["first_pose_intros"]:
        for pose_id, pose_data in POSES.items():
            phrases.add(template.format(pose_name=pose_data["name"]))

    for template in PHRASES["pose_intros"]:
        for pose_id, pose_data in POSES.items():
            phrases.add(template.format(pose_name=pose_data["name"]))

    # === POSE INSTRUCTIONS ===
    for pose_id, pose_data in POSES.items():
        for instruction in pose_data["instructions"]:
            phrases.add(instruction)

    # === HOLD PHRASES (with seconds) ===
    for template in PHRASES["hold_phrases"]:
        for seconds in HOLD_SECONDS:
            phrases.add(template.format(seconds=seconds))

    # === POSE-TO-POSE TRANSITIONS ===
    for transition_text in POSE_TRANSITIONS.values():
        phrases.add(transition_text)

    # === SIDE SWITCH TRANSITIONS ===
    for transition_text in SIDE_SWITCH_TRANSITIONS.values():
        phrases.add(transition_text)

    return sorted(phrases)


async def generate_audio(text: str) -> bool:
    """Generate audio for a single phrase."""
    cache_key = get_cache_key(text)
    output_path = AUDIO_DIR / f"{cache_key}.mp3"

    if output_path.exists():
        return True  # Already generated

    try:
        communicate = edge_tts.Communicate(
            text,
            voice=VOICE,
            rate=VOICE_RATE,
            pitch=VOICE_PITCH
        )
        await communicate.save(str(output_path))
        return output_path.exists()
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


async def main():
    print("=" * 60)
    print("YOGA VOICE AUDIO PRE-GENERATION")
    print("=" * 60)
    print()

    # Ensure output directory exists
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all phrases
    print("Collecting phrases...")
    phrases = collect_all_phrases()
    print(f"Total unique phrases: {len(phrases)}")
    print()

    # Count existing files
    existing = sum(1 for p in phrases if (AUDIO_DIR / f"{get_cache_key(p)}.mp3").exists())
    print(f"Already generated: {existing}")
    print(f"Need to generate: {len(phrases) - existing}")
    print()

    if existing == len(phrases):
        print("All audio files already exist!")
        return

    # Generate audio
    print("Generating audio files...")
    print("-" * 60)

    success = 0
    failed = 0

    for i, phrase in enumerate(phrases, 1):
        cache_key = get_cache_key(phrase)
        output_path = AUDIO_DIR / f"{cache_key}.mp3"

        if output_path.exists():
            continue

        # Show progress
        display_text = phrase[:50] + "..." if len(phrase) > 50 else phrase
        print(f"[{i}/{len(phrases)}] {display_text}")

        if await generate_audio(phrase):
            success += 1
        else:
            failed += 1
            print(f"  FAILED: {phrase[:80]}")

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)

    print()
    print("=" * 60)
    print(f"COMPLETE: {success} generated, {failed} failed")
    print(f"Total audio files: {len(list(AUDIO_DIR.glob('*.mp3')))}")
    print("=" * 60)

    # Write manifest for reference
    manifest_path = AUDIO_DIR / "manifest.json"
    manifest = {
        "total_phrases": len(phrases),
        "phrases": {get_cache_key(p): p for p in phrases}
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())
