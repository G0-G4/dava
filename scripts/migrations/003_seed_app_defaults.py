DEFAULTS = {
    "prompt_text": "Ultra-realistic portrait of the same handsome person from reference image, maintaining exact facial features, hairstyle, core expression and pose. The person is situated in {place} during {detailed_description}. Background shows {environmental_details} with appropriate landmarks or scenery of {place}. {lighting_description} creating {mood_description} atmosphere. The person wears {clothing} on top of clothing from reference image. Environmental effects: {weather_effects}. Photorealistic, 8K detail, cinematic environmental lighting, perfect skin texture, realistic fabric details, hyper-detailed eyes.",
    "place": "Moscow",
    "latitude": 55.7522,
    "longitude": 37.6156,
    "timezone": "Europe/Moscow",
    "image_generator": "nano-banana-2",
    "style": "sai-photographic",
    "image_cfg_scale": 0.8,
}


def upgrade(db):
    for key, value in DEFAULTS.items():
        db.set_global_default(key, value, skip_if_exists=True)


def downgrade(db):
    for key in DEFAULTS:
        db.delete_global_default(key)