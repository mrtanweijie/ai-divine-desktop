use std::fs::OpenOptions;
use std::io::Write;
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(exe_dir) = current_exe.parent() {
            let external = exe_dir.join(exe_name());
            if external.exists() {
                return Ok(external);
            }
        }
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

fn log_line(data_dir: Option<&Path>, message: &str) {
    eprintln!("[ai-divine-sidecar] {message}");
    if let Some(dir) = data_dir {
        let _ = std::fs::create_dir_all(dir);
        let path = dir.join("divine-sidecar.log");
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_secs())
            .unwrap_or(0);
        if let Ok(mut file) =
            OpenOptions::new().create(true).append(true).open(path)
        {
            let _ = writeln!(
                file,
                "[{timestamp}] [ai-divine-sidecar] {message}"
            );
        }
    }
}

pub fn spawn(app: &AppHandle) -> Result<(), String> {
    let data_dir = app.path().app_data_dir().ok();
    if port_open() {
        log_line(data_dir.as_deref(), "端口已占用，复用现有 sidecar");
        return Ok(());
    }
    let path = sidecar_path(app)?;
    log_line(
        data_dir.as_deref(),
        &format!("准备启动 sidecar: {}", path.display()),
    );
    let mut cmd = Command::new(&path);
    cmd.env("HOST", SIDECAR_HOST)
        .env("PORT", SIDECAR_PORT.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    if let Some(data_dir) = data_dir.as_ref() {
        cmd.env("DIVINE_DATA_DIR", data_dir);
        cmd.env("DIVINE_WORKSPACE_DIR", data_dir.join("workspace"));
    }
    let child = cmd
        .spawn()
        .map_err(|err| {
            log_line(
                data_dir.as_deref(),
                &format!("启动 sidecar 失败: {err}"),
            );
            format!("启动 sidecar 失败: {err}")
        })?;
    log_line(
        data_dir.as_deref(),
        &format!(
            "sidecar 已启动 pid={} port={}",
            child.id(),
            SIDECAR_PORT
        ),
    );

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
    let data_dir = app.path().app_data_dir().ok();
    let state: State<SidecarState> = app.state::<SidecarState>();
    let locked = state.0.lock();
    if let Ok(mut guard) = locked {
        if let Some(mut child) = guard.take() {
            let pid = child.id();
            let _ = child.kill();
            let _ = child.wait();
            log_line(
                data_dir.as_deref(),
                &format!("sidecar 已停止 pid={pid}"),
            );
        }
    }
}

pub fn spawn_and_monitor(app: AppHandle) -> Result<(), String> {
    spawn(&app)?;

    std::thread::spawn(move || {
        let data_dir = app.path().app_data_dir().ok();
        let deadline = Instant::now() + Duration::from_secs(20);
        while Instant::now() < deadline {
            if port_open() {
                log_line(data_dir.as_deref(), "sidecar 健康检查通过");
                break;
            }
            std::thread::sleep(Duration::from_millis(300));
        }

        loop {
            std::thread::sleep(Duration::from_secs(5));
            if port_open() {
                continue;
            }
            log_line(data_dir.as_deref(), "sidecar 掉线，准备重启");
            std::thread::sleep(Duration::from_secs(2));
            match spawn(&app) {
                Ok(()) => {
                    log_line(data_dir.as_deref(), "sidecar 重启成功");
                }
                Err(err) => {
                    eprintln!("[ai-divine-sidecar] 重启失败: {err}");
                    log_line(
                        data_dir.as_deref(),
                        &format!("sidecar 重启失败: {err}"),
                    );
                }
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
