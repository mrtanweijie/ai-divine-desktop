use std::path::Path;

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
