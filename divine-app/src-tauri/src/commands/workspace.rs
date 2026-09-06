use notify::{EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::Serialize;
use std::collections::hash_map::DefaultHasher;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, State};
use walkdir::WalkDir;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;

#[derive(Default)]
pub struct WorkspaceWatchState {
    watchers: Mutex<HashMap<String, RecommendedWatcher>>,
}

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct FileNode {
    name: String,
    path: String,
    is_dir: bool,
    children: Option<Vec<FileNode>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileDiff {
    rel_path: String,
    old_content: String,
    new_content: String,
    diff_text: String,
    additions: usize,
    deletions: usize,
    is_git: bool,
    tracked: bool,
    is_binary: bool,
    exists: bool,
    content_truncated: bool,
}

fn normalize_rel_path(raw: &str) -> Result<String, String> {
    let mut parts: Vec<&str> = Vec::new();
    for part in raw.split(['/', '\\']) {
        if part.is_empty() || part == "." {
            continue;
        }
        if part == ".." {
            return Err("路径越界".to_string());
        }
        parts.push(part);
    }
    if parts.is_empty() {
        return Err("缺少文件路径".to_string());
    }
    Ok(parts.join("/"))
}

fn find_git_root(start: &Path) -> Option<PathBuf> {
    let mut current = start.parent();
    while let Some(dir) = current {
        if dir.join(".git").exists() {
            return Some(dir.to_path_buf());
        }
        current = dir.parent();
    }
    None
}

fn should_ignore(name: &str) -> bool {
    matches!(
        name,
        ".git" | "node_modules" | ".pnpm-store" | "target" | ".DS_Store"
    )
}

fn is_git_ignored(root: &Path, path: &Path) -> bool {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .arg("check-ignore")
        .arg("-q")
        .arg("--")
        .arg(path)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn scan_dir(root: &Path) -> Vec<FileNode> {
    let git_aware = run_git(root, &["rev-parse", "--is-inside-work-tree"])
        .map(|value| value.trim() == "true")
        .unwrap_or(false);
    let mut nodes: Vec<FileNode> = Vec::new();
    for entry in WalkDir::new(root)
        .min_depth(1)
        .max_depth(1)
        .into_iter()
        .filter_entry(|entry| {
            if entry.depth() == 0 {
                return true;
            }
            let name = entry.file_name().to_string_lossy();
            !should_ignore(&name)
                && (!git_aware || !is_git_ignored(root, entry.path()))
        })
    {
        let Ok(entry) = entry else { continue };
        let rel = entry
            .path()
            .strip_prefix(root)
            .unwrap_or(entry.path())
            .to_string_lossy()
            .replace('\\', "/");
        nodes.push(FileNode {
            name: entry.file_name().to_string_lossy().into_owned(),
            path: rel,
            is_dir: entry.file_type().is_dir(),
            children: None,
        });
    }
    nodes.sort_by(|a, b| b.is_dir.cmp(&a.is_dir).then_with(|| a.name.cmp(&b.name)));
    nodes
}

fn run_git(dir: &Path, args: &[&str]) -> Option<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(args)
        .output()
        .ok()?;
    if output.status.success() {
        Some(String::from_utf8_lossy(&output.stdout).into_owned())
    } else {
        None
    }
}

fn run_git_lossy(dir: &Path, args: &[&str]) -> Option<String> {
    Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(args)
        .output()
        .ok()
        .map(|output| String::from_utf8_lossy(&output.stdout).into_owned())
}

fn count_diff(diff_text: &str) -> (usize, usize) {
    let additions = diff_text
        .lines()
        .filter(|line| line.starts_with('+') && !line.starts_with("+++"))
        .count();
    let deletions = diff_text
        .lines()
        .filter(|line| line.starts_with('-') && !line.starts_with("---"))
        .count();
    (additions, deletions)
}

const MAX_PREVIEW_BYTES: u64 = 1024 * 1024;
const MAX_PREVIEW_LINES: usize = 3000;
const BINARY_SAMPLE_BYTES: usize = 8192;

fn read_preview_bytes(path: &Path) -> Option<(Vec<u8>, bool)> {
    let file = std::fs::File::open(path).ok()?;
    let mut buffer = Vec::with_capacity(
        std::fs::metadata(path)
            .map(|meta| meta.len().min(MAX_PREVIEW_BYTES) as usize)
            .unwrap_or(0),
    );
    file.take(MAX_PREVIEW_BYTES + 1)
        .read_to_end(&mut buffer)
        .ok()?;
    let mut truncated = buffer.len() as u64 > MAX_PREVIEW_BYTES;
    if truncated {
        buffer.truncate(MAX_PREVIEW_BYTES as usize);
    }
    // Line-count cap: files with many short lines (e.g. 50k-row CSV-like
    // lists) stay under the byte cap but would still flood the frontend
    // with tens of thousands of rendered rows. Cut at a newline boundary
    // so the returned text is always line-complete.
    if !truncated && buffer.iter().filter(|byte| **byte == b'\n').count() > MAX_PREVIEW_LINES {
        let mut cut = buffer.len();
        let mut newlines = 0;
        for (index, byte) in buffer.iter().enumerate() {
            if *byte == b'\n' {
                newlines += 1;
                if newlines >= MAX_PREVIEW_LINES {
                    cut = index + 1;
                    break;
                }
            }
        }
        buffer.truncate(cut);
        truncated = true;
    }
    Some((buffer, truncated))
}

fn looks_binary(bytes: &[u8]) -> bool {
    bytes
        .iter()
        .take(BINARY_SAMPLE_BYTES)
        .any(|byte| *byte == 0)
}

const MAX_BINARY_PREVIEW_BYTES: u64 = 25 * 1024 * 1024;

/// MIME type for binary files that can be previewed inline (images/PDF).
fn binary_preview_mime(path: &Path) -> Option<&'static str> {
    let ext = path
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match ext.as_str() {
        "png" => Some("image/png"),
        "jpg" | "jpeg" => Some("image/jpeg"),
        "gif" => Some("image/gif"),
        "webp" => Some("image/webp"),
        "svg" => Some("image/svg+xml"),
        "bmp" => Some("image/bmp"),
        "avif" => Some("image/avif"),
        "pdf" => Some("application/pdf"),
        _ => None,
    }
}

/// Read a binary file (image/PDF) as a base64 data URL for inline preview.
#[tauri::command]
pub fn get_binary_preview(path: String) -> Result<serde_json::Value, String> {
    let file_path = PathBuf::from(&path);
    if !file_path.is_file() {
        return Err("文件不存在".to_string());
    }
    let mime = binary_preview_mime(&file_path)
        .ok_or_else(|| "该文件类型不支持预览".to_string())?;
    let size = std::fs::metadata(&file_path)
        .map_err(|err| format!("读取文件信息失败: {err}"))?
        .len();
    if size > MAX_BINARY_PREVIEW_BYTES {
        return Err("文件过大，无法预览".to_string());
    }
    let bytes = std::fs::read(&file_path).map_err(|err| format!("读取文件失败: {err}"))?;
    Ok(serde_json::json!({
        "mime": mime,
        "dataUrl": format!("data:{mime};base64,{}", STANDARD.encode(&bytes)),
    }))
}

#[tauri::command]
pub fn get_file_tree(root: String) -> Result<Vec<FileNode>, String> {
    let root = PathBuf::from(&root)
        .canonicalize()
        .map_err(|err| format!("项目路径无效: {err}"))?;
    if !root.is_dir() {
        return Err("项目路径不是文件夹".to_string());
    }
    Ok(scan_dir(&root))
}

#[tauri::command]
pub fn get_dir_children(root: String, dir: String) -> Result<Vec<FileNode>, String> {
    let root = PathBuf::from(&root)
        .canonicalize()
        .map_err(|err| format!("项目路径无效: {err}"))?;
    let rel = normalize_rel_path(&dir)?;
    let target = root
        .join(&rel)
        .canonicalize()
        .map_err(|err| format!("目录无效: {err}"))?;
    if !target.is_dir() {
        return Err("目录不存在".to_string());
    }
    if !target.starts_with(&root) {
        return Err("路径越界".to_string());
    }
    let mut nodes = scan_dir(&target);
    for node in &mut nodes {
        node.path = format!("{}/{}", rel, node.path);
    }
    Ok(nodes)
}

#[tauri::command]
pub fn get_file_diff(repo_path: String, rel_path: String) -> Result<FileDiff, String> {
    let repo = PathBuf::from(&repo_path)
        .canonicalize()
        .map_err(|err| format!("项目路径无效: {err}"))?;
    if !repo.is_dir() {
        return Err("项目路径不是文件夹".to_string());
    }

    let rel = normalize_rel_path(&rel_path)?;
    let target = repo.join(&rel);
    let exists = target.is_file();

    let new_bytes = if exists {
        read_preview_bytes(&target)
    } else {
        None
    };
    let new_is_binary = new_bytes
        .as_ref()
        .map(|(bytes, _)| looks_binary(bytes))
        .unwrap_or(false);
    let new_truncated = new_bytes
        .as_ref()
        .map(|(_, truncated)| *truncated)
        .unwrap_or(false);

    let mut is_git = false;
    let mut tracked = false;
    let mut old_bytes: Option<Vec<u8>> = None;
    let mut diff_text = String::new();

    if let Some(root) = find_git_root(&target) {
        is_git = true;
        let repo_rel = target
            .strip_prefix(&root)
            .unwrap_or(&target)
            .to_string_lossy()
            .replace('\\', "/");
        if !new_is_binary {
            if let Some(raw) = run_git(&root, &["show", &format!("HEAD:{repo_rel}")]) {
                tracked = true;
                old_bytes = Some(raw.into_bytes());
            }
        }

        if tracked {
            diff_text = run_git_lossy(&root, &["diff", "--no-color", "--", &repo_rel])
                .unwrap_or_default();
        } else if exists && !new_is_binary {
            diff_text = run_git_lossy(
                &root,
                &[
                    "diff",
                    "--no-index",
                    "--no-color",
                    "--",
                    "/dev/null",
                    target.to_str().unwrap_or(""),
                ],
            )
            .unwrap_or_default();
        }
    }

    let old_text = old_bytes
        .as_deref()
        .and_then(|bytes| String::from_utf8(bytes.to_vec()).ok());
    let new_text = if new_is_binary {
        None
    } else if exists {
        new_bytes.map(|(bytes, _)| String::from_utf8_lossy(&bytes).into_owned())
    } else {
        Some(String::new())
    };
    let is_binary = new_is_binary || (old_bytes.is_some() && old_text.is_none());
    let (additions, deletions) = if is_binary {
        (0, 0)
    } else {
        count_diff(&diff_text)
    };

    Ok(FileDiff {
        rel_path: rel,
        old_content: old_text.unwrap_or_default(),
        new_content: new_text.unwrap_or_default(),
        diff_text,
        additions,
        deletions,
        is_git,
        tracked,
        is_binary,
        exists,
        content_truncated: new_truncated,
    })
}

#[tauri::command]
pub fn get_external_file_preview(path: String) -> Result<FileDiff, String> {
    let target = PathBuf::from(&path)
        .canonicalize()
        .map_err(|err| format!("文件路径无效: {err}"))?;
    if !target.is_file() {
        return Err("目标不是文件".to_string());
    }
    let (bytes, truncated) = read_preview_bytes(&target)
        .ok_or_else(|| "读取文件失败".to_string())?;
    let is_binary = looks_binary(&bytes);
    let content = if is_binary {
        String::new()
    } else {
        String::from_utf8_lossy(&bytes).into_owned()
    };
    Ok(FileDiff {
        rel_path: target.to_string_lossy().into_owned(),
        old_content: String::new(),
        new_content: content,
        diff_text: String::new(),
        additions: 0,
        deletions: 0,
        is_git: false,
        tracked: true,
        is_binary,
        exists: true,
        content_truncated: truncated,
    })
}

#[tauri::command]
pub fn watch_workspace(
    app: AppHandle,
    state: State<'_, WorkspaceWatchState>,
    path: String,
) -> Result<(), String> {
    let workspace = PathBuf::from(&path)
        .canonicalize()
        .map_err(|err| format!("项目路径无效: {err}"))?;
    if !workspace.is_dir() {
        return Err("项目路径不是文件夹".to_string());
    }

    let key = workspace.to_string_lossy().into_owned();
    let app = app.clone();
    let mut watcher = notify::recommended_watcher(move |result: notify::Result<notify::Event>| {
        let Ok(event) = result else { return };
        let kind = match event.kind {
            EventKind::Create(_) => "created",
            EventKind::Remove(_) => "removed",
            EventKind::Modify(_) => "modified",
            _ => return,
        };
        if let Some(changed) = event.paths.first() {
            let _ = app.emit(
                "workspace:changed",
                serde_json::json!({
                    "path": changed.to_string_lossy(),
                    "kind": kind,
                }),
            );
        }
    })
    .map_err(|err| format!("初始化文件监听失败: {err}"))?;

    watcher
        .watch(&workspace, RecursiveMode::Recursive)
        .map_err(|err| format!("监听项目失败: {err}"))?;
    state
        .watchers
        .lock()
        .map_err(|_| "监听状态异常".to_string())?
        .insert(key, watcher);
    Ok(())
}

#[tauri::command]
pub fn unwatch_workspace(
    state: State<'_, WorkspaceWatchState>,
    path: String,
) -> Result<(), String> {
    let workspace = PathBuf::from(&path)
        .canonicalize()
        .map_err(|err| format!("项目路径无效: {err}"))?;
    let key = workspace.to_string_lossy().into_owned();
    state
        .watchers
        .lock()
        .map_err(|_| "监听状态异常".to_string())?
        .remove(&key);
    Ok(())
}

const MAX_EXPORT_BYTES: usize = 20 * 1024 * 1024;

/// Persist a chart exported from the webview's ECharts instance (base64,
/// no data: prefix) into <workspace>/charts/. The file name is sanitized and
/// gets a content-hash suffix so repeated exports never silently overwrite an
/// earlier one. The returned path lets the chat surface open its location.
#[tauri::command]
pub fn save_export_file(
    workspace: String,
    base64: String,
    name: String,
) -> Result<serde_json::Value, String> {
    let bytes = STANDARD
        .decode(base64.trim())
        .map_err(|err| format!("导出数据解码失败: {err}"))?;
    if bytes.is_empty() {
        return Err("导出内容为空".to_string());
    }
    if bytes.len() > MAX_EXPORT_BYTES {
        return Err("导出文件超过 20MB".to_string());
    }

    let root = PathBuf::from(&workspace);
    if !root.is_dir() {
        return Err(format!("工作区目录不存在: {}", root.display()));
    }
    let chart_dir = root.join("charts");
    std::fs::create_dir_all(&chart_dir)
        .map_err(|err| format!("创建 charts 目录失败: {err}"))?;

    // 只保留「字母数字(含中文)/_/-」，剥掉路径分隔与越界片段
    let (stem_in, ext_in) = match name.rsplit_once('.') {
        Some((stem, ext)) if !stem.is_empty() && !ext.is_empty() => (stem, ext),
        _ => (name.as_str(), ""),
    };
    let keep = |ch: char| ch.is_alphanumeric() || ch == '_' || ch == '-';
    let stem: String = stem_in.chars().filter(|c| keep(*c)).take(80).collect();
    let ext: String = ext_in.chars().filter(|c| keep(*c)).take(12).collect();
    let stem = if stem.is_empty() { "chart" } else { stem.as_str() };

    let mut hasher = DefaultHasher::new();
    bytes.hash(&mut hasher);
    let hash = format!("{:08x}", hasher.finish());
    let file_name = if ext.is_empty() {
        format!("{stem}-{hash}.bin")
    } else {
        format!("{stem}-{hash}.{ext}")
    };
    let path = chart_dir.join(&file_name);
    std::fs::write(&path, &bytes).map_err(|err| format!("写入文件失败: {err}"))?;

    Ok(serde_json::json!({
        "name": file_name,
        "path": path.to_string_lossy().to_string(),
        "size": bytes.len(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_build_rs_content() {
        let root = std::env::current_dir().expect("current dir");
        let diff =
            get_file_diff(root.to_string_lossy().into_owned(), "build.rs".to_string())
                .expect("diff command");
        assert!(!diff.is_binary);
        assert!(diff.new_content.contains("fn main"));
        let json = serde_json::to_value(&diff).expect("serialize diff");
        assert!(
            json.get("newContent").is_some(),
            "expected camelCase field newContent"
        );
    }

    #[test]
    fn marks_binary_preview() {
        let dir = std::env::temp_dir().join(format!(
            "divine-binary-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("create temp dir");
        let file = dir.join("sample.bin");
        std::fs::write(&file, [0u8, 1, 2, 3]).expect("write binary file");
        let diff = get_file_diff(
            dir.to_string_lossy().into_owned(),
            "sample.bin".to_string(),
        )
        .expect("diff command");
        assert!(diff.is_binary);
        assert!(diff.new_content.is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn finds_nearest_git_root_for_nested_repo() {
        let dir = std::env::temp_dir().join(format!(
            "divine-nested-git-{}",
            std::process::id()
        ));
        let nested = dir.join("outer").join("nested");
        std::fs::create_dir_all(nested.join("src")).expect("create temp dirs");
        std::fs::create_dir(dir.join("outer").join(".git")).expect("create outer git");
        std::fs::create_dir(nested.join(".git")).expect("create nested git");
        let target = nested.join("src/app.ts");
        std::fs::write(&target, "export const x = 1;").expect("write temp file");
        assert_eq!(
            find_git_root(&target),
            Some(nested)
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn caps_preview_line_count() {
        let dir = std::env::temp_dir().join(format!(
            "divine-lines-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("create temp dir");
        let file = dir.join("many-lines.txt");
        let mut content = String::new();
        for index in 0..(MAX_PREVIEW_LINES + 500) {
            content.push_str(&format!("line-{index}\n"));
        }
        std::fs::write(&file, &content).expect("write temp file");
        let diff = get_file_diff(
            dir.to_string_lossy().into_owned(),
            "many-lines.txt".to_string(),
        )
        .expect("diff command");
        assert!(diff.content_truncated);
        assert_eq!(
            diff.new_content.lines().count(),
            MAX_PREVIEW_LINES,
            "preview must be cut at the line cap"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn caps_50k_line_file_under_byte_cap() {
        // Regression: a 50k-row short-line file stays under the 1 MiB byte cap,
        // so only the line-count cap can stop it from flooding the frontend.
        let dir = std::env::temp_dir().join(format!(
            "divine-50k-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("create temp dir");
        let file = dir.join("清单.txt");
        let mut content = String::new();
        for index in 0..50_192 {
            content.push_str(&format!("6000000{:08}\n", index));
        }
        std::fs::write(&file, &content).expect("write temp file");
        let meta = std::fs::metadata(&file).expect("metadata");
        assert!(
            meta.len() < MAX_PREVIEW_BYTES,
            "simulated file must stay under the byte cap to exercise line capping"
        );
        let diff = get_file_diff(
            dir.to_string_lossy().into_owned(),
            "清单.txt".to_string(),
        )
        .expect("diff command");
        assert!(diff.content_truncated);
        assert_eq!(
            diff.new_content.lines().count(),
            MAX_PREVIEW_LINES,
            "50k-line preview must be cut to the line cap"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn does_not_cap_few_lines() {
        let dir = std::env::temp_dir().join(format!(
            "divine-few-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("create temp dir");
        let file = dir.join("few.txt");
        std::fs::write(&file, "a\nb\nc\n").expect("write temp file");
        let diff = get_file_diff(
            dir.to_string_lossy().into_owned(),
            "few.txt".to_string(),
        )
        .expect("diff command");
        assert!(!diff.content_truncated);
        assert_eq!(diff.new_content.lines().count(), 3);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn reads_diff_from_nested_repo() {
        let dir = std::env::temp_dir().join(format!(
            "divine-nested-diff-{}",
            std::process::id()
        ));
        let project = dir.join("project");
        let repo = project.join("nested");
        std::fs::create_dir_all(&repo).expect("create repo dir");
        let file = repo.join("note.txt");
        std::fs::write(&file, "line one\n").expect("write initial file");

        assert!(run_git(&repo, &["init", "-q"]).is_some());
        assert!(run_git(&repo, &["add", "-A"]).is_some());
        assert!(
            run_git(
                &repo,
                &[
                    "-c",
                    "user.name=divine test",
                    "-c",
                    "user.email=divine@example.com",
                    "commit",
                    "-m",
                    "init",
                    "-q",
                ],
            )
            .is_some()
        );

        std::fs::write(&file, "line one\nline two\n").expect("update file");
        let diff = get_file_diff(
            project.to_string_lossy().into_owned(),
            "nested/note.txt".to_string(),
        )
        .expect("diff command");
        assert!(diff.is_git);
        assert!(diff.tracked);
        assert!(diff.diff_text.contains("+line two"));

        let _ = std::fs::remove_dir_all(&dir);
    }
}
