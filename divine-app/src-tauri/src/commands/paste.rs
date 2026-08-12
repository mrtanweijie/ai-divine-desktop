use std::collections::hash_map::DefaultHasher;
use std::fs;
use std::hash::{Hash, Hasher};
use tauri::Manager;

const MAX_PASTE_CHARS: usize = 2_000_000;

fn content_hash(text: &str) -> String {
    let mut hasher = DefaultHasher::new();
    text.hash(&mut hasher);
    format!("{:016x}", hasher.finish())
}

#[tauri::command]
pub fn save_paste_text(
    app: tauri::AppHandle,
    text: String,
) -> Result<serde_json::Value, String> {
    if text.trim().is_empty() {
        return Err("粘贴文本不能为空".to_string());
    }
    if text.len() > MAX_PASTE_CHARS {
        return Err("粘贴文本过大".to_string());
    }

    let dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("无法定位应用数据目录: {err}"))?
        .join("chat_attachments");
    fs::create_dir_all(&dir).map_err(|err| format!("创建目录失败: {err}"))?;

    let hash = content_hash(&text);
    let path = dir.join(format!("{hash}.txt"));
    let cached = path.exists();
    if !cached {
        fs::write(&path, text.as_bytes()).map_err(|err| format!("写入文件失败: {err}"))?;
    }

    Ok(serde_json::json!({
        "name": format!("paste-{}.txt", &hash[..8]),
        "path": path.to_string_lossy().to_string(),
        "hash": hash,
        "size": text.len(),
        "cached": cached,
    }))
}
