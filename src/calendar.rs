use chrono::{Datelike, Local, NaiveDate};
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub struct Calendar {
    pub selected_date: NaiveDate,
    pub current_month: NaiveDate,
}

impl Calendar {
    pub fn new() -> Self {
        let today = Local::now().date_naive();
        Calendar {
            selected_date: today,
            current_month: today,
        }
    }

    pub fn next_day(&mut self) {
        self.selected_date = self
            .selected_date
            .succ_opt()
            .unwrap_or(self.selected_date);
        self.update_current_month();
    }

    pub fn previous_day(&mut self) {
        self.selected_date = self
            .selected_date
            .pred_opt()
            .unwrap_or(self.selected_date);
        self.update_current_month();
    }

    pub fn next_week(&mut self) {
        self.selected_date = self
            .selected_date
            .checked_add_days(chrono::Days::new(7))
            .unwrap_or(self.selected_date);
        self.update_current_month();
    }

    pub fn previous_week(&mut self) {
        self.selected_date = self
            .selected_date
            .checked_sub_days(chrono::Days::new(7))
            .unwrap_or(self.selected_date);
        self.update_current_month();
    }

    pub fn next_month(&mut self) {
        let year = self.current_month.year();
        let month = self.current_month.month();

        if month == 12 {
            self.current_month = NaiveDate::from_ymd_opt(year + 1, 1, 1).unwrap();
        } else {
            self.current_month = NaiveDate::from_ymd_opt(year, month + 1, 1).unwrap();
        }

        // Try to keep the same day, or use last day of month
        let target_day = self.selected_date.day();
        self.selected_date = NaiveDate::from_ymd_opt(
            self.current_month.year(),
            self.current_month.month(),
            target_day
        ).unwrap_or_else(|| {
            // If day doesn't exist in new month, use last day
            let next_month = if self.current_month.month() == 12 {
                NaiveDate::from_ymd_opt(self.current_month.year() + 1, 1, 1).unwrap()
            } else {
                NaiveDate::from_ymd_opt(self.current_month.year(), self.current_month.month() + 1, 1).unwrap()
            };
            next_month.pred_opt().unwrap()
        });
    }

    pub fn previous_month(&mut self) {
        let year = self.current_month.year();
        let month = self.current_month.month();

        if month == 1 {
            self.current_month = NaiveDate::from_ymd_opt(year - 1, 12, 1).unwrap();
        } else {
            self.current_month = NaiveDate::from_ymd_opt(year, month - 1, 1).unwrap();
        }

        // Try to keep the same day, or use last day of month
        let target_day = self.selected_date.day();
        self.selected_date = NaiveDate::from_ymd_opt(
            self.current_month.year(),
            self.current_month.month(),
            target_day
        ).unwrap_or_else(|| {
            // If day doesn't exist in new month, use last day
            let next_month = if self.current_month.month() == 12 {
                NaiveDate::from_ymd_opt(self.current_month.year() + 1, 1, 1).unwrap()
            } else {
                NaiveDate::from_ymd_opt(self.current_month.year(), self.current_month.month() + 1, 1).unwrap()
            };
            next_month.pred_opt().unwrap()
        });
    }

    fn update_current_month(&mut self) {
        if self.selected_date.month() != self.current_month.month()
            || self.selected_date.year() != self.current_month.year()
        {
            self.current_month = NaiveDate::from_ymd_opt(
                self.selected_date.year(),
                self.selected_date.month(),
                1,
            )
            .unwrap();
        }
    }

    pub fn render(&self, f: &mut Frame, area: Rect) {
        let today = Local::now().date_naive();

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(3),  // Header
                Constraint::Length(9),  // Calendar grid
            ])
            .split(area);

        // Render header with month/year
        let header = Paragraph::new(Line::from(vec![
            Span::styled(
                self.current_month.format("%B %Y").to_string(),
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
        ]))
        .alignment(Alignment::Center)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan))
                .title(" Select Due Date "),
        );
        f.render_widget(header, chunks[0]);

        // Render calendar grid
        let first_day = NaiveDate::from_ymd_opt(
            self.current_month.year(),
            self.current_month.month(),
            1,
        )
        .unwrap();

        let first_weekday = first_day.weekday().num_days_from_sunday() as usize;

        // Get days in month
        let days_in_month = if self.current_month.month() == 12 {
            NaiveDate::from_ymd_opt(self.current_month.year() + 1, 1, 1)
                .unwrap()
                .pred_opt()
                .unwrap()
                .day()
        } else {
            NaiveDate::from_ymd_opt(
                self.current_month.year(),
                self.current_month.month() + 1,
                1,
            )
            .unwrap()
            .pred_opt()
            .unwrap()
            .day()
        };

        // Build calendar lines
        let mut lines = vec![
            Line::from(vec![
                Span::raw(" Su  Mo  Tu  We  Th  Fr  Sa")
            ]),
        ];

        let mut week_line = Vec::new();

        // Add empty spaces for days before month starts
        for _ in 0..first_weekday {
            week_line.push(Span::raw("    "));
        }

        // Add days
        for day in 1..=days_in_month {
            let date = NaiveDate::from_ymd_opt(
                self.current_month.year(),
                self.current_month.month(),
                day,
            )
            .unwrap();

            let day_str = format!("{:3}", day);

            let span = if date == self.selected_date {
                Span::styled(
                    day_str,
                    Style::default()
                        .bg(Color::Cyan)
                        .fg(Color::Black)
                        .add_modifier(Modifier::BOLD),
                )
            } else if date == today {
                Span::styled(
                    day_str,
                    Style::default()
                        .fg(Color::Yellow)
                        .add_modifier(Modifier::BOLD),
                )
            } else {
                Span::styled(day_str, Style::default().fg(Color::White))
            };

            week_line.push(span);
            week_line.push(Span::raw(" "));

            // Start new week on Sunday
            if (first_weekday + day as usize) % 7 == 0 {
                lines.push(Line::from(week_line.clone()));
                week_line.clear();
            }
        }

        // Add remaining days if any
        if !week_line.is_empty() {
            lines.push(Line::from(week_line));
        }

        let calendar_widget = Paragraph::new(lines)
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::White)),
            );

        f.render_widget(calendar_widget, chunks[1]);
    }
}
