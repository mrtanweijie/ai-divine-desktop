mod commands;
mod services;

use services::sidecar::SidecarState;
use tauri::{Manager, RunEvent, WindowEvent};

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[cfg(target_os = "macos")]
fn setup_tray(app: &tauri::App) -> tauri::Result<()> {
    use tauri::menu::{MenuBuilder, MenuItem};
    use tauri::tray::{
        MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent,
    };

    let show_item =
        MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
    let quit_item =
        MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = MenuBuilder::new(app)
        .item(&show_item)
        .separator()
        .item(&quit_item)
        .build()?;

    let icon =
        tauri::image::Image::from_bytes(include_bytes!("../icons/tray-icon.png"))?;
    let tray = TrayIconBuilder::with_id("divine-tray")
        .icon(icon)
        .tooltip("AI Divine")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => show_main_window(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    app.manage(tray);

    Ok(())
}

pub fn run() {
    let app = tauri::Builder::default()
        .manage(SidecarState::default())
        .plugin(tauri_plugin_dialog::init())
        .on_window_event(|_window, _event| {
            #[cfg(target_os = "macos")]
            if let WindowEvent::CloseRequested { api, .. } = _event {
                api.prevent_close();
                let _ = _window.hide();
            }
        })
        .setup(|app| {
            if let Err(err) = services::sidecar::spawn_and_monitor(app.handle().clone()) {
                eprintln!("[ai-divine-sidecar] 启动失败: {err}");
            }
            #[cfg(target_os = "macos")]
            if let Err(err) = setup_tray(app) {
                eprintln!("[tray] 初始化失败: {err}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::sidecar::start_sidecar,
            commands::sidecar::stop_sidecar,
            commands::sidecar::sidecar_health,
            commands::sidecar::get_sidecar_env,
            commands::system::open_local_file,
            commands::system::open_file_location,
            commands::system::open_folder,
            commands::system::open_url,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        #[cfg(target_os = "macos")]
        if let RunEvent::Reopen { .. } = event {
            show_main_window(app_handle);
        }
        if let RunEvent::Exit = event {
            services::sidecar::stop(app_handle);
        }
    });
}
