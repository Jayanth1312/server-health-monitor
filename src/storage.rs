use crate::task::Project;
use std::fs;
use std::io;
use std::path::PathBuf;

pub struct Storage {
    file_path: PathBuf,
}

impl Storage {
    pub fn new() -> io::Result<Self> {
        let file_path = Self::get_storage_path()?;

        // Create parent directories if they don't exist
        if let Some(parent) = file_path.parent() {
            fs::create_dir_all(parent)?;
        }

        Ok(Storage { file_path })
    }

    fn get_storage_path() -> io::Result<PathBuf> {
        // Get user's home directory
        let home_dir = dirs::home_dir()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "Could not find home directory"))?;

        // Store in ~/.config/dev-todo/projects.json on Unix or %APPDATA%\dev-todo\projects.json on Windows
        #[cfg(target_os = "windows")]
        let config_dir = home_dir.join("AppData").join("Roaming").join("dev-todo");

        #[cfg(not(target_os = "windows"))]
        let config_dir = home_dir.join(".config").join("dev-todo");

        Ok(config_dir.join("projects.json"))
    }

    pub fn save(&self, projects: &[Project]) -> io::Result<()> {
        let json = serde_json::to_string_pretty(projects)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        fs::write(&self.file_path, json)?;
        Ok(())
    }

    pub fn load(&self) -> io::Result<Vec<Project>> {
        // If file doesn't exist, return empty vec
        if !self.file_path.exists() {
            return Ok(Vec::new());
        }

        let content = fs::read_to_string(&self.file_path)?;

        // If file is empty, return empty vec
        if content.trim().is_empty() {
            return Ok(Vec::new());
        }

        let projects = serde_json::from_str(&content)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        Ok(projects)
    }

    pub fn get_storage_location(&self) -> &PathBuf {
        &self.file_path
    }
}
