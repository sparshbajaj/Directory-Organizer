package cmd

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/sparshbajaj/directory-organizer/internal/config"
	"github.com/sparshbajaj/directory-organizer/internal/engine"
	"github.com/sparshbajaj/directory-organizer/internal/logger"
	"github.com/spf13/cobra"
)

var tuiCmd = &cobra.Command{
	Use:   "tui",
	Short: "Launch the interactive Terminal UI",
	RunE: func(cmd *cobra.Command, args []string) error {
		logger.DisableStdout() // Prevent logs from ruining the UI
		cfg, err := config.Load()
		if err != nil {
			return err
		}

		eng, err := engine.NewEngine(cfg)
		if err != nil {
			return err
		}
		defer eng.Close()

		m := initialModel(eng, cfg)
		p := tea.NewProgram(m, tea.WithAltScreen())
		if _, err := p.Run(); err != nil {
			return err
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(tuiCmd)
}

type sessionState int

const (
	stateMenu sessionState = iota
	stateInput
)

type model struct {
	eng      *engine.Engine
	cfg      *config.Settings
	state    sessionState
	cursor   int
	choices  []string
	input    textinput.Model
	scanning bool
	watching bool
	spinner  spinner.Model
	message  string
}

func initialModel(eng *engine.Engine, cfg *config.Settings) model {
	s := spinner.New()
	s.Spinner = spinner.Dot
	s.Style = lipgloss.NewStyle().Foreground(lipgloss.Color("205"))

	ti := textinput.New()
	ti.Placeholder = "Enter path to organize (e.g., D:\\Downloads)"
	ti.SetValue(cfg.WatchDir)
	ti.CharLimit = 256
	ti.Width = 50

	return model{
		eng:      eng,
		cfg:      cfg,
		state:    stateMenu,
		choices:  []string{"Organize Folder", "Change Target Folder", "Scan & Index", "Restart Watcher", "Quit"},
		spinner:  s,
		input:    ti,
		watching: true,
		message:  "Initializing background watcher...",
	}
}

func (m model) Init() tea.Cmd {
	return tea.Batch(
		textinput.Blink,
		m.spinner.Tick,
		func() tea.Msg {
			err := m.eng.RegisterWatcher()
			return actionMsg{action: "watch", err: err}
		},
	)
}

type actionMsg struct {
	action string
	err    error
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch m.state {
		case stateMenu:
			switch msg.String() {
			case "ctrl+c", "q":
				return m, tea.Quit
			case "up", "k":
				if m.cursor > 0 {
					m.cursor--
				}
			case "down", "j":
				if m.cursor < len(m.choices)-1 {
					m.cursor++
				}
			case "enter", " ":
				switch m.cursor {
				case 0: // Organize Folder
					m.message = "Queuing files for background organization..."
					return m, func() tea.Msg {
						err := m.eng.OrganizeDirectory()
						return actionMsg{action: "organize", err: err}
					}
				case 1: // Change Target Folder
					m.state = stateInput
					m.input.Focus()
					m.message = ""
					return m, textinput.Blink
				case 2: // Scan & Index
					if !m.scanning {
						m.scanning = true
						m.message = "Scanning directory to index into DB..."
						return m, tea.Batch(
							func() tea.Msg {
								err := m.eng.ScanDirectory()
								return actionMsg{action: "scan", err: err}
							},
							m.spinner.Tick,
						)
					}
				case 3: // Restart Watcher
					m.watching = true
					m.message = "Restarting watcher..."
					return m, func() tea.Msg {
						err := m.eng.RegisterWatcher()
						return actionMsg{action: "watch", err: err}
					}
				case 4: // Quit
					return m, tea.Quit
				}
			}
		case stateInput:
			switch msg.String() {
			case "enter":
				val := m.input.Value()
				if val != "" {
					m.cfg.WatchDir = val
					_ = config.Save(m.cfg)
					m.message = "Target folder updated. Starting organization and restarting watcher..."
					m.watching = true
					m.state = stateMenu
					m.input.Blur()
					return m, tea.Batch(
						func() tea.Msg {
							err := m.eng.RegisterWatcher()
							return actionMsg{action: "watch", err: err}
						},
						func() tea.Msg {
							err := m.eng.OrganizeDirectory()
							return actionMsg{action: "organize", err: err}
						},
					)
				}
				m.state = stateMenu
				m.input.Blur()
			case "esc":
				m.state = stateMenu
				m.input.Blur()
				m.input.SetValue(m.cfg.WatchDir) // revert
				m.message = "Folder change cancelled."
			}
		}

	case actionMsg:
		switch msg.action {
		case "scan":
			m.scanning = false
			if msg.err != nil {
				m.message = fmt.Sprintf("Scan failed: %v", msg.err)
			} else {
				m.message = "Scan completed successfully!"
			}
		case "watch":
			if msg.err != nil {
				m.watching = false
				m.message = fmt.Sprintf("Watcher failed: %v", msg.err)
			}
		case "organize":
			if msg.err != nil {
				m.message = fmt.Sprintf("Failed to organize: %v", msg.err)
			} else {
				m.message = "Files queued! Organization runs in the background. Check logs for details."
			}
		}

	case spinner.TickMsg:
		m.spinner, cmd = m.spinner.Update(msg)
		cmds = append(cmds, cmd)
	}

	if m.state == stateInput {
		m.input, cmd = m.input.Update(msg)
		cmds = append(cmds, cmd)
	}

	return m, tea.Batch(cmds...)
}

var (
	titleStyle   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#00FFFF")).MarginBottom(1)
	infoStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("#AAAAAA")).MarginBottom(1)
	successStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("#00FF00")).MarginTop(1)
	errorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF0000")).MarginTop(1)
	cursorStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("205"))
	inputStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("212"))
)

func (m model) View() string {
	s := titleStyle.Render("Directory Organizer TUI") + "\n"

	s += infoStyle.Render(fmt.Sprintf("Target Folder: %s\nDB Path: %s", m.cfg.WatchDir, m.cfg.DBPath)) + "\n"

	if m.state == stateMenu {
		for i, choice := range m.choices {
			cursor := " "
			if m.cursor == i {
				cursor = cursorStyle.Render(">")
				choice = cursorStyle.Render(choice)
			}
			s += fmt.Sprintf("%s %s\n", cursor, choice)
		}
	} else if m.state == stateInput {
		s += "\n" + inputStyle.Render("Enter new target directory path:") + "\n"
		s += m.input.View() + "\n\n(Press Enter to save, Esc to cancel)"
	}

	if m.scanning || m.watching {
		s += "\n" + m.spinner.View() + " " + m.message
	} else if m.message != "" {
		if strings.Contains(m.message, "failed") {
			s += errorStyle.Render(m.message)
		} else {
			s += successStyle.Render(m.message)
		}
	}

	if m.state == stateMenu {
		s += "\n\nPress q to quit.\n"
	}

	return lipgloss.NewStyle().Padding(1, 2).Render(s)
}