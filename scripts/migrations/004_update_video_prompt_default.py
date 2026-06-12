OLD_VIDEO_PROMPT_TEXT = "Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"
NEW_VIDEO_PROMPT_TEXT = "Animated portrait of a person centered in frame, {action}"


def upgrade(db):
    current = db.get_global_default("video_prompt_text")
    if current == OLD_VIDEO_PROMPT_TEXT:
        db.set_global_default("video_prompt_text", NEW_VIDEO_PROMPT_TEXT)


def downgrade(db):
    current = db.get_global_default("video_prompt_text")
    if current == NEW_VIDEO_PROMPT_TEXT:
        db.set_global_default("video_prompt_text", OLD_VIDEO_PROMPT_TEXT)
