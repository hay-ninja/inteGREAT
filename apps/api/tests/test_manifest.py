import pytest

from integreat.ingestion.manifest import ManifestError, load_manifest, normalize_mcu_pin

from .conftest import MANIFEST


@pytest.mark.parametrize("label,expected", [("GPIO18", ("GPIO18", 18)), ("io18", ("GPIO18", 18)),
                                            ("18", ("GPIO18", 18)), ("G2", ("GPIO2", 2)), ("gnd", ("GND", None))])
def test_pin_normalization(label, expected):
    assert normalize_mcu_pin(label) == expected


@pytest.mark.parametrize("label", ["D18", "A0", "GPIO6", "GPIO20", "GPIO40", "SDA"])
def test_pin_normalization_refuses_to_guess(label):
    with pytest.raises(ManifestError):
        normalize_mcu_pin(label)


def test_manifest_loads_with_line_numbers():
    m, _, lines = load_manifest(MANIFEST)
    assert {c.id for c in m.connections} >= {"servo_signal", "servo_power", "common_ground"}
    assert lines["servo_signal"] > 0


def test_manifest_bad_endpoint(tmp_path):
    bad = MANIFEST.read_text().replace("to: servo_1.signal", "to: servo_1.pwm")
    f = tmp_path / "m.yaml"
    f.write_text(bad)
    with pytest.raises(ManifestError, match="no pin 'pwm'"):
        load_manifest(f)
