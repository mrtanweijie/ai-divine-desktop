use notify::{EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::Serialize;
use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, State};
use walkdir::WalkDir;

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
    let truncated = buffer.len() as u64 > MAX_PREVIEW_BYTES;
    if truncated {
        buffer.truncate(MAX_PREVIEW_BYTES as usize);
    }
    Some((buffer, truncated))
}

fn looks_binary(bytes: &[u8]) -> bool {
    bytes
        .iter()
        .take(BINARY_SAMPLE_BYTES)
        .any(|byte| *byte == 0)
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

    if let Some(root_text) = run_git(&repo, &["rev-parse", "--show-toplevel"]) {
        is_git = true;
        let root = PathBuf::from(root_text.trim());
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
}
