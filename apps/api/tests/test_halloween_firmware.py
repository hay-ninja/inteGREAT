"""Host simulation checks scheduling/stop/wraparound; never hardware evidence."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_halloween_note_and_light_scheduling(tmp_path):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("Host C++ compiler unavailable")
    root = Path(__file__).resolve().parents[3]
    sketch = (root / "fixtures/esp32_halloween_lights/esp32_halloween_lights.ino").as_posix()
    (tmp_path / "Arduino.h").write_text(r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cassert>
#include <deque>
#include <vector>
constexpr int LOW=0, HIGH=1, OUTPUT=1, INPUT_PULLUP=2;
inline uint32_t clockMs=0;
inline int pins[40]={};
inline unsigned sounding=0;
inline int buttonReading=HIGH;
inline std::vector<int> litPins;
inline void pinMode(int, int) {}
inline int digitalRead(int pin) { assert(pin==4); return buttonReading; }
inline void digitalWrite(int pin, int value) {
  pins[pin]=value;
  assert(!(pins[18] && pins[21]));
  if(value == HIGH) litPins.push_back(pin);
}
inline void tone(int pin, unsigned frequency) {
  assert(pin==19 && frequency>0);
  assert(pins[18] + pins[21] == 1);
  sounding=frequency;
}
inline void noTone(int pin) { assert(pin==19); sounding=0; }
inline uint32_t millis() { return clockMs; }
inline void delay(unsigned) {}
struct SerialMock {
  std::deque<char> input;
  void begin(unsigned) {}
  void println(const char*) {}
  int available() { return static_cast<int>(input.size()); }
  char read() { char c=input.front(); input.pop_front(); return c; }
};
inline SerialMock Serial;
''', encoding="utf-8")
    (tmp_path / "check.cpp").write_text(f'#include "{sketch}"\n' + r'''
int main() {
  setup();
  assert(!pins[18] && !pins[21] && !sounding);
  assert(!playing);
  for(clockMs=0; clockMs<100; ++clockMs) loop();
  assert(!playing && litPins.empty());
  // Short switch bounce must not trigger; one settled press starts playback.
  buttonReading=LOW; loop();
  clockMs+=10; buttonReading=HIGH; loop();
  clockMs+=10; buttonReading=LOW; loop();
  clockMs+=34; loop(); assert(!playing);
  clockMs+=1; loop(); assert(playing && sounding);
  // Holding a button for a second cannot generate extra toggles.
  for(int i=0; i<1000; ++i) { ++clockMs; loop(); assert(playing); }
  buttonReading=HIGH; loop(); clockMs+=35; loop(); assert(playing);
  buttonReading=LOW; loop(); clockMs+=35; loop();
  assert(!playing && !sounding && !pins[18] && !pins[21]);
  buttonReading=HIGH; loop(); clockMs+=35; loop(); assert(!playing);
  Serial.input.push_back('p'); loop();
  litPins.clear();
  setPlaying(true);
  // Two complete songs; exactly one LED is on whenever a note sounds.
  for(clockMs=0; clockMs<24000; ++clockMs) {
    loop();
    assert((sounding!=0) == (pins[18] + pins[21] == 1));
  }
  assert(litPins.size() >= 32);
  for(size_t i=0; i<litPins.size(); ++i) assert(litPins[i] == (i%2 ? 21 : 18));
  Serial.input.push_back('s'); loop();
  assert(!playing && !sounding && !pins[18] && !pins[21]);
  for(int i=0; i<1000; ++i) { ++clockMs; loop(); }
  assert(!sounding && !pins[18] && !pins[21]);
  Serial.input.push_back('p'); loop();
  assert(playing && pins[18] && sounding==SONG[0].frequency);
  // Unsigned elapsed timing must still finish a note across millis rollover.
  silence(); noteIndex=0; noteStarted=false; clockMs=UINT32_MAX-100; loop();
  clockMs=500; loop();
  assert(!noteStarted && noteIndex==1 && !sounding);
  // Boot while held is quiet until release followed by a new press.
  setPlaying(false); buttonReading=LOW; setup();
  clockMs+=100; loop(); assert(!playing);
  buttonReading=HIGH; loop(); clockMs+=35; loop(); assert(!playing);
  buttonReading=LOW; loop(); clockMs+=35; loop(); assert(playing);
}
''', encoding="utf-8")
    executable = tmp_path / "check.exe"
    compiled = subprocess.run([compiler, "-std=c++17", "-I", str(tmp_path), str(tmp_path / "check.cpp"), "-o", str(executable)], capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    checked = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
    assert checked.returncode == 0, checked.stderr
