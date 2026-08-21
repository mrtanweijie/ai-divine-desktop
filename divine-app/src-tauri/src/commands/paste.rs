use std::collections::hash_map::DefaultHasher;
use std::fs;
use std::hash::{Hash, Hasher};
use tauri::Manager;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;

const MAX_PASTE_CHARS: usize = 2_000_000;
const MAX_PASTE_IMAGE_BYTES: usize = 10 * 1024 * 1024;
const MAX_PASTE_FILE_BYTES: usize = 100 * 1024 * 1024;

fn content_hash(text: &str) -> String {
    let mut hasher = DefaultHasher::new();
    text.hash(&mut hasher);
    format!("{:016x}", hasher.finish())
}

/// Extension for image MIME types the vision model accepts.
fn image_extension(mime: &str) -> Option<&'static str> {
    match mime {
        "image/png" => Some("png"),
        "image/jpeg" | "image/jpg" => Some("jpg"),
        "image/gif" => Some("gif"),
        "image/webp" => Some("webp"),
        _ => None,
    }
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

/// Persist a pasted screenshot (base64, no data: prefix) into the local
/// chat_attachments dir. The image stays on disk; the vision pipeline reads
/// the file path and sends base64 to the vision model when the message goes
/// out. Content-hash dedup keeps repeated pastes from duplicating files.
#[tauri::command]
pub fn save_paste_image(
    app: tauri::AppHandle,
    base64: String,
    mime: String,
) -> Result<serde_json::Value, String> {
    let ext = image_extension(&mime).ok_or_else(|| {
        format!("不支持的图片格式: {mime}（仅支持 png/jpg/gif/webp）")
    })?;
    let bytes = STANDARD
        .decode(base64.trim())
        .map_err(|err| format!("图片数据解码失败: {err}"))?;
    if bytes.is_empty() {
        return Err("图片数据为空".to_string());
    }
    if bytes.len() > MAX_PASTE_IMAGE_BYTES {
        return Err("图片超过 10MB".to_string());
    }

    let dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("无法定位应用数据目录: {err}"))?
        .join("chat_attachments");
    fs::create_dir_all(&dir).map_err(|err| format!("创建目录失败: {err}"))?;

    let hash = content_hash(&base64);
    let file_name = format!("screenshot-{}.{ext}", &hash[..8]);
    let path = dir.join(&file_name);
    if !path.exists() {
        fs::write(&path, &bytes).map_err(|err| format!("写入文件失败: {err}"))?;
    }

    Ok(serde_json::json!({
        "name": file_name,
        "path": path.to_string_lossy().to_string(),
        "size": bytes.len(),
    }))
}

/// Persist a pasted clipboard file (base64) that has no filesystem path (e.g.
/// a file copied from an app that only exposes its data). Saved into the local
/// chat_attachments dir with a content-hash suffix for dedup.
#[tauri::command]
pub fn save_paste_file(
    app: tauri::AppHandle,
    base64: String,
    name: String,
) -> Result<serde_json::Value, String> {
    let bytes = STANDARD
        .decode(base64.trim())
        .map_err(|err| format!("文件数据解码失败: {err}"))?;
    if bytes.is_empty() {
        return Err("粘贴文件内容为空".to_string());
    }
    if bytes.len() > MAX_PASTE_FILE_BYTES {
        return Err("粘贴文件超过 100MB".to_string());
    }

    let dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("无法定位应用数据目录: {err}"))?
        .join("chat_attachments");
    fs::create_dir_all(&dir).map_err(|err| format!("创建目录失败: {err}"))?;

    let hash = content_hash(&base64);
    // Keep only the file name (no path separators) and its extension.
    let base_name = name.rsplit(['/', '\\']).next().unwrap_or("paste-file");
    let mut stem = base_name.split('.').next().unwrap_or(base_name);
    let ext = base_name
        .rsplit_once('.')
        .map(|(_, ext)| ext.to_string())
        .unwrap_or_default();
    let sanitized: String = stem
        .chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ch == '_' || ch == '-' || ch == '.' {
                ch
            } else {
                '_'
            }
        })
        .collect();
    if sanitized.is_empty() || sanitized == "." {
        stem = "paste-file";
    } else {
        stem = &sanitized;
    }
    let file_name = if ext.is_empty() {
        format!("{stem}-{}.bin", &hash[..8])
    } else {
        format!("{stem}-{}.{ext}", &hash[..8])
    };
    let path = dir.join(&file_name);
    if !path.exists() {
        fs::write(&path, &bytes).map_err(|err| format!("写入文件失败: {err}"))?;
    }

    Ok(serde_json::json!({
        "name": file_name,
        "path": path.to_string_lossy().to_string(),
        "size": bytes.len(),
    }))
}
