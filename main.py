import os
import json
import time
import asyncio
import subprocess
import urllib.parse
import requests
import edge_tts
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================
# 1. CONFIGURATION & 2D CHARACTER LOCK
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VOICE = "en-US-ChristopherNeural"  # Native American Finance Narrator Voice

# Master Character DNA: Ye har scene mein character ko same rakhega
CHARACTER_DNA = (
    "2D minimalist vector animation style, flat illustration, clean bold outlines, "
    "The Swedish Investor and Two Cents aesthetic, dark slate background with neon green accents. "
    "Main character: A 28-year-old cartoon man with short brown hair, round black glasses, "
    "wearing a navy blue hoodie and white t-shirt, expressive posture, "
)

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 8-10 MINUTE SCRIPT & SCENE GENERATOR
# ==========================================
def generate_full_script():
    print("Generating USA Personal Finance Topic...")
    topic_prompt = (
        "Give me 1 high-CTR, viral USA Personal Finance YouTube video topic "
        "(focus on Roth IRA, 401k traps, S&P 500, FICO credit scores, middle-class tax traps, or wealth psychology). "
        "Return ONLY JSON: {\"title\": \"...\", \"description\": \"...\", \"tags\": [\"tag1\", \"tag2\"]}"
    )
    res = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=topic_prompt,
        config={"response_mime_type": "application/json"}
    )
    meta = json.loads(res.text)
    title = meta["title"]
    print(f"Selected Title: {title}")

    chapters = [
        "Chapter 1: High-Retention Hook & The Hidden Financial Trap (Why most Americans fail at this)",
        "Chapter 2: The Real Numbers & Wall Street / IRS Reality (Use real USD $ examples)",
        "Chapter 3: Case Study - Broke Mindset vs Wealthy Mindset (Storytelling with our main character)",
        "Chapter 4: The Step-by-Step Mathematical Breakdown (Compound interest, accounts, or tax percentages)",
        "Chapter 5: Actionable Blueprint (Exact steps using US tools like Vanguard, Fidelity, Roth IRA, HYSA)",
        "Chapter 6: The Ultimate Rule & Strong Conclusion"
    ]

    all_scenes = []
    for idx, chapter in enumerate(chapters, 1):
        print(f"Writing {chapter}...")
        chapter_prompt = f"""
        You are an expert USA Personal Finance documentary writer.
        Video Title: "{title}"
        Current Section: "{chapter}"

        Write approximately 250-280 words of engaging, conversational American English narration for this section.
        Break this section into 8 to 10 visual scenes (each scene having 25-30 words of narration, lasting ~10 seconds).
        For each scene, provide an `image_action` describing what our 2D character is doing (e.g., "looking stressed at a pile of red credit card bills", "standing confidently next to a glowing green compound interest chart"). Do NOT include text in the image description.

        Return ONLY a JSON list of objects:
        [
          {{"narration": "Exact spoken voiceover text...", "image_action": "Character action description..."}}
        ]
        """
        chap_res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=chapter_prompt,
            config={"response_mime_type": "application/json"}
        )
        scenes = json.loads(chap_res.text)
        all_scenes.extend(scenes)
        time.sleep(2)

    return meta, all_scenes

# ==========================================
# 3. AUDIO, 2D IMAGE & SCENE RENDER ENGINE
# ==========================================
async def create_voiceover(text, audio_path):
    communicate = edge_tts.Communicate(text, VOICE, rate="+2%")
    await communicate.save(audio_path)

def download_2d_image(action_prompt, image_path, seed):
    full_prompt = f"{CHARACTER_DNA} {action_prompt}, no text, clean vector art, 16:9 widescreen"
    encoded = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&seed={seed}&model=flux&nologo=true"
    
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=45)
            if r.status_code == 200:
                with open(image_path, "wb") as f:
                    f.write(r.content)
                return True
        except Exception as e:
            print(f"Image retry {attempt+1}: {e}")
            time.sleep(5)
    return False

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    out = subprocess.check_output(cmd).decode("utf-8").strip()
    return float(out)

def render_scene_clip(image_path, audio_path, output_clip):
    duration = get_audio_duration(audio_path)
    frames = int(duration * 25) + 10
    # Smooth 2D Ken Burns Zoom Effect via FFmpeg
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-vf", f"scale=2560:1440,zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1280x720:fps=25",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-shortest", output_clip
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==========================================
# 4. YOUTUBE AUTO-UPLOADER
# ==========================================
def upload_to_youtube(video_path, meta):
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube credentials missing. Skipping upload (video saved locally).")
        return

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"] + "\n\nDisclaimer: For educational and entertainment purposes only. Not financial advice.",
            "tags": meta["tags"],
            "categoryId": "27"  # Education category
        },
        "status": {
            "privacyStatus": "public",  # Change to "private" if you want to review before publishing
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print(f"SUCCESS! Uploaded to YouTube. Video ID: {response['id']}")

# ==========================================
# 5. MAIN PIPELINE EXECUTION
# ==========================================
async def main():
    os.makedirs("temp", exist_ok=True)
    meta, scenes = generate_full_script()
    
    clip_list_file = "temp/clips.txt"
    valid_clips = []

    print(f"Total Scenes to Render: {len(scenes)} (Est. 8-10 Minutes)")
    for i, scene in enumerate(scenes):
        print(f"Processing Scene {i+1}/{len(scenes)}...")
        audio_file = f"temp/audio_{i}.mp3"
        img_file = f"temp/img_{i}.jpg"
        clip_file = f"temp/clip_{i}.mp4"

        await create_voiceover(scene["narration"], audio_file)
        if download_2d_image(scene["image_action"], img_file, seed=1000 + i):
            render_scene_clip(img_file, audio_file, clip_file)
            valid_clips.append(f"file 'clip_{i}.mp4'")

    with open(clip_list_file, "w") as f:
        f.write("\n".join(valid_clips))

    print("Merging all scenes into final 8-10 minute video...")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", clip_list_file, "-c", "copy", "final_video.mp4"
    ], check=True)

    print("Video Render Complete: final_video.mp4")
    upload_to_youtube("final_video.mp4", meta)

if __name__ == "__main__":
    asyncio.run(main())
