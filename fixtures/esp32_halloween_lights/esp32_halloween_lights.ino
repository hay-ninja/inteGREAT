// "Haunted Breadboard" - an original minor-key Halloween jingle.
// Classic ESP32-WROOM; LED 1 = GPIO18, LED 2 = GPIO21, passive PIEZO = GPIO19.
// Each LED needs its own 330-ohm series resistor. See README.md for buzzer wiring.
// Starts OFF. Momentary button between GPIO4 and GND toggles playback.
// Serial Monitor at 115200: 's' stops sound/lights; 'p' restarts the song.
#include <Arduino.h>

const uint8_t LED_1_PIN = 18;
const uint8_t LED_2_PIN = 21;
const uint8_t BUZZER_PIN = 19;
const uint8_t BUTTON_PIN = 4;
const uint32_t DEBOUNCE_MS = 35;
const uint16_t BPM = 120;
const uint32_t EIGHTH_NOTE_MS = 60000UL / BPM / 2;

struct Note {
  uint16_t frequency;  // Hz; 0 is a rest.
  uint8_t eighths;     // 1 = eighth note, 2 = quarter, 4 = half.
};

// A minor with a chromatic "creepy" turn. Ends with a two-second silent rest.
const Note SONG[] = {
  {440, 2}, {523, 2}, {622, 2}, {659, 2},
  {622, 1}, {587, 1}, {523, 2}, {494, 2},
  {440, 4}, {330, 2}, {415, 2}, {440, 2},
  {523, 1}, {494, 1}, {415, 2}, {440, 4},
  {0, 8},
};
const size_t NOTE_COUNT = sizeof(SONG) / sizeof(SONG[0]);

size_t noteIndex = 0;
uint32_t noteStartedAt = 0;
bool playing = false;
bool noteStarted = false;
bool silenced = true;
bool nextIsLed1 = true;
int lastButtonReading = HIGH;
int stableButtonState = HIGH;
uint32_t buttonChangedAt = 0;

void silence() {
  noTone(BUZZER_PIN);
  digitalWrite(LED_1_PIN, LOW);
  digitalWrite(LED_2_PIN, LOW);
  silenced = true;
}

void setPlaying(bool enabled) {
  silence();
  playing = enabled;
  noteIndex = 0;
  nextIsLed1 = true;
  noteStarted = false;
}

void pollButton(uint32_t now) {
  const int reading = digitalRead(BUTTON_PIN);
  if (reading != lastButtonReading) {
    lastButtonReading = reading;
    buttonChangedAt = now;
  }
  if (now - buttonChangedAt >= DEBOUNCE_MS && reading != stableButtonState) {
    stableButtonState = reading;
    // One toggle on a debounced press; holding or releasing does not toggle.
    if (stableButtonState == LOW) setPlaying(!playing);
  }
}

void startNote(uint32_t now) {
  const Note& note = SONG[noteIndex];
  silence();
  if (note.frequency != 0) {
    // Both sound and light begin on the same scheduled note boundary.
    digitalWrite(nextIsLed1 ? LED_1_PIN : LED_2_PIN, HIGH);
    nextIsLed1 = !nextIsLed1;
    tone(BUZZER_PIN, note.frequency);
    silenced = false;
  }
  noteStartedAt = now;
  noteStarted = true;
}

void setup() {
  pinMode(LED_1_PIN, OUTPUT);
  pinMode(LED_2_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  // A button held during boot must be released before it can start playback.
  lastButtonReading = stableButtonState = digitalRead(BUTTON_PIN);
  buttonChangedAt = millis();
  digitalWrite(BUZZER_PIN, LOW);
  silence();
  Serial.begin(115200);
  Serial.println("Haunted Breadboard OFF: button=toggle, p=play, s=stop");
}

void loop() {
  const uint32_t now = millis();
  pollButton(now);
  while (Serial.available() > 0) {
    const char command = Serial.read();
    if (command == 's' || command == 'S') {
      setPlaying(false);
    } else if (command == 'p' || command == 'P') {
      setPlaying(true);
    }
  }
  if (!playing) {
    delay(1);
    return;
  }

  if (!noteStarted) startNote(now);
  const uint32_t duration = EIGHTH_NOTE_MS * SONG[noteIndex].eighths;
  const uint32_t elapsed = now - noteStartedAt;  // Safe across millis() wraparound.
  // Articulate every note: sound/light on for 80%, silence for 20%.
  if (!silenced && elapsed >= duration * 4 / 5) silence();
  if (elapsed >= duration) {
    silence();
    noteIndex = (noteIndex + 1) % NOTE_COUNT;
    noteStarted = false;
  }
  delay(1);
}
