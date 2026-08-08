use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, State};

pub const SIDECAR_HOST: &str = "127.0.0.1";
pub const SIDECAR_PORT: u16 = 8010;

pub struct SidecarState(pub Mutex<Option<Child>>);

impl Default for SidecarState {
    fn default() -> Self {
        Self(Mutex::new(None))
    }
}

fn target_dir() -> &'static str {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("macos", "aarch64") => "darwin-arm64",
        ("macos", "x86_64") => "darwin-x64",
        ("windows", "x86_64") => "win32-x64",
        ("linux", "x86_64") => "linux-x64",
        _ => "darwin-arm64",
    }
}

fn exe_name() -> &'static str {
    if cfg!(windows) {
        "divine-server.exe"
    } else {
        "divine-server"
    }
}

fn sidecar_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../divine-server/bin")
        .join(target_dir())
        .join(exe_name());
    if dev.exists() {
        return Ok(dev);
    }

    let resource = app
        .path()
        .resource_dir()
        .map_err(|err| format!("获取资源目录失败: {err}"))?
        .join("bin")
        .join(target_dir())
        .join(exe_name());
    if resource.exists() {
        return Ok(resource);
    }

    Err(format!("sidecar 不存在: {}", dev.display()))
}

fn port_open() -> bool {
    let addr: SocketAddr = format!("{SIDECAR_HOST}:{SIDECAR_PORT}")
        .parse()
        .expect("invalid sidecar address");
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

pub fn spawn(app: &AppHandle) -> Result<(), String> {
    if port_open() {
        return Ok(());
    }
    let path = sidecar_path(app)?;
    let mut cmd = Command::new(&path);
    cmd.env("HOST", SIDECAR_HOST)
        .env("PORT", SIDECAR_PORT.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    if let Ok(data_dir) = app.path().app_data_dir() {
        cmd.env("DIVINE_DATA_DIR", &data_dir);
        cmd.env("DIVINE_WORKSPACE_DIR", data_dir.join("workspace"));
    }
    let child = cmd
        .spawn()
        .map_err(|err| format!("启动 sidecar 失败: {err}"))?;

    let state: State<SidecarState> = app.state::<SidecarState>();
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "sidecar state 锁失败".to_string())?;
    if let Some(mut old) = guard.take() {
        let _ = old.kill();
    }
    *guard = Some(child);
    Ok(())
}

pub fn stop(app: &AppHandle) {
    let state: State<SidecarState> = app.state::<SidecarState>();
    let locked = state.0.lock();
    if let Ok(mut guard) = locked {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

pub fn spawn_and_monitor(app: AppHandle) -> Result<(), String> {
    spawn(&app)?;

    std::thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(20);
        while Instant::now() < deadline {
            if port_open() {
                break;
            }
            std::thread::sleep(Duration::from_millis(300));
        }

        loop {
            std::thread::sleep(Duration::from_secs(5));
            if port_open() {
                continue;
            }
            std::thread::sleep(Duration::from_secs(2));
            if let Err(err) = spawn(&app) {
                eprintln!("[sidecar] 重启失败: {err}");
            }
        }
    });

    Ok(())
}

pub fn health() -> bool {
    port_open()
}

pub fn env() -> serde_json::Value {
    serde_json::json!({
        "HOST": SIDECAR_HOST,
        "PORT": SIDECAR_PORT,
    })
}
