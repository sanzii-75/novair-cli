"""TUI color themes — env `NOVAIR_THEME` or the /theme slash command.

All palettes are tuned for dark terminals. Each theme carries the 5-color
banner gradient plus the semantic colors the UI consumes (accent, user text,
tool chips, dim/system text, status bar).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Theme:
    name: str
    gradient: List[str] = field(default_factory=list)  # 5 colors, teal → pink sweep
    accent: str = "#38BDF8"
    user: str = "#E9E9EF"
    tool: str = "#FBBF24"
    dim: str = "#6C7280"
    sys: str = "#94A3B8"
    bar_bg: str = "#11111B"
    bar_fg: str = "#A6ADC8"


THEMES: Dict[str, Theme] = {
    "novair": Theme(
        name="novair",
        gradient=["#5EEAD4", "#38BDF8", "#818CF8", "#C084FC", "#F472B6"],
        accent="#38BDF8", user="#E9E9EF", tool="#FBBF24",
        dim="#6C7280", sys="#94A3B8", bar_bg="#11111B", bar_fg="#A6ADC8",
    ),
    "catppuccin": Theme(
        name="catppuccin",
        gradient=["#94E2D5", "#89DCEB", "#B4BEFE", "#F5C2E7", "#F38BA8"],
        accent="#89B4FA", user="#CDD6F4", tool="#FAB387",
        dim="#6C7086", sys="#A6ADC8", bar_bg="#1E1E2E", bar_fg="#BAC2DE",
    ),
    "tokyonight": Theme(
        name="tokyonight",
        gradient=["#73DACA", "#7DCFFF", "#9D7CD8", "#BB9AF7", "#DB4B4B"],
        accent="#7AA2F7", user="#C0CAF5", tool="#E0AF68",
        dim="#565F89", sys="#A9B1D6", bar_bg="#1A1B26", bar_fg="#A9B1D6",
    ),
    "gruvbox": Theme(
        name="gruvbox",
        gradient=["#8EC07C", "#83A598", "#B16286", "#D3869B", "#FB4934"],
        accent="#83A598", user="#EBDBB2", tool="#FABD2F",
        dim="#928374", sys="#BDAE93", bar_bg="#1D2021", bar_fg="#EBDBB2",
    ),
    "dracula": Theme(
        name="dracula",
        gradient=["#50FA7B", "#8BE9FD", "#BD93F9", "#FF79C6", "#FF5555"],
        accent="#BD93F9", user="#F8F8F2", tool="#F1FA8C",
        dim="#6272A4", sys="#BFBFBF", bar_bg="#282A36", bar_fg="#F8F8F2",
    ),
    "matrix": Theme(
        name="matrix",
        gradient=["#5EFF95", "#4CDB6A", "#3AB845", "#2C9134", "#1F6B25"],
        accent="#5EFF95", user="#CCFFCC", tool="#8FFF8F",
        dim="#4E9A56", sys="#7FCF87", bar_bg="#0B0F0B", bar_fg="#7FCF87",
    ),
}


def resolve_theme(name: Optional[str]) -> Optional[Theme]:
    """Named theme lookup; None when unknown or unset."""
    if not name:
        return None
    return THEMES.get(name.strip().lower())


def theme_names() -> List[str]:
    return list(THEMES.keys())
