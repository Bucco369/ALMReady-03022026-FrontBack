/// ALMReady Tauri shell – sidecar lifecycle management.
///
/// Startup sequence
/// ────────────────
/// 1.  Resolve the PyInstaller one-directory bundle from the app resource dir.
/// 2.  Set ALMREADY_DATA_DIR (OS user-data dir) and ALMREADY_CORS_ORIGINS env
///     vars, then spawn the sidecar as a child process with stdout captured.
/// 3.  A blocking-reader task scans stdout for the "PORT:{n}" line printed by
///     sidecar_main.py and delivers the port over a oneshot channel.
/// 4.  A second async task waits for the port, polls
///     `GET http://127.0.0.1:{port}/api/health` (TCP connect) until 200 OK,
///     then creates the main WebviewWindow with an initialization_script that
///     injects `window.__BACKEND_PORT__ = {port}` **before** React modules
///     load – guaranteeing the value is synchronously available in api.ts.
/// 5.  On CloseRequested: the child process is killed so no zombie Python
///     processes remain after the native window closes.
///
/// Development note
/// ────────────────
/// When running via `cargo tauri dev`, `beforeDevCommand` starts Vite and
/// uvicorn via `npm run dev:all`.  In that case Tauri does NOT use the
/// sidecar path – it points the webview at the Vite dev server
/// (http://localhost:8080) and the backend is already running on :8000 from
/// the dev command.  The sidecar spawn code still executes, but the binary
/// won't exist in the dev tree, so the error is caught and logged, and the
/// app continues to work via the Vite dev server + dev uvicorn instance.

use std::{
    io::{BufRead as _, BufReader},
    sync::Mutex,
    time::Duration,
};

use tauri::{AppHandle, Manager, WebviewWindowBuilder, WebviewUrl};
use tokio::{net::TcpStream, time::sleep};

// ── App state ───────────────────────────────────────────────────────────────

/// Holds the sidecar child process handle so we can kill it on exit.
struct BackendProcess(Mutex<Option<std::process::Child>>);

// ── Health check ────────────────────────────────────────────────────────────

/// Poll port until a TCP connection succeeds (server is accepting) or we time out.
/// Returns true if the backend became ready within the timeout.
async fn wait_for_backend(port: u16) -> bool {
    // 60 attempts × 500 ms = 30 s maximum wait.
    // The ProcessPoolExecutor warm-up in the FastAPI lifespan is the slowest
    // part (~3-8 s depending on CPU count); 30 s is a comfortable upper bound.
    for _ in 0..60u32 {
        if TcpStream::connect(format!("127.0.0.1:{port}")).await.is_ok() {
            return true;
        }
        sleep(Duration::from_millis(500)).await;
    }
    false
}

// ── Sidecar spawn ───────────────────────────────────────────────────────────

fn spawn_sidecar(
    app: &AppHandle,
) -> Result<(std::process::Child, tokio::sync::oneshot::Receiver<u16>), String> {
    // Locate the PyInstaller bundle within the app's resource directory.
    // tauri.conf.json maps  ../backend/dist/almready-backend  →  almready-backend
    // so it lands at  {resource_dir}/almready-backend/almready-backend[.exe].
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    #[cfg(target_os = "windows")]
    let exe_name = "almready-backend.exe";
    #[cfg(not(target_os = "windows"))]
    let exe_name = "almready-backend";

    let exe_path = resource_dir.join("almready-backend").join(exe_name);

    // OS user-data directory for session persistence.
    // macOS → ~/Library/Application Support/ALMReady
    // Windows → %APPDATA%\ALMReady
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir: {e}"))?;

    // Tauri webview origins – one per platform, both listed for safety.
    let cors_origins = "tauri://localhost,https://tauri.localhost";

    let mut child = std::process::Command::new(&exe_path)
        .env("ALMREADY_DATA_DIR", &data_dir)
        .env("ALMREADY_CORS_ORIGINS", cors_origins)
        // Capture stdout so we can read the PORT:{n} line.
        .stdout(std::process::Stdio::piped())
        // Discard stderr from the sidecar (uvicorn noise).
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("spawn {exe_path:?}: {e}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "stdout pipe not available".to_string())?;

    // Channel: the stdout-reader task sends the port; the health-check task
    // receives it.
    let (tx, rx) = tokio::sync::oneshot::channel::<u16>();

    // Spawn a blocking task to read the sidecar's stdout line-by-line.
    // We use spawn_blocking because std::io::BufReader::lines() blocks.
    tauri::async_runtime::spawn(async move {
        let port = tauri::async_runtime::spawn_blocking(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                if let Some(port_str) = line.strip_prefix("PORT:") {
                    if let Ok(p) = port_str.trim().parse::<u16>() {
                        return p;
                    }
                }
            }
            // Sidecar exited without printing a port – return 0 as sentinel.
            0u16
        })
        .await
        .unwrap_or(0);

        let _ = tx.send(port);
    });

    Ok((child, rx))
}

// ── Main window creation ─────────────────────────────────────────────────────

async fn create_main_window(app: &AppHandle, port: u16) {
    // initialization_script runs BEFORE any page scripts (React, Vite bundle).
    // This guarantees window.__BACKEND_PORT__ is synchronously available when
    // api.ts evaluates its module-level API_BASE constant.
    let init_script = format!("window.__BACKEND_PORT__ = {port};");

    let _ = WebviewWindowBuilder::new(
        app,
        "main",
        WebviewUrl::App("index.html".into()),
    )
    .initialization_script(&init_script)
    .title("ALMReady")
    .inner_size(1440.0, 900.0)
    .min_inner_size(1024.0, 768.0)
    .center()
    .build()
    .inspect_err(|e| eprintln!("[ALMReady] failed to create main window: {e}"));
}

// ── Entry point ──────────────────────────────────────────────────────────────

pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let app_handle = app.handle().clone();

            tauri::async_runtime::spawn(async move {
                // Attempt to spawn the sidecar.
                match spawn_sidecar(&app_handle) {
                    Err(e) => {
                        // In `cargo tauri dev` the sidecar binary doesn't
                        // exist – dev mode uses the Vite dev server + a
                        // separately-running uvicorn.  Log and create the
                        // window pointing at the dev server (port from Vite).
                        eprintln!("[ALMReady] sidecar not available ({e}), assuming dev mode");
                        // In dev mode Tauri uses devUrl from config; the window
                        // is created by Tauri automatically when devUrl is set.
                        // Nothing to do here.
                    }

                    Ok((child, rx)) => {
                        // Store child handle for cleanup on close.
                        *app_handle.state::<BackendProcess>().0.lock().unwrap() = Some(child);

                        // Wait for the sidecar to print its port.
                        let port = rx.await.unwrap_or(0);

                        if port == 0 {
                            eprintln!("[ALMReady] FATAL: sidecar exited before printing port");
                            // Kill child and exit – no window was created yet.
                            if let Some(mut c) = app_handle
                                .state::<BackendProcess>()
                                .0
                                .lock()
                                .unwrap()
                                .take()
                            {
                                let _ = c.kill();
                                let _ = c.wait();
                            }
                            std::process::exit(1);
                        }

                        eprintln!("[ALMReady] sidecar reported port {port}, polling health...");

                        // Poll /api/health until ready.
                        if !wait_for_backend(port).await {
                            eprintln!("[ALMReady] FATAL: health check timed out after 30 s");
                            if let Some(mut c) = app_handle
                                .state::<BackendProcess>()
                                .0
                                .lock()
                                .unwrap()
                                .take()
                            {
                                let _ = c.kill();
                                let _ = c.wait();
                            }
                            std::process::exit(1);
                        }

                        eprintln!("[ALMReady] backend ready on port {port}, opening window");
                        create_main_window(&app_handle, port).await;
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Kill the sidecar so no zombie Python processes remain.
                if let Some(mut child) = window
                    .app_handle()
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .unwrap()
                    .take()
                {
                    let _ = child.kill();
                    let _ = child.wait(); // reap the zombie
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
