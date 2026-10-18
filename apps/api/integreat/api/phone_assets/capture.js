"use strict";
const token = location.hash.slice(1);
history.replaceState(null, "", location.pathname);
const video = document.querySelector("video");
const message = document.querySelector("#status");
const start = document.querySelector("#start");
const stop = document.querySelector("#stop");
const canvas = document.createElement("canvas");
const context = canvas.getContext("2d");
let stream, running = false, controller, generation = 0;
const auth = { Authorization: `Bearer ${token}` };
function closeCamera() {
  running = false;
  generation++;
  controller?.abort();
  stream?.getTracks().forEach(track => track.stop());
  stream = undefined;
  video.srcObject = null;
  stop.disabled = true;
}
async function revoke() {
  closeCamera();
  start.disabled = true;
  try { await fetch("/phone/session", { method: "DELETE", headers: auth, keepalive: true }); } catch {}
}
async function sendFrames(id) {
  while (running && id === generation) {
    if (video.readyState >= 2 && video.videoWidth) {
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", 0.7));
      if (!running || id !== generation) return;
      if (!blob) throw new Error("Unable to capture a JPEG frame");
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch("/phone/frame", { method: "POST", headers: { ...auth, "Content-Type": "image/jpeg" }, body: blob, signal: controller.signal });
        if (!response.ok) throw new Error(`Laptop rejected frame (${response.status}). Create a new pairing link.`);
        message.textContent = "Streaming to your laptop. Keep Safari open.";
      } finally { clearTimeout(timeout); }
    }
    await new Promise(resolve => setTimeout(resolve, 150));
  }
}
start.onclick = async () => {
  start.disabled = true;
  const id = ++generation;
  try {
    if (!token) throw new Error("Open the complete pairing link from your laptop.");
    if (!isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error("A trusted HTTPS connection is required. Follow the laptop's certificate setup guide.");
    const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    if (id !== generation) { media.getTracks().forEach(track => track.stop()); return; }
    stream = media;
    video.srcObject = stream;
    await video.play();
    running = true;
    stop.disabled = false;
    await sendFrames(id);
  } catch (error) {
    if (id !== generation) return;
    closeCamera();
    message.textContent = `${error.name === "NotAllowedError" ? "Camera permission denied. Allow it in Safari website settings." : error.message} Reopen the pairing link to retry.`;
  }
};
stop.onclick = async () => { await revoke(); message.textContent = "Camera stopped. Pair again from your laptop."; };
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { revoke(); message.textContent = "Camera stopped when Safari was hidden. Pair again from your laptop."; }
});
window.addEventListener("pagehide", revoke);
