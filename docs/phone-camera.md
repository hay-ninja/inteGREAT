# Phone camera input

## iPhone Safari, no third-party camera app

Safari requires a **trusted HTTPS** connection to use the camera. A warning-page
exception alone is not a substitute for trusting the certificate. This local demo
uses a seven-day CA and server certificate; no public tunnel or cloud is needed.

1. Find your laptop's Wi-Fi IPv4 address (`ipconfig` on Windows), for example
   `192.168.1.42`. Phone and laptop must be on the same trusted LAN without client
   isolation. Replace the example IP in every command below with your actual IP.
2. From the repository root, create certificates:

   ```powershell
   apps/api/.venv/Scripts/python scripts/make_phone_cert.py --ip 192.168.1.42
   ```

   Transfer **only `.phone-camera/root-ca.cer`** to your iPhone using a file-transfer
   method you trust (such as your own file storage or email). Never transfer the
   private `server-key.pem`. Open the `.cer` file on iPhone and install its profile
   in **Settings → General → VPN & Device Management**. Then enable this CA under
   **Settings → General → About → Certificate Trust Settings**. The name is
   `inteGREAT local phone camera demo CA`. Trust only the certificate you generated;
   remove its profile when the demo is finished.
3. Stop the usual API/dev launcher if running. Run this alternative API launcher:

   ```powershell
   apps/api/.venv/Scripts/python scripts/phone_camera_server.py --ip 192.168.1.42
   ```

   In another terminal run `cd apps/web` then `npm run dev`. Open the normal laptop
   UI at `http://localhost:5173`. The API stays on loopback port 8000. Only phone
   capture routes listen on the LAN, on HTTPS port **8443**. If Windows Firewall
   prompts, allow the Python listener on your trusted **Private** network only.
4. Open **Rig setup → iPhone / Safari (no app) → Pair iPhone camera**. Creating a
   pairing replaces any existing camera and revokes the previous pairing.
5. Copy/send the full pairing link to your iPhone and open it in **Safari**. The
   `#…` fragment is required: it holds a secret upload token. Keep it private.
   Tap **Start camera**, allow camera access, and point the rear camera at the rig.
   The laptop preview appears when frames arrive. No microphone permission is used.
6. Keep Safari visible and the phone awake. **Stop camera**, hiding Safari, or
   leaving the page closes its camera. Stop also revokes pairing. Laptop **Release**
   revokes it too; create a new link to reconnect. Pairings expire after two hours.

The capture page sends a small JPEG about every 150 ms, with one request at a time;
only the latest decoded frame is retained. Frames older than five seconds cannot
be used as a connected camera. Timing is host-receive correlated; Wi-Fi latency
is unknown. This transport supports existing CV; it does not implement LED metrics.

If Safari says camera access is unavailable, check certificate trust, matching IP,
camera permission, and that you opened HTTPS. If the laptop IP changes or the
certificate expires, generate into a new directory with `--out`, trust its new CA,
and start the server with matching `--cert-dir`. Remove the old profile afterward.

References: [browser camera secure contexts](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
[Apple certificate trust instructions](https://support.apple.com/en-us/102390).

## Existing HTTP MJPEG camera apps

1. Install/run a phone camera app that serves **HTTP MJPEG** on the local network.
   This is a video stream, not an RTSP stream, HLS playlist, or HTML viewing page.
2. Connect the phone and laptop to the same trusted Wi-Fi. Guest/client isolation
   may prevent access. No phone-to-laptop cable or GPIO wiring is needed.
3. Set the app to 640x480 or 1280x720. Mount the phone facing the circuit, keep the
   camera app foregrounded, and plug the phone into power if needed.
4. In inteGREAT open **Rig setup**, select **MJPEG camera app**, and enter
   the stream URL shown by the app, for example `http://192.168.1.42:8080/video`.
   The actual port/path depend on the app. Press **Connect phone camera**.
5. Check the preview. If disconnected, check Wi-Fi/app state and connect again.
   Release the camera when finished and stop the phone's streaming server.

Only literal RFC1918 IPv4 HTTP addresses are accepted. Hostnames, public IPs,
credentials, URL queries, redirects, HTTPS, and other protocols are unsupported.
Do not expose the phone camera on the public internet. Streams are unencrypted;
use a trusted LAN. There is no automatic third-party/cloud camera service.

Frames use laptop receive timestamps (network latency is not measured). Frames
older than five seconds are unavailable; reconnect is explicit. The backend keeps
only the latest decoded frame, with a bounded compressed-frame buffer.

This adds a camera source and preview to the existing CV pipeline. Servo ArUco
calibration still applies to servo tests. **It does not add LED brightness
evaluation or make the two-LED sketch compatible with servo-angle tests.**
