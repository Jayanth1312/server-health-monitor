use crate::app::{App, InputMode, ViewMode};
use crate::task::Status;
use crossterm::event::{self, Event, KeyCode};
use std::io;
use std::time::Duration;

pub fn handle_events(app: &mut App) -> io::Result<bool> {
    if event::poll(Duration::from_millis(100))? {
        if let Event::Key(key) = event::read()? {
            // Ignore key release events to prevent double processing
            if key.kind == crossterm::event::KeyEventKind::Release {
                return Ok(false);
            }

            match app.input_mode {
                InputMode::Normal => match app.view_mode {
                    ViewMode::ProjectList => {
                        if handle_project_mode(app, key.code) {
                            return Ok(true);
                        }
                    }
                    ViewMode::TaskList => {
                        if handle_task_mode(app, key.code) {
                            return Ok(true);
                        }
                    }
                    ViewMode::ViewingTask => {
                        if handle_viewing_mode(app, key.code) {
                            return Ok(true);
                        }
                    }
                    ViewMode::Searching => {
                        if handle_search_mode(app, key.code) {
                            return Ok(true);
                        }
                    }
                    ViewMode::SettingDueDate => {
                        if handle_calendar_mode(app, key.code) {
                            return Ok(true);
                        }
                    }
                },
                InputMode::AddingTask
                | InputMode::AddingTaskDescription
                | InputMode::EditingTask
                | InputMode::EditingTaskDescription
                | InputMode::AddingProject
                | InputMode::RenamingProject => handle_input_mode(app, key.code),
                InputMode::SettingTime => handle_time_input_mode(app, key.code),
            }
        }
    }
    Ok(false)
}

fn handle_project_mode(app: &mut App, key_code: KeyCode) -> bool {
    match key_code {
        KeyCode::Char('q') | KeyCode::Esc => return true,
        KeyCode::Down | KeyCode::Char('j') => app.next_project(),
        KeyCode::Up | KeyCode::Char('k') => app.previous_project(),
        KeyCode::Enter => app.enter_project(),
        KeyCode::Char('n') => app.start_adding_project(),
        KeyCode::Char('r') => app.start_renaming_project(),
        KeyCode::Char('d') => app.delete_project(),
        KeyCode::Char('s') => app.enter_search_mode(),
        _ => {}
    }
    false
}

fn handle_task_mode(app: &mut App, key_code: KeyCode) -> bool {
    match key_code {
        KeyCode::Char('q') | KeyCode::Esc => return true,
        KeyCode::Backspace | KeyCode::Char('b') | KeyCode::Char('h') => app.exit_to_projects(),
        KeyCode::Down | KeyCode::Char('j') => app.next_task(),
        KeyCode::Up | KeyCode::Char('k') => app.previous_task(),
        KeyCode::Enter => app.enter_task_view(),
        KeyCode::Char(' ') | KeyCode::Char('c') => app.cycle_status(),
        KeyCode::Char('p') => app.cycle_priority(),
        KeyCode::Char('d') => app.delete_task(),
        KeyCode::Char('a') => app.start_adding_task(),
        KeyCode::Char('e') => app.start_editing_task(),
        KeyCode::Char('s') => app.enter_search_mode(),
        KeyCode::Char('t') => app.start_setting_due_date(),
        KeyCode::Char('x') => app.clear_due_date(),
        KeyCode::Char('1') => app.set_status(Status::Todo),
        KeyCode::Char('2') => app.set_status(Status::InProgress),
        KeyCode::Char('3') => app.set_status(Status::Done),
        _ => {}
    }
    false
}

fn handle_viewing_mode(app: &mut App, key_code: KeyCode) -> bool {
    match key_code {
        KeyCode::Char('q') | KeyCode::Esc => return true,
        KeyCode::Backspace | KeyCode::Char('h') | KeyCode::Enter => app.exit_task_view(),
        _ => {}
    }
    false
}

fn handle_search_mode(app: &mut App, key_code: KeyCode) -> bool {
    match key_code {
        KeyCode::Char('q') => {
            if !app.search_focus_on_input {
                // Only quit when navigating, not while typing
                return true;
            } else {
                // Add 'q' to search when typing
                app.search_input('q');
            }
        }
        KeyCode::Tab => {
            // Toggle focus between search input and results
            if !app.search_results.is_empty() {
                app.toggle_search_focus();
            }
        }
        KeyCode::Esc => {
            if app.search_focus_on_input {
                if app.search_query.is_empty() {
                    app.exit_search_mode();
                } else {
                    // Clear search query
                    app.search_query.clear();
                    app.search_results.clear();
                    app.selected_search_result = 0;
                }
            } else {
                // If on results, go back to input
                app.search_focus_on_input = true;
            }
        }
        KeyCode::Backspace => {
            if app.search_focus_on_input {
                app.search_backspace();
            }
        }
        // Navigation keys only work when focus is on results
        KeyCode::Down | KeyCode::Char('j') => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.next_search_result();
            } else if app.search_focus_on_input {
                app.search_input('j');
            }
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.previous_search_result();
            } else if app.search_focus_on_input {
                app.search_input('k');
            }
        }
        KeyCode::Enter => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.view_search_task_details();
            } else if app.search_focus_on_input && !app.search_results.is_empty() {
                // Pressing Enter while typing switches to results
                app.search_focus_on_input = false;
            }
        }
        // Action keys only work when focus is on results
        KeyCode::Char(' ') | KeyCode::Char('c') => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.cycle_search_task_status();
            } else if app.search_focus_on_input {
                app.search_input(' ');
            }
        }
        KeyCode::Char('p') => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.cycle_search_task_priority();
            } else if app.search_focus_on_input {
                app.search_input('p');
            }
        }
        KeyCode::Char('t') => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.start_setting_due_date();
            } else if app.search_focus_on_input {
                app.search_input('t');
            }
        }
        KeyCode::Char('d') => {
            if !app.search_focus_on_input && !app.search_results.is_empty() {
                app.delete_search_task();
            } else if app.search_focus_on_input {
                app.search_input('d');
            }
        }
        // All other characters go to search input when focused
        KeyCode::Char(c) => {
            if app.search_focus_on_input {
                app.search_input(c);
            }
        }
        _ => {}
    }
    false
}

fn handle_calendar_mode(app: &mut App, key_code: KeyCode) -> bool {
    match key_code {
        KeyCode::Char('q') | KeyCode::Esc => {
            app.cancel_due_date_setting();
        }
        KeyCode::Left | KeyCode::Char('h') => app.calendar.previous_day(),
        KeyCode::Right | KeyCode::Char('l') => app.calendar.next_day(),
        KeyCode::Up | KeyCode::Char('k') => app.calendar.previous_week(),
        KeyCode::Down | KeyCode::Char('j') => app.calendar.next_week(),
        KeyCode::Char('n') => app.calendar.next_month(),
        KeyCode::Char('p') => app.calendar.previous_month(),
        KeyCode::Enter => {
            app.input_mode = InputMode::SettingTime;
            app.time_input.clear();
        }
        _ => {}
    }
    false
}

fn handle_time_input_mode(app: &mut App, key_code: KeyCode) {
    match key_code {
        KeyCode::Enter => {
            app.confirm_due_date();
            app.input_mode = InputMode::Normal;
        }
        KeyCode::Esc => {
            app.cancel_due_date_setting();
            app.input_mode = InputMode::Normal;
        }
        KeyCode::Char(c) if c.is_ascii_digit() || c == ':' => {
            if app.time_input.len() < 5 {
                app.time_input.push(c);
            }
        }
        KeyCode::Backspace => {
            app.time_input.pop();
        }
        _ => {}
    }
}

fn handle_input_mode(app: &mut App, key_code: KeyCode) {
    match key_code {
        KeyCode::Enter => app.finish_input(),
        KeyCode::Esc => app.cancel_input(),
        KeyCode::Char(c) => app.input_buffer.push(c),
        KeyCode::Backspace => {
            app.input_buffer.pop();
        }
        _ => {}
    }
}
