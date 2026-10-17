import pytest

from integreat.ingestion.arduino_parser import parse_project
from integreat.ingestion.repository import RepoError, RepoFile, resolve_inside, scan_repository

from .conftest import FAULT_A_REPO, GOOD_REPO


def test_parser_resolves_servo_pin_through_define():
    p = parse_project(scan_repository(FAULT_A_REPO).files)
    servo = [u for u in p.pin_uses if u.api == "servo_attach"]
    assert len(servo) == 1
    u = servo[0]
    assert (u.gpio, u.resolution, u.raw_arg, u.file, u.line) == (19, "define", "SERVO_PIN", "servo_control.cpp", 8)
    assert u.symbol.file == "servo_control.h" and u.symbol.line == 4
    assert u.function_id == "function:servo_control.cpp::servoSetup"


def test_parser_const_pin_and_log_and_command_literals():
    p = parse_project(scan_repository(GOOD_REPO).files)
    led = [u for u in p.pin_uses if u.api == "pinMode"]
    assert led[0].gpio == 2 and led[0].resolution == "const"
    assert any(l.text == "ACK MOVE " and l.function_id.endswith("::moveServoTo") for l in p.log_literals)
    assert [c.text for c in p.command_literals] == ["MOVE "]


def test_unresolvable_pin_is_flagged_not_guessed():
    src = "#include <ESP32Servo.h>\nServo s;\nint pinFromEeprom();\nvoid setup(){ s.attach(pinFromEeprom()); }\n"
    p = parse_project([RepoFile("a.ino", src)])
    assert p.pin_uses[0].gpio is None and p.pin_uses[0].resolution == "unresolved"
    assert any("could not statically resolve" in w[0] for w in p.warnings)


def test_scan_skips_secrets_and_build_dirs(tmp_path):
    (tmp_path / "a.ino").write_text("void setup(){}\nvoid loop(){}\n")
    (tmp_path / "secrets.h").write_text('#define WIFI_PASS "x"\n')
    (tmp_path / ".pio").mkdir()
    (tmp_path / ".pio" / "b.cpp").write_text("int x;")
    scan = scan_repository(tmp_path)
    assert [f.rel for f in scan.files] == ["a.ino"]
    assert ("secrets.h", "possible secret") in scan.skipped


def test_scan_rejects_non_source_repo(tmp_path):
    (tmp_path / "readme.md").write_text("hi")
    with pytest.raises(RepoError):
        scan_repository(tmp_path)


@pytest.mark.parametrize("bad", ["../outside.txt", "sub/../../x", "C:/Windows/win.ini", "/etc/passwd", ""])
def test_resolve_inside_blocks_traversal(tmp_path, bad):
    with pytest.raises(RepoError):
        resolve_inside(tmp_path, bad)
