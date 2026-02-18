import pygame

from zombie_escape.render.decay_effects import (
    BURNED_DECAY_EFFECT_DURATION_FRAMES,
    DECAY_EFFECT_DURATION_FRAMES,
    DecayingEntityEffect,
)


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        flags = pygame.HIDDEN if hasattr(pygame, "HIDDEN") else 0
        pygame.display.set_mode((1, 1), flags=flags)


def test_burned_tone_is_warmer_than_grayscale() -> None:
    _init_pygame()
    src = pygame.Surface((4, 4), pygame.SRCALPHA)
    src.fill((120, 120, 120, 255))

    gray = DecayingEntityEffect(src, (2, 2), tone="grayscale")
    burned = DecayingEntityEffect(src, (2, 2), tone="burned")

    g = gray.surface.get_at((1, 1))
    b = burned.surface.get_at((1, 1))
    assert b.r > b.g >= b.b
    assert b.r > g.r or b.g < g.g


def test_burned_tone_default_duration_is_extended() -> None:
    _init_pygame()
    src = pygame.Surface((6, 6), pygame.SRCALPHA)
    src.fill((120, 120, 120, 255))

    gray = DecayingEntityEffect(src, (3, 3), tone="grayscale")
    burned = DecayingEntityEffect(src, (3, 3), tone="burned")

    assert gray.duration_frames == DECAY_EFFECT_DURATION_FRAMES
    assert burned.duration_frames == BURNED_DECAY_EFFECT_DURATION_FRAMES
