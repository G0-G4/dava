# dynamic avatar (dava)

- get current weather from https://open-meteo.com/
- create prompt to generate new avatar based on base image and weather conditions with help of https://stablediffusionweb.com/ru
- upload it to telegram via Secretary Mode (Chat Automation)
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
cookies=cookies to auth in https://stablediffusionweb.com/ru
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
image_cfg_scale=0.6
style=sai-photographic
```

### 3. Run

- create `logs` folder
- create `images` folder
- place base image into `images` called `avatar.jpg`
- no phone login required — the bot uses Secretary Mode to update your profile photo

```bash
uv run main.py
```

### How it works

Instead of logging into your personal Telegram account, the bot uses **Secretary Mode** (Chat Automation). When you connect the bot to your profile via Settings > Chat Automation, the bot receives a `business_connection_id` with the `edit_profile_photo` right. This allows the bot to update your profile photo directly through the Telegram API — no full account access needed.