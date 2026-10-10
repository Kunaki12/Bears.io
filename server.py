import asyncio
import json
import math
import os
import random
import time
from pathlib import Path

from aiohttp import WSMsgType, web


WORLD = 5000
PORT = int(os.environ.get("PORT", "8765"))
PLAYER_SPEED = 240
FOOD_COUNT = 250
BOT_COUNT = 18
FOOD_COLORS = ["#ed9a5e", "#79bc80", "#e56f62", "#e6c56b", "#a5bd72"]
BEAR_COLORS = ["#754b32", "#a2673f", "#526d4c", "#b17a50", "#685547"]


def random_between(low, high):
    return random.uniform(low, high)


def make_food():
    return {
        "x": random_between(24, WORLD - 24),
        "y": random_between(24, WORLD - 24),
        "size": random_between(4, 8),
        "color": random.choice(FOOD_COLORS),
        "phase": random.uniform(0, math.tau),
    }


def make_bot(index):
    return {
        "id": f"bot-{index}",
        "x": random_between(80, WORLD - 80),
        "y": random_between(80, WORLD - 80),
        "radius": random_between(13, 34),
        "color": BEAR_COLORS[index % len(BEAR_COLORS)],
        "name": f"Bear {index + 1:02}",
        "direction": random.uniform(0, math.tau),
        "turnIn": random_between(0.5, 3),
    }


class Arena:
    def __init__(self):
        self.players = {}
        self.clients = {}
        self.next_id = 1
        self.food = [make_food() for _ in range(FOOD_COUNT)]
        self.bots = [make_bot(index) for index in range(BOT_COUNT)]

    def add_player(self, websocket, name):
        player_id = self.next_id
        self.next_id += 1
        player = {
            "id": player_id,
            "name": name[:18] or f"Bear {player_id}",
            "x": random_between(100, WORLD - 100),
            "y": random_between(100, WORLD - 100),
            "radius": 24,
            "score": 0,
            "energy": 1,
            "color": random.choice(BEAR_COLORS),
            "moveX": 0,
            "moveY": 0,
            "boost": False,
        }
        self.players[player_id] = player
        self.clients[player_id] = websocket
        return player_id

    def state(self):
        public_players = [
            {key: player[key] for key in ("id", "name", "x", "y", "radius", "score", "energy", "color")}
            for player in self.players.values()
        ]
        public_bots = [
            {key: bot[key] for key in ("id", "name", "x", "y", "radius", "color")}
            for bot in self.bots
        ]
        return {"type": "state", "players": public_players, "food": self.food, "bots": public_bots}

    def respawn(self, entity):
        entity["x"] = random_between(100, WORLD - 100)
        entity["y"] = random_between(100, WORLD - 100)

    def tick(self, dt):
        for player in list(self.players.values()):
            length = math.hypot(player["moveX"], player["moveY"])
            if length:
                speed = PLAYER_SPEED * (1.65 if player["boost"] and player["energy"] > 0 else 1)
                player["x"] += player["moveX"] / length * speed * dt
                player["y"] += player["moveY"] / length * speed * dt
            player["energy"] = max(0, min(1, player["energy"] + (-0.42 if player["boost"] and length else 0.22) * dt))
            player["x"] = max(player["radius"], min(WORLD - player["radius"], player["x"]))
            player["y"] = max(player["radius"], min(WORLD - player["radius"], player["y"]))

            for index in range(len(self.food) - 1, -1, -1):
                item = self.food[index]
                if math.hypot(player["x"] - item["x"], player["y"] - item["y"]) < player["radius"] + item["size"]:
                    player["radius"] += item["size"] * 0.12
                    player["score"] += 1
                    self.food[index] = make_food()

        for bot in self.bots:
            bot["turnIn"] -= dt
            if bot["turnIn"] <= 0:
                bot["direction"] += random_between(-1.5, 1.5)
                bot["turnIn"] = random_between(0.6, 2.8)
            bot_speed = 22
            bot["x"] += math.cos(bot["direction"]) * bot_speed * dt
            bot["y"] += math.sin(bot["direction"]) * bot_speed * dt
            if bot["x"] < bot["radius"] or bot["x"] > WORLD - bot["radius"]:
                bot["direction"] = math.pi - bot["direction"]
            if bot["y"] < bot["radius"] or bot["y"] > WORLD - bot["radius"]:
                bot["direction"] = -bot["direction"]
            bot["x"] = max(bot["radius"], min(WORLD - bot["radius"], bot["x"]))
            bot["y"] = max(bot["radius"], min(WORLD - bot["radius"], bot["y"]))

        for player in self.players.values():
            for bot in self.bots:
                if math.hypot(player["x"] - bot["x"], player["y"] - bot["y"]) >= player["radius"] + bot["radius"]:
                    continue
                if player["radius"] > bot["radius"] * 1.15:
                    player["radius"] += bot["radius"] * 0.15
                    player["score"] += 5
                    self.respawn(bot)
                    bot["radius"] = random_between(13, 34)
                elif bot["radius"] > player["radius"] * 1.15:
                    player["radius"] = max(20, player["radius"] * 0.97)
                    player["score"] = max(0, player["score"] - 3)
                    self.respawn(player)

        players = list(self.players.values())
        for index, player in enumerate(players):
            for other in players[index + 1:]:
                if math.hypot(player["x"] - other["x"], player["y"] - other["y"]) >= player["radius"] + other["radius"]:
                    continue
                if player["radius"] > other["radius"] * 1.15:
                    player["radius"] += other["radius"] * 0.15
                    player["score"] += 5
                    other["radius"] = 24
                    other["score"] = 0
                    self.respawn(other)
                elif other["radius"] > player["radius"] * 1.15:
                    other["radius"] += player["radius"] * 0.15
                    other["score"] += 5
                    player["radius"] = 24
                    player["score"] = 0
                    self.respawn(player)


async def handle_client(request):
    arena = request.app["arena"]
    websocket = web.WebSocketResponse(heartbeat=20, max_msg_size=16_384)
    await websocket.prepare(request)
    player_id = None
    try:
        async for incoming in websocket:
            if incoming.type != WSMsgType.TEXT:
                if incoming.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
                continue
            try:
                message = json.loads(incoming.data)
            except (json.JSONDecodeError, TypeError):
                continue

            if player_id is None:
                if message.get("type") != "join":
                    await websocket.send_json({"type": "error", "message": "Join message required."})
                    continue
                player_id = arena.add_player(websocket, str(message.get("name", "Bear")))
                await websocket.send_json({
                    "type": "welcome",
                    "id": player_id,
                    "state": arena.state(),
                }, dumps=lambda value: json.dumps(value, separators=(",", ":")))
            elif message.get("type") == "input":
                player = arena.players.get(player_id)
                if player is not None:
                    try:
                        player["moveX"] = max(-1, min(1, int(message.get("x", 0))))
                        player["moveY"] = max(-1, min(1, int(message.get("y", 0))))
                    except (TypeError, ValueError):
                        continue
                    player["boost"] = bool(message.get("boost", False))
    finally:
        if player_id is not None:
            arena.players.pop(player_id, None)
            arena.clients.pop(player_id, None)
    return websocket


async def serve_index(_request):
    return web.FileResponse(Path(__file__).with_name("index.html"))


async def game_loop(app):
    arena = app["arena"]
    previous = time.monotonic()
    last_broadcast = previous
    while True:
        now = time.monotonic()
        dt = min(now - previous, 0.05)
        previous = now
        arena.tick(dt)
        if now - last_broadcast >= 0.05:
            state = json.dumps(arena.state(), separators=(",", ":"))
            disconnected = []
            for player_id, websocket in list(arena.clients.items()):
                try:
                    await websocket.send_str(state)
                except (ConnectionError, RuntimeError):
                    disconnected.append(player_id)
            for player_id in disconnected:
                arena.players.pop(player_id, None)
                arena.clients.pop(player_id, None)
            last_broadcast = now
        await asyncio.sleep(1 / 60)


async def start_game_loop(app):
    app["game_task"] = asyncio.create_task(game_loop(app))


async def stop_game_loop(app):
    app["game_task"].cancel()
    try:
        await app["game_task"]
    except asyncio.CancelledError:
        pass


def create_app():
    app = web.Application()
    app["arena"] = Arena()
    app.router.add_get("/", serve_index)
    app.router.add_get("/index.html", serve_index)
    app.router.add_get("/ws", handle_client)
    app.on_startup.append(start_game_loop)
    app.on_cleanup.append(stop_game_loop)
    return app


if __name__ == "__main__":
    try:
        web.run_app(create_app(), host="0.0.0.0", port=PORT)
    except KeyboardInterrupt:
        print("\nBears.io server stopped.")