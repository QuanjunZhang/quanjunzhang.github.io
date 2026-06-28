#!/usr/bin/env python3
"""Generate a deterministic research word cloud from publication titles."""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS = ROOT / "_pages" / "publications.md"
OUTPUT = ROOT / "images" / "research-wordcloud.png"

WIDTH = 1200
HEIGHT = 520
PADDING = 34
MAX_WORDS = 62
SEED = 20260628

TITLE_PATTERN = re.compile(r"^-\s+`[^`]+`\s+\*\*(.+?)\*\*", re.MULTILINE)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "via",
    "we",
    "with",
    "across",
    "based",
    "boosting",
    "case",
    "class",
    "exploring",
    "far",
    "fine",
    "how",
    "improving",
    "joint",
    "large",
    "level",
    "literature",
    "partial",
    "pre",
    "progress",
    "research",
    "revisiting",
    "scale",
    "systematic",
    "the",
    "trained",
    "tuning",
    "using",
}

DISPLAY_OVERRIDES = {
    "ag": "AG",
    "ai": "AI",
    "appt": "APPT",
    "apr": "APR",
    "circle": "CIRCLE",
    "compass": "ComPass",
    "gamma": "GAMMA",
    "llm": "LLM",
    "llms": "LLMs",
    "rag": "RAG",
    "sgagent": "SGAgent",
    "testbench": "TestBench",
}

PHRASES: tuple[tuple[str, str, float], ...] = (
    ("large language models", "Large Language Models", 5.0),
    ("software engineering", "Software Engineering", 4.5),
    ("automated program repair", "Automated Program Repair", 5.5),
    ("program repair", "Program Repair", 3.5),
    ("assertion generation", "Assertion Generation", 4.0),
    ("deep assertion generation", "Deep Assertion Generation", 4.5),
    ("unit testing", "Unit Testing", 3.6),
    ("software testing", "Software Testing", 3.6),
    ("patch correctness", "Patch Correctness", 3.6),
    ("vulnerability repair", "Vulnerability Repair", 3.6),
    ("language models", "Language Models", 3.4),
    ("retrieval augmented", "Retrieval-Augmented", 3.1),
    ("machine translation", "Machine Translation", 3.0),
    ("syntactic tree pruning", "Syntactic Tree Pruning", 3.0),
    ("contrastive learning", "Contrastive Learning", 2.8),
    ("repository level", "Repository-Level", 2.8),
    ("test case prioritization", "Test Case Prioritization", 2.8),
    ("mask prediction", "Mask Prediction", 2.6),
)

PALETTE = (
    "#0f4c81",
    "#7a1f4d",
    "#256d5a",
    "#6d4c9f",
    "#a34d2f",
    "#1f6f9f",
    "#31572c",
    "#475569",
)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)


def extract_titles(markdown: str) -> list[str]:
    titles = []
    for match in TITLE_PATTERN.finditer(markdown):
        title = match.group(1)
        title = re.sub(r"\[[^\]]+\]\([^)]+\)", "", title)
        title = re.sub(r"\s+", " ", title)
        titles.append(title.strip().rstrip("."))
    if not titles:
        raise RuntimeError(f"No publication titles found in {PUBLICATIONS}")
    return titles


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[’']", "", text)
    text = re.sub(r"[-/]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def display_word(word: str) -> str:
    if word in DISPLAY_OVERRIDES:
        return DISPLAY_OVERRIDES[word]
    if word.endswith("llms"):
        return word.upper()
    return word.capitalize()


def title_terms(titles: Iterable[str]) -> Counter[str]:
    counts: Counter[str] = Counter()

    for title in titles:
        normalized = normalize(title)
        padded = f" {normalized} "

        for phrase, label, weight in PHRASES:
            if f" {phrase} " in padded:
                counts[label] += weight

        for word in normalized.split():
            if len(word) < 3 or word in STOPWORDS:
                continue
            counts[display_word(word)] += 1.0

    return counts


def find_font() -> str | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path:
        return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def intersects(rect: tuple[int, int, int, int], placed: list[tuple[int, int, int, int]]) -> bool:
    left, top, right, bottom = rect
    for other_left, other_top, other_right, other_bottom in placed:
        if not (
            right < other_left
            or left > other_right
            or bottom < other_top
            or top > other_bottom
        ):
            return True
    return False


def spiral_positions() -> Iterable[tuple[float, float]]:
    angle = 0.0
    radius = 0.0
    while True:
        yield (
            WIDTH / 2 + math.cos(angle) * radius,
            HEIGHT / 2 + math.sin(angle) * radius,
        )
        angle += 0.32
        radius += 1.35


def font_size(score: float, minimum: float, maximum: float) -> int:
    if math.isclose(minimum, maximum):
        return 36
    normalized = (score - minimum) / (maximum - minimum)
    return int(18 + normalized**0.72 * 56)


def draw_wordcloud(counts: Counter[str]) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(image)
    font_path = find_font()
    rng = random.Random(SEED)

    # Gentle guide lines make the image feel less empty without competing with words.
    for y in (HEIGHT // 3, HEIGHT * 2 // 3):
        draw.line((PADDING, y, WIDTH - PADDING, y), fill="#f3f4f6", width=1)

    terms = counts.most_common(MAX_WORDS)
    scores = [score for _, score in terms]
    min_score, max_score = min(scores), max(scores)
    placed: list[tuple[int, int, int, int]] = []

    for index, (term, score) in enumerate(terms):
        base_size = font_size(score, min_score, max_score)
        if " " in term:
            base_size = int(base_size * 0.9)
        size = base_size
        placed_word = False

        while size >= 12 and not placed_word:
            font = load_font(font_path, size)
            width, height = text_size(draw, term, font)
            margin = max(5, int(size * 0.15))

            for center_x, center_y in spiral_positions():
                jitter_x = rng.randint(-10, 10)
                jitter_y = rng.randint(-8, 8)
                left = int(center_x - width / 2 + jitter_x)
                top = int(center_y - height / 2 + jitter_y)
                rect = (
                    left - margin,
                    top - margin,
                    left + width + margin,
                    top + height + margin,
                )

                if (
                    rect[0] < PADDING
                    or rect[1] < PADDING
                    or rect[2] > WIDTH - PADDING
                    or rect[3] > HEIGHT - PADDING
                ):
                    if abs(center_x - WIDTH / 2) > WIDTH:
                        break
                    continue

                if intersects(rect, placed):
                    continue

                color = PALETTE[(index + rng.randint(0, len(PALETTE) - 1)) % len(PALETTE)]
                draw.text((left, top), term, fill=color, font=font)
                placed.append(rect)
                placed_word = True
                break

            size -= 2

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)


def main() -> None:
    titles = extract_titles(PUBLICATIONS.read_text(encoding="utf-8"))
    counts = title_terms(titles)
    draw_wordcloud(counts)
    print(f"Generated {OUTPUT.relative_to(ROOT)} from {len(titles)} publication titles")


if __name__ == "__main__":
    main()
