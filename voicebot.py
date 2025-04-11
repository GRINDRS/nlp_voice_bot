import speech_recognition as sr
from gtts import gTTS
import os
import re
import time
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def listen_to_user():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Press [Enter] to start speaking")
        input()
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        print("Listening...")
        audio = recognizer.listen(source, timeout=4, phrase_time_limit=10)

    try:
        text = recognizer.recognize_google(audio)
        print("🗣️ You said:", text)
        return text
    except Exception as e:
        print("Error:", e)
        return None

def get_bot_reply(user_text):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=180,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a friendly, efficient museum tour guide robot. "
                    "When a visitor mentions an interest (e.g., Da Vinci), reply with a short, engaging 2-stop tour plan:\n"
                    "- Greet them and acknowledge the interest\n"
                    "- Mention two places you’ll take them, in order\n"
                    "- Keep it under 3 sentences — punchy, helpful, natural\n"
                    "- End with a movement command like:\n"
                    "'ROBOT_CMD: MOVE_FORWARD:12; TURN_RIGHT:90'"
                )
            },
            {"role": "user", "content": user_text}
        ]
    )
    return response.choices[0].message.content

def extract_movement_code(text):
    match = re.search(r'ROBOT_CMD:\s*(.*)', text)
    if match:
        return match.group(1).strip()
    return "IDLE"

def speak_response(reply_text):
    tts = gTTS(reply_text)
    tts.save("response.mp3")
    os.system("afplay response.mp3 -r 1.3")

def save_output_json(user_input, reply_text, movement_code):
    output = {
        "input": user_input,
        "spoken_reply": reply_text,
        "movement_code": movement_code,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open("output.json", "w") as f:
        json.dump(output, f, indent=2)
    print("Saved response to output.json")

user_input = listen_to_user()
if user_input:
    bot_reply = get_bot_reply(user_input)
    print("Bot:", bot_reply)

    movement_code = extract_movement_code(bot_reply)
    print(" Movement Code:", movement_code)

    spoken_reply = bot_reply.split("ROBOT_CMD:")[0].strip()
    speak_response(spoken_reply)

    save_output_json(user_input, spoken_reply, movement_code)
