# dynamic avatar (dava)

- get current weather from https://open-meteo.com/
- create prompt to generate new avatar based on base image and weather conditions with help of image generators
- upload it to telegram via Secretary Mode (Chat Automation)
- optionally generate **video profile photos** on holidays and extreme weather using Veo 3.1 Fast
- profit

![dava](dava.gif)

## setup

### 1. Telegram Bot Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) if you don't have one
2. In @BotFather, enable **Secretary Mode** for your bot:
   - Go to your bot's settings → **Secretary Mode** → Enable
3. In the Telegram app, go to **Settings > Chat Automation** and connect your bot
   - Grant the **Edit Profile Photo** permission when connecting
4. Note your `allowed_chat_id` (your user ID) — you can get it by messaging [@userinfobot](https://t.me/userinfobot)

### 2. Configuration

Create a `.env` file:

```properties
# Required for all generators
image_dir=images
prompt_text=Ultra-realistic portrait of the same person from reference image, maintaining exact facial features, hairstyle and core expression. The person is situated in {place} during {detailed_description}. Background shows {environmental_details} with appropriate landmarks or scenery of {place}. {lighting_description} creating {mood_description} atmosphere. The person wears {clothing} while maintaining their signature style from original image. Environmental effects: {weather_effects}. Photorealistic, 8K detail, cinematic environmental lighting, perfect skin texture, realistic fabric details, hyper-detailed eyes.
place=Moscow
api_id=read https://docs.telethon.dev/en/stable/basic/signing-in.html how to get api_id and api_hash
api_hash=
latitude=55.7522
longitude=37.6156
timezone=Europe/Moscow
bot_token=your_bot_token_from_botfather
allowed_chat_id=your_telegram_user_id
previous_prompt_text="will not update photo if prompt hasn't changed"

# Image generator: stable-diffusion, nano-banana, or nano-banana-2
image_generator=stable-diffusion

# Stable Diffusion settings (required if image_generator=stable-diffusion)
cookies=cookies to auth in https://stablediffusionweb.com/ru
image_cfg_scale=0.6
style=sai-photographic

# Polza.ai settings (required if image_generator=nano-banana or nano-banana-2)
polza_api_key=your_polza_api_key
# polza_model=google/gemini-2.5-flash-image   (optional override, defaults based on image_generator)
```

#### Image Generators

| Generator | `image_generator` value | Model | Description |
|-----------|------------------------|-------|-------------|
| Stable Diffusion | `stable-diffusion` | SD-XL | Uses stablediffusionweb.com (requires `cookies`) |
| Nano Banana | `nano-banana` | `google/gemini-2.5-flash-image` | Uses Polza.ai API (requires `polza_api_key`) |
| Nano Banana 2 | `nano-banana-2` | `google/gemini-3.1-flash-image-preview` | Polza.ai, 4K support (requires `polza_api_key`) |

You can also override the Polza model by setting `polza_model` to any model ID supported by Polza.ai (e.g. `google/gemini-2.5-flash-image`).

#### Video Generation

The bot can also generate **video profile photos** using Veo 3.1 Fast via the Polza.ai API. Video generation is triggered automatically on:

- **Holidays** — Russian public holidays and Friday the 13th
- **Extreme weather** — thunderstorms, heavy rain/snow, hail, etc. (weather codes with actions in `video_actions.weather`)

Video settings are seeded with sensible defaults in the database and can be configured via bot commands:

| Setting | Config key | Type | Description |
|---------|-----------|------|-------------|
| Video mode | `video_mode` | `auto` or `never` | `auto` generates video on triggers; `never` disables it. Default: `auto` |
| Video actions | `video_actions` | dict | Maps weather codes and holiday names to action descriptions for the prompt |
| Video prompt | `video_prompt_text` | string | Template for video prompts. Default: `"Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"` |

Use the `/video_mode` bot command to toggle video generation on/off.

**System requirements**: `ffmpeg` must be installed — it's used to crop video from 9:16 to 1:1 and truncate to 3 seconds for Telegram compatibility.

### 3. Run

- create `logs` folder
- create `images` folder
- place base image into `images` called `avatar.jpg`
- no phone login required — the bot uses Secretary Mode to update your profile photo

```bash
# First run: apply database migrations
uv run scripts/run_migrations.py

# Start the bot
uv run main.py
```

### How it works

Instead of logging into your personal Telegram account, the bot uses **Secretary Mode** (Chat Automation). When you connect the bot to your profile via Settings > Chat Automation, the bot receives a `business_connection_id` with the `edit_profile_photo` right. This allows the bot to update your profile photo directly through the Telegram API — no full account access needed.

For video avatars, the bot generates a 9:16 video via Veo 3.1 Fast, then uses `ffmpeg` to center-crop it to 1:1, truncate to 3 seconds, and strip audio. Telegram requires both a static frame (JPG) and the video file to set a video profile photo.