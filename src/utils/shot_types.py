"""BWF Shot Type Taxonomy — 23 technical actions.

Consistent with Sheng et al. (Scientific Reports, 2025).
"""

SHOT_TYPES = {
    1: "High",
    2: "Smash",
    3: "Dribble",
    4: "Push",
    5: "Slice / Drop",
    6: "Lift",
    7: "Block smash",
    8: "Net front",
    9: "Clear",
    10: "Net drop from lift",
    11: "Lift from slice",
    12: "Pull",
    13: "Hook",
    14: "Slice lift",
    15: "Block",
    16: "Lift smash",
    17: "Block hook",
    18: "Hook from lift",
    19: "Drive",
    20: "Net drop from slice drive",
    21: "Lift from slice drive",
    22: "Flat high",
    23: "Block from slice drive",
}

COURT_ZONES = {
    1: {"row": "net", "position": "left"},
    2: {"row": "net", "position": "center"},
    3: {"row": "net", "position": "right"},
    4: {"row": "mid", "position": "left"},
    5: {"row": "mid", "position": "center"},
    6: {"row": "mid", "position": "right"},
    7: {"row": "back", "position": "left"},
    8: {"row": "back", "position": "center"},
    9: {"row": "back", "position": "right"},
}

OUTCOMES = ["in_play", "winner", "error"]
