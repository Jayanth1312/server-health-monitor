use ratatui::style::Color;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Local};

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

    pub fn description(&self) -> &str {
        match self {
            Priority::UrgentImportant => "Urgent & Important (Do First)",
            Priority::NotUrgentImportant => "Not Urgent & Important (Schedule)",
            Priority::UrgentNotImportant => "Urgent & Not Important (Delegate)",
            Priority::NotUrgentNotImportant => "Not Urgent & Not Important (Eliminate)",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub title: String,
    pub status: Status,
    #[serde(default = "default_priority")]
    pub priority: Priority,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub due_date: Option<DateTime<Local>>,
    #[serde(default)]
    pub completed_at: Option<DateTime<Local>>,
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
            description: None,
            due_date: None,
            completed_at: None,
        }
    }

    pub fn cycle_status(&mut self) {
        self.status = match self.status {
            Status::Todo => Status::InProgress,
            Status::InProgress => {
                self.completed_at = Some(Local::now());
                Status::Done
            }
            Status::Done => {
                self.completed_at = None;
                Status::Todo
            }
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

    pub fn get_due_display(&self) -> Option<(String, Color)> {
        self.due_date.as_ref().map(|due| {
            // If task is completed, show due date in white/gray
            if self.status == Status::Done {
                let text = due.format("%Y-%m-%d %H:%M").to_string();
                return (text, Color::White);
            }

            let now = Local::now();
            let diff = *due - now;

            let (text, color) = if due < &now {
                let days = -diff.num_days();
                let text = if days == 0 {
                    format!("Overdue {}", due.format("%H:%M"))
                } else if days == 1 {
                    format!("Overdue 1 day")
                } else {
                    format!("Overdue {} days", days)
                };
                (text, Color::Red)
            } else if due.date_naive() == now.date_naive() {
                (format!("Today {}", due.format("%H:%M")), Color::Yellow)
            } else if diff.num_days() == 1 {
                (format!("Tomorrow {}", due.format("%H:%M")), Color::Green)
            } else if diff.num_days() <= 7 {
                (format!("{} {}", due.format("%a"), due.format("%H:%M")), Color::Green)
            } else {
                (due.format("%Y-%m-%d %H:%M").to_string(), Color::Cyan)
            };

            (text, color)
        })
    }

    pub fn is_overdue(&self) -> bool {
        if let Some(due) = &self.due_date {
            due < &Local::now()
        } else {
            false
        }
    }

    pub fn is_due_today(&self) -> bool {
        if let Some(due) = &self.due_date {
            due.date_naive() == Local::now().date_naive()
        } else {
            false
        }
    }



    pub fn format_due_date(&self) -> Option<String> {
        self.due_date.as_ref().map(|due| {
            let now = Local::now();
            let diff = *due - now;

            if due < &now {
                let days = -diff.num_days();
                if days == 0 {
                    format!("Overdue by {} hours", -diff.num_hours())
                } else if days == 1 {
                    "Overdue by 1 day".to_string()
                } else {
                    format!("Overdue by {} days", days)
                }
            } else if due.date_naive() == now.date_naive() {
                format!("Due today at {}", due.format("%H:%M"))
            } else if diff.num_days() == 1 {
                format!("Due tomorrow at {}", due.format("%H:%M"))
            } else if diff.num_days() <= 7 {
                format!("Due {} at {}", due.format("%A"), due.format("%H:%M"))
            } else {
                due.format("Due %Y-%m-%d %H:%M").to_string()
            }
        })
    }

    pub fn was_completed_on_time(&self) -> Option<bool> {
        if self.status != Status::Done {
            return None;
        }

        match (&self.due_date, &self.completed_at) {
            (Some(due), Some(completed)) => Some(completed <= due),
            _ => None,
        }
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
