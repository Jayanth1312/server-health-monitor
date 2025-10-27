use crate::app::{App, InputMode, ViewMode};
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap},
    Frame,
};

const SELECTOR_ARROW: &str = "> ";

pub fn render(f: &mut Frame, app: &App) {
    match app.view_mode {
        ViewMode::ProjectList => render_project_view(f, app),
        ViewMode::TaskList => render_task_view(f, app),
        ViewMode::ViewingTask => render_task_detail_view(f, app),
        ViewMode::Searching => render_search_view(f, app),
        ViewMode::SettingDueDate => {
            if app.input_mode == crate::app::InputMode::SettingTime {
                render_time_input_view(f, app);
            } else {
                render_calendar_view(f, app);
            }
        }
    }
}

fn render_project_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Title
            Constraint::Min(5),     // Project list (reduced)
            Constraint::Length(7),  // Upcoming tasks
            Constraint::Length(3),  // Input area
            Constraint::Length(8),  // Help section (increased)
        ])
        .split(size);

    render_project_title(f, chunks[0], app);
    render_project_list(f, chunks[1], app);
    render_upcoming_tasks(f, chunks[2], app);
    render_input(f, chunks[3], app);
    render_project_help(f, chunks[4]);
}

fn render_task_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Title
            Constraint::Min(5),     // Task list (reduced)
            Constraint::Length(3),  // Input area
            Constraint::Length(10), // Help section (increased)
        ])
        .split(size);

    render_task_title(f, chunks[0], app);
    render_task_list(f, chunks[1], app);
    render_input(f, chunks[2], app);
    render_task_help(f, chunks[3]);
}

fn render_task_detail_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Title
            Constraint::Min(5),     // Task details
            Constraint::Length(3),  // Help
        ])
        .split(size);

    render_task_title(f, chunks[0], app);
    render_task_details(f, chunks[1], app);
    render_viewing_help(f, chunks[2]);
}

fn render_project_title(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let title_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .style(Style::default().bg(Color::Black));

    let title = Paragraph::new(Line::from(vec![
        Span::styled(
            "📁",
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(" "),
        Span::styled(
            "Projects",
            Style::default()
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(" "),
        Span::styled(
            format!("({} projects)", app.projects.len()),
            Style::default().fg(Color::DarkGray),
        ),
    ]))
    .alignment(Alignment::Center)
    .block(title_block);

    f.render_widget(title, area);
}

fn render_task_title(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let title_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .style(Style::default().bg(Color::Black));

    let project_name = app.get_current_project().map(|p| p.name.as_str()).unwrap_or("Unknown");
    let (total, completed) = app.get_current_project()
        .map(|p| (p.count_total(), p.count_completed()))
        .unwrap_or((0, 0));

    let title = Paragraph::new(Line::from(vec![
        Span::styled(
            project_name,
            Style::default()
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(" "),
        Span::styled(
            format!("({}/{})", completed, total),
            Style::default().fg(Color::DarkGray),
        ),
    ]))
    .alignment(Alignment::Center)
    .block(title_block);

    f.render_widget(title, area);
}

fn render_project_list(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let items: Vec<ListItem> = app
        .projects
        .iter()
        .map(|p| {
            let task_count = format!("({}/{})", p.count_completed(), p.count_total());
            let display = format!("📁 {}  {}", p.name, task_count);
            ListItem::new(display).style(Style::default().fg(Color::Cyan))
        })
        .collect();

    let mut state = ListState::default();
    if !app.projects.is_empty() {
        state.select(Some(app.selected_project));
    }

    let list = List::new(items)
        .block(
            Block::default()
                .title(" Projects (Press Enter to open) ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::White)),
        )
        .highlight_style(
            Style::default()
                .bg(Color::DarkGray)
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol(SELECTOR_ARROW);

    f.render_stateful_widget(list, area, &mut state);
}

fn render_task_list(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let items: Vec<ListItem> = if let Some(project) = app.get_current_project() {
        project
            .tasks
            .iter()
            .map(|t| {
                let (display, color) = t.display();

                // Create line with due date on the right if present
                let line = if let Some((due_text, due_color)) = t.get_due_display() {
                    // Calculate padding to push due date to the right
                    let display_len = display.chars().count();
                    let due_len = due_text.chars().count();
                    let available_width = area.width.saturating_sub(4) as usize; // Account for borders and selector
                    let padding = if display_len + due_len + 5 < available_width {
                        available_width.saturating_sub(display_len + due_len + 2)
                    } else {
                        2
                    };

                    Line::from(vec![
                        Span::styled(display, Style::default().fg(color)),
                        Span::raw(" ".repeat(padding)),
                        Span::styled(due_text, Style::default().fg(due_color)),
                    ])
                } else {
                    Line::from(Span::styled(display, Style::default().fg(color)))
                };

                ListItem::new(line)
            })
            .collect()
    } else {
        Vec::new()
    };

    let mut state = ListState::default();
    if let Some(project) = app.get_current_project() {
        if !project.tasks.is_empty() {
            state.select(Some(app.selected_task));
        }
    }

    let list = List::new(items)
        .block(
            Block::default()
                .title(" Tasks (Press Backspace/b/h to go back) ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::White)),
        )
        .highlight_style(
            Style::default()
                .bg(Color::DarkGray)
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol(SELECTOR_ARROW);

    f.render_stateful_widget(list, area, &mut state);
}

fn render_task_details(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let content = if let Some(task) = app.get_current_task() {
        let (status_symbol, status_color) = match task.status {
            crate::task::Status::Todo => ("[ ] Todo", Color::Yellow),
            crate::task::Status::InProgress => ("[>] In Progress", Color::Blue),
            crate::task::Status::Done => ("[X] Completed", Color::Green),
        };
        let (priority_symbol, priority_color) = task.priority.display();

        let mut lines = vec![
            Line::from(vec![
                Span::styled("Title: ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(&task.title, Style::default().fg(Color::White)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("Status: ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(status_symbol, Style::default().fg(status_color)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("Priority: ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(priority_symbol, Style::default().fg(priority_color)),
                Span::raw(" - "),
                Span::styled(task.priority.description(), Style::default().fg(Color::DarkGray)),
            ]),
            Line::from(""),
        ];

        // Add due date if present
        if let Some((due_text, due_color)) = task.get_due_display() {
            lines.push(Line::from(vec![
                Span::styled("Due Date: ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(due_text, Style::default().fg(due_color)),
            ]));
            lines.push(Line::from(""));
        }

        // Add completion time if task is done
        if task.status == crate::task::Status::Done {
            if let Some(completed_at) = &task.completed_at {
                let mut completion_spans = vec![
                    Span::styled("Completed: ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                    Span::styled(completed_at.format("%Y-%m-%d %H:%M").to_string(), Style::default().fg(Color::Green)),
                ];

                // Add on-time/late indicator
                if let Some(on_time) = task.was_completed_on_time() {
                    completion_spans.push(Span::raw("  "));
                    if on_time {
                        completion_spans.push(Span::styled("✓ On Time", Style::default().fg(Color::Green)));
                    } else {
                        completion_spans.push(Span::styled("⚠ Late", Style::default().fg(Color::Red)));
                    }
                }

                lines.push(Line::from(completion_spans));
                lines.push(Line::from(""));
            }
        }

        // Add description
        lines.push(Line::from(vec![
            Span::styled("Description:", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        ]));
        lines.push(Line::from(
            task.description
                .as_ref()
                .map(|d| d.as_str())
                .unwrap_or("No description")
        ));

        lines
    } else {
        vec![Line::from("No task selected")]
    };

    let details = Paragraph::new(content)
        .style(Style::default().fg(Color::White))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan))
                .title(" Task Details "),
        )
        .wrap(Wrap { trim: false });

    f.render_widget(details, area);
}

fn render_calendar_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(12),    // Calendar
            Constraint::Length(5),  // Help
        ])
        .split(size);

    app.calendar.render(f, chunks[0]);
    render_calendar_help(f, chunks[1]);
}

fn render_time_input_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Date display
            Constraint::Length(3),  // Time input
            Constraint::Length(5),  // Help
        ])
        .split(size);

    // Show selected date
    let date_display = Paragraph::new(Line::from(vec![
        Span::styled(
            "Selected Date: ",
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            app.calendar.selected_date.format("%Y-%m-%d").to_string(),
            Style::default().fg(Color::White),
        ),
    ]))
    .alignment(Alignment::Center)
    .block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan)),
    );
    f.render_widget(date_display, chunks[0]);

    // Time input
    let time_input = Paragraph::new(app.time_input.as_str())
        .style(Style::default().fg(Color::White))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Yellow))
                .title(" Enter Time (HH:MM, or press Enter for 23:59) "),
        );
    f.render_widget(time_input, chunks[1]);

    // Help
    let help_text = vec![
        Line::from(vec![
            Span::styled("Enter", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
            Span::raw(" to save "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled("Esc", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)),
            Span::raw(" to cancel"),
        ]),
        Line::from(vec![
            Span::styled("Format: ", Style::default().fg(Color::Cyan)),
            Span::raw("HH:MM (e.g., 14:30)"),
        ]),
    ];
    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Help ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        );
    f.render_widget(help, chunks[2]);
}

fn render_calendar_help(f: &mut Frame, area: ratatui::layout::Rect) {
    let help_text = vec![
        Line::from(vec![
            Span::styled(
                "Navigate: ",
                Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
            ),
            Span::raw("←→↑↓ or hjkl "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Month: ",
                Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
            ),
            Span::raw("n (next) p (previous)"),
        ]),
        Line::from(vec![
            Span::styled(
                "Select: ",
                Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
            ),
            Span::raw("Enter "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Cancel: ",
                Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
            ),
            Span::raw("Esc "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Quit: ",
                Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
            ),
            Span::raw("q"),
        ]),
    ];

    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Calendar Controls ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        );

    f.render_widget(help, area);
}

fn render_upcoming_tasks(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let upcoming = app.get_upcoming_tasks();

    let items: Vec<ListItem> = upcoming
        .iter()
        .take(5)  // Show only first 5 upcoming tasks
        .map(|(proj_idx, _, task)| {
            let project = &app.projects[*proj_idx];
            let due_text = task.format_due_date().unwrap_or_else(|| "No date".to_string());

            let color = if task.is_overdue() {
                Color::Red
            } else if task.is_due_today() {
                Color::Yellow
            } else {
                Color::Green
            };

            let display = format!("{} - {} [{}]", due_text, task.title, project.name);
            ListItem::new(display).style(Style::default().fg(color))
        })
        .collect();

    let list = List::new(items)
        .block(
            Block::default()
                .title(format!(" 📅 Upcoming Tasks ({}) ", upcoming.len()))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan)),
        );

    f.render_widget(list, area);
}

fn render_search_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Search input
            Constraint::Min(5),     // Search results (reduced)
            Constraint::Length(7),  // Help (increased)
        ])
        .split(size);

    render_search_input(f, chunks[0], app);
    render_search_results(f, chunks[1], app);
    render_search_help(f, chunks[2]);
}

fn render_search_input(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let (border_color, title) = if app.search_focus_on_input {
        (Color::Yellow, format!(" 🔍 Search Tasks ({} results) [TYPING - Press Tab to navigate] ", app.search_results.len()))
    } else {
        (Color::DarkGray, format!(" 🔍 Search Tasks ({} results) [Press Tab to type] ", app.search_results.len()))
    };

    let search_input = Paragraph::new(app.search_query.as_str())
        .style(Style::default().fg(Color::White))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(border_color))
                .title(title),
        );

    f.render_widget(search_input, area);
}

fn render_search_results(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let items: Vec<ListItem> = app
        .search_results
        .iter()
        .map(|&(proj_idx, task_idx)| {
            if let Some(project) = app.projects.get(proj_idx) {
                if let Some(task) = project.tasks.get(task_idx) {
                    let (display, color) = task.display();
                    let project_tag = format!(" [{}]", project.name);

                    // Create line with due date on the right if present
                    let line = if let Some((due_text, due_color)) = task.get_due_display() {
                        let full_display = format!("{}{}", display, project_tag);
                        let display_len = full_display.chars().count();
                        let due_len = due_text.chars().count();
                        let available_width = area.width.saturating_sub(4) as usize;
                        let padding = if display_len + due_len + 5 < available_width {
                            available_width.saturating_sub(display_len + due_len + 2)
                        } else {
                            2
                        };

                        Line::from(vec![
                            Span::styled(full_display, Style::default().fg(color)),
                            Span::raw(" ".repeat(padding)),
                            Span::styled(due_text, Style::default().fg(due_color)),
                        ])
                    } else {
                        Line::from(Span::styled(format!("{}{}", display, project_tag), Style::default().fg(color)))
                    };

                    return ListItem::new(line);
                }
            }
            ListItem::new("Error loading task").style(Style::default().fg(Color::Red))
        })
        .collect();

    let mut state = ListState::default();
    if !app.search_results.is_empty() {
        state.select(Some(app.selected_search_result));
    }

    let (border_color, title) = if !app.search_focus_on_input {
        (Color::Yellow, " Search Results [NAVIGATING - j/k/Enter/p/t/d] ")
    } else {
        (Color::White, " Search Results (Press Tab or Enter to navigate) ")
    };

    let list = List::new(items)
        .block(
            Block::default()
                .title(title)
                .borders(Borders::ALL)
                .border_style(Style::default().fg(border_color)),
        )
        .highlight_style(
            Style::default()
                .bg(Color::DarkGray)
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol(SELECTOR_ARROW);

    f.render_stateful_widget(list, area, &mut state);
}

fn render_search_help(f: &mut Frame, area: ratatui::layout::Rect) {
    let help_text = vec![
        Line::from(vec![
            Span::styled(
                "Tab: ",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("Toggle typing/navigation "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Esc: ",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("Clear search or go back "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Enter: ",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("View details"),
        ]),
        Line::from(vec![
            Span::styled(
                "While navigating: ",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("j/k (move) Space/c (status) p (priority) t (due date) d (delete) q (quit)"),
        ]),
    ];

    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Help ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        )
        .wrap(Wrap { trim: true });

    f.render_widget(help, area);
}

fn render_input(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let input_title = match app.input_mode {
        InputMode::AddingTask => " Enter Task Title (Enter to continue, Esc to cancel) ",
        InputMode::AddingTaskDescription => " Enter Task Description (Enter to save, Esc to skip) ",
        InputMode::EditingTask => " Edit Task Title (Enter to continue, Esc to cancel) ",
        InputMode::EditingTaskDescription => " Edit Task Description (Enter to save, Esc to cancel, empty to clear) ",
        InputMode::AddingProject => " Add New Project (Enter to save, Esc to cancel) ",
        InputMode::RenamingProject => " Rename Project (Enter to save, Esc to cancel) ",
        InputMode::SettingTime => " Enter Time (HH:MM format, Enter to save, Esc to cancel) ",
        InputMode::Normal => " Input ",
    };

    let input_color = match app.input_mode {
        InputMode::Normal => Color::DarkGray,
        _ => Color::Yellow,
    };

    let input = Paragraph::new(app.input_buffer.as_str())
        .style(Style::default().fg(Color::White))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(input_color))
                .title(input_title),
        );

    f.render_widget(input, area);
}

fn render_project_help(f: &mut Frame, area: ratatui::layout::Rect) {
    let help_text = vec![
        Line::from(vec![
            Span::styled(
                "Navigation: ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("↑/↓ or j/k "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Open: ",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("Enter"),
        ]),
        Line::from(vec![
            Span::styled(
                "New Project: ",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("n "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Rename: ",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("r "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Delete: ",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("d "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Search: ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("s"),
        ]),
        Line::from(vec![
            Span::styled(
                "Quit: ",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("q or Esc"),
        ]),
    ];

    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Help ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        )
        .wrap(Wrap { trim: true });

    f.render_widget(help, area);
}

fn render_task_help(f: &mut Frame, area: ratatui::layout::Rect) {
    let help_text = vec![
        Line::from(vec![
            Span::styled(
                "Navigation: ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("↑/↓ or j/k "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "View: ",
                Style::default()
                    .fg(Color::Magenta)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("Enter "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Back: ",
                Style::default()
                    .fg(Color::Magenta)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("Backspace/b/h"),
        ]),
        Line::from(vec![
            Span::styled(
                "Add: ",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("a "),
            Span::styled(
                "Edit: ",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("e "),
            Span::styled(
                "Delete: ",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("d "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Search: ",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("s "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Due: ",
                Style::default()
                    .fg(Color::Magenta)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("t (set) x (clear)"),
        ]),
        Line::from(vec![
            Span::styled(
                "Priority: ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled("p", Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::styled(
                "Status: ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("Space/c "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled("1", Style::default().fg(Color::Yellow)),
            Span::raw(" Todo "),
            Span::styled("2", Style::default().fg(Color::Blue)),
            Span::raw(" InProgress "),
            Span::styled("3", Style::default().fg(Color::Green)),
            Span::raw(" Done "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "Priority: ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled("p", Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::styled("🔴 Q1", Style::default().fg(Color::Red)),
            Span::raw(" Urgent & Important (Do First) "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled("🟢 Q2", Style::default().fg(Color::Green)),
            Span::raw(" Not Urgent & Important (Schedule)"),
        ]),
        Line::from(vec![
            Span::styled("🟡 Q3", Style::default().fg(Color::Yellow)),
            Span::raw(" Urgent & Not Important (Delegate) "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled("⚪ Q4", Style::default().fg(Color::Gray)),
            Span::raw(" Not Urgent & Not Important (Eliminate)"),
        ]),
        Line::from(vec![
            Span::styled(
                "Quit: ",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("q or Esc"),
        ]),
    ];

    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Help ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        )
        .wrap(Wrap { trim: true });

    f.render_widget(help, area);
}

fn render_viewing_help(f: &mut Frame, area: ratatui::layout::Rect) {
    let help_text = vec![
        Line::from(vec![
            Span::styled(
                "Press ",
                Style::default().fg(Color::White),
            ),
            Span::styled(
                "Enter",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(", "),
            Span::styled(
                "Backspace",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(", or "),
            Span::styled(
                "h",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(" to go back "),
            Span::styled("│ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "q",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(" or "),
            Span::styled(
                "Esc",
                Style::default()
                    .fg(Color::Red)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(" to quit"),
        ]),
    ];

    let help = Paragraph::new(help_text)
        .block(
            Block::default()
                .title(" Help ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        )
        .wrap(Wrap { trim: true });

    f.render_widget(help, area);
}
