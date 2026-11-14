"""The drawing credential is separate config, never a brain route.

These contracts do not call any provider and never read a real deployment.
"""
import copy
import json
from pathlib import Path

import pytest

from soyo.app import config, render
from soyo.app.config import image_gen
from soyo.platform import assert_private


def route(**changes):
    return {"name": "fixture-model", "base_url": "http://127.0.0.1:12345/v1", "auth_mode": "none", "api_key": "",
            "api": "openai-completions", "context_window": 8192, "max_tokens": 1024, "vision": False, **changes}


def drawing(**changes):
    return {"base_url": "https://images.invalid/v1", "api_key": "sk-fixture-drawing-key",
            "model": "gpt-image-2.5", "size": "1024x1024", "timeout_ms": 180000, **changes}


def test_unconfigured_drawing_section_is_empty_not_a_brain_key():
    assert image_gen(None) == {}
    assert image_gen({}) == {}
    assert image_gen({"base_url": "", "api_key": "", "model": ""}) == {}


def test_drawing_section_validates_and_normalises_its_own_fields():
    value = image_gen(drawing(base_url="https://images.invalid/v1/"))
    assert value["base_url"] == "https://images.invalid/v1"
    assert value["model"] == "gpt-image-2.5"
    assert value["size"] == "1024x1024"
    assert value["timeout_ms"] == 180000
    assert value["api_key"] == "sk-fixture-drawing-key"


@pytest.mark.parametrize("changes, match", [
    ({"api_key": ""}, "api_key"),
    ({"base_url": ""}, "base_url"),
    ({"model": ""}, "model"),
    ({"model": "bad model!"}, "model"),
    ({"size": "huge"}, "size"),
    ({"timeout_ms": 10 ** 9}, "timeout_ms"),
    ({"timeout_ms": "soon"}, "timeout_ms"),
])
def test_invalid_drawing_fields_are_refused(changes, match):
    with pytest.raises(ValueError, match=match):
        image_gen(drawing(**changes))


def test_unknown_drawing_field_is_refused():
    with pytest.raises(ValueError, match="image_gen"):
        image_gen(drawing(endpoint_path="/images/generations"))


def test_image_gen_is_not_a_model_field_and_never_enters_a_brain_lane():
    # `model()` is the brain validator. Feeding it the drawing section must fail
    # rather than silently storing a second, shared credential.
    with pytest.raises(ValueError, match="Unsupported model fields"):
        config.model(drawing())


def test_render_image_gen_writes_its_own_key_file_and_leaves_brains_alone(tmp_path):
    home = tmp_path / "instance"
    (home / "private").mkdir(parents=True)
    (home / "backups").mkdir()
    brain = {"action": route(api_key="sk-brain-action"), "character": route(api_key="sk-brain-character")}
    value = {"revision": 7, "image_gen": image_gen(drawing()), "models": copy.deepcopy(brain)}
    native = {}
    result = render.render_image_gen(home, value, native)

    assert result["enabled"] is True
    assert result["model"] == "gpt-image-2.5"
    assert result["base_url"] == "https://images.invalid/v1"
    assert result["key_file"] == str(home / "private/image-gen-key")
    assert (home / "private/image-gen-key").read_text(encoding="utf-8").strip() == "sk-fixture-drawing-key"
    # The brain routes in the caller's config are untouched by rendering.
    assert value["models"] == brain
    # The drawing key is nowhere in the native worker config.
    assert "sk-fixture-drawing-key" not in json.dumps(native)


def test_render_creates_the_character_picture_shelf(tmp_path):
    """Favourites need a durable directory that outlives the media-cache TTL."""
    home = tmp_path / "instance"
    (home / "private").mkdir(parents=True)
    (home / "backups").mkdir()
    native = {}
    result = render.render_image_gen(home, {"revision": 1, "image_gen": image_gen(drawing())}, native)
    shelf = home / "media/shelf"
    assert shelf.is_dir()
    assert result["shelf_dir"] == str(shelf)
    # POSIX mode bits are not Windows permissions; verify the actual platform
    # boundary (0700/ownership on POSIX, protected private DACL on Windows).
    assert_private(shelf, directory=True)


def test_unconfigured_render_has_no_shelf_and_no_key(tmp_path):
    home = tmp_path / "instance"
    (home / "private").mkdir(parents=True)
    native = {}
    result = render.render_image_gen(home, {"revision": 1, "models": {}}, native)
    assert result["enabled"] is False
    assert result["shelf_dir"] == ""
    assert not (home / "media/shelf").exists()


def test_unconfigured_render_reports_disabled_without_creating_a_key_file(tmp_path):
    home = tmp_path / "instance"
    (home / "private").mkdir(parents=True)
    native = {}
    result = render.render_image_gen(home, {"revision": 1, "models": {}}, native)
    assert result["enabled"] is False
    assert result["model"] == "" and result["key_file"] == ""
    assert not (home / "private/image-gen-key").exists()


def test_rotating_the_drawing_key_backs_up_the_previous_one(tmp_path):
    home = tmp_path / "instance"
    (home / "private").mkdir(parents=True)
    (home / "backups").mkdir()
    render.render_image_gen(home, {"revision": 3, "image_gen": image_gen(drawing())}, {})
    render.render_image_gen(home, {"revision": 4, "image_gen": image_gen(drawing(api_key="sk-fixture-rotated"))}, {})
    assert (home / "private/image-gen-key").read_text(encoding="utf-8").strip() == "sk-fixture-rotated"
    backups = list((home / "backups").glob("image-gen-key-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8").strip() == "sk-fixture-drawing-key"


def test_validate_keeps_a_configured_drawing_section_alongside_brain_models(tmp_path):
    home = tmp_path / "instance"
    value = config.initialize(home)
    value = config.update(home, {"character_name": "Fixture", "models": {"character": route()},
                                 "action_uses_character": True}, value["revision"])
    # The drawing section lands through the same locked write path as any other
    # field, and comes back through the UI/API view with its key redacted.
    value = config.update(home, {"image_gen": drawing()}, value["revision"])
    saved = config.read_json(home / "deployment.json")
    assert saved["image_gen"]["model"] == "gpt-image-2.5"
    assert saved["models"]["character"]["name"] == "fixture-model"
    visible = config.redacted(saved)
    assert visible["image_gen"]["api_key_configured"] is True
    assert "sk-fixture-drawing-key" not in json.dumps(visible)
    # A blank key edit keeps the stored credential instead of erasing it.
    kept = config.update(home, {"image_gen": {"api_key": ""}}, saved["revision"])
    assert config.read_json(home / "deployment.json")["image_gen"]["api_key"] == "sk-fixture-drawing-key"


def test_image_gen_survives_moving_a_brain_lane(tmp_path):
    """Rotating models.action must not disturb the drawing credential."""
    home = tmp_path / "instance"
    value = config.initialize(home)
    value = config.update(home, {"character_name": "Fixture", "models": {"character": route()},
                                 "action_uses_character": True, "image_gen": drawing()}, value["revision"])
    before = config.read_json(home / "deployment.json")["image_gen"]
    value = config.update(home, {"models": {"action": route(name="fixture-model-next", api_key="sk-brain-next")}},
                          value["revision"])
    after = config.read_json(home / "deployment.json")["image_gen"]
    assert after == before
    assert after["api_key"] == "sk-fixture-drawing-key"
