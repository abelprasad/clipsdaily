from gtts import gTTS
text = ("Four score and seven years ago our fathers brought forth a new "
        "nation conceived in liberty. This is a clipsdaily test.")
gTTS(text, lang="en").save("/home/abel/clipsdaily/recordings/speech.mp3")
print("tts ok")
