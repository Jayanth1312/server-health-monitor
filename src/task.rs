use ratatui::style::Color;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Status {
    Todo,
    InProgress,
    Done,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Priority {
    UrgentImportant,      // Quadrant 1: Do First
    NotUrgentImportant,   // Quadrant 2: Schedule
    UrgentNotImportant,   // Quadrant 3: Delegate
    NotUrgentNotImportant, // Quadrant 4: Eliminate
}

impl Priority {
    pub fn display(&self) -> (&str, Color) {
        match self {
            Priority::UrgentImportant => ("🔴 Q1", Color::Red),
            Priority::NotUrgentImportant => ("🟢 Q2", Color::Green),
            Priority::UrgentNotImportant => ("🟡 Q3", Color::Yellow),
            Priority::NotUrgentNotImportant => ("⚪ Q4", Color::Gray),
        }
    }

    pub fn next(&self) -> Self {
        match self {
            Priority::UrgentImportant => Priority::NotUrgentImportant,
            Priority::NotUrgentImportant => Priority::UrgentNotImportant,
            Priority::UrgentNotImportant => Priority::NotUrgentNotImportant,
            Priority::NotUrgentNotImportant => Priority::UrgentImportant,
        }
    }


#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub title: String,
    pub status: Status,
    #[serde(default = "default_priority")]
    pub priority: Priority,
}

fn default_priority() -> Priority {
    Priority::NotUrgentImportant
}

impl Task {
    pub fn new(title: &str) -> Self {
        Task {
            title: title.to_string(),
            status: Status::Todo,
            priority: Priority::NotUrgentImportant, // Default to Q2
        }
    }

    pub fn cycle_status(&mut self) {
        self.status = match self.status {
            Status::Todo => Status::InProgress,
            Status::InProgress => Status::Done,
            Status::Done => Status::Todo,
        };
    }

    pub fn cycle_priority(&mut self) {
        self.priority = self.priority.next();
    }

    pub fn display(&self) -> (String, Color) {
        let (status_symbol, status_color) = match self.status {
            Status::Todo => ("[ ]", Color::Yellow),
            Status::InProgress => ("[>]", Color::Blue),
            Status::Done => ("[X]", Color::Green),
        };
        let (priority_symbol, _) = self.priority.display();
        (
            format!("{} {} {}", status_symbol, priority_symbol, self.title),
            status_color,
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub name: String,
    pub tasks: Vec<Task>,
}

impl Project {
    pub fn new(name: &str) -> Self {
        Project {
            name: name.to_string(),
            tasks: Vec::new(),
        }
    }

    pub fn count_completed(&self) -> usize {
        self.tasks.iter().filter(|t| t.status == Status::Done).count()
    }

    pub fn count_total(&self) -> usize {
        self.tasks.len()
    }
}
