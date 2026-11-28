"""Unit tests for state_store.py."""

import json
import logging

from linux_peripherals_controller.light import LightState
from linux_peripherals_controller.state_store import StoredState, load_state, save_state


def test_missing_file_gives_the_defaults(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        assert load_state(tmp_path / "state.json") == StoredState()
    assert "No state file yet" in caplog.text


def test_saved_state_is_loaded_again(tmp_path):
    path = tmp_path / "data" / "state.json"
    state = StoredState(child_lock=True, light=LightState(on=True, brightness=0.2))
    save_state(path, state)
    assert load_state(path) == state
    assert not (tmp_path / "data" / "state.json.tmp").exists()


def test_invalid_json_gives_the_defaults_and_a_warning(tmp_path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{nope", encoding="utf-8")
    assert load_state(path) == StoredState()
    assert "is not valid JSON" in caplog.text


def test_invalid_values_keep_their_default(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"child_lock": "yes", "light": 3}), encoding="utf-8")
    assert load_state(path) == StoredState()


def test_not_an_object_gives_the_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")
    assert load_state(path) == StoredState()


def test_failed_write_is_logged(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    save_state(blocker / "state.json", StoredState())
    assert "Cannot write the state file" in caplog.text
