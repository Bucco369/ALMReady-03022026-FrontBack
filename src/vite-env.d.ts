/// <reference types="vite/client" />

// Injected by the Tauri Rust shell via WebviewWindowBuilder::initialization_script()
// before any page scripts run.  Set to the dynamic port chosen by sidecar_main.py.
// Undefined in browser/dev contexts – api.ts falls back to VITE_API_BASE_URL.
interface Window {
  __BACKEND_PORT__?: number;
}
