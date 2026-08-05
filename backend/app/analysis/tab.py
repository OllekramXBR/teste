"""Mapping a melodic line onto a fretboard as playable tablature.

Any note above the open low E can be played in several places on a guitar. The
choice is not arbitrary: a good transcription keeps the hand in one position and
only shifts when the music demands it. That makes this a shortest-path problem —
each note contributes a set of candidate positions, and the cost of moving
between consecutive notes is what a player's hand actually has to do.
"""

from __future__ import annotations

from dataclasses import dataclass

# Standard tuning, low string first.
GUITAR_TUNING = (40, 45, 50, 55, 59, 64)
GUITAR_STRING_NAMES = ("E", "A", "D", "G", "B", "e")
MAX_FRET = 17

# Cost weights, in arbitrary units tuned against how the resulting tab reads.
POSITION_SHIFT_COST = 1.0  # per fret the hand travels
STRING_CHANGE_COST = 0.35  # per string crossed
HIGH_FRET_COST = 0.06  # mild preference for the lower neck
OPEN_STRING_BONUS = 0.8  # open strings are free to play and ring out


@dataclass(frozen=True)
class TabPosition:
    string: int  # 0 = lowest-pitched string
    fret: int


def candidates(midi: int, tuning: tuple[int, ...] = GUITAR_TUNING) -> list[TabPosition]:
    """Every place ``midi`` can be played on the neck."""
    positions = []
    for string, open_note in enumerate(tuning):
        fret = midi - open_note
        if 0 <= fret <= MAX_FRET:
            positions.append(TabPosition(string=string, fret=fret))
    return positions


def _transition_cost(previous: TabPosition, current: TabPosition) -> float:
    # Open strings do not move the hand, so they never incur a shift cost.
    if previous.fret == 0 or current.fret == 0:
        shift = 0.0
    else:
        shift = abs(previous.fret - current.fret) * POSITION_SHIFT_COST
    return shift + abs(previous.string - current.string) * STRING_CHANGE_COST


def _node_cost(position: TabPosition) -> float:
    cost = position.fret * HIGH_FRET_COST
    if position.fret == 0:
        cost -= OPEN_STRING_BONUS
    return cost


def assign_positions(
    midi_notes: list[int], tuning: tuple[int, ...] = GUITAR_TUNING
) -> list[TabPosition | None]:
    """Choose a fretboard position for each note, minimising hand movement.

    Notes outside the instrument's range get ``None`` rather than being forced
    into a wrong octave — a transcription that silently moves notes is worse
    than one that admits the gap.
    """
    if not midi_notes:
        return []

    layers = [candidates(note, tuning) for note in midi_notes]

    best_costs: list[list[float]] = []
    backpointers: list[list[int]] = []
    previous_costs: list[float] = []
    previous_layer: list[TabPosition] = []

    for layer in layers:
        if not layer:
            # Unplayable note: break the chain so the next note starts fresh.
            best_costs.append([])
            backpointers.append([])
            previous_costs, previous_layer = [], []
            continue

        costs: list[float] = []
        pointers: list[int] = []
        for position in layer:
            base = _node_cost(position)
            if not previous_layer:
                costs.append(base)
                pointers.append(-1)
                continue
            options = [
                previous_costs[index] + _transition_cost(previous_position, position)
                for index, previous_position in enumerate(previous_layer)
            ]
            best_index = min(range(len(options)), key=options.__getitem__)
            costs.append(base + options[best_index])
            pointers.append(best_index)

        best_costs.append(costs)
        backpointers.append(pointers)
        previous_costs, previous_layer = costs, layer

    # Walk backwards through each contiguous run of playable notes.
    result: list[TabPosition | None] = [None] * len(midi_notes)
    index = len(midi_notes) - 1
    while index >= 0:
        if not layers[index]:
            index -= 1
            continue
        run_end = index
        run_start = index
        while run_start > 0 and layers[run_start - 1]:
            run_start -= 1

        chosen = min(range(len(best_costs[run_end])), key=best_costs[run_end].__getitem__)
        for step in range(run_end, run_start - 1, -1):
            result[step] = layers[step][chosen]
            chosen = backpointers[step][chosen] if backpointers[step][chosen] >= 0 else chosen
        index = run_start - 1

    return result


def note_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"
