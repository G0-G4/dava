VIDEO_ACTIONS = {
    "weather": {
        "55": "thick drizzle falling steadily, rain streaks across the frame as user pulls up a hood, water dripping from its edge",
        "57": "intense freezing drizzle, ice forming on surfaces while user shivers dramatically, rubbing arms, breath visible in the cold air",
        "65": "torrential rain pouring in sheets, rapid splashing in puddles as user holds a newspaper over their head, running for cover",
        "66": "freezing rain coating surfaces with ice, ice crackling while user carefully walks on icy ground, arms out for balance, slipping slightly",
        "67": "heavy freezing rain, ice accumulating, dramatic ice formations as user chips ice off their jacket, shivering uncontrollably",
        "71": "gentle snowfall, snowflakes drifting softly in the air as user catches snowflakes on their tongue, looking up with wonder",
        "73": "moderate snowfall, snowflakes swirling in the wind while user brushes snow off their shoulders, adjusting a scarf",
        "75": "heavy snowfall with large flakes swirling in the wind, blizzard-like as user squints through the snow, holding a hand up to shield their face",
        "77": "snow grains scattering in the wind, icy particles dancing while user shakes icy particles out of their hair, scrunching up their face",
        "82": "violent rain showers, water splashing intensely, dramatic downpour as user gets drenched instantly, wiping water from their eyes",
        "86": "snow blowing sideways in gusty wind, wintry squall while user leans into the wind, scarf blowing horizontally behind them",
        "95": "dramatic lightning flash illuminating the scene, thunder rumble, wind howling as user flinches at the lightning strike, eyes wide",
        "96": "thunderstorm with hail stones bouncing off surfaces while user covers their head with both hands, flinching",
        "99": "intense thunderstorm with large hail, violent wind gusts, dramatic lightning as user braces against the wind, shielding their face from hail",
    },
    "holidays": {
        "New Year's Day": "fireworks exploding in colorful bursts, confetti drifting down, festive lights twinkling as user pops a party popper, wearing a 'Happy New Year' headband",
        "Christmas Day": "twinkling Christmas lights, gentle snow falling, warm candlelight flickering as user wears a Santa hat, holding a wrapped gift box with a warm smile",
        "Orthodox Christmas Day": "candle flame flickering softly, golden church bells, snow drifting gently as user lights a candle, crossing themselves gently",
        "Defender of the Fatherland Day": "military bands marching, flags waving in the wind as user salutes formally, wearing a military-style cap",
        "International Women's Day": "flowers gently swaying, soft petals falling, warm spring light as user holds a bouquet of mimosa flowers, offering them forward with a smile",
        "Spring and Labour Day": "cherry blossoms fluttering in a gentle breeze, bright sunshine as user plants a small seedling, wiping their brow with a satisfied nod",
        "Victory Day": "fireworks bursting over a city skyline, flags waving solemnly as user pins a St. George ribbon to their chest, placing a hand over their heart",
        "Russia Day": "flag waving proudly, fireworks lighting up the sky as user waves a small Russian flag gently, looking upward with pride",
        "Unity Day": "warm candlelight glowing, autumn leaves swirling gently as user holds a candle in cupped hands, walking slowly in a quiet procession",
        "friday the 13th": "eerie fog rolling across the frame, candle flame flickering, shadows creeping along walls as user slowly puts on a Jason hockey mask, tilting their head menacingly",
    },
}

VIDEO_PROMPT_TEXT = "Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"


def upgrade(db):
    db.set_global_default("video_actions", VIDEO_ACTIONS, skip_if_exists=True)
    db.set_global_default("video_prompt_text", VIDEO_PROMPT_TEXT, skip_if_exists=True)


def downgrade(db):
    db.delete_global_default("video_actions")
    db.delete_global_default("video_prompt_text")