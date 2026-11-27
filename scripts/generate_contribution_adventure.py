#!/usr/bin/env python3
"""Render an original pixel-art adventure over GitHub's real contribution grid."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


USERNAME = "AoojunHappyman"
PROFILE_CALENDAR_URL = f"https://github.com/users/{USERNAME}/contributions?include_private=true"
WIDTH = 1080
HEIGHT = 348
CELL = 12
GAP = 4
PITCH = CELL + GAP
GRID_TOP = 111
GROUND_TOP = 299
SPRITE_LOGICAL_SIZE = (16, 20)
SPRITE_SCALE = 3
SPRITE_SIZE = tuple(value * SPRITE_SCALE for value in SPRITE_LOGICAL_SIZE)
FRAME_COUNT = 112
FRAME_DURATION_MS = 75

COLORS = {
    "background": "#0D1117",
    "background_soft": "#101820",
    "panel": "#161B22",
    "border": "#30363D",
    "muted": "#8B949E",
    "text": "#C9D1D9",
    "white": "#F0F6FC",
    "green_dark": "#0E4429",
    "green": "#26A641",
    "green_bright": "#39D353",
    "gold": "#FFD700",
    "gold_dark": "#9E6A03",
    "block": "#D29922",
    "red": "#E53935",
    "red_light": "#FF5A4E",
    "blue": "#2563EB",
    "blue_light": "#60A5FA",
    "skin": "#F2C38B",
    "hair": "#55351F",
    "boot": "#7A4328",
    "boot_light": "#A45A35",
    "soil": "#30261F",
    "soil_light": "#4A3428",
    "grass": "#238636",
    "grass_light": "#39D353",
}

LEVEL_COLORS = {
    0: "#161B22",
    1: "#0E4429",
    2: "#26A641",
    3: "#D29922",
    4: "#FFD700",
}


@dataclass
class ContributionDay:
    day: date
    count: int
    level: int
    week: int = 0
    row: int = 0


class CalendarHTMLParser(HTMLParser):
    """Read the same public calendar cells and tooltips GitHub renders on profiles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.days: dict[str, ContributionDay] = {}
        self.current_tooltip: str | None = None
        self.tooltip_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "td" and "ContributionCalendar-day" in (attributes.get("class") or ""):
            day_id = attributes.get("id")
            raw_date = attributes.get("data-date")
            raw_level = attributes.get("data-level")
            if day_id and raw_date and raw_level is not None:
                try:
                    self.days[day_id] = ContributionDay(
                        day=date.fromisoformat(raw_date), count=-1,
                        level=max(0, min(4, int(raw_level))),
                    )
                except ValueError:
                    return
        elif tag == "tool-tip":
            self.current_tooltip = attributes.get("for")
            self.tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self.current_tooltip:
            self.tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tool-tip" or not self.current_tooltip:
            return
        text = " ".join(self.tooltip_text)
        match = re.search(r"([\d,]+)\s+contributions?\b", text, flags=re.IGNORECASE)
        if match and self.current_tooltip in self.days:
            self.days[self.current_tooltip].count = int(match.group(1).replace(",", ""))
        elif re.search(r"\bno contributions\b", text, flags=re.IGNORECASE):
            if self.current_tooltip in self.days:
                self.days[self.current_tooltip].count = 0
        self.current_tooltip = None
        self.tooltip_text = []


def fetch_contributions() -> list[ContributionDay]:
    request = urllib.request.Request(
        PROFILE_CALENDAR_URL,
        headers={
            "User-Agent": "AoojunHappyman-contribution-adventure/1.0",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        source = response.read().decode("utf-8", errors="replace")

    parser = CalendarHTMLParser()
    parser.feed(source)
    days = sorted(parser.days.values(), key=lambda item: item.day)
    if len(days) < 350:
        raise RuntimeError(f"GitHub returned only {len(days)} contribution days; refusing to render partial data.")
    missing_counts = [item.day.isoformat() for item in days if item.count < 0]
    if missing_counts:
        preview = ", ".join(missing_counts[:4])
        raise RuntimeError(f"Could not read GitHub contribution counts for {len(missing_counts)} cells ({preview}).")

    first_sunday = days[0].day - timedelta(days=(days[0].day.weekday() + 1) % 7)
    for item in days:
        offset = (item.day - first_sunday).days
        item.week = offset // 7
        item.row = (item.day.weekday() + 1) % 7
    return days


def load_fixture(path: Path) -> list[ContributionDay]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("days", payload) if isinstance(payload, dict) else payload
    days = [
        ContributionDay(
            day=date.fromisoformat(item["date"]),
            count=int(item["count"]),
            level=max(0, min(4, int(item["level"]))),
        )
        for item in records
    ]
    days.sort(key=lambda item: item.day)
    if not days:
        raise ValueError("The input JSON contains no contribution days.")
    first_sunday = days[0].day - timedelta(days=(days[0].day.weekday() + 1) % 7)
    for item in days:
        offset = (item.day - first_sunday).days
        item.week = offset // 7
        item.row = (item.day.weekday() + 1) % 7
    return days


def make_sprite(stance: str) -> Image.Image:
    """Draw one original plumber-adventurer pose from simple pixel primitives."""
    image = Image.new("RGBA", SPRITE_LOGICAL_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    red = COLORS["red"]
    red_light = COLORS["red_light"]
    blue = COLORS["blue"]
    blue_light = COLORS["blue_light"]
    skin = COLORS["skin"]
    hair = COLORS["hair"]

    # Cap, face, fringe, moustache, nose, and a small star badge.
    draw.rectangle((4, 1, 10, 2), fill=red)
    draw.rectangle((3, 3, 11, 3), fill=red_light)
    draw.rectangle((2, 4, 10, 4), fill=red)
    draw.point((8, 2), fill=COLORS["white"])
    draw.rectangle((5, 5, 10, 7), fill=skin)
    draw.point((4, 6), fill=skin)
    draw.rectangle((5, 4, 7, 4), fill=hair)
    draw.point((9, 5), fill=COLORS["background"])
    draw.rectangle((6, 7, 10, 7), fill=hair)
    draw.point((11, 6), fill=skin)

    # Shirt and overalls.
    draw.rectangle((4, 8, 11, 12), fill=red)
    draw.rectangle((5, 10, 10, 15), fill=blue)
    draw.rectangle((5, 8, 6, 11), fill=blue_light)
    draw.rectangle((9, 8, 10, 11), fill=blue_light)
    draw.point((5, 10), fill=COLORS["gold"])
    draw.point((10, 10), fill=COLORS["gold"])

    if stance == "idle":
        draw.rectangle((2, 9, 3, 11), fill=red)
        draw.rectangle((2, 12, 3, 13), fill=skin)
        draw.rectangle((11, 9, 12, 11), fill=red)
        draw.rectangle((11, 12, 12, 13), fill=skin)
        draw.rectangle((5, 15, 7, 17), fill=blue)
        draw.rectangle((9, 15, 11, 17), fill=blue)
        draw.rectangle((4, 18, 7, 19), fill=COLORS["boot"])
        draw.rectangle((9, 18, 12, 19), fill=COLORS["boot_light"])
    elif stance == "jump":
        draw.rectangle((2, 6, 3, 8), fill=red)
        draw.rectangle((1, 5, 2, 6), fill=skin)
        draw.rectangle((11, 7, 12, 9), fill=red)
        draw.rectangle((12, 6, 13, 7), fill=skin)
        draw.rectangle((4, 15, 7, 16), fill=blue)
        draw.rectangle((9, 15, 12, 16), fill=blue)
        draw.rectangle((3, 16, 6, 17), fill=COLORS["boot"])
        draw.rectangle((10, 16, 13, 17), fill=COLORS["boot_light"])
    elif stance == "collect":
        draw.rectangle((2, 9, 3, 11), fill=red)
        draw.rectangle((1, 10, 2, 12), fill=skin)
        draw.rectangle((11, 8, 12, 10), fill=red)
        draw.rectangle((12, 7, 13, 8), fill=skin)
        draw.rectangle((5, 15, 7, 17), fill=blue)
        draw.rectangle((9, 15, 11, 17), fill=blue)
        draw.rectangle((4, 18, 7, 19), fill=COLORS["boot"])
        draw.rectangle((9, 18, 12, 19), fill=COLORS["boot_light"])
    else:
        swing = stance == "run_b"
        if swing:
            draw.rectangle((2, 7, 3, 9), fill=red)
            draw.rectangle((1, 9, 2, 10), fill=skin)
            draw.rectangle((11, 9, 12, 11), fill=red)
            draw.rectangle((12, 11, 13, 12), fill=skin)
            draw.rectangle((4, 15, 7, 16), fill=blue)
            draw.rectangle((9, 15, 12, 16), fill=blue)
            draw.rectangle((2, 17, 6, 18), fill=COLORS["boot"])
            draw.rectangle((10, 17, 14, 18), fill=COLORS["boot_light"])
        else:
            draw.rectangle((2, 9, 3, 11), fill=red)
            draw.rectangle((1, 11, 2, 12), fill=skin)
            draw.rectangle((11, 7, 12, 9), fill=red)
            draw.rectangle((12, 6, 13, 7), fill=skin)
            draw.rectangle((5, 15, 7, 17), fill=blue)
            draw.rectangle((9, 15, 11, 17), fill=blue)
            draw.rectangle((3, 18, 7, 19), fill=COLORS["boot"])
            draw.rectangle((9, 18, 13, 19), fill=COLORS["boot_light"])

    return image.resize(SPRITE_SIZE, Image.Resampling.NEAREST)


def write_sprite_sheet(path: Path) -> list[Image.Image]:
    path.parent.mkdir(parents=True, exist_ok=True)
    poses = ["idle", "run_a", "run_b", "jump", "collect"]
    sprites = [make_sprite(pose) for pose in poses]
    sheet = Image.new("RGBA", (SPRITE_SIZE[0] * len(sprites), SPRITE_SIZE[1]), (0, 0, 0, 0))
    for index, sprite in enumerate(sprites):
        sheet.alpha_composite(sprite, (index * SPRITE_SIZE[0], 0))
    sheet.save(path, optimize=True)
    return sprites


def load_font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def grid_dimensions(days: list[ContributionDay]) -> tuple[int, int, int]:
    columns = max(item.week for item in days) + 1
    grid_width = columns * PITCH - GAP
    return columns, grid_width, (WIDTH - grid_width) // 2


def build_jump_targets(days: list[ContributionDay], columns: int, grid_left: int) -> list[dict[str, int | str]]:
    by_week: dict[int, list[ContributionDay]] = {week: [] for week in range(columns)}
    for item in days:
        by_week[item.week].append(item)

    targets: list[dict[str, int | str]] = []
    for start in range(2, columns, 8):
        group = [item for week in range(start, min(start + 8, columns)) for item in by_week[week]]
        active = [item for item in group if item.level >= 2]
        if active:
            chosen = max(active, key=lambda item: (item.level, item.count, -item.row))
            target_week, target_row, kind = chosen.week, chosen.row, "coin" if chosen.level == 2 else "block"
        else:
            target_week, target_row, kind = min(start + 3, columns - 1), 4, "gap"
        targets.append({
            "x": grid_left + target_week * PITCH + CELL // 2,
            "y": GRID_TOP + target_row * PITCH + CELL // 2,
            "kind": kind,
            "level": max((item.level for item in group), default=0),
        })
    return targets


def draw_background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(image)
    # Deterministic low-contrast stars keep the background stable across frames.
    for index in range(40):
        x = (index * 193 + 73) % WIDTH
        y = 8 + ((index * 47 + 19) % 265)
        color = "#202A35" if index % 4 else "#2B3947"
        draw.point((x, y), fill=color)
        if index % 9 == 0:
            draw.point((x + 1, y), fill=color)
    draw.polygon([(0, 279), (130, 235), (230, 279), (390, 246), (520, 279), (705, 238), (835, 279), (980, 244), (1080, 270), (1080, GROUND_TOP), (0, GROUND_TOP)], fill="#111922")
    draw.polygon([(0, 288), (175, 258), (285, 288), (470, 251), (635, 288), (820, 260), (970, 289), (1080, 265), (1080, GROUND_TOP), (0, GROUND_TOP)], fill="#141E27")

    # Pixel ground, with a grass lip and repeating soil blocks.
    draw.rectangle((0, GROUND_TOP, WIDTH, HEIGHT), fill=COLORS["soil"])
    draw.rectangle((0, GROUND_TOP, WIDTH, GROUND_TOP + 7), fill=COLORS["grass"])
    draw.rectangle((0, GROUND_TOP, WIDTH, GROUND_TOP + 2), fill=COLORS["grass_light"])
    for x in range(0, WIDTH, 24):
        draw.rectangle((x, GROUND_TOP + 8, x + 23, GROUND_TOP + 29), outline=COLORS["soil_light"], width=1)
        draw.rectangle((x + 5, GROUND_TOP + 14, x + 8, GROUND_TOP + 17), fill="#5B3D2C")
    return image


def draw_pipe(draw: ImageDraw.ImageDraw, x: int) -> None:
    y = GROUND_TOP - 36
    draw.rectangle((x + 4, y + 7, x + 25, GROUND_TOP), fill="#238636")
    draw.rectangle((x, y, x + 29, y + 10), fill="#39D353", outline="#0E4429", width=2)
    draw.rectangle((x + 7, y + 12, x + 11, GROUND_TOP - 2), fill="#2EA043")
    draw.rectangle((x + 21, y + 12, x + 25, GROUND_TOP - 2), fill="#196C2E")


def draw_flag(draw: ImageDraw.ImageDraw, x: int, celebration: bool = False) -> None:
    draw.rectangle((x, GROUND_TOP - 75, x + 3, GROUND_TOP), fill="#8B949E")
    draw.ellipse((x - 2, GROUND_TOP - 80, x + 6, GROUND_TOP - 72), fill=COLORS["gold"])
    flag_color = COLORS["green_bright"] if celebration else COLORS["red"]
    draw.polygon([(x + 4, GROUND_TOP - 74), (x + 38, GROUND_TOP - 64), (x + 4, GROUND_TOP - 54)], fill=flag_color)
    draw.rectangle((x + 5, GROUND_TOP - 69, x + 15, GROUND_TOP - 65), fill=COLORS["white"])


def draw_coin(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    # Tiny original coin mark; the shine is drawn as square pixels for crisp scaling.
    draw.ellipse((cx - 3, cy - 5, cx + 3, cy + 5), fill=COLORS["gold_dark"], outline=COLORS["gold"])
    draw.rectangle((cx - 1, cy - 3, cx + 1, cy + 3), fill="#FFF2A6")
    draw.point((cx - 1, cy - 2), fill=COLORS["white"])


def draw_cell(draw: ImageDraw.ImageDraw, item: ContributionDay, grid_left: int) -> None:
    x = grid_left + item.week * PITCH
    y = GRID_TOP + item.row * PITCH
    if item.level == 0:
        draw.rounded_rectangle((x, y, x + CELL - 1, y + CELL - 1), radius=2, fill=LEVEL_COLORS[0], outline="#21262D")
    elif item.level == 1:
        draw.rounded_rectangle((x, y, x + CELL - 1, y + CELL - 1), radius=2, fill="#111922", outline="#1F6F43")
        draw.rectangle((x + 2, y + 7, x + CELL - 3, y + 10), fill=COLORS["green"])
        draw.point((x + 3, y + 6), fill=COLORS["green_bright"])
    elif item.level == 2:
        draw.rounded_rectangle((x, y, x + CELL - 1, y + CELL - 1), radius=2, fill=COLORS["green_dark"], outline=COLORS["green"])
        draw_coin(draw, x + CELL // 2, y + CELL // 2)
    elif item.level == 3:
        draw.rectangle((x, y, x + CELL - 1, y + CELL - 1), fill=COLORS["block"], outline=COLORS["gold_dark"])
        draw.line((x, y + 5, x + CELL - 1, y + 5), fill=COLORS["gold_dark"])
        draw.line((x + CELL // 2, y, x + CELL // 2, y + 4), fill=COLORS["gold_dark"])
        draw.line((x + 3, y + 6, x + 3, y + CELL - 1), fill="#F0B72F")
    else:
        draw.rectangle((x, y, x + CELL - 1, y + CELL - 1), fill=COLORS["gold"], outline=COLORS["gold_dark"])
        draw.rectangle((x + 2, y + 2, x + CELL - 4, y + 4), fill="#FFF2A6")
        draw.rectangle((x + 3, y + 7, x + 8, y + 8), fill="#D99A00")


def draw_grid(image: Image.Image, days: list[ContributionDay], columns: int, grid_left: int) -> None:
    draw = ImageDraw.Draw(image)
    month_font = load_font(10)
    row_font = load_font(9)
    by_week: dict[int, list[ContributionDay]] = {week: [] for week in range(columns)}
    for item in days:
        by_week[item.week].append(item)

    start_day = min(item.day for item in days)
    first_sunday = start_day - timedelta(days=(start_day.weekday() + 1) % 7)
    last_month: tuple[int, int] | None = None
    for week in range(columns):
        week_day = first_sunday + timedelta(days=7 * week)
        month_key = (week_day.year, week_day.month)
        if month_key != last_month:
            label = week_day.strftime("%b").upper()
            draw.text((grid_left + week * PITCH, GRID_TOP - 18), label, font=month_font, fill=COLORS["muted"])
            last_month = month_key
        for item in by_week[week]:
            draw_cell(draw, item, grid_left)

    for row, label in ((1, "M"), (3, "W"), (5, "F")):
        draw.text((grid_left - 18, GRID_TOP + row * PITCH + 2), label, font=row_font, fill="#6E7681")


def draw_legend(draw: ImageDraw.ImageDraw, grid_left: int) -> None:
    font = load_font(9)
    items = [("LOW", COLORS["green"]), ("MID", COLORS["gold"]), ("HIGH", COLORS["block"]), ("PEAK", COLORS["gold"])]
    x = grid_left + 320
    for label, color in items:
        if label == "MID":
            draw_coin(draw, x + 4, 84)
        elif label == "PEAK":
            draw.polygon([(x + 4, 79), (x + 6, 83), (x + 10, 84), (x + 6, 86), (x + 4, 90), (x + 2, 86), (x - 1, 84), (x + 2, 82)], fill=color)
        else:
            draw.rectangle((x, 80, x + 8, 88), fill=color)
        draw.text((x + 12, 80), label, font=font, fill=COLORS["muted"])
        x += 77


def draw_hud(
    image: Image.Image,
    grid_left: int,
    grid_width: int,
    total_contributions: int,
    collected_coins: int,
    progress: float,
) -> None:
    draw = ImageDraw.Draw(image)
    panel_bottom = 51
    draw.rounded_rectangle((grid_left - 1, 13, grid_left + grid_width + 1, panel_bottom), radius=7, fill=COLORS["panel"], outline=COLORS["border"])
    font = load_font(13)
    small_font = load_font(10)
    y = 25
    draw.text((grid_left + 18, y), "WORLD 1-1", font=font, fill=COLORS["gold"])
    draw.rectangle((grid_left + 166, 22, grid_left + 167, 42), fill=COLORS["border"])
    draw.text((grid_left + 187, y), f"COINS {collected_coins:03d}", font=font, fill=COLORS["gold"])
    draw.rectangle((grid_left + 351, 22, grid_left + 352, 42), fill=COLORS["border"])
    draw.text((grid_left + 372, y), f"CONTRIBUTIONS {total_contributions:04d}", font=font, fill=COLORS["text"])
    draw.text((grid_left + grid_width - 103, y + 1), "AOOJUN", font=small_font, fill=COLORS["green_bright"])

    bar_y = 62
    bar_right = grid_left + grid_width
    draw.rounded_rectangle((grid_left, bar_y, bar_right, bar_y + 5), radius=2, fill="#21262D")
    fill_right = grid_left + int(grid_width * max(0.0, min(1.0, progress)))
    if fill_right > grid_left:
        draw.rounded_rectangle((grid_left, bar_y, fill_right, bar_y + 5), radius=2, fill=COLORS["green_bright"])
        draw.rectangle((max(grid_left, fill_right - 3), bar_y, fill_right, bar_y + 5), fill=COLORS["gold"])


def draw_coin_burst(draw: ImageDraw.ImageDraw, x: int, y: int, frame: int, peak: bool) -> None:
    phase = frame % 6
    spread = 5 + phase * 2
    color = COLORS["gold"] if peak else COLORS["green_bright"]
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        px = x + dx * spread
        py = y + dy * spread // 2
        draw.rectangle((px, py, px + 2, py + 2), fill=color)
    draw.rectangle((x - 1, y - spread - 3, x + 1, y - spread), fill=COLORS["white"])


def make_palette() -> Image.Image:
    colors = list(dict.fromkeys(COLORS.values())) + ["#21262D", "#1F6F43", "#FFF2A6", "#F0B72F", "#D99A00", "#202A35", "#2B3947", "#111922", "#141E27", "#5B3D2C"]
    swatch = Image.new("RGB", (len(colors), 1))
    for x, color in enumerate(colors):
        swatch.putpixel((x, 0), Image.new("RGB", (1, 1), color).getpixel((0, 0)))
    return swatch.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def render_adventure(days: list[ContributionDay], output_path: Path, sprite_path: Path) -> dict[str, int]:
    columns, grid_width, grid_left = grid_dimensions(days)
    total_contributions = sum(item.count for item in days)
    total_coins = sum(item.level == 2 for item in days)
    targets = build_jump_targets(days, columns, grid_left)
    sprite_frames = write_sprite_sheet(sprite_path)
    sprite_by_pose = dict(zip(("idle", "run_a", "run_b", "jump", "collect"), sprite_frames))
    background = draw_background()
    static_scene = background.convert("RGBA")

    draw_hud(static_scene, grid_left, grid_width, total_contributions, 0, 0.0)
    draw = ImageDraw.Draw(static_scene)
    label_font = load_font(10)
    draw.text((grid_left, 78), "CONTRIBUTION CALENDAR", font=label_font, fill=COLORS["text"])
    draw.text((grid_left + grid_width - 145, 78), "LAST 12 MONTHS", font=label_font, fill=COLORS["muted"])
    draw_legend(draw, grid_left)
    draw_grid(static_scene, days, columns, grid_left)

    grid_right = grid_left + grid_width
    start_pipe_x = max(9, grid_left - 47)
    finish_x = min(WIDTH - 48, grid_right + 23)
    draw_pipe(draw, start_pipe_x)
    draw_flag(draw, finish_x)
    # A subtle date rail makes the graph read as a left-to-right course.
    draw.rectangle((grid_left, GRID_TOP + 7 * PITCH + 3, grid_right, GRID_TOP + 7 * PITCH + 4), fill="#21262D")

    travel_start = -SPRITE_SIZE[0] - 4
    travel_end = finish_x - SPRITE_SIZE[0] // 2
    travel_frames = 88
    celebration_frames = 10
    warp_frames = FRAME_COUNT - travel_frames - celebration_frames
    palette = make_palette()
    palette_frames: list[Image.Image] = []

    for frame_index in range(FRAME_COUNT):
        frame = static_scene.copy()
        active_travel = frame_index < travel_frames
        if active_travel:
            progress = frame_index / max(1, travel_frames - 1)
            player_x = round(travel_start + (travel_end - travel_start) * progress)
        elif frame_index < travel_frames + celebration_frames:
            progress = 1.0
            player_x = travel_end
        else:
            reset_progress = (frame_index - travel_frames - celebration_frames + 1) / warp_frames
            progress = max(0.0, 1.0 - reset_progress)
            player_x = WIDTH + 8

        collected = 0
        if progress > 0:
            current_week = (player_x + SPRITE_SIZE[0] // 2 - grid_left) // PITCH
            collected = sum(item.level == 2 and item.week <= current_week for item in days)
        if not active_travel and frame_index < travel_frames + celebration_frames:
            collected = total_coins

        draw_hud(frame, grid_left, grid_width, total_contributions, collected, progress)
        draw = ImageDraw.Draw(frame)
        draw_flag(draw, finish_x, celebration=(travel_frames <= frame_index < travel_frames + celebration_frames))

        if active_travel:
            player_center = player_x + SPRITE_SIZE[0] // 2
            chosen_target: dict[str, int | str] | None = None
            local_phase = 0.0
            for target in targets:
                distance = player_center - int(target["x"])
                if abs(distance) <= 60:
                    chosen_target = target
                    local_phase = (distance + 60) / 120
                    break

            jump_height = 0.0
            pose = "run_a" if frame_index % 6 < 3 else "run_b"
            if chosen_target:
                jump_height = (GROUND_TOP - SPRITE_SIZE[1] - int(chosen_target["y"])) * max(0.0, math.sin(local_phase * math.pi))
                pose = "collect" if chosen_target["kind"] == "coin" and 0.36 <= local_phase <= 0.64 else "jump"
            player_y = GROUND_TOP - SPRITE_SIZE[1] - round(jump_height)
            sprite = sprite_by_pose[pose]
            frame.alpha_composite(sprite, (player_x, player_y))
            if chosen_target and 0.36 <= local_phase <= 0.64:
                peak_effect = int(chosen_target["level"]) >= 4
                draw_coin_burst(draw, player_center, player_y + 20, frame_index, peak_effect)

        elif travel_frames <= frame_index < travel_frames + celebration_frames:
            sprite = sprite_by_pose["jump"]
            frame.alpha_composite(sprite, (player_x, GROUND_TOP - SPRITE_SIZE[1] - 8))
            draw.text((finish_x - 92, GROUND_TOP - 110), "COURSE CLEAR!", font=load_font(12), fill=COLORS["gold"])

        # The last and first frames are intentionally identical so the GIF loops cleanly.
        palette_frames.append(frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    palette_frames[0].save(
        output_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        disposal=2,
        optimize=True,
    )

    with Image.open(output_path) as generated:
        actual_frame_count = generated.n_frames

    return {
        "days": len(days),
        "weeks": columns,
        "contributions": total_contributions,
        "coins": total_coins,
        "frames": actual_frame_count,
        "bytes": output_path.stat().st_size,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Optional JSON fixture for local preview generation.")
    parser.add_argument("--output", type=Path, default=Path("dist/contribution-adventure.gif"))
    parser.add_argument("--sprite-sheet", type=Path, default=Path("assets/contribution-adventure-sprites.png"))
    args = parser.parse_args(argv)

    try:
        days = load_fixture(args.input) if args.input else fetch_contributions()
        result = render_adventure(days, args.output, args.sprite_sheet)
    except Exception as error:  # fail the workflow instead of publishing a blank or fabricated graph
        print(f"Contribution adventure generation failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
