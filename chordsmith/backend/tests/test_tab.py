from app.analysis import tab
from app.analysis.tab import TabPosition


def test_candidates_cover_every_playable_string():
    # A4 (69) sits on the G, B and high E strings within reach; on the D string
    # it would be fret 19, past where the transcription bothers to look.
    positions = tab.candidates(69)
    assert {(p.string, p.fret) for p in positions} == {(3, 14), (4, 10), (5, 5)}


def test_candidates_are_empty_below_the_range():
    assert tab.candidates(30) == []  # F#1, below the open low E


def test_open_strings_are_found():
    assert TabPosition(string=0, fret=0) in tab.candidates(40)  # open low E


def test_assignment_keeps_the_hand_in_one_position():
    # G3 to G4 fits comfortably in open position. A scale should be laid out
    # across the strings there rather than run up a single string, which is what
    # a naive per-fret distance cost would produce.
    scale = [55, 57, 59, 60, 62, 64, 66, 67]
    positions = tab.assign_positions(scale)
    assert all(position is not None for position in positions)

    frets = [position.fret for position in positions if position]
    assert max(frets) - min(frets) <= 5

    strings = {position.string for position in positions if position}
    assert len(strings) >= 3, "a scale played on one string is not how anyone reads tab"


def test_assignment_goes_up_the_neck_when_the_notes_demand_it():
    # G4 to G5 cannot be played low: the top G only exists above the 14th fret,
    # so the transcription has to commit to a high position.
    scale = [67, 69, 71, 72, 74, 76, 78, 79]
    positions = tab.assign_positions(scale)
    assert all(position is not None for position in positions)
    assert max(position.fret for position in positions if position) >= 14


def test_unplayable_notes_are_left_unassigned_rather_than_moved():
    positions = tab.assign_positions([30, 67, 31])
    assert positions[0] is None
    assert positions[2] is None
    assert positions[1] is not None


def test_assignment_handles_an_empty_input():
    assert tab.assign_positions([]) == []


def test_every_assigned_position_sounds_the_right_note():
    notes = [55, 60, 64, 67, 72, 76]
    for note, position in zip(notes, tab.assign_positions(notes)):
        assert position is not None
        assert tab.GUITAR_TUNING[position.string] + position.fret == note


def test_note_names():
    assert tab.note_name(60) == "C4"
    assert tab.note_name(69) == "A4"
    assert tab.note_name(40) == "E2"
