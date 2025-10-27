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
                },
                InputMode::AddingTask
                | InputMode::EditingTask
                | InputMode::AddingProject
                | InputMode::RenamingProject => handle_input_mode(app, key.code),
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
        KeyCode::Char(' ') | KeyCode::Char('c') => app.cycle_status(),
        KeyCode::Char('d') => app.delete_task(),
        KeyCode::Char('a') => app.start_adding_task(),
        KeyCode::Char('e') => app.start_editing_task(),
        KeyCode::Char('1') => app.set_status(Status::Todo),
        KeyCode::Char('2') => app.set_status(Status::InProgress),
        KeyCode::Char('3') => app.set_status(Status::Done),
        _ => {}
    }
    false
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
