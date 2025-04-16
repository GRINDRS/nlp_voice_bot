import paho.mqtt.client as mqtt
import speech_recognition as sr
from gtts import gTTS
import os
import time
import json
import random
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MQTT_BROKER = "localhost" 
MQTT_PORT = 1883
TOPIC_MOVEMENT = "movement"
TOPIC_ARRIVED = "arrived"

mqtt_client = mqtt.Client()

EXHIBITS = [
    {"keyword": "da vinci", "location": "Renaissance Art Hall"},
    {"keyword": "van gogh", "location": "Impressionist Gallery"},
    {"keyword": "dinosaur", "location": "Natural History Wing"},
    {"keyword": "space", "location": "Cosmos Exploration Room"},
    {"keyword": "egypt", "location": "Ancient Egypt Exhibit"},
    {"keyword": "robot", "location": "Technology and Innovation Lab"},
    {"keyword": "marine", "location": "Ocean Wonders Zone"},
    {"keyword": "volcano", "location": "Earth Science Theatre"},
    {"keyword": "medieval", "location": "Medieval Europe Hall"},
    {"keyword": "fashion", "location": "Historic Fashion Gallery"},
    {"keyword": "ai", "location": "Artificial Intelligence Hub"},
    {"keyword": "greek", "location": "Ancient Greece Exhibit"},
    {"keyword": "china", "location": "Dynasties of China Pavilion"},
    {"keyword": "australia", "location": "First Nations Cultural Space"},
    {"keyword": "insect", "location": "Entomology Showcase"},
    {"keyword": "music", "location": "Sounds Through the Ages Room"},
    {"keyword": "photography", "location": "Digital Media and Photography Wing"},
    {"keyword": "cars", "location": "Automotive Innovations Hall"},
    {"keyword": "planes", "location": "Aviation Heritage Gallery"},
    {"keyword": "medicine", "location": "History of Medicine Chamber"},
]

def on_arrived(client, userdata, message):
    print(" Arrived at exhibit!")
    handle_conversation_after_arrival()

mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.subscribe(TOPIC_ARRIVED)
mqtt_client.on_message = on_arrived
mqtt_client.loop_start()

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
        print("You said:", text)
        return text
    except Exception as e:
        print("Error:", e)
        return None

def is_vague_input(user_text):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Determine if the user input is vague (unspecific or unsure) or specific (mentions topics or interests). Reply ONLY with 'vague' or 'specific'."},
            {"role": "user", "content": user_text}
        ]
    )
    return response.choices[0].message.content.strip().lower() == "vague"

def choose_exhibit_locations(user_text):
    lower_text = user_text.lower()
    matched_locations = []

    for exhibit in EXHIBITS:
        if exhibit["keyword"] in lower_text and exhibit["location"] not in matched_locations:
            matched_locations.append(exhibit["location"])
        if len(matched_locations) == 3:
            break

    if len(matched_locations) < 3:
        remaining = [ex["location"] for ex in EXHIBITS if ex["location"] not in matched_locations]
        matched_locations += random.sample(remaining, 3 - len(matched_locations))

    return matched_locations

def generate_gpt_reply(user_text, locations):
    location_str = ", ".join(locations)
    prompt = (
        f"You are a friendly museum tour guide robot. A visitor has shown interest. "
        f"Generate a warm, concise tour intro using these stops: {location_str}. "
        "Keep it under 3 sentences. Do not include movement instructions."
    )
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text}
        ]
    )
    return response.choices[0].message.content.strip()

def speak_response(reply_text):
    tts = gTTS(reply_text)
    tts.save("response.mp3")
    os.system("afplay response.mp3 -r 1.3")

def send_movement_command(location):
    print(f"Sending location to movement channel: {location}")
    mqtt_client.publish(TOPIC_MOVEMENT, location)

def handle_conversation_after_arrival():
    response = "Here we are! This piece is truly fascinating. Would you like to hear more about it or continue the tour?"
    print("Bot:", response)
    speak_response(response)

def save_output_json(user_input, reply_text, locations):
    output = {
        "input": user_input,
        "spoken_reply": reply_text,
        "matched_locations": locations,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open("output.json", "w") as f:
        json.dump(output, f, indent=2)
    print("Saved response to output.json")

user_input = listen_to_user()
if user_input:
    vague = is_vague_input(user_input)
    locations = choose_exhibit_locations(user_input) if not vague else random.sample([ex["location"] for ex in EXHIBITS], 3)

    intro = "Hey! I’m your guide for today’s museum tour."
    print("Bot:", intro)
    speak_response(intro)

    gpt_reply = generate_gpt_reply(user_input, locations)
    print("Bot:", gpt_reply)
    speak_response(gpt_reply)

    send_movement_command(locations[0])
    save_output_json(user_input, gpt_reply, locations)
