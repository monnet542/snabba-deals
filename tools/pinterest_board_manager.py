"""
Pinterest Board Manager
Lists existing boards and creates new ones as needed.
"""

import json
import os
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_BASE = "https://api.pinterest.com/v5"


def get_boards(token):
    """List all boards for the authenticated user."""
    boards = []
    bookmark = None

    while True:
        params = {"page_size": 25}
        if bookmark:
            params["bookmark"] = bookmark

        resp = requests.get(
            f"{API_BASE}/boards",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )

        if resp.status_code != 200:
            print(f"[ERROR] Failed to list boards: {resp.status_code}")
            print(resp.text)
            return boards

        data = resp.json()
        boards.extend(data.get("items", []))

        bookmark = data.get("bookmark")
        if not bookmark:
            break

    return boards


def create_board(token, name, description=""):
    """Create a new Pinterest board."""
    resp = requests.post(
        f"{API_BASE}/boards",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "name": name,
            "description": description,
            "privacy": "PUBLIC",
        },
    )

    if resp.status_code in (200, 201):
        board = resp.json()
        print(f"  Created board: {name} (ID: {board['id']})")
        return board
    else:
        print(f"  [ERROR] Failed to create board '{name}': {resp.status_code}")
        print(f"  {resp.text}")
        return None


def ensure_boards_exist(token, config):
    """Make sure all boards from config exist. Create missing ones."""
    board_mapping = config["pinterest"]["board_mapping"]
    needed_boards = set(board_mapping.values())

    existing = get_boards(token)
    existing_names = {b["name"].lower(): b for b in existing}

    board_id_map = {}

    for board_name in needed_boards:
        if board_name.lower() in existing_names:
            board = existing_names[board_name.lower()]
            board_id_map[board_name] = board["id"]
            print(f"  Board exists: {board_name} (ID: {board['id']})")
        else:
            board = create_board(token, board_name, f"Curated picks: {board_name}")
            if board:
                board_id_map[board_name] = board["id"]

    return board_id_map


def get_board_id_for_category(category, config, board_id_map):
    """Get the board ID for a given product category."""
    board_mapping = config["pinterest"]["board_mapping"]
    board_name = board_mapping.get(category, board_mapping.get("default", "Top Deals"))
    return board_id_map.get(board_name)


def main():
    from pinterest_auth import get_valid_token

    token = get_valid_token()
    if not token:
        print("[ERROR] Could not get Pinterest token")
        sys.exit(1)

    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    print("\nEnsuring all boards exist...")
    board_id_map = ensure_boards_exist(token, config)

    print(f"\nBoard mapping ({len(board_id_map)} boards):")
    for name, bid in board_id_map.items():
        print(f"  {name} -> {bid}")

    return board_id_map


if __name__ == "__main__":
    main()
