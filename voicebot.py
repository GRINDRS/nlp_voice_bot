import paho.mqtt.client as mqtt
import speech_recognition as sr
import os
import time
import random
import subprocess
from gtts import gTTS
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_MOVEMENT = "movement"
TOPIC_ARRIVED = "arrived"

mqtt_client = mqtt.Client(protocol=mqtt.MQTTv311)

EXHIBITS = [
    {"keyword": "scream",       "location": "The Scream by Edvard Munch"},
    {"keyword": "starry night", "location": "Starry Night by Vincent van Gogh"},
    {"keyword": "sunflower",    "location": "Sunflowers by Vincent van Gogh"},
    {"keyword": "liberty",      "location": "Liberty Leading the People by Eugène Delacroix"},
    {"keyword": "mona lisa",    "location": "Mona Lisa by Leonardo da Vinci"},
    {"keyword": "egyptian",     "location": "Ancient Egyptian Statue"},
    {"keyword": "plushy dog",   "location": "Plushy Dog Sculpture"},
]
pop_locations = ["The Scream by Edvard Munch", "Mona Lisa by Leonardo da Vinci", "Starry Night by Vincent van Gogh"]
current_location = None
upcoming_locations = []
visited: set[str] = set()

def speak(text):
    print("Bot:", text)
    try:
        tts = gTTS(text=text, lang='en')
        tts.save("output.mp3")
        subprocess.run([
            "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
            "-af", "atempo=1.3", "output.mp3"
        ], check=True)
    except Exception as e:
        print(f"Audio error (continuing with text only): {e}")

def listen_to_user():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        print("Listening ...")
        try:
            audio = recognizer.listen(source, timeout=6, phrase_time_limit=20)
            text = recognizer.recognize_google(audio)
            print("You said:", text)
            return text
        except Exception as e:
            print("Error:", e)
            return None

YES_WORDS  = {"yes", "sure", "okay", "sounds good", "yep", "yeah", "alright", "why not"}
NO_WORDS   = {"no", "nope", "another", "different", "change", "don't"}
MOVE_WORDS = {
    "move on", "next", "continue", "let's go", "go on",
    "no questions", "no question"     
}
END_WORDS  = {"done", "stop", "that's all", "end", "quit", "exit"}  

def _contains(text: str, word_set: set[str]) -> bool:
    t = text.lower()
    return any(w in t for w in word_set)

def wants_yes(text: str | None) -> bool:
    return bool(text) and _contains(text, YES_WORDS)

def wants_no(text: str | None) -> bool:
    return bool(text) and _contains(text, NO_WORDS)

def wants_move_on(text: str | None) -> bool:
    return bool(text) and (_contains(text, MOVE_WORDS) or wants_yes(text))

def wants_to_end(text: str | None) -> bool:
    return bool(text) and _contains(text, END_WORDS)

def send_movement_command(location: str) -> None:
    print(f"Sending location to movement channel: {location}")
    mqtt_client.publish(TOPIC_MOVEMENT, location)

def simulate_arrival() -> None:         
    time.sleep(2)
    on_arrived(None, None, type("MQTTMessage", (object,), {"topic": TOPIC_ARRIVED, "payload": b""}))

def on_arrived(client, userdata, message):
    print(f"\nArrived at: {current_location}")

def exhibit_summary(name: str) -> str:
    return client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system",
                   "content": f"You are a museum guide. Provide a warm, engaging 2-3 sentence summary about the exhibit '{name}'."}]
    ).choices[0].message.content.strip()

def answer_question(exhibit: str, question: str) -> str:
    return client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": f"You are a museum guide at '{exhibit}'. Answer visitor questions clearly but concisely."},
            {"role": "user", "content": question}
        ]
    ).choices[0].message.content.strip()

def propose_exhibit(unvisited: list[str]) -> str | None:
    if not unvisited:
        return None
    while unvisited:
        choice = random.choice(unvisited)
        speak(f"How about we head to the {choice}? How does that sound?")
        reply = listen_to_user()

        if wants_to_end(reply):
            return None
        if wants_yes(reply):
            return choice        
        unvisited.remove(choice)
        if unvisited:
            speak("No problem, let me suggest another option.")
    return None

def end_tour() -> None:
    speak("Thanks for visiting! I hope you enjoy the rest of your day at the museum.")
    send_movement_command("initial")
    raise SystemExit

def wants_to_see_another(text):
    # Filter exhibits not already visited or upcoming
    available_exhibits = [
        e for e in EXHIBITS 
        if e['location'] not in visited and e['location'] not in upcoming
    ]
    # Format as string for GPT
    exhibit_list = ", ".join(f"{e['keyword']} ({e['location']})" for e in available_exhibits)
    if not available_exhibits:
        return []
    # Query the model
    reply = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a helpful museum guide. If the user is asking to see another painting, "
                    f"select the most relevant one from this list: {exhibit_list}. "
                    f"Return only the full painting name (in parentheses). If not asking to see another painting, reply with 'none'."
                )
            },
            {"role": "user", "content": text}
        ]
    ).choices[0].message.content.strip()
    # Clean output
    if reply.lower() == "none":
        return [] 
    # Match the returned location to confirm it's valid
    for e in available_exhibits:
        if e['location'].lower() == reply.lower():
            return [e['location']]
    return []  # fallback if response doesn't match any available location

def find_painting(text):
    # Filter exhibits not already visited or upcoming
    available_exhibits = [
        e for e in EXHIBITS 
        if e['location'] not in visited and e['location'] not in upcoming
    ]
    
    # Return empty if no exhibits left
    if not available_exhibits:
        return []

    # Format exhibits as a string for GPT
    exhibit_list = ", ".join(f"{e['keyword']} ({e['location']})" for e in available_exhibits)

    # Query OpenAI
    reply = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a helpful museum guide. The user is asking to see another painting. "
                    f"Choose the most relevant one from this list: {exhibit_list}. "
                    f"If none clearly match the request, choose the most popular. "
                    f"Return only the full painting name (in parentheses), then a comma, then a short message explaining the choice."
                )
            },
            {"role": "user", "content": text}
        ]
    ).choices[0].message.content.strip()

    # Parse response
    if "," in reply:
        painting, message = reply.split(",", 1)
        return [painting.strip(), message.strip()]
    else:
        # fallback if response wasn't comma-separated
        return [reply.strip(), "Here's your next painting."]


# MQTT setup
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.subscribe(TOPIC_ARRIVED)
mqtt_client.on_message = on_arrived
mqtt_client.loop_start()

# Start interaction
speak("""Hi! Welcome to the museum, I will be your tour guide for today. 
      Would you like a guided tour or to roam freely?""")
tour_type = listen_to_user()
if tour_type is None or _contains(tour_type, {"guided tour", "shown", "guide", "show me", "tour"}):
    speak("Great! we will commence a guided tour.")
    speak("What kind of exhibits are you interested in seeing today?")
    first = listen_to_user()
    if not first or _contains(first, {"don't know", "not sure", "unsure", "idk"}):
        speak("""You are unsure, that is all good. 
              Let's start with the popular one, if you decide to you want to see an exhibit, just ask.""")
        upcoming = pop_locations
    else:
        def choose_locs(text: str) -> list[str]:
            exhibit_list = ", ".join(f"{e['keyword']} ({e['location']})" for e in EXHIBITS)
            reply = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system",
                    "content": f"Choose up to 3 exhibit matching the user's interest from: {exhibit_list}. Return a comma-separated list or 'none'."},
                    {"role": "user", "content": text}
                ]
            ).choices[0].message.content.strip()
            return [] if reply.lower() == "none" else [loc.strip() for loc in reply.split(",")]
        upcoming = choose_locs(first)
    if not upcoming:
        speak("""I couldn't find any exhibits matching your interest. 
              Let's start with the popular one, if you decide to you want to see an exhibit, just ask.""")
        upcoming = pop_locations
    while True:
        current_location = upcoming.pop(0)
        visited.add(current_location)
        send_movement_command(current_location)
        simulate_arrival()
        speak(exhibit_summary(current_location))

        while True:
            speak("Do you have any questions about this exhibit, or would you like to move on?")
            r = listen_to_user()
            if not r:
                speak("I didn't catch that, so let's move on.")
                break
            if wants_to_see_another(r) is not None:
                upcoming.append(wants_to_see_another(r))
                break
            if wants_to_end(r):
                end_tour()
            if wants_move_on(r):
                break
        
            speak(answer_question(current_location, r))

        if not upcoming:
            speak("That is the end of our tour would you like to visit any more exhibits or finish the tour?")
            nxt = listen_to_user()
            if wants_to_end(nxt) or wants_no(nxt) or not nxt or _contains(nxt, {"don't know", "not sure", "idk"}):  
                end_tour()
            else:
                speak("Great! Anything you want to see that you have not yet")
                text= listen_to_user()
                def choose_more_locs(text: str) -> list[str]:
                    exhibit_list = ", ".join(f"{e['keyword']} ({e['location']})" for e in EXHIBITS)
                    visited_list = ", ".join(visited)
                    reply = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system",
                            "content": f"Choose up to 3 exhibit that best match the user's interest from: {exhibit_list}, that has not been visited in {visited_list}. If no exhibits can be found pick the most popular. Return a comma-separated list."},
                            {"role": "user", "content": text}
                        ]
                    ).choices[0].message.content.strip()
                    return [loc.strip() for loc in reply.split(",")]
                upcoming = choose_more_locs(text)
else:
    speak("Great we will roam freely!")
    while True:
        speak("What exhibit do you want to see now?")
        ans = listen_to_user()
        if wants_to_end(ans) or ans is None:
            end_tour()
        ##functionality for choosing painting here
        [current_location, message] = find_painting(ans)
        speak(message)
        visited.add(current_location)
        send_movement_command(current_location)
        simulate_arrival()
        speak(exhibit_summary(current_location))
        while True:
            speak("Do you have any questions about this exhibit, or would you like to move on?")
            r = listen_to_user()
            if not r:
                speak("I didn't catch that, so let's move on.")
                break
            if wants_move_on(r):
                speak("Okay, let's move on.")
                break
        
            speak(answer_question(current_location, r))  
