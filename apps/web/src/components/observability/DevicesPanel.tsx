import { useEffect, useState } from "react";
import { api, type DeviceStatus } from "../../lib/api";

/** Live rig controls: serial port, camera, calibration, preview. */
export function DevicesPanel({ status, onStatus, onError }: {
  status: DeviceStatus | null;
  onStatus: (s: DeviceStatus) => void;
  onError: (m: string) => void;
}) {
  const [port, setPort] = useState("");
  const [cams, setCams] = useState<number[] | null>(null);
  const [camIndex, setCamIndex] = useState(0);
  const [angle, setAngle] = useState(0);
  const [probing, setProbing] = useState(false);
  const run = (p: Promise<DeviceStatus>) => p.then(onStatus).catch((e) => onError(e.message));

  useEffect(() => {
    if (!port && status?.serial.ports.length) setPort(status.serial.ports[0].port);
  }, [status, port]);

  if (!status) return <div className="empty">Loading device status…</div>;
  const s = status.serial;
  const c = status.camera;
  return (
    <div className="devices">
      <div className="dev-col">
        <h4>ESP32 serial</h4>
        <div className={`dev-state ${s.connected ? "ok" : ""}`}>
          {s.connected ? `Connected ${s.port} @ ${s.baud}` : "Not connected"}
        </div>
        {s.last_error && <div className="small warn">{s.last_error}</div>}
        <div className="row">
          <select value={port} onChange={(e) => setPort(e.target.value)} disabled={s.connected}>
            {s.ports.length === 0 && <option value="">no serial ports found</option>}
            {s.ports.map((p) => <option key={p.port} value={p.port}>{p.port} — {p.description}</option>)}
          </select>
          {s.connected ? (
            <button className="ghost" onClick={() => run(api.serialRelease())}
                    title="Free the COM port so the Arduino IDE can flash">Release port</button>
          ) : (
            <button className="action-btn" disabled={!port} onClick={() => run(api.serialConnect(port))}>Connect</button>
          )}
        </div>
        <div className="dim small">
          Opened once with DTR/RTS held low so the board doesn't reset. Release before reflashing.
        </div>
      </div>
      <div className="dev-col">
        <h4>Camera</h4>
        <div className={`dev-state ${c.connected ? "ok" : ""}`}>
          {c.connected ? `${c.source_id} · ${c.fps} fps · ${c.calibrated ? `calibrated (offset ${c.offset_deg?.toFixed(1)}°)` : "NOT calibrated"}` : "Not connected"}
        </div>
        {c.last_error && <div className="small warn">{c.last_error}</div>}
        <div className="row">
          {cams === null ? (
            <button className="ghost" disabled={probing}
                    onClick={() => { setProbing(true); api.cameraProbe().then((x) => { setCams(x); if (x.length) setCamIndex(x[0]); })
                      .catch((e) => onError(e.message)).finally(() => setProbing(false)); }}>
              {probing ? "Probing…" : "Find cameras"}
            </button>
          ) : (
            <select value={camIndex} onChange={(e) => setCamIndex(+e.target.value)} disabled={c.connected}>
              {cams.length === 0 && <option>none found</option>}
              {cams.map((i) => <option key={i} value={i}>camera {i}</option>)}
            </select>
          )}
          {c.connected ? (
            <button className="ghost" onClick={() => run(api.cameraRelease())}>Release</button>
          ) : (
            <button className="action-btn" disabled={cams === null || cams.length === 0}
                    onClick={() => run(api.cameraConnect(camIndex))}>Connect</button>
          )}
        </div>
        {c.connected && (
          <div className="row">
            <span className="small">Servo is now at</span>
            <input type="number" value={angle} style={{ width: 70 }} onChange={(e) => setAngle(+e.target.value)} />
            <span className="small">°</span>
            <button className="ghost" onClick={() => run(api.cameraCalibrate(angle))}>Calibrate</button>
          </div>
        )}
        <div className="dim small">ArUco marker id 1 on the horn, id 0 fixed beside the servo (print: scripts/make_aruco_markers.py).</div>
      </div>
      {c.connected && (
        <div className="dev-col preview">
          <img src="/api/v1/devices/camera/stream.mjpg" alt="Live camera preview with marker detection" />
        </div>
      )}
    </div>
  );
}
