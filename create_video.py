from moviepy.editor import TextClip, CompositeVideoClip

text = "Funny video man falling from first floor building holding a microwave"

clip = TextClip(text, fontsize=50, color='white', size=(1280, 720)).set_duration(10).set_position('center')
video = CompositeVideoClip([clip])
video.write_videofile("video_output/generated_video.mp4", fps=24)
