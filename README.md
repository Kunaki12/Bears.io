# Bears.io

A small Agar.io-style survival game where you start as a small bear and grow by eating food, stealing territory, and out-sizing rivals.

## Play Locally

Install the server dependency and start the web game:

```powershell
python -m pip install -r requirements.txt
python server.py
```

Open `http://localhost:8765` in Chrome, enter a bear name, and select **Join arena**. The page and WebSocket game server are served together.

## Deploy Publicly

The included `render.yaml` can deploy the page and multiplayer server together on Render. Push this folder to a GitHub repository, create a new Blueprint in Render from that repository, and deploy it. Render assigns an HTTPS public URL; the game automatically uses a secure WebSocket at that same host. The free service may sleep when unused, so choose an always-on plan for a continuously available arena.

## Run the Python Version

```bash
python -m pip install pygame
python main.py
```

## Controls
- `W`, `A`, `S`, `D` or arrow keys: move
- Hold `SPACE`: dash
- `P` or `ESC`: pause
- Avoid larger bears
- Eat smaller bears and food to grow

## Goal
Become the biggest bear on the map and dominate the arena.
