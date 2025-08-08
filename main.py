from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json
from typing import List, Dict
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "data.json"
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-r1-0528:free"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:3000",
    "X-Title": "AI Game Generator"
}


# Models
class GenerateGameInput(BaseModel):
    description: str
    genre_tags: List[str]

class SceneRequest(BaseModel):
    game_title: str
    previous_story: str  # can be empty if it's the first scene

class AddSceneInput(BaseModel):
    game_title: str
    scene_description: str
    characters: List[str]
    choices: List[str]

class AddCharacterInput(BaseModel):
    game_title: str
    name: str
    description: str
    abilities: List[str]

class PhaserGameRequest(BaseModel):
    game_data: Dict

# Data model
class GameFile(BaseModel):
    path: str
    content: str

class CodeAssistantRequest(BaseModel):
    prompt: str
    files: List[GameFile]

class CodeAssistantResponse(BaseModel):
    message: str
    updatedFiles: List[GameFile]


@app.post("/generate-game")
def generate_game(data: GenerateGameInput):
    prompt = (
        f"You are an expert game designer.\n"
        f"Generate a fully structured and rich adventure game based on:\n\n"
        f"Description: {data.description}\n"
        f"Genres: {', '.join(data.genre_tags)}\n\n"
        f"Return ONLY valid JSON. No markdown, no explanation.\n\n"
        f"### JSON FORMAT ###\n"
        f"{{\n"
        f"  title: string,\n"
        f"  description: string,\n"
        f"  characters: [\n"
        f"    {{ id, name, role, traits[], avatar, voiceStyle }}\n"
        f"  ],\n"
        f"environments: array of objects with id, name, description, style, accessibility_tags[] \n"
        f"scenes: [\n"
        f"    {{\n"
        f"      id: string,\n"
        f"      title: string,\n"
        f"      environment: {{ id, name, description, style, accessibility_tags[] }},\n"
        f"      dialogue: string[],\n"
        f"      choices: [\n"
        f"        {{ id, label, nextSceneId, character (optional) }}\n"
        f"      ]\n"
        f"    }}\n"
        f"  ]\n"
        f"}}"
    )

    game = call_openrouter_ai(prompt)

    if "title" in game:
        save_game_to_file(game)

    return game


# Endpoint 2 - Generate Scene for Game
@app.post("/generate-scene")
def generate_scene(data: SceneRequest):
    prompt = (
        f"Generate the next scene for a game titled '{data.game_title}'.\n"
        f"Previous story so far:\n{data.previous_story}\n\n"
        f"Return scene in JSON with: scene_description, characters (names), and choices (list of decisions)."
    )
    
    game = call_openrouter_ai(prompt)

    if "title" in game:
        save_game_to_file(game)

    return game


# Endpoint 3 - Add Scene Manually
@app.post("/add-scene")
def add_scene(scene: AddSceneInput):
    return {
        "status": "Scene added",
        "game_title": scene.game_title,
        "scene": {
            "description": scene.scene_description,
            "characters": scene.characters,
            "choices": scene.choices
        }
    }


# Endpoint 4 - Add Character
@app.post("/add-character")
def add_character(char: AddCharacterInput):
    return {
        "status": "Character added",
        "game_title": char.game_title,
        "character": {
            "name": char.name,
            "description": char.description,
            "abilities": char.abilities
        }
    }


@app.post("/generate-phaser-game")
def generate_phaser_game(data: PhaserGameRequest):
    prompt = f"""
You are an expert game developer.
Convert the following adventure game JSON into a Phaser 3 game implementation.

GAME DATA:
{json.dumps(data.game_data, indent=2)}

REQUIREMENTS:
1. Output must be valid JSON containing all files required to run the Phaser game.
2. JSON format:
{{
  "index.html": "<full HTML file code here>",
  "main.js": "<Phaser game bootstrap code>",
}}
3. The Phaser game must:
   - Load characters, environments, and scenes from the provided game JSON.
   - Use dialogue text and choices from scenes to drive gameplay.
   - Fully run using built-in Phaser example assets such as:
     - sky.png
     - platform.png
     - star.png
     - other assets from https://labs.phaser.io
   - No placeholder assets, no download instructions — the code should directly use these assets from Phaser’s CDN or example repository so the game is playable immediately.
4. The game must support keyboard, mouse, and touch input for accessibility.
5. For all graphics and platforms, TRY TO USE existing sprites, tilesets, and platforms already available in the Phaser library
6. Do NOT return markdown or explanations — only the JSON described.
"""

    game_code = call_openrouter_ai(prompt)
    return game_code

# 🔁 OpenRouter AI Call Helper
def call_openrouter_ai(user_prompt: str):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(OPENROUTER_URL, headers=HEADERS, data=json.dumps(body))
    if response.status_code == 200:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if content.startswith("```json"):
            content = content.strip("```json").strip("```").strip()
        elif content.startswith("```"):
            content = content.strip("```").strip()

        try:
            return json.loads(content)
        except:
            return content
    else:
        return {"error": response.status_code, "details": response.text}
   
def call_code_assistant(prompt: str, files: List[GameFile]) -> Dict:
    file_text = json.dumps([file.dict() for file in files], indent=2)
    full_prompt = f"""You are a helpful AI coding assistant.
The user asked:
"{prompt}"

Here is the current file structure and contents:
{file_text}

Please return:
--- message ---
Your assistant reply message.
--- updatedFiles ---
List of updated files only, in this format:
[
  {{ "path": "/src/main.js", "content": "new updated content here..." }},
  ...
]

ONLY return the above format. No markdown, no extra explanation.
"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a smart code assistant that updates files based on user intent."},
            {"role": "user", "content": full_prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(OPENROUTER_URL, headers=HEADERS, json=payload)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return parse_assistant_output(content)


# Parses AI's response into message and updated files
def parse_assistant_output(text: str) -> Dict:
    try:
        message_split = text.split("--- updatedFiles ---")
        message = message_split[0].replace("--- message ---", "").strip()
        updated_files_json = message_split[1].strip()
        updated_files = json.loads(updated_files_json)
        return {"message": message, "updatedFiles": updated_files}
    except Exception as e:
        return {
            "message": "⚠️ Error parsing assistant output: " + str(e),
            "updatedFiles": []
        }


# Route handler
@app.post("/code-assistant", response_model=CodeAssistantResponse)
def code_assistant(data: CodeAssistantRequest):
    result = call_code_assistant(data.prompt, data.files)
    return result


# Save Game to data.json
def save_game_to_file(game_data):
    existing = {}

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = {}

    title = game_data["title"]
    existing[title] = game_data

    with open(DATA_FILE, "w") as f:
        json.dump(existing, f, indent=2)