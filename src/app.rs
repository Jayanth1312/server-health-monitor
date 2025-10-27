use crate::calendar::Calendar;
use crate::storage::Storage;
use crate::task::{Project, Status, Task};
use chrono::{Local, NaiveTime};
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
    SettingTime,
}

#[derive(PartialEq, Clone)]
pub enum ViewMode {
    ProjectList,
    TaskList,
    ViewingTask,
    Searching,
    SettingDueDate,
}

pub struct App {
    pub projects: Vec<Project>,
    pub selected_project: usize,
    pub selected_task: usize,
    pub input_mode: InputMode,
    pub view_mode: ViewMode,
    pub previous_view_mode: ViewMode,
    pub input_buffer: String,
    pub temp_task_title: String,
    pub search_query: String,
    pub search_results: Vec<(usize, usize)>,
    pub selected_search_result: usize,
    pub search_focus_on_input: bool,
    pub calendar: Calendar,
    pub time_input: String,
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
            previous_view_mode: ViewMode::TaskList,
            input_buffer: String::new(),
            temp_task_title: String::new(),
            search_query: String::new(),
            search_results: Vec::new(),
            selected_search_result: 0,
            search_focus_on_input: true,
            calendar: Calendar::new(),
            time_input: String::new(),
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
                self.previous_view_mode = self.view_mode.clone();
                self.view_mode = ViewMode::ViewingTask;
            }
        }
    }

    pub fn exit_task_view(&mut self) {
        self.view_mode = self.previous_view_mode.clone();
    }

    pub fn enter_search_mode(&mut self) {
        self.view_mode = ViewMode::Searching;
        self.search_query.clear();
        self.search_results.clear();
        self.selected_search_result = 0;
        self.search_focus_on_input = true;
    }

    pub fn exit_search_mode(&mut self) {
        self.view_mode = ViewMode::TaskList;
        self.search_query.clear();
        self.search_results.clear();
        self.selected_search_result = 0;
        self.search_focus_on_input = true;
    }

    pub fn toggle_search_focus(&mut self) {
        self.search_focus_on_input = !self.search_focus_on_input;
    }

    pub fn update_search(&mut self) {
        use fuzzy_matcher::FuzzyMatcher;
        use fuzzy_matcher::skim::SkimMatcherV2;

        self.search_results.clear();

        if self.search_query.trim().is_empty() {
            return;
        }

        let matcher = SkimMatcherV2::default();
        let query = self.search_query.trim();

        let mut scored_results: Vec<(usize, usize, i64)> = Vec::new();

        for (proj_idx, project) in self.projects.iter().enumerate() {
            for (task_idx, task) in project.tasks.iter().enumerate() {
                // Search in title
                if let Some(score) = matcher.fuzzy_match(&task.title, query) {
                    scored_results.push((proj_idx, task_idx, score));
                } else if let Some(desc) = &task.description {
                    // Search in description
                    if let Some(score) = matcher.fuzzy_match(desc, query) {
                        scored_results.push((proj_idx, task_idx, score / 2)); // Lower score for description matches
                    }
                }
            }
        }

        // Sort by score (highest first)
        scored_results.sort_by(|a, b| b.2.cmp(&a.2));

        self.search_results = scored_results
            .into_iter()
            .map(|(proj_idx, task_idx, _)| (proj_idx, task_idx))
            .collect();

        self.selected_search_result = 0;
    }

    pub fn search_input(&mut self, c: char) {
        self.search_query.push(c);
        self.update_search();
    }

    pub fn search_backspace(&mut self) {
        self.search_query.pop();
        self.update_search();
    }

    pub fn next_search_result(&mut self) {
        if !self.search_results.is_empty() {
            self.selected_search_result = (self.selected_search_result + 1) % self.search_results.len();
        }
    }

    pub fn previous_search_result(&mut self) {
        if !self.search_results.is_empty() {
            if self.selected_search_result == 0 {
                self.selected_search_result = self.search_results.len() - 1;
            } else {
                self.selected_search_result -= 1;
            }
        }
    }



    pub fn cycle_search_task_status(&mut self) {
        if let Some(&(proj_idx, task_idx)) = self.search_results.get(self.selected_search_result) {
            if let Some(project) = self.projects.get_mut(proj_idx) {
                if let Some(task) = project.tasks.get_mut(task_idx) {
                    task.cycle_status();
                    let _ = self.save();
                }
            }
        }
    }

    pub fn cycle_search_task_priority(&mut self) {
        if let Some(&(proj_idx, task_idx)) = self.search_results.get(self.selected_search_result) {
            if let Some(project) = self.projects.get_mut(proj_idx) {
                if let Some(task) = project.tasks.get_mut(task_idx) {
                    task.cycle_priority();
                    let _ = self.save();
                }
            }
        }
    }

    pub fn delete_search_task(&mut self) {
        if let Some(&(proj_idx, task_idx)) = self.search_results.get(self.selected_search_result) {
            if let Some(project) = self.projects.get_mut(proj_idx) {
                if task_idx < project.tasks.len() {
                    project.tasks.remove(task_idx);
                    let _ = self.save();
                    // Update search results
                    self.update_search();
                    if self.selected_search_result >= self.search_results.len() && !self.search_results.is_empty() {
                        self.selected_search_result = self.search_results.len() - 1;
                    }
                }
            }
        }
    }

    pub fn view_search_task_details(&mut self) {
        if let Some(&(proj_idx, task_idx)) = self.search_results.get(self.selected_search_result) {
            self.selected_project = proj_idx;
            self.selected_task = task_idx;
            self.previous_view_mode = ViewMode::Searching;
            self.view_mode = ViewMode::ViewingTask;
        }
    }

    // Due date operations
    pub fn start_setting_due_date(&mut self) {
        self.previous_view_mode = self.view_mode.clone();
        self.view_mode = ViewMode::SettingDueDate;
        self.calendar = Calendar::new();
        self.time_input.clear();
    }

    pub fn cancel_due_date_setting(&mut self) {
        self.view_mode = self.previous_view_mode.clone();
        self.time_input.clear();
    }

    pub fn confirm_due_date(&mut self) {
        // Parse time (HH:MM format)
        let time = if self.time_input.trim().is_empty() {
            NaiveTime::from_hms_opt(23, 59, 0).unwrap()
        } else {
            let parts: Vec<&str> = self.time_input.trim().split(':').collect();
            if parts.len() == 2 {
                let hour = parts[0].parse::<u32>().unwrap_or(23);
                let minute = parts[1].parse::<u32>().unwrap_or(59);
                NaiveTime::from_hms_opt(hour, minute, 0).unwrap_or_else(|| NaiveTime::from_hms_opt(23, 59, 0).unwrap())
            } else {
                NaiveTime::from_hms_opt(23, 59, 0).unwrap()
            }
        };

        let due_datetime = self.calendar.selected_date.and_time(time).and_local_timezone(Local).unwrap();

        // Set due date based on previous view mode
        match self.previous_view_mode {
            ViewMode::TaskList => {
                if let Some(project) = self.projects.get_mut(self.selected_project) {
                    if let Some(task) = project.tasks.get_mut(self.selected_task) {
                        task.due_date = Some(due_datetime);
                        let _ = self.save();
                    }
                }
            }
            ViewMode::Searching => {
                if let Some(&(proj_idx, task_idx)) = self.search_results.get(self.selected_search_result) {
                    if let Some(project) = self.projects.get_mut(proj_idx) {
                        if let Some(task) = project.tasks.get_mut(task_idx) {
                            task.due_date = Some(due_datetime);
                            let _ = self.save();
                        }
                    }
                }
            }
            _ => {}
        }

        self.view_mode = self.previous_view_mode.clone();
        self.time_input.clear();
    }

    pub fn clear_due_date(&mut self) {
        if let Some(project) = self.projects.get_mut(self.selected_project) {
            if let Some(task) = project.tasks.get_mut(self.selected_task) {
                task.due_date = None;
                let _ = self.save();
            }
        }
    }

    pub fn get_upcoming_tasks(&self) -> Vec<(usize, usize, &Task)> {
        let mut upcoming = Vec::new();

        for (proj_idx, project) in self.projects.iter().enumerate() {
            for (task_idx, task) in project.tasks.iter().enumerate() {
                if task.due_date.is_some() && task.status != Status::Done {
                    upcoming.push((proj_idx, task_idx, task));
                }
            }
        }

        // Sort by due date
        upcoming.sort_by(|a, b| {
            match (&a.2.due_date, &b.2.due_date) {
                (Some(a_due), Some(b_due)) => a_due.cmp(b_due),
                (Some(_), None) => std::cmp::Ordering::Less,
                (None, Some(_)) => std::cmp::Ordering::Greater,
                (None, None) => std::cmp::Ordering::Equal,
            }
        });

        upcoming
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
                // Record completion time when marking as done
                if status == Status::Done && task.status != Status::Done {
                    task.completed_at = Some(Local::now());
                } else if status != Status::Done {
                    task.completed_at = None;
                }
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
            InputMode::SettingTime => {
                // Handled separately in handle_time_input_mode
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
