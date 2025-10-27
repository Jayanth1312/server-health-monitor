mod app;
mod calendar;
mod event;
mod storage;
mod task;
mod ui;

use crossterm::{
    event::{DisableMouseCapture, EnableMouseCapture},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io;

fn main() -> Result<(), io::Error> {
    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Create app state
    let mut app = app::App::new()?;

    // Run the app
    let result = run_app(&mut terminal, &mut app);

    // Restore terminal
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    // Handle any errors
    if let Err(err) = result {
        eprintln!("Error: {:?}", err);
    } else {
        println!("Tasks saved to: {}", app.get_storage_location());
    }

    Ok(())
}

fn run_app<B: ratatui::backend::Backend>(
    terminal: &mut Terminal<B>,
    app: &mut app::App,
) -> io::Result<()> {
    loop {
        terminal.draw(|f| ui::render(f, app))?;

        if event::handle_events(app)? {
            break;
        }
    }
    Ok(())
}
