use crate::task::{Project, Status, Task};
use crate::storage::Storage;
use std::io;

#[derive(PartialEq)]
pub enum InputMode {
    Normal,
    AddingTask,
    AddingTaskDescription,
    EditingTask,
    EditingTaskDescription,
    AddingProject,
    RenamingProject,
}

#[derive(PartialEq)]
pub enum ViewMode {
    ProjectList,
    TaskList,
    ViewingTask,
}

pub struct App {
    pub projects: Vec<Project>,
    pub selected_project: usize,
    pub selected_task: usize,
    pub input_mode: InputMode,
    pub view_mode: ViewMode,
    pub input_buffer: String,
    pub temp_task_title: String,
    storage: Storage,
}

impl App {
    pub fn new() -> io::Result<Self> {
        let storage = Storage::new()?;
        let mut projects = storage.load().unwrap_or_else(|_| Vec::new());

        // If no projects exist, create a default one
        if projects.is_empty() {
            let mut default_project = Project::new("Getting Started");
            default_project.tasks.push(Task::new("Press 'n' to create a new project"));
            default_project.tasks.push(Task::new("Press 'Enter' to view project tasks"));
            default_project.tasks.push(Task::new("Press 'a' to add tasks to a project"));
            projects.push(default_project);
        }

        Ok(App {
            projects,
            selected_project: 0,
            selected_task: 0,
            input_mode: InputMode::Normal,
            view_mode: ViewMode::ProjectList,
            input_buffer: String::new(),
            temp_task_title: String::new(),
            storage,
        })
    }

    // Project navigation
    pub fn next_project(&mut self) {
        if !self.projects.is_empty() {
            self.selected_project = (self.selected_project + 1) % self.projects.len();
        }
    }

    pub fn previous_project(&mut self) {
        if !self.projects.is_empty() {
            if self.selected_project == 0 {
                self.selected_project = self.projects.len() - 1;
            } else {
                self.selected_project -= 1;
            }
        }
    }

    // Task navigation
    pub fn next_task(&mut self) {
        if let Some(project) = self.projects.get(self.selected_project) {
            if !project.tasks.is_empty() {
                self.selected_task = (self.selected_task + 1) % project.tasks.len();
            }
        }
    }

    pub fn previous_task(&mut self) {
        if let Some(project) = self.projects.get(self.selected_project) {
            if !project.tasks.is_empty() {
                if self.selected_task == 0 {
                    self.selected_task = project.tasks.len() - 1;
                } else {
                    self.selected_task -= 1;
                }
            }
        }
    }

    // View mode
    pub fn enter_project(&mut self) {
        self.view_mode = ViewMode::TaskList;
        self.selected_task = 0;
    }

    pub fn exit_to_projects(&mut self) {
        self.view_mode = ViewMode::ProjectList;
    }

    pub fn enter_task_view(&mut self) {
        if let Some(project) = self.projects.get(self.selected_project) {
            if !project.tasks.is_empty() {
                self.view_mode = ViewMode::ViewingTask;
            }
        }
    }

    pub fn exit_task_view(&mut self) {
        self.view_mode = ViewMode::TaskList;
    }

    // Task operations
    pub fn cycle_status(&mut self) {
        if let Some(project) = self.projects.get_mut(self.selected_project) {
            if let Some(task) = project.tasks.get_mut(self.selected_task) {
                task.cycle_status();
                let _ = self.save();
            }
        }
    }

    pub fn cycle_priority(&mut self) {
        if let Some(project) = self.projects.get_mut(self.selected_project) {
            if let Some(task) = project.tasks.get_mut(self.selected_task) {
                task.cycle_priority();
                let _ = self.save();
            }
        }
    }

    pub fn set_status(&mut self, status: Status) {
        if let Some(project) = self.projects.get_mut(self.selected_project) {
            if let Some(task) = project.tasks.get_mut(self.selected_task) {
                task.status = status;
                let _ = self.save();
            }
        }
    }

    pub fn delete_task(&mut self) {
        if let Some(project) = self.projects.get_mut(self.selected_project) {
            if !project.tasks.is_empty() {
                project.tasks.remove(self.selected_task);
                if self.selected_task >= project.tasks.len() && !project.tasks.is_empty() {
                    self.selected_task = project.tasks.len() - 1;
                }
                let _ = self.save();
            }
        }
    }

    pub fn delete_project(&mut self) {
        if !self.projects.is_empty() {
            self.projects.remove(self.selected_project);
            if self.selected_project >= self.projects.len() && !self.projects.is_empty() {
                self.selected_project = self.projects.len() - 1;
            }
            let _ = self.save();
        }
    }

    // Input operations
    pub fn start_adding_task(&mut self) {
        self.input_mode = InputMode::AddingTask;
        self.input_buffer.clear();
    }

    pub fn start_editing_task(&mut self) {
        if let Some(project) = self.projects.get(self.selected_project) {
            if let Some(task) = project.tasks.get(self.selected_task) {
                self.input_mode = InputMode::EditingTask;
                self.input_buffer = task.title.clone();
            }
        }
    }

    pub fn start_adding_project(&mut self) {
        self.input_mode = InputMode::AddingProject;
        self.input_buffer.clear();
    }

    pub fn start_renaming_project(&mut self) {
        if let Some(project) = self.projects.get(self.selected_project) {
            self.input_mode = InputMode::RenamingProject;
            self.input_buffer = project.name.clone();
        }
    }



    pub fn finish_input(&mut self) {
        match self.input_mode {
            InputMode::AddingTask => {
                if !self.input_buffer.trim().is_empty() {
                    // Save title and transition to description input
                    self.temp_task_title = self.input_buffer.trim().to_string();
                    self.input_buffer.clear();
                    self.input_mode = InputMode::AddingTaskDescription;
                    return;
                }
            }
            InputMode::AddingTaskDescription => {
                // Create task with title and description
                if let Some(project) = self.projects.get_mut(self.selected_project) {
                    let mut task = Task::new(&self.temp_task_title);
                    if !self.input_buffer.trim().is_empty() {
                        task.description = Some(self.input_buffer.trim().to_string());
                    }
                    project.tasks.push(task);
                    self.selected_task = project.tasks.len() - 1;
                }
                self.temp_task_title.clear();
            }
            InputMode::EditingTask => {
                if !self.input_buffer.trim().is_empty() {
                    // Save title and transition to description editing
                    self.temp_task_title = self.input_buffer.trim().to_string();
                    if let Some(project) = self.projects.get(self.selected_project) {
                        if let Some(task) = project.tasks.get(self.selected_task) {
                            self.input_buffer = task.description.clone().unwrap_or_default();
                            self.input_mode = InputMode::EditingTaskDescription;
                            return;
                        }
                    }
                }
            }
            InputMode::EditingTaskDescription => {
                // Save both title and description
                if let Some(project) = self.projects.get_mut(self.selected_project) {
                    if let Some(task) = project.tasks.get_mut(self.selected_task) {
                        task.title = self.temp_task_title.clone();
                        if self.input_buffer.trim().is_empty() {
                            task.description = None;
                        } else {
                            task.description = Some(self.input_buffer.trim().to_string());
                        }
                    }
                }
                self.temp_task_title.clear();
            }
            InputMode::AddingProject => {
                if !self.input_buffer.trim().is_empty() {
                    self.projects.push(Project::new(self.input_buffer.trim()));
                    self.selected_project = self.projects.len() - 1;
                }
            }
            InputMode::RenamingProject => {
                if !self.input_buffer.trim().is_empty() {
                    if let Some(project) = self.projects.get_mut(self.selected_project) {
                        project.name = self.input_buffer.trim().to_string();
                    }
                }
            }
            InputMode::Normal => {}
        }
        if self.input_mode != InputMode::Normal {
            let _ = self.save();
        }
        self.input_buffer.clear();
        self.temp_task_title.clear();
        self.input_mode = InputMode::Normal;
    }

    pub fn cancel_input(&mut self) {
        self.input_buffer.clear();
        self.temp_task_title.clear();
        self.input_mode = InputMode::Normal;
    }

    pub fn get_current_project(&self) -> Option<&Project> {
        self.projects.get(self.selected_project)
    }

    pub fn get_current_task(&self) -> Option<&Task> {
        self.projects
            .get(self.selected_project)
            .and_then(|p| p.tasks.get(self.selected_task))
    }

    fn save(&self) -> io::Result<()> {
        self.storage.save(&self.projects)
    }

    pub fn get_storage_location(&self) -> String {
        self.storage.get_storage_location().display().to_string()
    }
}
