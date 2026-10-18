# Phone camera input

1. Install/run a phone camera app that serves **HTTP MJPEG** on the local network.
   This is a video stream, not an RTSP stream, HLS playlist, or HTML viewing page.
2. Connect the phone and laptop to the same trusted Wi-Fi. Guest/client isolation
   may prevent access. No phone-to-laptop cable or GPIO wiring is needed.
3. Set the app to 640x480 or 1280x720. Mount the phone facing the circuit, keep the
   camera app foregrounded, and plug the phone into power if needed.
4. In inteGREAT open **Rig setup**, select **Phone / network camera**, and enter
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
