use std::path::Path;
use std::process::Command;

#[cfg(target_os = "macos")]
fn native_notification_available() -> Result<(), String> {
    let current_exe = std::env::current_exe()
        .map_err(|err| format!("无法定位可执行文件: {err}"))?;
    let path = current_exe.to_string_lossy();
    if !path.contains(".app/Contents/MacOS/") {
        return Err("原生通知需要以 .app 应用包方式运行".to_string());
    }
    Ok(())
}

#[cfg(target_os = "macos")]
#[tauri::command]
pub async fn request_notification_permission() -> Result<bool, String> {
    native_notification_available()?;
    notify_rust::request_auth()
        .await
        .map_err(|err| err.to_string())
}

#[cfg(target_os = "macos")]
#[tauri::command]
pub async fn show_native_notification(title: String, body: String) -> Result<(), String> {
    native_notification_available()?;
    notify_rust::Notification::new()
        .summary(&title)
        .body(&body)
        .show_async()
        .await
        .map(|_| ())
        .map_err(|err| err.to_string())
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
pub async fn request_notification_permission() -> Result<bool, String> {
    Err("原生通知权限仅在 macOS 可用".to_string())
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
pub async fn show_native_notification(_title: String, _body: String) -> Result<(), String> {
    Err("原生通知仅在 macOS 可用".to_string())
}

#[tauri::command]
pub fn open_local_file(path: String) -> Result<(), String> {
    let target = Path::new(&path)
        .canonicalize()
        .map_err(|err| format!("路径无效: {err}"))?;
    if !target.is_file() {
        return Err("目标不是文件".to_string());
    }
    open::that(&target).map_err(|err| format!("打开文件失败: {err}"))
}

#[tauri::command]
pub fn open_file_location(path: String) -> Result<(), String> {
    let target = Path::new(&path)
        .canonicalize()
        .map_err(|err| format!("路径无效: {err}"))?;
    let dir = target
        .parent()
        .ok_or_else(|| "无法定位文件目录".to_string())?;
    open::that(dir).map_err(|err| format!("打开目录失败: {err}"))
}

#[tauri::command]
pub fn open_folder(path: String) -> Result<(), String> {
    let target = Path::new(&path)
        .canonicalize()
        .map_err(|err| format!("路径无效: {err}"))?;
    if !target.is_dir() {
        return Err("目标不是目录".to_string());
    }
    open::that(&target).map_err(|err| format!("打开文件夹失败: {err}"))
}

#[tauri::command]
pub fn open_url(url: String) -> Result<(), String> {
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("只支持 http/https 链接".to_string());
    }
    open::that(url).map_err(|err| format!("打开链接失败: {err}"))
}

fn js_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn run_osascript(script: &str) -> Result<String, String> {
    let output = Command::new("osascript")
        .args(["-l", "JavaScript", "-e", script])
        .output()
        .map_err(|err| format!("无法执行 AppleScript: {err}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("写入系统日历失败: {}", stderr.trim()));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

#[tauri::command]
pub async fn add_calendar_event(
    title: String,
    start_at: String,
    end_at: Option<String>,
    notes: Option<String>,
) -> Result<String, String> {
    let title = js_escape(&title);
    let notes = js_escape(notes.as_deref().unwrap_or(""));
    let start = js_escape(&start_at);
    let end = js_escape(end_at.as_deref().unwrap_or(""));
    let end_expr = if end.is_empty() {
        "new Date(start.getTime() + 60 * 60 * 1000)".to_string()
    } else {
        format!("new Date('{end}')")
    };
    let script = format!(
        r#"const app = Application('Calendar');
const cal = app.calendars[0];
const start = new Date('{start}');
const end = {end_expr};
const event = app.Event({{summary: '{title}', description: '{notes}', startDate: start, endDate: end}});
cal.events.push(event);
event.uid();"#
    );
    // osascript 会阻塞到进程退出：首次调用还要拉起 Calendar.app 并等 TCC
    // 授权弹窗（用户不点就一直等）。同步命令跑在主线程，会把整个窗口冻住。
    // 脚本已在上面构造好，这里只 move 一个 String 进闭包。
    let uid = tauri::async_runtime::spawn_blocking(move || run_osascript(&script))
        .await
        .map_err(|err| format!("日历命令执行失败: {err}"))??;
    if uid.is_empty() {
        Ok(title)
    } else {
        Ok(uid)
    }
}

#[tauri::command]
pub async fn remove_calendar_event(title: String, start_at: String) -> Result<String, String> {
    let title = js_escape(&title);
    let start = js_escape(&start_at);
    let script = format!(
        r#"const app = Application('Calendar');
let removed = 0;
for (const cal of app.calendars()) {{
  for (const ev of cal.events()) {{
    try {{
      const start = new Date('{start}');
      if (ev.summary() === '{title}' && Math.abs(ev.startDate().getTime() - start.getTime()) < 60000) {{
        ev.delete();
        removed++;
      }}
    }} catch (err) {{}}
  }}
}}
removed;"#
    );
    // 同 add_calendar_event：JXA 是双重遍历所有日历的所有事件，事件量大时
    // 是 O(全部事件)，且同样要等 TCC 授权，必须移出主线程。
    let removed = tauri::async_runtime::spawn_blocking(move || run_osascript(&script))
        .await
        .map_err(|err| format!("日历命令执行失败: {err}"))??;
    Ok(removed)
}

/// 启用/停用全局唤起快捷键（CmdOrCtrl+Shift+D）。设置页开关调用；
/// 默认在启动时由 lib.rs 注册，用户关闭后经此命令注销。
#[tauri::command]
pub fn set_global_shortcut_enabled(
    app: tauri::AppHandle,
    enabled: bool,
) -> Result<(), String> {
    crate::set_global_shortcut_enabled(&app, enabled)
}
