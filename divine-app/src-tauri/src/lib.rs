mod commands;
mod services;

use services::sidecar::SidecarState;
use tauri::RunEvent;

pub fn run() {
    let app = tauri::Builder::default()
        .manage(SidecarState::default())
        .setup(|app| {
            if let Err(err) = services::sidecar::spawn_and_monitor(app.handle().clone()) {
                eprintln!("[sidecar] 启动失败: {err}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::sidecar::start_sidecar,
            commands::sidecar::stop_sidecar,
            commands::sidecar::sidecar_health,
            commands::sidecar::get_sidecar_env,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            services::sidecar::stop(app_handle);
        }
    });
}
