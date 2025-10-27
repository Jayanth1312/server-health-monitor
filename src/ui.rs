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
    }
}

fn render_project_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Title
            Constraint::Min(10),    // Project list
            Constraint::Length(3),  // Input area
            Constraint::Length(6),  // Help section
        ])
        .split(size);

    render_project_title(f, chunks[0], app);
    render_project_list(f, chunks[1], app);
    render_input(f, chunks[2], app);
    render_project_help(f, chunks[3]);
}

fn render_task_view(f: &mut Frame, app: &App) {
    let size = f.size();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Title
            Constraint::Min(10),    // Task list
            Constraint::Length(3),  // Input area
            Constraint::Length(7),  // Help section
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
                ListItem::new(display).style(Style::default().fg(color))
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

        vec![
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
            Line::from(vec![
                Span::styled("Description:", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            ]),
            Line::from(
                task.description
                    .as_ref()
                    .map(|d| d.as_str())
                    .unwrap_or("No description")
            ),
        ]
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

fn render_input(f: &mut Frame, area: ratatui::layout::Rect, app: &App) {
    let input_title = match app.input_mode {
        InputMode::AddingTask => " Enter Task Title (Enter to continue, Esc to cancel) ",
        InputMode::AddingTaskDescription => " Enter Task Description (Enter to save, Esc to skip) ",
        InputMode::EditingTask => " Edit Task Title (Enter to continue, Esc to cancel) ",
        InputMode::EditingTaskDescription => " Edit Task Description (Enter to save, Esc to cancel, empty to clear) ",
        InputMode::AddingProject => " Add New Project (Enter to save, Esc to cancel) ",
        InputMode::RenamingProject => " Rename Project (Enter to save, Esc to cancel) ",
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
            Span::raw("d"),
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
