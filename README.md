# Todo - Terminal-based Task Manager

A fast, lightweight, and intuitive terminal-based todo application built with Rust. Organize your tasks by projects and track their progress with a beautiful TUI interface.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Rust](https://img.shields.io/badge/rust-1.70%2B-orange.svg)

## Features

✨ **Project-based Organization**

- Create and manage multiple projects
- Each project contains its own task list
- Track completion progress per project

📋 **Task Management**

- Add, edit, and delete tasks
- Three status levels: Todo, In Progress, Completed
- Quick status cycling with keyboard shortcuts
- Color-coded task visualization

🎨 **Beautiful TUI Interface**

- Clean and intuitive terminal user interface
- Vim-style navigation (hjkl) supported
- Arrow key navigation also available
- Color-coded status indicators:
  - 🟡 **Yellow** - Todo tasks
  - 🔵 **Blue** - In Progress tasks
  - 🟢 **Green** - Completed tasks

💾 **Persistent Storage**

- Automatic saving of all projects and tasks
- Data stored in JSON format
- Cross-platform storage location:
  - Windows: `%APPDATA%\dev-todo\projects.json`
  - Linux/Mac: `~/.config/dev-todo/projects.json`

⚡ **Fast and Lightweight**

- Written in Rust for maximum performance
- Minimal resource usage
- Instant startup time

## Installation

### Prerequisites

- Rust 1.70 or higher
- Cargo (comes with Rust)

### Building from Source

1. Clone the repository:

```bash
git clone <repository-url>
cd rust
```

2. Build the release version:

```bash
cargo build --release
```

3. The executable will be located at:

```
target/release/todo.exe (Windows)
target/release/todo (Linux/Mac)
```

### Setting Up for Easy Access (Windows)

After building, you have several options to run the application:

#### Option 1: Run Directly

Navigate to the directory and run:

```cmd
cd target\release
todo.exe
```

#### Option 2: Add to PATH (Recommended)

This allows you to run `devtodo` from anywhere in your terminal.

1. **Copy the executable to a permanent location:**

   ```cmd
   mkdir C:\DevTools
   copy target\release\todo.exe C:\DevTools\
   ```

````

2. **Add to System PATH:**
   - Press `Win + X` and select "System"
   - Click "Advanced system settings"
   - Click "Environment Variables"
   - Under "User variables" (or "System variables" for all users), find "Path"
   - Click "Edit"
   - Click "New"
   - Add: `C:\DevTools`
   - Click "OK" on all windows

3. **Restart your terminal** (Command Prompt, PowerShell, or Windows Terminal)

4. **Run from anywhere:**
   ```cmd
   todo
````

#### Option 3: Create a Desktop Shortcut

1. Right-click on `todo.exe`
2. Select "Create shortcut"
3. Move the shortcut to your Desktop
4. Double-click the shortcut to launch

### Quick Build and Run

```bash
cargo run --release
```

## Usage

### Starting the Application

**From the build directory:**

```bash
./target/release/todo  # Linux/Mac
.\target\release\todo.exe  # Windows
```

**If added to PATH:**

```bash
todo
```

**On Windows (if not in PATH):**

- Navigate to the folder containing `todo.exe`
- Double-click `todo.exe`
- Or run from Command Prompt/PowerShell in that directory

### Project View

When you start the application, you'll see the project list.

**Keyboard Shortcuts:**

| Key            | Action                    |
| -------------- | ------------------------- |
| `↑/↓` or `j/k` | Navigate through projects |
| `Enter`        | Open selected project     |
| `n`            | Create new project        |
| `r`            | Rename selected project   |
| `d`            | Delete selected project   |
| `q` or `Esc`   | Quit application          |

### Task View

After opening a project, you'll see its task list.

**Keyboard Shortcuts:**

| Key                      | Action                                        |
| ------------------------ | --------------------------------------------- |
| `↑/↓` or `j/k`           | Navigate through tasks                        |
| `a`                      | Add new task                                  |
| `e`                      | Edit selected task                            |
| `d`                      | Delete selected task                          |
| `Space` or `c`           | Cycle task status (Todo → In Progress → Done) |
| `1`                      | Set task to Todo                              |
| `2`                      | Set task to In Progress                       |
| `3`                      | Set task to Done/Completed                    |
| `Backspace`, `b`, or `h` | Go back to project list                       |
| `q` or `Esc`             | Quit application                              |

### Input Mode

When adding or editing projects/tasks, you enter input mode.

**Keyboard Shortcuts:**

| Key           | Action                     |
| ------------- | -------------------------- |
| `Enter`       | Save and exit input mode   |
| `Esc`         | Cancel and exit input mode |
| `Backspace`   | Delete last character      |
| Any character | Type into input buffer     |

## Project Structure

```
rust/
├── src/
│   ├── main.rs       # Application entry point
│   ├── app.rs        # Core application state and logic
│   ├── event.rs      # Keyboard event handling
│   ├── ui.rs         # Terminal UI rendering
│   ├── task.rs       # Task and Project data structures
│   └── storage.rs    # JSON file persistence
├── target/
│   └── release/
│       └── todo.exe  # Built executable (Windows)
├── Cargo.toml        # Rust dependencies
├── Cargo.lock        # Dependency lock file
└── README.md         # This file
```

## Data Storage

All data is automatically saved to a JSON file:

- **Windows**: `%APPDATA%\dev-todo\projects.json`
- **Linux**: `~/.config/dev-todo/projects.json`
- **macOS**: `~/.config/dev-todo/projects.json`

The data is saved automatically whenever you make changes.

## Dependencies

- **ratatui** (0.27) - Terminal user interface framework
- **crossterm** (0.28) - Cross-platform terminal manipulation
- **serde** (1.0) - Serialization framework
- **serde_json** (1.0) - JSON serialization
- **dirs** (5.0) - System directory paths

## Customization

### Changing Colors

Edit `src/task.rs` to customize status colors:

```rust
pub fn display(&self) -> (String, Color) {
    let (status_symbol, color) = match self.status {
        Status::Todo => ("[ ]", Color::Yellow),        // Change Yellow to your color
        Status::InProgress => ("[>]", Color::Blue),    // Change Blue to your color
        Status::Done => ("[X]", Color::Green),         // Change Green to your color
    };
    // ...
}
```

### Changing Icons

Edit `src/ui.rs` to customize folder icons:

```rust
let display = format!("> {}  {}", p.name, task_count);
```

### Data Not Persisting

- Check that the application has write permissions to the config directory
- Manually create the directory if it doesn't exist:
  - Windows: `mkdir %APPDATA%\dev-todo`
  - Linux/Mac: `mkdir -p ~/.config/dev-todo`

### Application Crashes on Startup

- Try deleting the JSON file and restarting (you'll lose your data):
  - Windows: Delete `%APPDATA%\dev-todo\projects.json`
  - Linux/Mac: Delete `~/.config/dev-todo/projects.json`

## Contributing

Contributions are welcome! Feel free to:

- Report bugs
- Suggest new features
- Submit pull requests
- Improve documentation

## License

This project is licensed under the MIT License.

## Acknowledgments

- Built with [Ratatui](https://github.com/ratatui-org/ratatui) - Rust TUI library
- Inspired by modern terminal-based productivity tools

## Future Enhancements

- [ ] Task priorities
- [ ] Due dates and reminders
- [ ] Task filtering and search
- [ ] Multiple task lists per project
- [ ] Export to different formats (CSV, Markdown)
- [ ] Task notes/descriptions
- [ ] Keyboard shortcut customization
- [ ] Theme customization
- [ ] Task tags/categories

---

**Made with ❤️ and Rust**
