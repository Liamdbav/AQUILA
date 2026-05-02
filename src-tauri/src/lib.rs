use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use tauri::Emitter;

#[derive(serde::Deserialize)]
struct AquilaConfig {
    python: String,
    packager: String,
}

fn load_config() -> Result<AquilaConfig, String> {
    let candidates = [
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("aquila.local.json"))),
        Some(std::path::PathBuf::from("aquila.local.json")),
    ];

    for path in candidates.into_iter().flatten() {
        if path.exists() {
            let raw = std::fs::read_to_string(&path)
                .map_err(|e| format!("Erreur lecture config : {e}"))?;
            return serde_json::from_str(&raw)
                .map_err(|e| format!("Erreur parsing config : {e}"));
        }
    }

    Err("Configuration manquante — lancez ./setup.sh pour configurer AQUILA.".to_string())
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// Lance le pipeline Python et streame chaque ligne stdout vers le frontend
/// via l'event "packaging-progress" au format STATUS:message.
#[tauri::command]
async fn run_packaging(
    app: tauri::AppHandle,
    input_path: String,
    output_dir: String,
) -> Result<(), String> {
    let config = load_config()?;
    let python = config.python;
    let packager = config.packager;

    tokio::task::spawn_blocking(move || {
        let mut child = Command::new(&python)
            .arg(&packager)
            .arg(&input_path)
            .arg(&output_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Impossible de lancer Python : {e}"))?;

        // Draine stderr dans un thread séparé pour éviter le deadlock pipe :
        // si le buffer stderr (~64 Ko) sature, Python se bloque en attendant
        // qu'il soit lu, pendant que Rust attend la fin de stdout → deadlock.
        let stderr = child.stderr.take().expect("stderr piped");
        std::thread::spawn(move || {
            use std::io::Read;
            let _ = std::io::BufReader::new(stderr).bytes().last();
        });

        let stdout = child.stdout.take().expect("stdout piped");
        let reader = BufReader::new(stdout);

        for line in reader.lines() {
            let line = line.map_err(|e| e.to_string())?;
            app.emit("packaging-progress", &line)
                .map_err(|e| e.to_string())?;
        }

        let status = child.wait().map_err(|e| e.to_string())?;
        if status.success() {
            Ok(())
        } else {
            Err("Le pipeline a terminé avec un code d'erreur non nul".to_string())
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Ouvre le dossier de sortie dans le Finder macOS.
#[tauri::command]
fn open_output_folder(path: String) -> Result<(), String> {
    Command::new("open")
        .arg(&path)
        .spawn()
        .map_err(|e| format!("Impossible d'ouvrir le dossier : {e}"))?;
    Ok(())
}

/// Ouvre le dialogue natif de sélection de dossier de sortie.
#[tauri::command]
async fn select_output_dir(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_folder(move |path| {
        let _ = tx.send(path);
    });
    let path = rx.await.map_err(|e| e.to_string())?;
    Ok(path.map(|p| p.to_string()))
}

/// Ouvre le dialogue natif de sélection d'un fichier .py en entrée.
#[tauri::command]
async fn select_input_file(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .add_filter("Python", &["py"])
        .pick_file(move |path| {
            let _ = tx.send(path);
        });
    let path = rx.await.map_err(|e| e.to_string())?;
    Ok(path.map(|p| p.to_string()))
}

/// Ouvre le dialogue natif de sélection d'un dossier projet en entrée.
#[tauri::command]
async fn select_input_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_folder(move |path| {
        let _ = tx.send(path);
    });
    let path = rx.await.map_err(|e| e.to_string())?;
    Ok(path.map(|p| p.to_string()))
}

/// Retourne "dossier" ou "fichier" pour un chemin donné.
#[tauri::command]
fn get_path_kind(path: String) -> &'static str {
    if std::path::Path::new(&path).is_dir() {
        "dossier"
    } else {
        "fichier"
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            run_packaging,
            open_output_folder,
            select_output_dir,
            select_input_file,
            select_input_folder,
            get_path_kind,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
