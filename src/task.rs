use ratatui::style::Color;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Status {
    Todo,
    InProgress,
    Done,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub title: String,
    pub status: Status,
}

impl Task {
    pub fn new(title: &str) -> Self {
        Task {
            title: title.to_string(),
            status: Status::Todo,
        }
    }

    pub fn cycle_status(&mut self) {
        self.status = match self.status {
            Status::Todo => Status::InProgress,
            Status::InProgress => Status::Done,
            Status::Done => Status::Todo,
        };
    }

    pub fn display(&self) -> (String, Color) {
        let (status_symbol, color) = match self.status {
            Status::Todo => ("[ ]", Color::Yellow),
            Status::InProgress => ("[>]", Color::Blue),
            Status::Done => ("[X]", Color::Green),
        };
        (format!("{} {}", status_symbol, self.title), color)
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
