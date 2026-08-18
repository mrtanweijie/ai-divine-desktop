mod commands;
mod services;

use commands::workspace::WorkspaceWatchState;
use services::sidecar::SidecarState;
use std::thread;
use tauri::{Emitter, Manager, RunEvent, WindowEvent};

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

// macOS 原生全屏通知监听：
// 监听 NSWindowWillEnterFullScreenNotification / NSWindowWillExitFullScreenNotification。
// 注意必须用 Will（动画【开始前】触发）而不是 Did（动画结束后才触发）——
// 退出全屏时红绿灯在动画开始时就会出现，Did 通知太慢，会导致左侧 actions
// 先被红绿灯遮住；Will 通知在红绿灯出现前触发，前端收到事件时立即切换布局。
#[cfg(target_os = "macos")]
fn observe_fullscreen_notifications(app: &tauri::AppHandle) {
    use objc2::runtime::AnyObject;
    use objc2_app_kit::{NSWindowWillEnterFullScreenNotification, NSWindowWillExitFullScreenNotification};
    use objc2_foundation::NSNotificationCenter;

    let Some(window) = app.get_webview_window("main") else { return; };
    let ns_window = match window.ns_window() {
        Ok(ptr) => ptr as *mut AnyObject,
        Err(_) => return,
    };
    let center = NSNotificationCenter::defaultCenter();

    // 进入全屏 → 事件 payload = true；退出全屏 → payload = false。
    // RcBlock 使 block 持有 AppHandle 克隆并在通知回调里 emit；
    // 观察者 token（ProtocolObject）用 mem::forget 常驻，与应用同生命周期。
    let enter_handle = app.clone();
    let enter_block = block2::RcBlock::new(move |_notification: core::ptr::NonNull<objc2_foundation::NSNotification>| {
        eprintln!("[fullscreen] WILL_ENTER notification fired");
        let _ = enter_handle.emit("window-fullscreen-changed", true);
    });
    let exit_handle = app.clone();
    let exit_block = block2::RcBlock::new(move |_notification: core::ptr::NonNull<objc2_foundation::NSNotification>| {
        eprintln!("[fullscreen] WILL_EXIT notification fired");
        let _ = exit_handle.emit("window-fullscreen-changed", false);
    });

    unsafe {
        let enter_name: &objc2_foundation::NSNotificationName = NSWindowWillEnterFullScreenNotification;
        let enter_obs = center.addObserverForName_object_queue_usingBlock(
            Some(enter_name),
            Some(&*ns_window),
            None,
            &enter_block,
        );
        std::mem::forget(enter_obs);

        let exit_name: &objc2_foundation::NSNotificationName = NSWindowWillExitFullScreenNotification;
        let exit_obs = center.addObserverForName_object_queue_usingBlock(
            Some(exit_name),
            Some(&*ns_window),
            None,
            &exit_block,
        );
        std::mem::forget(exit_obs);
    }
}

#[cfg(target_os = "macos")]
fn handle_close_request(window: &tauri::Window) {
    if window.is_fullscreen().unwrap_or(false) {
        let window = window.clone();
        thread::spawn(move || {
            // In fullscreen the close button only exits fullscreen and keeps
            // the window visible.
            let _ = window.set_fullscreen(false);
        });
        return;
    } else {
        let _ = window.hide();
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
    let builder = tauri::Builder::default()
        .manage(SidecarState::default())
        .manage(WorkspaceWatchState::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build());
    #[cfg(not(target_os = "macos"))]
    let builder = builder.plugin(tauri_plugin_notification::init());
    let app = builder
        .on_window_event(|_window, _event| {
            #[cfg(target_os = "macos")]
            if let WindowEvent::CloseRequested { api, .. } = _event {
                api.prevent_close();
                handle_close_request(_window);
            }
        })
        .setup(|app| {
            if let Err(err) = services::sidecar::spawn_and_monitor(app.handle().clone()) {
                eprintln!("[ai-divine-sidecar] 启动失败: {err}");
            }
            #[cfg(target_os = "macos")]
            {
                use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};
                if let Some(window) = app.get_webview_window("main") {
                    let _ = apply_vibrancy(
                        &window,
                        NSVisualEffectMaterial::Sidebar,
                        None,
                        Some(18.0),
                    );
                }
            }
            #[cfg(target_os = "macos")]
            if let Err(err) = setup_tray(app) {
                eprintln!("[tray] 初始化失败: {err}");
            }
            #[cfg(target_os = "macos")]
            observe_fullscreen_notifications(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::sidecar::start_sidecar,
            commands::sidecar::stop_sidecar,
            commands::sidecar::sidecar_health,
            commands::sidecar::get_sidecar_env,
            commands::paste::save_paste_text,
            commands::system::open_local_file,
            commands::system::open_file_location,
            commands::system::open_folder,
            commands::system::open_url,
            commands::system::request_notification_permission,
            commands::system::show_native_notification,
            commands::system::add_calendar_event,
            commands::system::remove_calendar_event,
            commands::workspace::get_file_tree,
            commands::workspace::get_dir_children,
            commands::workspace::get_file_diff,
            commands::workspace::get_external_file_preview,
            commands::workspace::watch_workspace,
            commands::workspace::unwatch_workspace,
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
