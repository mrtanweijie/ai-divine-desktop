use tauri::AppHandle;

use crate::services::sidecar;

#[tauri::command]
pub fn start_sidecar(app: AppHandle) -> Result<(), String> {
    sidecar::spawn_and_monitor(app)
}

#[tauri::command]
pub fn stop_sidecar(app: AppHandle) -> Result<(), String> {
    sidecar::stop(&app);
    Ok(())
}

#[tauri::command]
pub fn sidecar_health() -> bool {
    sidecar::health()
}

#[tauri::command]
pub fn get_sidecar_env() -> serde_json::Value {
    sidecar::env()
}
