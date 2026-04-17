from datetime import datetime

from app.scene_index import normalize_scene_id, parse_scene_name, parse_scene_timestamps


def test_normalize_scene_id_variants() -> None:
    base = "S1A_EW_GRDM_1SDH_20250213T012708_20250213T012812_057871_072378_6956"
    cases = [
        f"{base}_fix_IceClass.tif",
        f"{base}_composite.tif",
        f"{base}.SAFE_composite_IceClass.tif",
        f"{base}_IceClass.tif",
    ]
    for c in cases:
        assert normalize_scene_id(c) == base


def test_parse_scene_timestamps() -> None:
    scene_id = "S1A_EW_GRDM_1SDH_20250417T015152_20250417T015256_058790_0748A6_2866"
    start, end = parse_scene_timestamps(scene_id)
    assert start == datetime(2025, 4, 17, 1, 51, 52, tzinfo=start.tzinfo)
    assert end == datetime(2025, 4, 17, 1, 52, 56, tzinfo=end.tzinfo)
    assert end > start


def test_parse_scene_name_blocks() -> None:
    scene_id = "S1A_EW_GRDM_1SDH_20250218T031612_20250218T031712_057945_07267C_A597"
    p = parse_scene_name(scene_id)
    assert p.mission == "S1A"
    assert p.acquisition_mode == "EW"
    assert p.product_type == "GRDM"
    assert p.level_polarization == "1SDH"
    assert p.absolute_orbit == "057945"
    assert p.datatake_id == "07267C"
    assert p.product_uid == "A597"
